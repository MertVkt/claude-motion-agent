# Working style: creative codes, export names, folder rules

This file loads in every session. It describes how jobs and exports are named and organized. It adds to
the hard rules in `~/.claude/CLAUDE.md`; it does not replace them.

---

## 1. App codes

Each app has a **fixed three-letter code**, for example *MyApp* -> `MYA`. The code is not always derived
from the name, so do not guess it: if the job or the brief does not show it, **ask the user** once and
reuse it.

## 2. Creative folder names

Each creative has its own folder under `projects/<App Name>/`. The dashboard creates them.

| Pattern | Meaning | Example |
|---|---|---|
| `<CODE><nn> folder` | A creative made **by hand in After Effects** (AE project + `(Footage)` + export folder). Read only. | `MYA104 folder` |
| `<CODE><nn>-AI` | A **code-based** creative (Remotion + AI generation). | `MYA113-AI` |

Numbers have two or three digits and go up within an app. A new creative takes **the next free number**.
Every creative the agent makes gets the `-AI` suffix.

## 3. Export names

```
<CODE><nn>_<LANG>_<KeywordSummary>_<Duration>s_<Width>x<Height>.mp4
```

| Part | Rule | Example |
|---|---|---|
| Code | same as the folder code, **without** `-AI` | `MYA113` |
| Language | `EN`, `ES`, `PT-BR`, `DE`, ... | `EN` |
| Keywords | CamelCase, no spaces, the creative's strongest line | `DontRiskABadHaircut` |
| Duration | rounded to whole seconds + `s` | `16s` |
| Size | `widthxheight` | `1080x1920` |

```
MYA113_EN_DontRiskABadHaircut_16s_1080x1920.mp4
MYA104_ES_VideoBeforeAfter2ScreenUGC_12s_1080x1350.mp4
```

For a localization **only the language code changes**; everything else stays identical.

## 4. When to OPEN a new folder

- A **new creative** is being made: open `<CODE><nn>-AI` (from the dashboard, or copy the previous
  `-AI` job's `src/` so the series stays consistent).
- `node_modules` can be a **symlink** (`ln -s`) to the previous job's; no need to `npm install` again.
- The inner layout follows the table in `~/.claude/CLAUDE.md` §3
  (`Brief/ Ref.Videos/ Asset/ Audio/ Shots/ Work/ Final/ Logs/ src/ public/`).

## 5. When NOT to open a new folder (important)

- A **revision, localization or new format** of an existing delivery: work **in that creative's own
  folder**. No new folder, no new code. New exports go **next to** the existing ones.
- New assets (images, shots, audio) for it: create them **inside the same creative's** folder tree.
- **Never** produce media in a scratch workspace.
- **Never** write into another creative's folder. **Reading** assets from other jobs is allowed and
  preferred (packshot, music, fonts, measurements); writing is not.
- If unsure, ask. Producing into the wrong folder is the most expensive mistake to undo.

## 6. Delivery standard

Written to `Final/`. H.264 High, `yuv420p`, bt709 (four tags + mp4 `colr`), 30 fps, `+faststart`,
AAC 48 kHz stereo **encoded once**, **-14 LUFS**, true peak <= -1 dBTP.

The standard path, from the job root:

```
bash ~/.claude/skills/app-ad-video/scripts/deliver_png.sh <composition> Final/<name>.mp4 <seconds>
```

Remotion writes lossless PNG frames. ffmpeg converts RGB to YUV with the **real BT.709** matrix in
limited range and writes all four tags. Audio goes from the Remotion WAV through two-pass loudnorm to a
**single AAC** encode. The core of it:

```
ffmpeg -framerate 30 -pattern_type glob -i "f_*.png" -i mix_norm.wav -map 0:v:0 -map 1:a:0 \
  -vf "scale=out_color_matrix=bt709:out_range=tv:flags=accurate_rnd+full_chroma_int,format=yuv420p,setparams=range=tv:color_primaries=bt709:color_trc=bt709:colorspace=bt709" \
  -c:v libx264 -preset slow -crf 17 -profile:v high -level 4.2 \
  -af apad -c:a aac -b:a 320k -ar 48000 -ac 2 -t <exact_duration> -movflags +faststart out.mp4
```

Paths measured to be wrong, do not use them:
- **The raw Remotion mp4:** `yuvj420p`, BT.601 full range. **Never deliver it directly.**
- **Remotion `--color-space=bt709`:** encodes the data with the BT.601 matrix and stamps a bt709 tag
  (a CTA orange of 176,64,19 came out as 183,72,15).
- **Re-tagging the raw render as bt709/tv with `h264_metadata`:** the data is not converted, so the
  color shifts (a whole batch of past deliveries came out like this). That remux is only for when the
  video stream is **already real BT.709** and only the audio changes. Pass
  `-color_primaries bt709 -color_trc bt709` together with `-c copy` so the mp4 `colr` box is updated too.

Do not use `-shortest`: because of the AAC frame size it cuts 2 to 3 frames from the video. Use
`apad -t <seconds>` instead.

**Before delivering, measure the file you deliver, not the one you produced:**
`python3 ~/.claude/skills/app-ad-video/scripts/verify_delivery.py --dur <seconds>`. It measures:
- frame count and duration;
- the four tags, `colr` and VUI;
- LUFS, peak and faststart;
- color **in a saturated region** (the CTA) against the source frame. A whole-frame average hides
  matrix errors.

If there is a voiceover, also confirm the voice is actually in the file; this script does not check it.

## 7. Working from a reference video: the order

1. `ffprobe`: size, duration, fps, loudness. `fal analyze` for a first breakdown.
2. Find cuts by frame difference, make contact sheets, look at the shots.
3. **Measure whether there is speech.** RMS is not enough; get a transcript with
   `python3 ~/.claude/skills/app-ad-video/scripts/speech.py stt` (fal speech-to-text).
4. OCR the captions (`ocr` on macOS, or `fal ask` on frames). **Measure** style and timing, do not eyeball.
5. Talk scope and cost **first**; state the model before paid generation (CLAUDE.md §2.1).
6. **Voiceover comes first.** Shot lengths and caption timing are derived from the VO.
7. Replace every mention of the competitor's name with ours; tie every claim to a **real feature** of
   the product.
