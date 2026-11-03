#!/usr/bin/env python3
"""fal: image, video, voice and analysis tool for the motion agent, built on fal.ai.

Commands:
  fal models <search> [--category text-to-video]   find endpoint ids (fal models seedance)
  fal schema <endpoint_id>                         input fields, required fields, options, price
  fal run <endpoint_id> key=value ...              submit, wait, download outputs
        --out DIR  --name NAME  --no-wait  --timeout SEC  --json '{"k":"v"}'
  fal wait <request_id> [--out DIR] [--name NAME]  wait for a request sent with --no-wait
  fal upload <file>                                upload a local file to the fal CDN, print the URL
  fal analyze <video> [--prompt "..."]             break down a reference ad -> Brief/reference-analysis.md
        --model google/gemini-2.5-flash  --out FILE
  fal ask "<question>" [--image FILE ...]          quick question to a vision LLM
  fal cost                                         estimated spend for this job (Logs/fal.csv)

File fields (*_url, *_urls): pass a local path and it is uploaded to the fal CDN first.
Files produced by `fal` reuse their existing URL, so chains like image -> video cost no upload.
Needs FAL_KEY in the environment. Python 3.9+, standard library only.
"""
import base64, csv, datetime, json, mimetypes, os, re, shutil, subprocess, sys, tempfile, time
import urllib.error, urllib.parse, urllib.request

QUEUE = os.environ.get("FAL_QUEUE_URL", "https://queue.fal.run")
PLATFORM = os.environ.get("FAL_PLATFORM_URL", "https://api.fal.ai/v1")
REST = os.environ.get("FAL_REST_URL", "https://rest.fal.ai")
CDN = os.environ.get("FAL_CDN_URL", "https://v3.fal.media")
KEY = (os.environ.get("FAL_KEY") or "").strip()
JOB = os.environ.get("MA_JOB_DIR") or os.getcwd()
UA = {"User-Agent": "claude-motion-agent/1.0"}
DEFAULT_LLM = os.environ.get("MA_ANALYSIS_MODEL", "google/gemini-2.5-flash")


def die(msg, code=1):
    print("ERROR: " + msg, file=sys.stderr)
    sys.exit(code)


def need_key():
    if not KEY:
        die("FAL_KEY is not set. Add it in the dashboard or export FAL_KEY=... (https://fal.ai/dashboard/keys).")


