// Motion Agent dashboard server.
// Run: npm start  (inside dashboard/)
import http from 'node:http';
import fs from 'node:fs';
import fsp from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import crypto from 'node:crypto';
import { execFile } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { query } from '@anthropic-ai/claude-agent-sdk';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = process.env.MA_ROOT || path.resolve(HERE, '..');
const PORT = Number(process.env.MA_PORT || 3333);
const RUNTIME = path.join(ROOT, '.runtime');
const HOME = path.join(RUNTIME, 'home');
const BIN = path.join(HOME, 'bin');
const CHATS = path.join(RUNTIME, 'chats');
const STATE_FILE = path.join(RUNTIME, 'state.json');
const PROJECTS = path.join(ROOT, 'projects');
const ENV_FILE = path.join(ROOT, '.env');

const MODELS = {
  sonnet: { label: 'Sonnet' },
  opus: { label: 'Opus' },
};
const DEFAULT_MODEL = 'sonnet';
const WRITE_TOOLS = new Set(['Write', 'Edit', 'MultiEdit', 'NotebookEdit']);
const MEDIA_DIRS = ['Final', 'Ref.Videos', 'Shots', 'Asset', 'Audio', 'Work'];
const VIDEO_RE = /\.(mp4|mov|m4v|webm)$/i;
const IMAGE_RE = /\.(png|jpe?g|webp|gif)$/i;
const AUDIO_RE = /\.(mp3|wav|m4a|aac|ogg)$/i;

const AGENT_RULES = `
# Rules for this setup (these win if the skills or CLAUDE.md say otherwise)
- All generation and analysis runs on fal.ai through the \`fal\` command: images, video, voice (TTS), transcription and video analysis. Read the fal skill before your first generation.
- Do not ask for approval. When you get an instruction, carry it out. State the model choice, the expected cost and the plan in a sentence or two, then continue. The user watches spend on their fal.ai dashboard.
- Use AskUserQuestion only when the instruction really points two different ways, once, with as few questions as possible.
- Reference and competitor videos the user uploads are in Ref.Videos/. When asked to "analyze", run \`fal analyze\` first.
- The deliverable goes in Final/. When you finish, give the file name in Final/, its duration and the total generation cost (\`fal cost\`).
- Your working folder is this job's folder. Do not write into other jobs' folders.
- Reply in the language the user writes in. Keep it short, clear and friendly.
`;

// ---------- helpers ----------
const idOf = (rel) => Buffer.from(rel).toString('base64url');
const relOf = (id) => Buffer.from(id, 'base64url').toString();
const inside = (base, p) => { const r = path.resolve(p); return r === base || r.startsWith(base + path.sep); };
const run = (cmd, args) => new Promise((ok) => execFile(cmd, args, { timeout: 60000 }, (err, stdout, stderr) => ok({ err, stdout, stderr })));

