// Render several frames of a composition as PNGs with one bundle and one browser (much faster than
// one `remotion still` per frame). Run from the project root:
//   node ~/.claude/skills/app-ad-video/scripts/stills.mjs <composition> <out_dir> <frame,frame,...>
import path from "node:path";
import fs from "node:fs";
import { createRequire } from "node:module";
import { pathToFileURL } from "node:url";

// Resolve Remotion from the project (cwd), not from this script's folder.
const req = createRequire(path.resolve("package.json"));
const load = (name) => import(pathToFileURL(req.resolve(name)).href);
const { bundle } = await load("@remotion/bundler");
const { renderStill, selectComposition, openBrowser } = await load("@remotion/renderer");

const [comp, outDir, list] = process.argv.slice(2);
if (!comp || !outDir || !list) {
  console.error("usage: node stills.mjs <composition> <out_dir> <frame,frame,...>");
  process.exit(2);
}
const frames = list.split(",").map((s) => parseInt(s, 10));
fs.mkdirSync(outDir, { recursive: true });
const serveUrl = await bundle({ entryPoint: path.resolve("src/index.ts"), publicDir: path.resolve("public") });
const browser = await openBrowser("chrome");
const composition = await selectComposition({ serveUrl, id: comp, puppeteerInstance: browser });
for (const f of frames) {
  const output = path.join(outDir, `${comp}_${String(f).padStart(3, "0")}.png`);
  await renderStill({ composition, serveUrl, output, frame: f, puppeteerInstance: browser, overwrite: true });
  console.log("wrote", output);
}
await browser.close({ silent: true });