def http(method, url, body=None, auth=True, timeout=120, raw=None, headers=None):
    h = dict(UA)
    if auth:
        need_key()
        h["Authorization"] = "Key " + KEY
    if headers:
        h.update(headers)
    data = raw
    if body is not None:
        data = json.dumps(body).encode()
        h["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            payload = r.read()
            try:
                return r.status, (json.loads(payload) if payload else {})
            except ValueError:
                return r.status, {"text": payload.decode(errors="replace")[:800]}
    except urllib.error.HTTPError as e:
        payload = e.read().decode(errors="replace")
        try:
            return e.code, json.loads(payload)
        except ValueError:
            return e.code, {"error": payload[:800]}
    except urllib.error.URLError as e:
        die("could not reach fal.ai: %s" % e.reason)


# ---------- local records (per job, in Logs/) ----------
def logs_dir():
    d = os.path.join(JOB, "Logs")
    return d if os.path.isdir(d) else tempfile.gettempdir()


def _load(name):
    try:
        with open(os.path.join(logs_dir(), name)) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _save(name, data):
    with open(os.path.join(logs_dir(), name), "w") as f:
        json.dump(data, f, indent=1)


def remember_urls(pairs):
    m = _load("fal-urls.json")
    for path, url in pairs:
        m[os.path.realpath(path)] = url
    _save("fal-urls.json", m)


def remember_request(rid, info):
    m = _load("fal-requests.json")
    m[rid] = info
    _save("fal-requests.json", m)


def log_cost(endpoint, rid, cost, outputs, note=""):
    d = os.path.join(JOB, "Logs")
    if not os.path.isdir(d):
        return
    p = os.path.join(d, "fal.csv")
    new = not os.path.exists(p)
    with open(p, "a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["time", "endpoint", "cost_usd", "request_id", "outputs", "note"])
        w.writerow([datetime.datetime.now().isoformat(timespec="seconds"), endpoint,
                    "" if cost is None else round(cost, 4), rid, " ".join(outputs), note])


# ---------- catalog and schema ----------
def fetch_models(params):
    url = PLATFORM + "/models?" + urllib.parse.urlencode(params, doseq=True)
    s, r = http("GET", url, auth=bool(KEY))
    if s == 404:
        return []
    if s != 200:
        die("model lookup failed (%s): %s" % (s, json.dumps(r)[:300]))
    return r.get("models") or []


def cmd_models(args):
    opts, rest = parse_opts(args, ("--category", "--limit"))
    params = {"q": " ".join(rest), "status": "active", "limit": opts.get("--limit", "30")}
    if opts.get("--category"):
        params["category"] = opts["--category"]
    found = fetch_models(params)
    if not found:
        print("No results. Try a shorter word: seedance, kling, veo, nano banana, minimax speech, wizper.")
    for m in found:
        md = m.get("metadata") or {}
        print("%-52s %-16s %s" % (m["endpoint_id"], md.get("category", ""), md.get("display_name", "")))


_schema_cache = {}


def input_schema(endpoint):
    if endpoint in _schema_cache:
        return _schema_cache[endpoint]
    found = fetch_models({"endpoint_id": endpoint, "expand": "openapi-3.0"})
    if not found or not found[0].get("openapi"):
        near = fetch_models({"q": endpoint.split("/")[-2] if "/" in endpoint else endpoint, "limit": 8, "status": "active"})
        die("unknown endpoint: %s. Close matches: %s" % (endpoint, ", ".join(m["endpoint_id"] for m in near) or "none, try `fal models <word>`"))
    oa = found[0]["openapi"]
    comps = (oa.get("components") or {}).get("schemas") or {}
    sch = {}
    for p, ops in (oa.get("paths") or {}).items():
        post = ops.get("post") if isinstance(ops, dict) else None
        if not post or "/requests/" in p:
            continue
        ref = ((((post.get("requestBody") or {}).get("content") or {}).get("application/json") or {}).get("schema") or {}).get("$ref")
        if ref:
            sch = comps.get(ref.split("/")[-1], {})
            break
    sch = {"properties": sch.get("properties") or {}, "required": sch.get("required") or [],
           "category": (found[0].get("metadata") or {}).get("category", "")}
    _schema_cache[endpoint] = sch
    return sch


def price_of(endpoint):
    if not KEY:
        return None
    s, r = http("GET", PLATFORM + "/models/pricing?endpoint_id=" + urllib.parse.quote(endpoint))
    if s == 200 and r.get("prices"):
        return r["prices"][0]
    return None


def types_of(spec):
    if "anyOf" in spec:
        out = []
        for alt in spec["anyOf"]:
            out += types_of(alt)
        return [t for t in out if t != "null"] or ["string"]
    t = spec.get("type", "object" if "$ref" in spec or "allOf" in spec else "string")
    return t if isinstance(t, list) else [t]


def enum_of(spec):
    if spec.get("enum"):
        return spec["enum"]
    for alt in spec.get("anyOf", []):
        if alt.get("enum"):
            return alt["enum"]
    return None


def cmd_schema(args):
    if not args:
        die("usage: fal schema <endpoint_id>")
    ep = args[0]
    sch = input_schema(ep)
    print("%s  (%s)" % (ep, sch["category"]))
    pr = price_of(ep)
    if pr:
        print("price: %s %s per %s" % (pr.get("unit_price"), pr.get("currency", "USD"), pr.get("unit")))
    req = set(sch["required"])
    for k, v in sch["properties"].items():
        if k in ("end_user_id", "sync_mode"):
            continue
        line = "  %s%s [%s]" % (k, " (required)" if k in req else "", "/".join(str(t) for t in types_of(v)))
        en = enum_of(v)
        if en:
            line += " options=" + ",".join(str(e) for e in en if e is not None)
        if "default" in v:
            line += " default=" + json.dumps(v["default"], ensure_ascii=False)
        print(line)
        desc = (v.get("description") or "").strip().replace("\n", " ")
        if desc:
            print("      " + desc[:180])


# ---------- inputs ----------
def is_file_field(key):
    return key.endswith("_url") or key.endswith("_urls") or key in ("image", "video", "audio")


def upload_file(path):
    """Upload to the fal CDN. Returns a public https URL."""
    need_key()
    size = os.path.getsize(path)
    if size > 100 * 1024 * 1024:
        die("%s is %.0f MB; trim or compress it below 100 MB first." % (path, size / 1e6))
    mt = mimetypes.guess_type(path)[0] or "application/octet-stream"
    with open(path, "rb") as f:
        data = f.read()
    name = os.path.basename(path)
    s, tok = http("POST", REST + "/storage/auth/token?storage_type=fal-cdn-v3", body={})
    if s == 200 and tok.get("token"):
        base = tok.get("base_url") or CDN
        s2, r2 = http("POST", base + "/files/upload", auth=False, raw=data, timeout=600,
                      headers={"Authorization": "%s %s" % (tok.get("token_type", "Bearer"), tok["token"]),
                               "Content-Type": mt, "X-Fal-File-Name": name})
        if s2 in (200, 201) and r2.get("access_url"):
            return r2["access_url"]
    s, init = http("POST", REST + "/storage/upload/initiate?storage_type=gcs",
                   body={"file_name": name, "content_type": mt})
    if s != 200 or not init.get("upload_url"):
        die("upload failed (%s): %s" % (s, json.dumps(init)[:300]))
    s3, _ = http("PUT", init["upload_url"], auth=False, raw=data, timeout=600, headers={"Content-Type": mt})
    if s3 not in (200, 201):
        die("upload failed while sending the file (%s)" % s3)
    return init["file_url"]


def to_url(value):
    if not isinstance(value, str):
        return value
    v = value[1:] if value.startswith("@") else value
    if v.startswith(("http://", "https://", "data:")):
        return v
    path = os.path.expanduser(v if os.path.isabs(v) else os.path.join(JOB, v) if not os.path.exists(v) else v)
    if not os.path.isfile(path):
        if value.startswith("@"):
            die("file not found: %s" % path)
        return value
    known = _load("fal-urls.json").get(os.path.realpath(path))
    if known:
        print("  %s -> reusing its fal URL" % os.path.basename(path), file=sys.stderr)
        return known
    print("  %s -> uploading (%.1f MB)" % (os.path.basename(path), os.path.getsize(path) / 1e6), file=sys.stderr)
    url = upload_file(path)
    remember_urls([(path, url)])
    return url


def coerce(key, raw, spec):
    ts = types_of(spec) if spec else []
    val = raw
    if isinstance(raw, str):
        try:
            val = json.loads(raw)
        except ValueError:
            val = raw
    if spec:
        if "array" in ts and not isinstance(val, list):
            val = [x.strip() for x in str(raw).split(",") if x.strip()] if isinstance(val, str) else [val]
        elif ts and ts[0] == "string" and not isinstance(val, str) and val is not None and not isinstance(val, (list, dict)):
            val = str(raw)
        elif ("integer" in ts or "number" in ts) and isinstance(val, str):
            try:
                val = int(val) if "integer" in ts and "number" not in ts else float(val)
            except ValueError:
                pass
        en = enum_of(spec)
        if en and val not in en and str(val) in [str(e) for e in en]:
            val = next(e for e in en if str(e) == str(val))
    if is_file_field(key):
        val = [to_url(x) for x in val] if isinstance(val, list) else to_url(val)
    return val


def build_input(endpoint, pairs, extra_json):
    sch = input_schema(endpoint)
    props = sch["properties"]
    inp = {}
    if extra_json:
        if os.path.isfile(extra_json):
            with open(extra_json) as f:
                extra_json = f.read()
        try:
            inp.update(json.loads(extra_json))
        except ValueError as e:
            die("--json is not valid JSON: %s" % e)
    for p in pairs:
        if "=" not in p:
            die("inputs must look like key=value: %s" % p)
        k, v = p.split("=", 1)
        inp[k.strip()] = v
    out = {}
    for k, v in inp.items():
        spec = props.get(k)
        if props and spec is None:
            die("'%s' is not an input of %s. Valid fields: %s" % (k, endpoint, ", ".join(props)))
        out[k] = coerce(k, v, spec)
        en = enum_of(spec) if spec else None
        if en and out[k] not in en:
            die("invalid value %r for '%s'. Options: %s" % (out[k], k, ", ".join(str(e) for e in en if e is not None)))
    missing = [r for r in sch["required"] if r not in out]
    if missing:
        die("missing required field(s): %s. See `fal schema %s`." % (", ".join(missing), endpoint))
    return out


# ---------- outputs ----------
def collect_urls(o):
    urls = []
    if isinstance(o, str):
        if o.startswith("http") and re.search(r"\.(mp4|mov|webm|png|jpe?g|webp|gif|mp3|wav|m4a|ogg|flac|json|srt|vtt|zip)(\?|$)", o, re.I):
            urls.append(o)
    elif isinstance(o, list):
        for x in o:
            urls += collect_urls(x)
    elif isinstance(o, dict):
        if isinstance(o.get("url"), str) and o["url"].startswith("http"):
            urls.append(o["url"])
        else:
            for x in o.values():
                urls += collect_urls(x)
    seen, out = set(), []
    for u in urls:
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def default_out(url):
    ext = os.path.splitext(urllib.parse.urlparse(url).path)[1].lower()
    if ext in (".mp4", ".mov", ".webm"):
        return "Shots"
    if ext in (".mp3", ".wav", ".m4a", ".ogg", ".flac"):
        return "Audio"
    if ext in (".png", ".jpg", ".jpeg", ".webp", ".gif"):
        return "Asset"
    return "Work"


def download(urls, out, name, endpoint, rid):
    saved = []
    stamp = datetime.datetime.now().strftime("%H%M%S")
    base = re.sub(r"[^A-Za-z0-9._-]+", "-", name or "-".join(endpoint.split("/")[1:]) or endpoint)[:60]
    for i, u in enumerate(urls):
        d = out or os.path.join(JOB, default_out(u))
        os.makedirs(d, exist_ok=True)
        ext = os.path.splitext(urllib.parse.urlparse(u).path)[1] or ".bin"
        fn = "%s_%s-%s%s%s" % (base, stamp, re.sub(r"[^A-Za-z0-9]", "", rid)[-4:], ("_%d" % (i + 1)) if len(urls) > 1 else "", ext)
        path = os.path.join(d, fn)
        try:
            with urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=300) as r, open(path, "wb") as f:
                shutil.copyfileobj(r, f)
            saved.append((path, u))
        except Exception as e:
            print("  download failed (%s): %s" % (e, u), file=sys.stderr)
    if saved:
        remember_urls(saved)
    return saved


def media_seconds(path):
    if not shutil.which("ffprobe"):
        return None
    p = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                       capture_output=True, text=True)
    try:
        return float(p.stdout.strip())
    except ValueError:
        return None


