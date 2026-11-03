# Working rules: app ad production

This file loads automatically in every agent session. The rules apply to every job.

---

## 1. Who you work for

The user makes mobile app ads. The pipeline is **hybrid**: deterministic, code-based composition
(Remotion) + AI generation on fal.ai (images, video, voice, sound) + assembly and delivery (ffmpeg) +
quality control (measurement with ffmpeg/ffprobe, creative review with a vision model).

Reply in the language the user writes in. Technical terms can stay in English (render, hook, CTA, LUFS).

Do not read every reference file up front. Open only the section for the stage you are in.

---

## 2. Hard rules

These apply every time unless the user says otherwise.

### 2.1 Say what you will spend before you spend it

Before a paid generation, state the model, the number of generations and the estimated cost in one or
two lines, with a short quality / speed / cost comparison if there is a real choice. Then continue,
unless the user has asked you to wait for a yes.

Example: *"Key visual with `fal-ai/nano-banana-pro` (best realism) rather than
`google/nano-banana-2-lite` (cheaper, a bit less detail). 4 images, about $0.60."*

**Variants too.** Even when a variant repeats an approved setup exactly, name the setup:

1. The model used in the previous creative, by name, as the default. It keeps the series consistent.
2. At least one alternative, in case the user wants to try something new.
3. The number of generations and the estimated cost.

Free, local work needs no announcement: ffmpeg, Remotion renders, file work, measurements.

### 2.2 Keep track of spend

Every `fal run` writes a line to the job's `Logs/fal.csv` (endpoint, cost, request id, outputs).
LLM calls report their real cost; image and video costs are estimates from fal's price list. Check the
running total with `fal cost` and mention it at milestones. Failed generations can also be billed, so
leave room for retries in estimates. The user's real balance is on their fal.ai dashboard.

### 2.3 Every job stays in its own folder

Before you start, check that you are in the right job folder (`pwd`). Never write a job's files into
another job's folder and never produce media in a scratch workspace. Reading from other jobs (packshot,
music, fonts, measurements) is allowed and encouraged.

### 2.4 Do not open After Effects projects

If the user has After Effects project folders, **never open, script or render `.aep` files**
(`aerender` included) and never launch After Effects.

What you may use from such a folder: **assets and measurements**. The files in the `(Footage)` folder,
the layer and effect dump in `*Report.txt`, and pixel measurements from delivered exports (color,
layout, timing). Reusing assets is encouraged because it saves tokens and generation cost. Composition
and rendering always happen in code: Remotion and/or ffmpeg.

To localize or revise a delivered mp4, do not go back to the source project. Rebuild from the delivered
file plus the `(Footage)` sources (restore what is behind burned-in layers from the source clips, remix
the audio bed from the source track).

---

## 3. Folder layout

> Creative codes, creative folders, export names and when to open a new folder:
> `~/.claude/rules/working-style.md`. It loads in every session; read it if it is not in context.

Every job folder follows this layout:

| Folder | Contents |
|---|---|
| `Brief/` | Brief, audience, KPI, CTA copy, `reference-analysis.md` |
| `Ref.Videos/` | Reference ads, analyzed with `fal analyze` |
| `Asset/` | Images, logo, product shots (fal image outputs) |
| `Audio/` | VO, music, SFX (fal audio outputs) |
| `Shots/` | AI video shots (fal video outputs) |
| `Work/` | Remotion renders, intermediate cuts. **Never delivered** |
| `Final/` | Delivery masters, made with `deliver_png.sh` (`working-style.md` §6) |
| `Logs/` | `fal.csv` spend log, request and URL caches |
| `src/` | Remotion compositions (`compositions/`, `components/`) |

---

## 4. API keys

Keys reach the agent as environment variables (`FAL_KEY`). The tools read them from there. If a tool
says a key is missing, tell the user to add it in the dashboard. Do not search for keys.

**Never** hard-code keys, write them to logs, commit them or print them back in full. Every job's
`.gitignore` covers `.env`.

---

## 5. Tools

### `fal`: generation and analysis on fal.ai

```bash
fal models seedance                          # find endpoint ids
fal schema bytedance/seedance-2.0/image-to-video    # fields, options, price
fal run fal-ai/nano-banana-pro prompt="..." aspect_ratio=9:16 --name key
fal run bytedance/seedance-2.0/image-to-video image_url=Asset/key_*.png prompt="..." \
    duration=5 aspect_ratio=9:16 generate_audio=false
fal run <endpoint> ... --no-wait              # long jobs: submit now
fal wait <request_id>                         # ...collect later
fal analyze Ref.Videos/ref.mp4                # reference breakdown -> Brief/reference-analysis.md
fal ask "Is the hook readable?" --image Work/f_030.png
fal upload Work/frame.png                     # get a URL for a local file
fal cost                                      # spend for this job
```