function readEnv() {
  const out = {};
  try {
    for (const line of fs.readFileSync(ENV_FILE, 'utf8').split('\n')) {
      const m = line.match(/^\s*([A-Z0-9_]+)\s*=\s*(.*)\s*$/);
      if (m) out[m[1]] = m[2].replace(/^['"]|['"]$/g, '');
    }
  } catch {}
  return out;
}
const envVal = (name) => (readEnv()[name] || process.env[name] || '').trim();
const KEY_NAMES = { fal: 'FAL_KEY', anthropic: 'ANTHROPIC_API_KEY' };
const getKey = (provider) => envVal(KEY_NAMES[provider]);
// A gateway token (ANTHROPIC_AUTH_TOKEN + ANTHROPIC_BASE_URL) also counts as Claude access.
const claudeReady = () => !!(getKey('anthropic') || envVal('ANTHROPIC_AUTH_TOKEN'));
function writeKey(provider, key) {
  const env = readEnv(); env[KEY_NAMES[provider]] = key;
  fs.writeFileSync(ENV_FILE, Object.entries(env).map(([k, v]) => `${k}=${v}`).join('\n') + '\n', { mode: 0o600 });
  fs.chmodSync(ENV_FILE, 0o600);
}
const THINKING_ON = () => /^(on|1|true|yes)$/i.test(envVal('MA_THINKING'));

let state = { jobs: {} };
try { state = JSON.parse(fs.readFileSync(STATE_FILE, 'utf8')); state.jobs ||= {}; } catch {}
let saveTimer;
const saveState = () => { clearTimeout(saveTimer); saveTimer = setTimeout(() => fs.writeFileSync(STATE_FILE, JSON.stringify(state, null, 2)), 200); };
const jstate = (id) => (state.jobs[id] ||= { sessionId: null, model: DEFAULT_MODEL });

// ---------- runtime ----------
async function copyInto(src, dst) {
  if (!fs.existsSync(src)) return;
  for (const name of await fsp.readdir(src)) {
    await fsp.rm(path.join(dst, name), { recursive: true, force: true });
    await fsp.cp(path.join(src, name), path.join(dst, name), { recursive: true });
  }
}
async function prepareRuntime() {
  for (const d of [RUNTIME, HOME, BIN, CHATS, PROJECTS]) await fsp.mkdir(d, { recursive: true });

  // Sandboxed home: ~/.claude = agent-home (CLAUDE.md, rules, skills), ~/Desktop/Projects = projects/
  const claudeDir = path.join(HOME, '.claude');
  await fsp.mkdir(path.join(claudeDir, 'skills'), { recursive: true });
  const agentHome = path.join(ROOT, 'agent-home');
  if (fs.existsSync(agentHome)) await copyInto(agentHome, claudeDir);
  else console.warn('WARNING: agent-home not found, the agent will run without its skills:', agentHome);

  const desk = path.join(HOME, 'Desktop');
  await fsp.mkdir(desk, { recursive: true });
  const link = path.join(desk, 'Projects');
  try { await fsp.rm(link, { force: true }); } catch {}
  try { await fsp.symlink(PROJECTS, link); } catch {}

  // the `fal` command
  const falPy = path.join(ROOT, 'tools', 'fal.py');
  const wrapper = path.join(BIN, 'fal');
  await fsp.writeFile(wrapper, `#!/bin/sh\nexec python3 "${falPy}" "$@"\n`, { mode: 0o755 });
  await fsp.chmod(wrapper, 0o755);
}

async function testKey(provider, key) {
  try {
    if (provider === 'fal') {
      const r = await fetch('https://api.fal.ai/v1/models/pricing?endpoint_id=fal-ai/nano-banana-pro', {
        headers: { Authorization: `Key ${key}` }, signal: AbortSignal.timeout(15000) });
      if (r.status === 200) return { ok: true };
      if (r.status === 401 || r.status === 403) return { ok: false, error: 'fal.ai did not accept this key. Copy it again from fal.ai/dashboard/keys.' };
      return { ok: false, error: `fal.ai returned ${r.status}.` };
    }
    const r = await fetch('https://api.anthropic.com/v1/models', {
      headers: { 'x-api-key': key, 'anthropic-version': '2023-06-01' }, signal: AbortSignal.timeout(15000) });
    if (r.status === 200) return { ok: true };
    if (r.status === 401 || r.status === 403) return { ok: false, error: 'Anthropic did not accept this key. Check it in the Claude Console.' };
    return { ok: false, error: `Anthropic returned ${r.status}.` };
  } catch (e) { return { ok: false, error: `Could not reach ${provider === 'fal' ? 'fal.ai' : 'Anthropic'}: ${e.message}` }; }
}

// ---------- event stream ----------
const clients = new Set();
function broadcast(ev) { const data = `data: ${JSON.stringify(ev)}\n\n`; for (const res of clients) res.write(data); }
function emit(id, ev, persist = true) {
  ev.job = id; ev.ts = Date.now();
  if (persist) fs.appendFileSync(path.join(CHATS, `${id}.jsonl`), JSON.stringify(ev) + '\n');
  broadcast(ev);
}

// ---------- jobs ----------
function jobCost(dir) {
  try {
    const lines = fs.readFileSync(path.join(dir, 'Logs', 'fal.csv'), 'utf8').trim().split('\n').slice(1);
    return lines.reduce((s, l) => s + (parseFloat(l.split(',')[2]) || 0), 0);
  } catch { return 0; }
}
async function listJobs() {
  const out = [];
  let apps = []; try { apps = await fsp.readdir(PROJECTS, { withFileTypes: true }); } catch {}
  for (const a of apps) {
    if (!a.isDirectory() || a.name.startsWith('.')) continue;
    for (const c of await fsp.readdir(path.join(PROJECTS, a.name), { withFileTypes: true })) {
      if (!c.isDirectory() || c.name.startsWith('.')) continue;
      const rel = `${a.name}/${c.name}`; const id = idOf(rel);
      let mtime = (await fsp.stat(path.join(PROJECTS, rel))).mtimeMs;
      try { mtime = Math.max(mtime, (await fsp.stat(path.join(CHATS, `${id}.jsonl`))).mtimeMs); } catch {}
      out.push({ id, app: a.name, name: c.name, busy: running.has(id), mtime,
        asking: [...pending.values()].some((p) => p.job === id) });
    }
  }
  return out.sort((x, y) => y.mtime - x.mtime);
}
const templateDir = () => { const t = path.join(ROOT, 'project-template'); return fs.existsSync(t) ? t : null; };
async function createJob(app, code) {
  app = (app || '').trim();
  code = (code || '').trim().toUpperCase().replace(/-AI$/, '');
  if (!/^[\p{L}\p{N} ._-]{1,60}$/u.test(app)) throw new Error('Type the app name, for example "MyApp".');
  if (!code) {
    const d = new Date(); const base = `V${String(d.getMonth() + 1).padStart(2, '0')}${String(d.getDate()).padStart(2, '0')}`;
    let n = 1; while (fs.existsSync(path.join(PROJECTS, app, `${base}${n}-AI`))) n++;
    code = `${base}${n}`;
  }
  if (!/^[A-Z0-9]{2,12}$/.test(code)) throw new Error('The creative code can only use letters and numbers, for example APP101.');
  const name = `${code}-AI`; const dest = path.join(PROJECTS, app, name);
  if (fs.existsSync(dest)) throw new Error(`${app} / ${name} already exists, pick it from the list.`);
  for (const d of ['Brief', 'Ref.Videos', 'Asset', 'Audio', 'Shots', 'Work', 'Final', 'Logs', 'src/compositions', 'src/components', 'public'])
    await fsp.mkdir(path.join(dest, d), { recursive: true });
  const t = templateDir();
  if (t) {
    for (const f of ['package.json', 'tsconfig.json', 'remotion.config.ts', '.gitignore'])
      if (fs.existsSync(path.join(t, f))) await fsp.copyFile(path.join(t, f), path.join(dest, f));
    if (fs.existsSync(path.join(t, 'src'))) await fsp.cp(path.join(t, 'src'), path.join(dest, 'src'), { recursive: true });
    const pj = path.join(dest, 'package.json');
    if (fs.existsSync(pj)) { const j = JSON.parse(await fsp.readFile(pj, 'utf8')); j.name = `${app}-${code}`.toLowerCase().replace(/[^a-z0-9]+/g, '-'); await fsp.writeFile(pj, JSON.stringify(j, null, 2) + '\n'); }
  }
  await fsp.writeFile(path.join(dest, 'Brief', 'README.md'), `# ${app} ${code}\n\n## Product\n\n## Goal\n\n## Format\n\n## Hook\n\n## CTA\n`);
  return idOf(`${app}/${name}`);
}
const jobDir = (id) => {
  const dir = path.resolve(PROJECTS, relOf(id));
  if (!inside(PROJECTS, dir) || !fs.existsSync(dir)) throw new Error('Job not found.');
  return dir;
};
async function listMedia(dir) {
  const items = [];
  const walk = async (rel, depth) => {
    let ents = []; try { ents = await fsp.readdir(path.join(dir, rel), { withFileTypes: true }); } catch { return; }
    for (const e of ents) {
      if (e.name.startsWith('.')) continue;
      const r = rel ? `${rel}/${e.name}` : e.name;
      if (e.isDirectory()) { if (depth < 2) await walk(r, depth + 1); continue; }
      const kind = VIDEO_RE.test(e.name) ? 'video' : IMAGE_RE.test(e.name) ? 'image' : AUDIO_RE.test(e.name) ? 'audio' : null;
      if (!kind) continue;
      const st = await fsp.stat(path.join(dir, r)).catch(() => null); if (!st) continue;
      items.push({ path: r, group: r.split('/')[0], kind, size: st.size, mtime: st.mtimeMs });
    }
  };
  for (const d of MEDIA_DIRS) await walk(d, 1);
  return items.sort((a, b) => b.mtime - a.mtime).slice(0, 300);
}

// ---------- agent ----------
const running = new Map();   // id -> { q, startedAt, ac }
const pending = new Map();   // reqId -> { job, resolve }
let reqSeq = 0;

function summarize(name, input) {
  if (name === 'Bash') return input.command;
  if (input.file_path) return input.file_path;
  if (input.pattern) return input.pattern + (input.path ? `  ${input.path}` : '');
  if (input.url) return input.url;
  if (input.description) return input.description;
  if (input.skill) return input.skill;
  return '';
}

// Large images are shrunk before the agent reads them, to save tokens.
async function shrinkImage(fp) {
  try {
    if (!IMAGE_RE.test(fp) || !fs.existsSync(fp)) return null;
    const st = fs.statSync(fp);
    let big = st.size > 700 * 1024;
    if (!big && /\.png$/i.test(fp)) {
      const fd = fs.openSync(fp, 'r'); const b = Buffer.alloc(24); fs.readSync(fd, b, 0, 24, 0); fs.closeSync(fd);
      if (b.readUInt32BE(16) > 1568 || b.readUInt32BE(20) > 1568) big = true;
    }
    if (!big) return null;
    const outDir = path.join(os.tmpdir(), 'ma-img'); fs.mkdirSync(outDir, { recursive: true });
    const out = path.join(outDir, crypto.createHash('md5').update(fp + st.mtimeMs).digest('hex').slice(0, 12) + '.jpg');
    if (!fs.existsSync(out)) {
      const r = await run('ffmpeg', ['-v', 'error', '-y', '-i', fp, '-vf', "scale='min(1568,iw)':'min(1568,ih)':force_original_aspect_ratio=decrease", '-q:v', '3', out]);
      if (r.err || !fs.existsSync(out)) return null;
    }
    return out;
  } catch { return null; }
}

function makeCanUseTool(id, dir) {
  const allowedRoots = [dir, os.tmpdir(), '/tmp', '/private/tmp'].map((p) => path.resolve(p));
  return async (toolName, input, { signal }) => {
    if (toolName === 'AskUserQuestion') {
      const reqId = `q${++reqSeq}`;
      emit(id, { t: 'question', reqId, questions: input.questions || [] });
      const answers = await new Promise((resolve) => {
        pending.set(reqId, { job: id, resolve });
        signal?.addEventListener('abort', () => resolve(null));
      });
      pending.delete(reqId);
      emit(id, { t: 'question_done', reqId, answers });
      if (!answers) return { behavior: 'deny', message: 'The user skipped the questions. Continue with a sensible assumption and say what you assumed.' };
      return { behavior: 'allow', updatedInput: { ...input, answers } };
    }
    if (WRITE_TOOLS.has(toolName)) {
      const fp = input.file_path || input.notebook_path;
      if (fp && !allowedRoots.some((r) => inside(r, path.resolve(dir, fp))))
        return { behavior: 'deny', message: `You can only write inside this job's folder (${dir}) and the temp folder.` };
    }
    return { behavior: 'allow', updatedInput: input };
  };
}

function toolResultText(content) {
  if (typeof content === 'string') return content;
  if (Array.isArray(content)) return content.map((c) => (c.type === 'text' ? c.text : `[${c.type}]`)).join('\n');
  return JSON.stringify(content);
}

async function runTurn(id, text, attachments, model) {
  const dir = jobDir(id);
  const js = jstate(id);
  if (model && MODELS[model]) js.model = model;
  if (!MODELS[js.model]) js.model = DEFAULT_MODEL;
  saveState();
  const ac = new AbortController();
  const entry = { q: null, startedAt: Date.now(), ac };
  running.set(id, entry);
  emit(id, { t: 'user', text, attachments });
  emit(id, { t: 'busy', busy: true, startedAt: entry.startedAt }, false);

  let prompt = text;
  if (attachments?.length) prompt += `\n\nFiles I uploaded (in this job's folder): ${attachments.join(', ')}`;

  const fileEnv = readEnv();
  const env = {
    ...process.env,
    HOME,
    PATH: `${BIN}:${process.env.PATH || ''}:/opt/homebrew/bin:/usr/local/bin`,
    FAL_KEY: getKey('fal'),
    MA_JOB_DIR: dir,
    BASH_DEFAULT_TIMEOUT_MS: '600000',
    BASH_MAX_TIMEOUT_MS: '1200000',
    CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC: '1',
    DISABLE_AUTOUPDATER: '1',
    CLAUDE_AGENT_SDK_CLIENT_APP: 'claude-motion-agent/1.0',
  };
  for (const k of ['ANTHROPIC_API_KEY', 'ANTHROPIC_AUTH_TOKEN', 'ANTHROPIC_BASE_URL', 'MA_LANGUAGE', 'MA_ANALYSIS_MODEL'])
    if (fileEnv[k] || process.env[k]) env[k] = fileEnv[k] || process.env[k];

  try {
    const q = query({
      prompt,
      options: {
        cwd: dir, env, model: js.model,
        resume: js.sessionId || undefined,
        permissionMode: 'default',
        canUseTool: makeCanUseTool(id, dir),
        settingSources: ['user', 'project'],
        skills: 'all',
        systemPrompt: { type: 'preset', preset: 'claude_code', append: AGENT_RULES },
        includePartialMessages: true,
        ...(THINKING_ON() ? {} : { thinking: { type: 'disabled' } }),
        hooks: {
          PreToolUse: [{
            matcher: 'Read',
            hooks: [async (input) => {
              const ti = input.tool_input || {};
              const small = ti.file_path ? await shrinkImage(path.resolve(dir, ti.file_path)) : null;
              if (!small) return {};
              return { hookSpecificOutput: { hookEventName: 'PreToolUse', permissionDecision: 'allow', updatedInput: { ...ti, file_path: small } } };
            }],
          }],
        },
        abortController: ac,
        stderr: (d) => fs.appendFileSync(path.join(RUNTIME, 'agent-stderr.log'), d),
      },
    });
    entry.q = q;
    for await (const m of q) {
      if (m.session_id && js.sessionId !== m.session_id) { js.sessionId = m.session_id; saveState(); }
      const sub = !!m.parent_tool_use_id;
      if (m.type === 'stream_event' && !sub) {
        const e = m.event;
        if (e.type === 'content_block_delta' && e.delta?.type === 'text_delta') emit(id, { t: 'delta', text: e.delta.text }, false);
      } else if (m.type === 'assistant') {
        for (const b of m.message.content || []) {
          if (b.type === 'text' && b.text.trim()) emit(id, { t: 'text', text: b.text, sub });
          else if (b.type === 'tool_use') emit(id, { t: 'tool', toolId: b.id, name: b.name, summary: summarize(b.name, b.input || {}), input: b.input, sub });
        }
      } else if (m.type === 'user' && Array.isArray(m.message?.content)) {
        for (const b of m.message.content) {
          if (b.type !== 'tool_result') continue;
          let txt = toolResultText(b.content);
          if (txt.length > 6000) txt = txt.slice(0, 6000) + `\n... (${txt.length - 6000} characters cut)`;
          emit(id, { t: 'tool_result', toolId: b.tool_use_id, text: txt, isError: !!b.is_error, sub });
        }
      } else if (m.type === 'result') {
        emit(id, { t: 'result', isError: m.is_error, turns: m.num_turns, ms: m.duration_ms, cost: jobCost(dir),
          error: m.is_error ? String(m.result || m.subtype || '') : '' });
      }
    }
  } catch (e) {
    const msg = ac.signal.aborted ? 'Stopped.' : `Agent error: ${e.message}`;
    emit(id, { t: 'error', text: msg });
    if (/no conversation found|session.*not found/i.test(e.message)) { js.sessionId = null; saveState(); }
  } finally {
    for (const [rid, p] of pending) if (p.job === id) { p.resolve(null); pending.delete(rid); }
    running.delete(id);
    emit(id, { t: 'busy', busy: false, cost: jobCost(dir) }, false);
  }
}

// ---------- HTTP ----------
const MIME = { '.html': 'text/html; charset=utf-8', '.json': 'application/json', '.mp4': 'video/mp4', '.mov': 'video/quicktime',
  '.m4v': 'video/mp4', '.webm': 'video/webm', '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.gif': 'image/gif',
  '.webp': 'image/webp', '.wav': 'audio/wav', '.mp3': 'audio/mpeg', '.m4a': 'audio/mp4', '.aac': 'audio/aac', '.ogg': 'audio/ogg',
  '.md': 'text/plain; charset=utf-8', '.txt': 'text/plain; charset=utf-8', '.csv': 'text/plain; charset=utf-8' };
const json = (res, code, obj) => { res.writeHead(code, { 'Content-Type': 'application/json' }); res.end(JSON.stringify(obj)); };
async function body(req) { const chunks = []; for await (const c of req) chunks.push(c); const s = Buffer.concat(chunks).toString(); return s ? JSON.parse(s) : {}; }
function sendFile(req, res, fp) {
  if (!fs.existsSync(fp) || !fs.statSync(fp).isFile()) return json(res, 404, { error: 'File not found.' });
  const stat = fs.statSync(fp);
  const type = MIME[path.extname(fp).toLowerCase()] || 'application/octet-stream';
  const range = req.headers.range;
  if (range) {
    const [s, e] = range.replace('bytes=', '').split('-');
    const start = Number(s) || 0; const end = e ? Math.min(Number(e), stat.size - 1) : stat.size - 1;
    res.writeHead(206, { 'Content-Type': type, 'Content-Range': `bytes ${start}-${end}/${stat.size}`, 'Accept-Ranges': 'bytes', 'Content-Length': end - start + 1 });
    fs.createReadStream(fp, { start, end }).pipe(res);
  } else {
    res.writeHead(200, { 'Content-Type': type, 'Content-Length': stat.size, 'Accept-Ranges': 'bytes' });
    fs.createReadStream(fp).pipe(res);
  }
}
const keyInfo = (k) => (k ? { set: true, len: k.length, head: k.slice(0, 4), tail: k.slice(-4) } : { set: false });

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, `http://${req.headers.host}`);
  const p = url.pathname;
  try {
    if (p === '/' || p === '/index.html') return sendFile(req, res, path.join(HERE, 'public', 'index.html'));
    if (p === '/api/events') {
      res.writeHead(200, { 'Content-Type': 'text/event-stream', 'Cache-Control': 'no-cache', Connection: 'keep-alive' });
      res.write('retry: 2000\n\n'); clients.add(res);
      const hb = setInterval(() => res.write(': hb\n\n'), 20000);
      req.on('close', () => { clearInterval(hb); clients.delete(res); });
      return;
    }
    if (p === '/api/status') {
      return json(res, 200, {
        keys: {
          fal: keyInfo(getKey('fal')),
          anthropic: getKey('anthropic') ? keyInfo(getKey('anthropic')) : { set: claudeReady(), gateway: claudeReady() },
        },
        ready: !!getKey('fal') && claudeReady(),
        models: Object.entries(MODELS).map(([id, m]) => ({ id, label: m.label })),
        agentHome: fs.existsSync(path.join(ROOT, 'agent-home')),
      });
    }
    if (p === '/api/key' && req.method === 'POST') {
      const { provider, key } = await body(req);
      if (!KEY_NAMES[provider]) return json(res, 400, { error: 'Unknown provider.' });
      const k = String(key || '').trim().replace(/\s+/g, '');
      if (k.length < 20) return json(res, 400, { error: 'That key looks too short.' });
      const t = await testKey(provider, k);
      if (!t.ok) return json(res, 400, { error: t.error });
      writeKey(provider, k);
      broadcast({ t: 'status' });
      return json(res, 200, { ok: true, len: k.length });
    }
    if (p === '/api/jobs' && req.method === 'GET') return json(res, 200, await listJobs());
    if (p === '/api/jobs' && req.method === 'POST') { const { app, code } = await body(req); return json(res, 200, { id: await createJob(app, code) }); }
    if (p === '/api/answer' && req.method === 'POST') {
      const { reqId, answers } = await body(req);
      const pr = pending.get(reqId);
      if (!pr) return json(res, 404, { error: 'This question is no longer open.' });
      const clean = {};
      for (const [k, v] of Object.entries(answers || {})) if (String(v).trim()) clean[String(k)] = String(v).trim();
      pr.resolve(Object.keys(clean).length ? clean : null);
      return json(res, 200, { ok: true });
    }

    const m = p.match(/^\/api\/jobs\/([\w-]+)\/(chat|message|stop|reset|settings|media|file|upload|reveal)$/);
    if (m) {
      const [, id, action] = m; const dir = jobDir(id);
      if (action === 'chat') {
        let lines = []; try { lines = fs.readFileSync(path.join(CHATS, `${id}.jsonl`), 'utf8').trim().split('\n').filter(Boolean); } catch {}
        const events = []; for (const l of lines) { try { events.push(JSON.parse(l)); } catch {} }
        return json(res, 200, { events, busy: running.has(id), startedAt: running.get(id)?.startedAt,
          pending: [...pending.entries()].filter(([, v]) => v.job === id).map(([k]) => k), model: jstate(id).model, cost: jobCost(dir) });
      }
      if (action === 'message' && req.method === 'POST') {
        const { text, attachments, model } = await body(req);
        if (!text?.trim()) return json(res, 400, { error: 'The message is empty.' });
        if (!getKey('fal')) return json(res, 409, { error: 'Add your fal.ai key first (top right).' });
        if (!claudeReady()) return json(res, 409, { error: 'Add your Anthropic API key first (top right).' });
        if (running.has(id)) return json(res, 409, { error: 'The agent is still working. Wait for it or stop it.' });
        const att = (Array.isArray(attachments) ? attachments : []).filter((a) => typeof a === 'string' && inside(dir, path.resolve(dir, a)));
        runTurn(id, text.trim(), att, model);
        return json(res, 200, { ok: true });
      }
      if (action === 'stop' && req.method === 'POST') {
        const r = running.get(id);
        if (r) { try { await r.q?.interrupt(); } catch {} setTimeout(() => r.ac.abort(), 3000); }
        return json(res, 200, { ok: true });
      }
      if (action === 'reset' && req.method === 'POST') {
        if (running.has(id)) return json(res, 409, { error: 'Stop the agent first.' });
        jstate(id).sessionId = null; saveState();
        emit(id, { t: 'note', text: 'Conversation reset. The agent will not remember earlier messages; the files stay where they are.' });
        return json(res, 200, { ok: true });
      }
      if (action === 'settings' && req.method === 'POST') {
        const b = await body(req); const js = jstate(id);
        if (b.model && MODELS[b.model]) js.model = b.model;
        saveState(); return json(res, 200, js);
      }
      if (action === 'media') return json(res, 200, { items: await listMedia(dir), cost: jobCost(dir) });
      const rel = url.searchParams.get('path') || '';
      const target = path.resolve(dir, rel);
      if (!inside(dir, target)) return json(res, 403, { error: 'Outside the job folder.' });
      if (action === 'file') return sendFile(req, res, target);
      if (action === 'reveal' && req.method === 'POST') { if (process.platform === 'darwin') execFile('open', ['-R', target]); return json(res, 200, { ok: true }); }
      if (action === 'upload' && req.method === 'POST') {
        const name = path.basename(decodeURIComponent(url.searchParams.get('name') || '')).replace(/[^\p{L}\p{N}._ -]+/gu, '_');
        if (!name) return json(res, 400, { error: 'Missing file name.' });
        const folder = path.resolve(dir, rel || 'Ref.Videos');
        if (!inside(dir, folder)) return json(res, 403, { error: 'Outside the job folder.' });
        await fsp.mkdir(folder, { recursive: true });
        let out = path.join(folder, name); let i = 2;
        while (fs.existsSync(out)) { const e = path.extname(name); out = path.join(folder, `${path.basename(name, e)}-${i++}${e}`); }
        await new Promise((ok, bad) => { const w = fs.createWriteStream(out); req.pipe(w); w.on('finish', ok); w.on('error', bad); });
        return json(res, 200, { ok: true, path: path.relative(dir, out) });
      }
    }
    json(res, 404, { error: 'Not found.' });
  } catch (e) {
    if (!res.headersSent) json(res, 500, { error: e.message });
  }
});

await prepareRuntime();
server.listen(PORT, '127.0.0.1', () => {
  const u = `http://localhost:${PORT}`;
  console.log(`\nMotion Agent is ready: ${u}\nFolder: ${ROOT}\nPress Ctrl+C to stop.\n`);
  if (process.platform === 'darwin' && !process.env.MA_NO_OPEN) execFile('open', [u]);
});
const shutdown = () => { for (const r of running.values()) r.ac.abort(); process.exit(0); };
process.on('SIGINT', shutdown); process.on('SIGTERM', shutdown);
