---
name: app-ad-video
description: >-
  Make mobile app ad videos with a hybrid pipeline (Remotion + fal.ai + ffmpeg + vision QC). Break down a
  reference ad by measuring frames, pixels and audio and rebuild it frame-accurately in Remotion; generate
  AI talent images and shots on fal.ai (nano-banana, Seedance, Kling, Veo); face tracking for overlays and
  shot placement; voiceover + karaoke captions; music/SFX alignment and levels; color-correct delivery and
  verification by measuring the delivered file. Use whenever the user asks to make, rebuild, vary, localize
  or re-format an app ad / creative / video for ANY app ("make a video", "ad", "creative", "variant",
  "localize", "new format", "watch/analyze the reference", "deliver"), to analyze a reference ad, or to
  deliver/verify a master.
---

# App ad video: the skill

This is not a list of rules. It is the **how-to** knowledge built up over many ad series, with the
measurements behind it. The rules live elsewhere and still apply in full: `~/.claude/CLAUDE.md` (state the
model and cost before paid generation, track spend, every job in its own folder, never open `.aep`, keys)
and `~/.claude/rules/working-style.md` (app code, folders, export names). Everything here is about doing
the work well inside those rules.

```bash
SK=~/.claude/skills/app-ad-video/scripts     # used in every command below
```

## Approach: five habits that make this work

1. **Measure, do not eyeball.** Every position, size, color, timing, easing and level from the reference
   comes from a measurement, and every constant in the code carries a note on *how it was measured*.
   "Looks similar" is not enough: side-by-side frame difference, profile error and dB difference decide.
2. **Build models, choose by measurement.** If you do not know what an effect is, build the candidate
   models (box or Gaussian blur, plain or mirrored tiling) and compare their error against the
   measurement. Example: a whip transition measured Gaussian error 133, box 9.7, mirrored tiling 2.7.
3. **Composition lives in code; AI only makes what code cannot** (faces, places, motion, voice). UI, text,
   transitions, overlays, captions and the packshot are built in Remotion, which is why variants and
   localizations are cheap.
4. **Use up what already exists first.** AE `(Footage)` assets, earlier `-AI` jobs' code, shots and audio,
   editing tricks (splitting a scene). Generation comes last. One past series made four creatives for $0.
5. **Measure what you deliver.** Not what you produced, the file in `Final/`: frames, duration, color path
   (in a saturated region), LUFS, peak, and that the voice is in the file. The most expensive mistakes
   all slipped through because "the intermediate file was fine".

## Flow

| # | Stage | What | Details |
|---|---|---|---|
| 0 | Prep | New creative or variant, code, folder; copy the previous `-AI` job's `src/`, symlink `node_modules`, open `PRODUCTION.md` | decision table below |
| 1 | Break down the reference | `fal analyze`, cuts, contact sheets, speech (STT), OCR, pixel/time measurement, font matching, multi-format model | [01-reference-breakdown](reference/01-reference-breakdown.md) |
| 2 | Scope + cost | number of shots/generations, model choice (quality/speed/cost), realistic cost, **say it** | [03-ai-generation](reference/03-ai-generation.md) |
| 3 | Audio first | VO, alignment, shot lengths and captions; align reference music/SFX, measure levels | [05-audio](reference/05-audio.md) |
| 4 | Images + shots | talent recipe, choosing via collage, image-to-video shots, keying | [03-ai-generation](reference/03-ai-generation.md) |
| 5 | Composition | Remotion skeleton, stage + format model, mask painting, motion blur, whip, text, calibration | [02-remotion](reference/02-remotion.md) |
| 6 | Face-bound layers | face tracking, clean shot window, slow-down/freeze, placement, mesh/oval/nose, portrait | [04-faces-and-shot-plan](reference/04-faces-and-shot-plan.md) |
| 7 | Delivery | PNG -> real BT.709 -> single AAC; measure the delivered file | [06-delivery](reference/06-delivery.md) |
| 8 | QC + presentation | vision model (creative), ffmpeg (measurement), collage; report + `PRODUCTION.md` | [07-qc](reference/07-qc.md) |

All the pitfalls in one place: [08-pitfalls](reference/08-pitfalls.md). Skim it before a new job.

