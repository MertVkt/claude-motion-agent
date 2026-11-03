# 06 · Delivery and verification

```bash
SK=~/.claude/skills/app-ad-video/scripts
bash $SK/deliver_png.sh MYA083-Vertical Final/MYA083_EN_FamilyTreeReveal_15s_1080x1920.mp4 15
bash $SK/deliver_png.sh MYA083-Portrait Final/MYA083_EN_FamilyTreeReveal_15s_1080x1350.mp4 15
python3 $SK/verify_delivery.py --dur 15 --platform meta          # Final/*.mp4, exit code 0 = OK
```
Run from the job root. Write a creative-specific wrapper (`Work/tools/deliver<code>.sh`) with these two lines.
Naming follows `working-style.md` §3: duration rounded to whole seconds (19.6 s -> `20s`).

## Color: measured facts (Remotion 4, ffmpeg 7+)

| Path | Data | Tag | Result |
|---|---|---|---|
| Raw `npx remotion render` mp4 | BT.601, full range (`yuvj420p/pc/bt470bg`) | correctly tagged | shifts in some players; **never delivered** |
| `--color-space=bt709` | BT.601 matrix, limited range | bt709 | **wrong**: CTA 176,64,19 -> 183,72,15; neon green 18,255,40 -> 1,218,34 |
| Raw render re-tagged with `h264_metadata` | BT.601, full range | tv/bt709 | **wrong**: the data is not converted (a batch of past deliveries off by 7.6 to 11.6/255) |
| PNG sequence -> ffmpeg `scale=out_color_matrix=bt709:out_range=tv` + `setparams` | BT.709, limited | bt709 ×4, colr and VUI 1/1/1 | **correct** (CTA 173,63,17): `deliver_png.sh` |

- `working-style.md` §6 makes this path the standard. The `h264_metadata` remux is only for when the video
  stream is **already real BT.709** and only the audio changes; never on a raw render.
- **The colr trap:** `-c copy` + `h264_metadata` only changes the SPS VUI. The mp4 muxer writes `colr nclx` from
  the input's codecpar, so the two can disagree (AVFoundation reads `colr`). The output options
  `-color_primaries bt709 -color_trc bt709` given together with `-c copy` update `colr` too (measured).
- A whole-frame average **hides** matrix errors. The wrong path gave 2.08 over the whole frame at f440 (under the
  threshold) and 6.39 in the saturated CTA region. The right path gives 2.6 to 2.9 in the saturated region. Always
  measure the color path in a saturated region (CTA orange, neon, flag red), decoded **according to the file's
  tags**.

## What `deliver_png.sh` does

1. Remotion -> lossless PNG sequence. Stops if the frame count is not `duration × fps`.
2. Audio: the Remotion WAV (`remotion.audio.config.ts`, copied in if missing) or `--audio mix.wav`.
3. Two-pass loudnorm (−14 LUFS, TP −1.5, linear). `--no-loudnorm` when the mix is already around −14 (loudnorm
   was seen dropping into dynamic mode and overshooting by 1.1 dB). `--limit` adds a peak limiter at 192 kHz.
4. ffmpeg: real BT.709, libx264 High CRF 17, **single AAC** 320k/48k stereo, `apad -t <seconds>`, `+faststart`.
   It writes a `.part` first and moves the old delivery to `Work/previous/`.
5. Verification frames go to `Work/ref_<name>/f_<n>.png` (default: the middle frame and the 10th from the end
   = CTA). For other frames, `--ref 300,440`. The PNG sequence is deleted.

A 450-frame 9:16 master took 49 s.

## What `verify_delivery.py` measures

| Area | Requirement |
|---|---|
| Video | H.264 High, `yuv420p`, four tags `tv/bt709/bt709/bt709`, `colr` 1/1/1 full0, SPS VUI 1/1/1/0 |
| Time | frames = duration × fps; video duration = `--dur` (±1 ms); container duration (±2 ms) |
| Audio | AAC 48 kHz stereo; LUFS −14 ±0.5; true peak ≤ −1 dBTP; not silent |
| File | `moov` before `mdat` (faststart); `--platform` size limit (meta 250, tiktok 280, google 200 MB) |
| Color | per reference frame: whole frame < 2.5; saturated region (≥ 2000 pixels) ≤ 3.5 |

Also check by hand:
- `fx.py cuts Final/x.mp4`: are the cuts on the frames you planned?
- If there is VO, confirm it is in the file ([05](05-audio.md#6-mix---delivery-audio)).
- OCR the on-screen text; is it exact on the key frames?

## Revisions and redelivery

Work in the same folder. The new file is written next to the old one, which moves to `Work/previous/`
(`Work/old_color/` for a color fix). First measure how many files are affected with a **read-only audit** and
show the user. Bulk redelivery happens only after a yes (one 30-delivery audit found 13 wrong).

## A cut from delivered masters: cut in YUV, do not go through RGB

If the sources are already real BT.709 (AME deliveries tagged tv/bt709), the Remotion/PNG path is not needed; it
converts from RGB. In ffmpeg, `trim=start_frame/end_frame` + `concat` works in YUV with a single x264 encode:
`setparams=range=tv:color_primaries=bt709:color_trc=bt709:colorspace=bt709` + the `-color_*` flags (colr and VUI
get written). For `verify_delivery.py`'s color comparison, extract the reference frames **from the source with
the correct decoder**:
`select=eq(n\,N),scale=in_color_matrix=bt709:in_range=tv:flags=accurate_rnd+full_chroma_int,format=rgb24`.
Measured: saturated region 2.44 to 2.80, whole frame 0.74 to 2.16.