def estimate_cost(price, inp, saved, result):
    usage = result.get("usage") if isinstance(result, dict) else None
    if isinstance(usage, dict) and isinstance(usage.get("cost"), (int, float)):
        return float(usage["cost"]), "usage"
    if not price or price.get("unit_price") is None:
        return None, ""
    unit = str(price.get("unit", "")).lower()
    up = float(price["unit_price"])
    if "second" in unit:
        secs = sum(filter(None, (media_seconds(p) for p, _ in saved)))
        if not secs:
            try:
                secs = float(inp.get("duration"))
            except (TypeError, ValueError):
                secs = 0
        return (up * secs, "estimate") if secs else (None, "")
    if "minute" in unit:
        secs = sum(filter(None, (media_seconds(p) for p, _ in saved)))
        return (up * secs / 60, "estimate") if secs else (None, "")
    if "image" in unit or "video" in unit or "request" in unit or "generation" in unit or "audio" in unit:
        return up * max(1, len(saved)), "estimate"
    if "1000 char" in unit or "1k char" in unit or "character" in unit:
        n = len(str(inp.get("prompt") or inp.get("text") or ""))
        per = 1000 if "1000" in unit or "1k" in unit else 1
        return up * n / per, "estimate"
    return None, ""


def wait_and_fetch(rid, info, out, name, timeout):
    t0 = time.time()
    last = ""
    status_url, response_url, endpoint = info["status_url"], info["response_url"], info["endpoint"]
    while True:
        s, r = http("GET", status_url, timeout=60)
        if s >= 500 or s == 429:
            time.sleep(4)
            continue
        if s not in (200, 202):
            die("status check failed (%s): %s" % (s, json.dumps(r)[:400]))
        st = r.get("status", "")
        if st != last:
            pos = r.get("queue_position")
            print("  status: %s%s (%ds)" % (st, (" #%s" % pos) if pos is not None and st == "IN_QUEUE" else "", time.time() - t0), file=sys.stderr)
            last = st
        if st == "COMPLETED":
            if r.get("error"):
                die("generation failed: %s %s" % (r.get("error_type", ""), r.get("error")))
            break
        if time.time() - t0 > timeout:
            print("Still running. To keep waiting: fal wait %s%s%s" % (
                rid, (" --out " + out) if out else "", (" --name " + name) if name else ""))
            sys.exit(3)
        time.sleep(3)
    s, result = http("GET", response_url, timeout=120)
    if s != 200:
        die("could not fetch the result (%s): %s" % (s, json.dumps(result)[:600]))
    urls = collect_urls(result)
    saved = download(urls, out, name, endpoint, rid)
    cost, how = estimate_cost(info.get("price"), info.get("input") or {}, saved, result)
    log_cost(endpoint, rid, cost, [os.path.relpath(p, JOB) for p, _ in saved], how)
    if not urls:
        print("Result (no files):")
        print(json.dumps(result, ensure_ascii=False, indent=1)[:4000])
    for p, u in saved:
        print("SAVED %s" % os.path.relpath(p, JOB))
        print("  url: %s" % u)
    print("cost: %s, time: %ds, request: %s" % (
        "?" if cost is None else ("$%.3f%s" % (cost, " (est.)" if how == "estimate" else "")), time.time() - t0, rid))
    return result


