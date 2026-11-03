---
name: reel-studio
description: Build punchy 1080x1920 Instagram Reels / TikToks / Shorts from raw action footage (sports, fitness, dance, events, product demos) with heavy effects. The effects are whip pans, RGB split, glitch tears, impact punches, zoom-through, flashes and slow motion. Typography is League Gothic + Space Mono, and strikes in the footage are synced to the music's beats. Use when the user says "make a reel from this footage", "turn these clips into an edit with effects", "sync hits to the beat", or wants to edit, re-time or re-music an existing reel-studio project. Renders locally with Tesseract (tsrct). HyperFrames is the alternative engine for HTML/GSAP motion graphics.
---

# Reel Studio

Turns raw footage into effect-heavy vertical reels. Each reel is a small Python **spec**. `scripts/build.py` turns the spec into a native, editable Tesseract project (`.tsrct`); `tsrct export` then renders the MP4.

Tools this relies on, all installed by this plugin's `install.sh`:
- `tsrct` (Mirage Tesseract CLI, version pinned by the tesseract-video skill)
- the `tesseract-*` skills
- ffmpeg/ffprobe and python3
- optionally the HyperFrames skills (for SFX and an HTML/GSAP alternative)
- optionally the heygen CLI (music library)

Before authoring anything new in Tesseract, read the `tesseract-video` skill. Also read `references/tesseract-gotchas.md`: it lists things the Tesseract docs don't say, and each one cost real debugging time.

## Workflow

1. **Look at the footage first.** Probe with ffprobe and build contact sheets (`ffmpeg -vf "fps=N/dur,scale=200:-2,tile=6x4"`). Read them, and pick moments: entrances, strikes or peak action, faces, the location itself, logos. Never decide from metadata alone.
2. **Create a workspace:** `python3 scripts/init_project.py <root>`. This creates `<root>/.shared/{clips,audio}` and copies the bundled SFX.
3. **Cut segments.** Write `<root>/.shared/segments.json` (see `examples/segments.example.json`) and run `python3 scripts/cut_clips.py segments.json <raw_dir> <root>/.shared`. You get 1080x1920 SDR clips with 0.5s handles, and `clips.json`.
4. **Music.** Put tracks in `.shared/audio/`.
   - Use the user's own licensed tracks if they supply them. Otherwise use the HeyGen library: `npx hyperframes media-use resolve --type bgm --intent "..." --project .` (needs `heygen auth login --oauth`).
   - Analyze the track with `python3 scripts/analyze.py` helpers: `onsets(rms(path))` gives beat and drop candidates, and a per-0.5s loudness map shows the intro, build-ups, breaks and drops.
   - Trim with ffmpeg so the **biggest drop lands on the edit's key moment** (e.g. the reveal) and a break sits just before it. Fade the tail out.
   - Claude can't listen. Say so, and offer the user a choice of alternatives instead of claiming a track "sounds great".
5. **Write the spec** (copy one from `examples/`):
   - `shots`: clip, timeline start `t`, `dur`, optional `rate` (slow motion; 60 fps sources work best) and `off` (source in-point offset)
   - `events`: punch, whip, zoom, snap, push, glitch, flash, dip, ca
   - `cards`: text cards in rise or slam style (full Unicode, including accented characters)
   - `endcard`, `brandLabel`, `sfx`, `music`, `gain`
   - `sync`: slides each shot's in-point by ±0.35s so a **real hit** (strike, footstep, impact) found in the clip audio lands on a **music onset**, and puts the punch there
   - `gate`: footage audio opens only around detected hits. Use it to remove talking or crowd noise while keeping impact sounds.
6. **Build and inspect:** `python3 scripts/build.py spec.py <project_dir>`, then `tsrct filmstrip --project X.tsrct --timestamps-ms ... --output Previews/f.png` and **look at the PNG**. Check that the text fits and transitions render, and that no shot is blank.
7. **Export and verify:** `tsrct export --project X.tsrct --output X.mp4`. Then:
   - Measure loudness with `ffmpeg -af ebur128=peak=true`. Target about −15 LUFS with true peak ≤ −1 dBTP; adjust `gain` (and per-track volumes) in the spec and rebuild.
   - Scan for black frames with signalstats YAVG. The only expected black is an intentional `dip`.
8. Hand back the MP4 path, list what was actually checked, and state any limits.

## Design defaults (change them if the user has a brand)

- Fonts are in `fonts/` (OFL): League Gothic for display caps, Space Mono Bold for labels.
- Colours are paper #F5F2EC, accent orange #FF7426 and ink #0B0B0C.
- Keep text between y ≈ 330 and 1450. Instagram's UI covers the top ~220 px and the bottom ~420 px.
- Transition vocabulary: flash cut on the first beat, whip pans between action shots, snap-zoom on hard cuts, zoom-through with glitch and double strobe into the hero location, slow-motion kick with an RGB hit, then a dip to black into the end card.

## Audio rules

- Never stack an impact SFX on top of a real impact sound. Let the real sound carry it.
- For loud, music-driven story reels, mute footage audio (`footageVol: 0`). For "sound-on" reels, keep it but gate it.
- Put SFX at their *transient*, not at the start of the file: the spec's sfx entry carries the transient offset (see `references/audio-notes.md`).

## Optional: generate missing shots with fal.ai

If a shot is missing (b-roll, an establishing still, an end-card background), and the repo's `fal` tool is available, you can generate it instead of asking for more footage:

    python3 <repo>/tools/fal.py run fal-ai/nano-banana-pro prompt="..." aspect_ratio=9:16 --out .shared/clips
    python3 <repo>/tools/fal.py run bytedance/seedance-2.0/image-to-video prompt="..." image_url=<still> aspect_ratio=9:16 generate_audio=false

It needs `FAL_KEY` in the environment. Run generated videos through `cut_clips.py` like any other source so they are SDR, 1080x1920 and have matched audio. This is optional: reel-studio works fully offline from real footage.

See `references/` for details and `examples/` for three complete specs: a story reel, an impact-sound reel and a text-card reel.