- Local paths in `*_url` / `*_urls` fields are uploaded automatically. Files that `fal` itself produced
  reuse their existing URL, so chains like image -> video need no upload.
- Every `run` validates the fields against the live schema first, so a wrong field name, a missing
  required field or an invalid option fails before any money is spent. When unsure, run `fal schema`.
- Model choices and recipes: the fal skill and `skills/app-ad-video/reference/03-ai-generation.md`.

### Delivery

Delivery only goes through `deliver_png.sh` (`~/.claude/rules/working-style.md` §6).

### Optional macOS helpers

`skills/app-ad-video/scripts/macos/` holds three Swift tools that use Apple's Vision framework:
`facetrack` (face landmarks), `ocr` (on-screen text) and `collage` (labeled image grid). Compile once,
for example `swiftc -O facetrack.swift -o ~/.local/bin/facetrack`. On other systems, fall back to
ffmpeg plus `fal ask` with frames.

---

## 6. Remotion

```bash
npm run studio          # Remotion Studio (browser preview + timeline)
npm run render <id> <output>
npm run compositions    # list registered compositions
```

- Never type sizes or fps by hand. Take them from `src/formats.ts` (`FORMATS`, `FPS`, `sec()`).
- The safe area is defined in `SAFE_AREA`. Keep text and CTA **inside** it; platform UI covers anything
  outside.
- New ad: add a file under `src/compositions/` and a `<Composition>` in `src/Root.tsx`.
- Remotion package versions must match **exactly** (no `^`). Check with `npx remotion versions`.
- `SmokeTest-*` compositions verify the setup; delete them in real work if you like.
- Run `npm install` once in a new job before the first render.

---

## 7. Quality control

Before delivering any master:

1. **Produce it with `deliver_png.sh`.** Color is converted to real BT.709, audio gets a single AAC
   encode at -14 LUFS (`~/.claude/rules/working-style.md` §6).
2. **Have a vision model watch it** (`fal analyze Final/x.mp4 --prompt "QC: ..."`): hook, pacing,
   readability, CTA, sync.
3. **Measure the delivered file** with `verify_delivery.py` (ffprobe/ffmpeg): duration, frames, codec,
   the four color tags + `colr`, LUFS / peak, file size, color in a saturated region.

### What vision models are not good at

Measured in testing: a vision model read on-screen text verbatim, counted audio events and their timing
correctly, and got duration and aspect ratio right. But it **reported pitch order backwards** (real
440 -> 880 -> 220 Hz, reported "low -> mid -> high").

So: use the model for **content and creative QC** (what is being said, does the hook work, is the text
readable, is the CTA clear). Leave **measurement** to ffmpeg/ffprobe: loudness, frequency, frame
accuracy, color values.

Fast cuts and single-frame glitches can slip past a model that samples sparsely. When cut rhythm
matters, also check frames yourself (`fx.py sheet` at a higher fps).

---

## 8. Delivery standards

| Platform | Format | Audio | Note |
|---|---|---|---|
| Meta (Reels/Feed) | 9:16 + 4:5 + 1:1 | -14 LUFS | <= 250 MB |
| TikTok | 9:16 | -14 LUFS | <= 280 MB |
| YouTube | 16:9 + 9:16 (Shorts) | -14 LUFS | high bitrate |
| Google Ads | 9:16 + 1:1 + 16:9 | -14 LUFS | <= 200 MB |

All: H.264 High profile, `yuv420p`, bt709, `+faststart`, 30 fps.

Ad rules: the hook lands **in the first 2 seconds**, assume sound off so **captions/on-screen text are
required**, the CTA stays on screen **at least 1.5 seconds** at the end.

---

## 9. Environment notes

- Node 18+, Python 3.9+, ffmpeg/ffprobe with `libx264` and `aac`. Remotion 4 with React 19.
- No hardware acceleration is assumed; long renders use `libx264`.
- Some scripts need numpy + Pillow. Create a venv in the job (`Work/venv`) when they ask for it.
- **npm 11 `allowScripts`:** some packages' postinstall steps are blocked. esbuild was not affected
  (its binary comes as an optionalDependency), but if a package does not work, check
  `npm install-scripts ls` first.
- **Raw Remotion output is `yuvj420p`** (BT.601, full range) and shifts color in some players.
  `--color-space=bt709` and re-tagging the raw render also break color. The correct path is
  `deliver_png.sh` (`~/.claude/rules/working-style.md` §6). **Never deliver a raw render.**