def parse_opts(args, flags, bools=()):
    opts, rest, i = {}, [], 0
    while i < len(args):
        a = args[i]
        if a in bools:
            opts[a] = True
        elif a in flags:
            if i + 1 >= len(args):
                die("missing value for %s" % a)
            if a == "--image":
                opts.setdefault(a, []).append(args[i + 1])
            else:
                opts[a] = args[i + 1]
            i += 1
        else:
            rest.append(a)
        i += 1
    return opts, rest


def submit(endpoint, inp):
    s, r = http("POST", QUEUE + "/" + endpoint, body=inp)
    if s not in (200, 201, 202) or not r.get("request_id"):
        hint = ""
        if s == 401:
            hint = " (fal rejected the key)"
        elif s in (402, 403) and "balance" in json.dumps(r).lower():
            hint = " (fal balance is too low)"
        die("submit failed (%s): %s%s" % (s, json.dumps(r)[:800], hint))
    app = "/".join(endpoint.split("/")[:2])
    info = {"endpoint": endpoint,
            "status_url": r.get("status_url") or "%s/%s/requests/%s/status" % (QUEUE, app, r["request_id"]),
            "response_url": r.get("response_url") or "%s/%s/requests/%s" % (QUEUE, app, r["request_id"]),
            "input": {k: v for k, v in inp.items() if not (isinstance(v, str) and v.startswith("data:"))},
            "price": price_of(endpoint)}
    remember_request(r["request_id"], info)
    return r["request_id"], info