## What was asked -> what to do

| Request | What you do | What you reuse |
|---|---|---|
| New reference, new creative | open `<CODE><nn>-AI`; measure the reference from scratch | the series' code (previous `-AI`), palette, fonts, packshot |
| Same creative, new talent | new `-AI` (new number); only the talent chain: image -> shot -> tracking -> window -> placement -> portrait | code, measurements, audio, packshot. Fit the talent's features to the VO/UI so the VO need not be regenerated (VO says "Bangs, bob, pixie" -> pick matching hair) |
| Another creative with existing talent | reuse the existing shots; present candidates in a collage and let the user pick | shots + face tracks ($0) |
| Localization | **same folder**, only the language code changes; redo VO + alignment + captions, translate on-screen text | delivered file + `(Footage)`; rebuild what is behind burned-in layers from source clips |
| New format (1:1, 16:9) | same folder; a new `LAYOUTS` key; if the reference has that format, measure it separately | everything |
| Revision | same folder; the old delivery moves to `Work/previous/` | everything |
| A long cut from existing deliveries ("back to back, packshot at the end") | new `-AI`; measure the cut point (packshot transition), set length from the held end card; picture in YUV with ffmpeg, music continuous + SFX extracted from the source ([05](reference/05-audio.md), [06](reference/06-delivery.md)) | delivered mp4s, `(Footage)` music; $0 |

## Starting a new app

1. **Code and folder:** if the app's three-letter code is unknown, ask the user. The first creative is
   `projects/<App>/<CODE>01-AI`, created from the dashboard (project template).