def cmd_run(args):
    opts, rest = parse_opts(args, ("--out", "--name", "--timeout", "--json"), ("--no-wait",))
    if not rest:
        die("usage: fal run <endpoint_id> key=value ...")
    endpoint, pairs = rest[0], rest[1:]
    inp = build_input(endpoint, pairs, opts.get("--json"))
    print("submitting: %s %s" % (endpoint, json.dumps(inp, ensure_ascii=False)[:600]), file=sys.stderr)
    rid, info = submit(endpoint, inp)
    print("request: %s" % rid)
    if opts.get("--no-wait"):
        print("Not waiting. Later: fal wait %s" % rid)
        return
    out = opts.get("--out")
    if out and not os.path.isabs(out):
        out = os.path.join(JOB, out)
    wait_and_fetch(rid, info, out, opts.get("--name"), float(opts.get("--timeout", 570)))


def cmd_wait(args):
    opts, rest = parse_opts(args, ("--out", "--name", "--timeout"))
    if not rest:
        die("usage: fal wait <request_id>")
    info = _load("fal-requests.json").get(rest[0])
    if not info:
        die("unknown request %s (it was not sent from this job folder)" % rest[0])
    out = opts.get("--out")
    if out and not os.path.isabs(out):
        out = os.path.join(JOB, out)
    wait_and_fetch(rest[0], info, out, opts.get("--name"), float(opts.get("--timeout", 570)))


def cmd_upload(args):
    if not args:
        die("usage: fal upload <file>")
    print(to_url("@" + args[0]))


def cmd_cost(_args):
    p = os.path.join(JOB, "Logs", "fal.csv")
    try:
        rows = list(csv.DictReader(open(p)))
    except OSError:
        print("No spend recorded for this job yet.")
        return
    total = sum(float(r["cost_usd"]) for r in rows if r.get("cost_usd"))
    unknown = sum(1 for r in rows if not r.get("cost_usd"))
    print("%d requests, about $%.2f%s" % (len(rows), total, (", %d without a price" % unknown) if unknown else ""))


# ---------- LLM helpers (OpenRouter on fal) ----------
def llm(endpoint, inp, timeout=600):
    rid, info = submit(endpoint, inp)
    t0 = time.time()
    while True:
        s, r = http("GET", info["status_url"], timeout=60)
        if s == 200 and r.get("status") == "COMPLETED":
            break
        if s not in (200, 202, 429) and s < 500:
            return s, {"error": r}
        if time.time() - t0 > timeout:
            return 504, {"error": "timeout"}
        time.sleep(2)
    s, result = http("GET", info["response_url"], timeout=120)
    cost = (result.get("usage") or {}).get("cost") if isinstance(result, dict) else None
    log_cost(endpoint, rid, cost, [], "usage" if cost is not None else "")
    return s, result


def cmd_ask(args):
    opts, rest = parse_opts(args, ("--model", "--image", "--system"))
    if not rest:
        die('usage: fal ask "<question>" [--image file]')
    inp = {"prompt": " ".join(rest), "model": opts.get("--model", DEFAULT_LLM)}
    if opts.get("--system"):
        inp["system_prompt"] = opts["--system"]
    imgs = [to_url("@" + p) for p in opts.get("--image", [])]
    if imgs:
        inp["image_urls"] = imgs
    s, r = llm("openrouter/router/vision" if imgs else "openrouter/router", inp)
    if s != 200:
        die("LLM error (%s): %s" % (s, json.dumps(r)[:600]))
    print((r.get("output") or "").strip())


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True)


ANALYZE_PROMPT = """You are a performance-marketing creative analyst. This is a mobile app ad (a competitor's or a reference).
Goal: rebuild something similar for our own app. Write clearly and precisely in Markdown. Write in {lang}.

Technical info: duration {dur:.2f} s, {w}x{h}, {fps} fps. Detected scene cuts (s): {cuts}
{extra}

Fill in these sections:
1. Summary: the concept in one sentence and why it works.
2. Hook (0-3 s): exactly what happens on screen, the first frame, the first text.
3. Shot-by-shot flow: a table with columns start-end (s), picture (camera, framing, talent, location), on-screen text (verbatim), audio/VO (verbatim), transition.
4. All on-screen text: verbatim, in order, with rough position and style (font feel, color, size).
5. Audio: VO script verbatim with timestamps, voice tone and gender, music genre and tempo, SFX.
6. Visual style: lighting, color, camera movement, UGC or studio, talent type.
7. App/UI moments: which screens are shown and how they animate.
8. CTA and ending: packshot, logo, copy.
9. Rebuild recipe: for every shot, "AI-generated live footage" or "UI/text/graphics built in Remotion code"; for AI shots, the suggested method (image-to-video, text-to-video, reference-to-video) and a short English generation prompt.
10. Caution: brand elements, licensed music and original characters that must not be copied."""