2. **Brand kit:** logo, palette, fonts and packshot/CTA. Sources in order: the app's existing AE
   creatives' `(Footage)`, delivered masters (take the packshot exactly, sample colors from pixels) and
   App Store images. If you only have a 16:9 packshot, do not crop and upscale; measure it and rebuild
   ([01](reference/01-reference-breakdown.md#if-you-only-have-a-169-packshot)). With no font, pick the closest
   by measurement ([01](reference/01-reference-breakdown.md#4-font-matching)).
3. **Product truth:** the App Store description and a real screen recording or screenshots. UI, names,
   labels and categories in the ad are **never invented**; they come from the real product. Every promised
   feature must exist in the app.
4. **The first creative is the series' skeleton:** build `theme.ts`, `layout.ts` and the components
   cleanly, with measurement notes on the constants. Later creatives copy it. Keep a `HANDOFF.md` at the
   series root: cross-job knowledge, repeating mistakes, open decisions.

## Toolbox (`$SK`)

`$SK` is `~/.claude/skills/app-ad-video/scripts`. They run on the system python without numpy/PIL unless
noted. Job-specific builders you write yourself (caption, audio or montage builders) go in the job's
`Work/tools/` so the job can be reproduced on its own. `vision.py` and `_fal.py` are shared helpers that
the other scripts import.

| Script | What it does | Example |
|---|---|---|
| `fx.py` | measurement library + CLI: probe, cuts, contact sheet, region curve, frame grab; `frames/px/bbox/bands/row_profile/match_1d/parabola` | `python3 $SK/fx.py cuts ref.mp4` |
| `face_track.py` | face tracking -> `faceTrack.ts` (eyes, eye distance, roll, nose); `--mesh` Procrustes; `--stats` target from a reference | `python3 $SK/face_track.py Shots/talent_plate.mp4 --out src/faceTrack.ts` |
| `plate_qc.py` | QC for closed-mouth (inner voice) shots: per-frame face track, face box (for placement), outer lip ratio and **speech oscillation**, mouth crop sheet | `Work/venv/bin/python $SK/plate_qc.py public/shots/k1_30.mp4 ...` (numpy + PIL) |
| `plate_windows.py` | talking / looking-away / turned ranges in a shot, the best window, suggested slow-down | `python3 $SK/plate_windows.py plate.mp4 --need 5.07` |
| `fit_plate.py` | `PLATE_FIT {s, ox, oy}` that puts the window average on the target, coverage check | `... --offset 6.2 --rate 0.757 --frames 153 --target 554.2,1378.3,280.9 --panel 0,953,1080,1920` |
| `portrait_crop.py` | portrait from a shot with the reference framing (eyes open, frontal, mouth closed) | `... plate.mp4 auto --card 923x779 --eye 0.533,0.502,0.175` |
| `audio_match.py` | music alignment + residual, SFX search (with speed sweep), energy level, mix comparison | `python3 $SK/audio_match.py music ref.mp4 music.wav --out Work/au` |
| `speech.py` | speech-to-text (reference transcript) and forced alignment (caption timing) on fal | `python3 $SK/speech.py stt ref.mp4 Work/stt.json` |
| `stills.mjs` | many PNG frames with one bundle and one browser (quick checks) | `node $SK/stills.mjs <id> Work/st 0,30,150` (from the job root) |
| `prep_plate.sh` | AI shot -> 30 fps + audio + STT + (if green screen) tracking | `bash $SK/prep_plate.sh v2 Shots/v2.mp4 --stt --track` (from the job root) |
| `screen_track.py` | green phone screen tracking -> corner TS + RGBA patch; `--fill-from` trail fill (numpy + PIL, venv) | `Work/venv/bin/python $SK/screen_track.py public/shots/v1_30.mp4 --name v1 --ts src/track/v1.ts --patch public/patch/v1` |
| `teeth_whiten.py` | naturally whitens yellowed teeth in an AI shot: inner lip mask, reduces yellow in YUV (lips/skin untouched) | `Work/venv/bin/python $SK/teeth_whiten.py Shots/plate.mp4 Shots/plate_teeth.mp4 --sheet Work/teeth.png` |
| `voice_design.py` | voice design on fal: preview voices for your VO script from a description | `python3 $SK/voice_design.py --desc "..." --text-file Work/vo_script.txt --out-dir Audio/design --tag x` |
| `ref_edit.py` | reference-based image edit on fal (same face / same character in a new scene) | `python3 $SK/ref_edit.py -p prompt.txt -r Asset/a.png -o Asset/b.png` |
| `cover_check.py` | whether the UI covers the screen in a composite (dark ratio along the inner edge) | `... cover_check.py Work/x.mp4 src/track/v1.ts --start 9` |
| `slow_clip.sh` | motion-interpolated slow motion from a shot's closed-mouth window (24 fps source) | `bash $SK/slow_clip.sh k5_slow Shots/k5.mp4 0 1.42 0.58` |
| `prelimit.sh` | iterative peak limiting before loudnorm (192 kHz, `latency=1`) | `bash $SK/prelimit.sh Work/mix_raw.wav Work/mix_pre.wav` |
| `deliver_png.sh` | color-correct, single-AAC delivery (+ verification frames) | `bash $SK/deliver_png.sh <id> Final/<name>.mp4 15` |
| `sat_diag.py` | splits verify's saturated-region alarm into measurement / 4:2:0 / encoding (four numbers) | `python3 $SK/sat_diag.py Final/x.mp4 Work/ref_x/f_262.png 262` |
| `verify_delivery.py` | full measurement of the delivered file, color path included; exit code | `python3 $SK/verify_delivery.py --dur 15 --platform meta` |
| `macos/facetrack` · `macos/ocr` · `macos/collage` | face landmarks, on-screen text OCR, labeled grid (ffmpeg builds often lack drawtext). macOS only, Apple Vision | `swiftc -O $SK/macos/ocr.swift -o ~/.local/bin/ocr` |

Long generations: `fal run ... --no-wait` to submit, then `fal wait <request_id>` to collect.

## Working with the user

- Reply in the user's language, briefly; technical terms can stay in English. At the end: a delivery
  table (file, duration/frames, LUFS, peak), what was measured and how, spend (`fal cost`), open items.
  Point to the delivered files.
- Where a choice is needed (talent, shot, variant), make a **labeled collage** and ask; put your
  recommendation first.
- Write down every deliberate deviation from the reference and why (for example, not promising a feature
  the app does not have).
- Do not change an approved look on your own to be "closer to the reference"; report the difference.

## Grow this skill

When you learn a new technique, a measured model behavior or a pitfall, add it to the right
`reference/` file **with its measurement and the situation where you saw it**; when you fix a script,
update the copy here too. Job-specific numbers stay in that job's `PRODUCTION.md`; only what generalizes
comes here.