def cmd_analyze(args):
    opts, rest = parse_opts(args, ("--model", "--prompt", "--out", "--lang"))
    if not rest:
        die("usage: fal analyze <video> [--prompt 'extra request']")
    src = os.path.expanduser(rest[0])
    if not os.path.isabs(src) and not os.path.exists(src):
        src = os.path.join(JOB, src)
    if not os.path.isfile(src):
        die("video not found: %s" % src)
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        die("ffmpeg/ffprobe not found.")
    model = opts.get("--model", DEFAULT_LLM)
    lang = opts.get("--lang") or os.environ.get("MA_LANGUAGE", "English")
    pr = run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
              "stream=width,height,r_frame_rate:format=duration", "-of", "json", src])
    info = json.loads(pr.stdout or "{}")
    st = (info.get("streams") or [{}])[0]
    dur = float((info.get("format") or {}).get("duration") or 0)
    w, h = st.get("width", 0), st.get("height", 0)
    fr = st.get("r_frame_rate", "0/1").split("/")
    fps = round(float(fr[0]) / float(fr[1]), 2) if len(fr) == 2 and float(fr[1] or 0) else "?"
    sc = run(["ffmpeg", "-hide_banner", "-i", src, "-vf", "select='gt(scene,0.3)',showinfo", "-an", "-f", "null", "-"])
    cuts = [round(float(x), 2) for x in re.findall(r"pts_time:([0-9.]+)", sc.stderr)]
    cuts_s = ", ".join(str(c) for c in cuts) or "no clear cuts"
    extra = ("Extra request from the user: " + opts["--prompt"]) if opts.get("--prompt") else ""
    base_name = os.path.splitext(os.path.basename(src))[0]
    work = os.path.join(JOB, "Work", "analysis-" + re.sub(r"[^A-Za-z0-9_-]+", "-", base_name)[:40])
    os.makedirs(work, exist_ok=True)

    # contact sheets: always made, so the agent can look at the frames itself
    sheets = []
    if dur > 0:
        step = dur / 36
        for k in range(3):
            times = [round(step * (k * 12 + j) + step / 2, 2) for j in range(12)]
            times = [t for t in times if t < dur]
            if not times:
                break
            fps_f = float(fps) if fps != "?" else 30.0
            sel = "+".join("eq(n,%d)" % int(t * fps_f) for t in times)
            outp = os.path.join(work, "sheet%d.jpg" % (k + 1))
            rr = run(["ffmpeg", "-v", "error", "-y", "-i", src, "-vf",
                      "select='%s',scale=300:-2,tile=4x3:padding=4:color=black" % sel, "-frames:v", "1", "-q:v", "4", outp])
            if rr.returncode == 0 and os.path.exists(outp):
                sheets.append((outp, times))

    prompt = ANALYZE_PROMPT.format(dur=dur, w=w, h=h, fps=fps, cuts=cuts_s, extra=extra, lang=lang)
    text, used, errors = "", "", []
    bad = re.compile(r"(video|audio).{0,40}(cannot|can't|unable|not able)", re.I)

    if os.path.getsize(src) <= 95 * 1024 * 1024:
        print("  analyzing the full video (%s)" % model, file=sys.stderr)
        s, r = llm("openrouter/router/video", {"prompt": prompt, "model": model, "video_urls": [to_url("@" + src)], "max_tokens": 8000})
        t = (r.get("output") or "").strip() if s == 200 else ""
        if len(t) > 200 and not bad.search(t[:400]):
            text, used = t, "video"
        else:
            errors.append("video: HTTP %s %s" % (s, json.dumps(r)[:200] if s != 200 else t[:120]))
    if not text and sheets:
        print("  falling back to contact sheets (%s)" % model, file=sys.stderr)
        note = "\n\nOnly frames are attached, as contact sheets (12 frames each, left to right, top to bottom). Times (s): " + \
               " | ".join(", ".join(str(t) for t in ts) for _, ts in sheets) + ". Write 'not audible' for VO and music."
        s, r = llm("openrouter/router/vision", {"prompt": prompt + note, "model": model,
                                                 "image_urls": [to_url("@" + p) for p, _ in sheets], "max_tokens": 8000})
        t = (r.get("output") or "").strip() if s == 200 else ""
        if len(t) > 200:
            text, used = t, "contact sheets"
        else:
            errors.append("frames: HTTP %s %s" % (s, json.dumps(r)[:200] if s != 200 else t[:120]))
    if not text:
        die("analysis failed. Attempts: " + " | ".join(errors))

    out = opts.get("--out") or os.path.join(JOB, "Brief", "reference-analysis.md")
    out = out if os.path.isabs(out) else os.path.join(JOB, out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    header = "# Reference analysis: %s\n\nSource: %s, method: %s, model: %s\nDuration %.2f s, %sx%s, %s fps. Cuts: %s\n\n" % (
        os.path.basename(src), os.path.relpath(src, JOB), used, model, dur, w, h, fps, cuts_s)
    with open(out, "w") as f:
        f.write(header + text + "\n")
    print(header + text)
    print("\nSAVED %s" % os.path.relpath(out, JOB))
    if sheets:
        print("Contact sheets: %s" % ", ".join(os.path.relpath(p, JOB) for p, _ in sheets))


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help", "help"):
        print(__doc__)
        return
    cmd, args = sys.argv[1], sys.argv[2:]
    fn = {"models": cmd_models, "schema": cmd_schema, "run": cmd_run, "wait": cmd_wait, "upload": cmd_upload,
          "analyze": cmd_analyze, "ask": cmd_ask, "cost": cmd_cost}.get(cmd)
    if not fn:
        die("unknown command: %s. See `fal help`." % cmd)
    fn(args)


if __name__ == "__main__":
    main()
