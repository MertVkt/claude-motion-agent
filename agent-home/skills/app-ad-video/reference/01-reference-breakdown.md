# 01 · Breaking down and measuring the reference

Goal: turn every element of the reference (shot, UI, text, motion, color, audio) into **numbers** and
write them into a table in `PRODUCTION.md`: `Element | Value | How it was measured`. The composition is
built from that table.

```bash
SK=~/.claude/skills/app-ad-video/scripts
```

## 1. First look (free, minutes)

```bash
fal analyze Ref.Videos/ref.mp4                     # written breakdown -> Brief/reference-analysis.md (paid, cheap)
python3 $SK/fx.py probe ref.mp4                    # size, fps, frames, color tags, audio, LUFS
python3 $SK/fx.py cuts  ref.mp4                    # hard cuts: small gray frame diff > 6x the mean
python3 $SK/fx.py sheet ref.mp4 Work/sheet --fps 2 # 5x2 contact sheets -> look at them with Read
```

- `fal analyze` gives a shot list, on-screen text, VO and a rebuild recipe. Treat it as a draft: verify
  every number it gives with the measurements below.
- Quick alternative for cuts: `ffmpeg -i ref.mp4 -vf "select='gt(scene,0.28)',showinfo" -f null - 2>&1 | grep -o "pts_time:[0-9.]*"`.
- **A crossfade does not show up as a cut.** Look at a region's per-frame mean:
  `fx.py curve ref.mp4 0,953,1080,967 --from 140 --to 175` showed a linear crossfade over 14 frames.
- **Whip / blurred transitions** give high difference over 2 to 4 frames; `cuts` lists them as
  "soft transition?".
- A contact sheet at 1 fps misses fast cuts; if rhythm matters use `--fps 6` or pull the range frame by
  frame with `fx.py grab`.

## 2. Speech and on-screen text

- **Is there speech?** Do not look at RMS, ask STT: `python3 $SK/speech.py stt ref.mp4 Work/stt.json`.
  If it only returns a tag like `[upbeat music]`, there is no speech. The message is carried by on-screen
  text + music; do not generate VO. If there is speech, the word times give you the shot boundaries.
- **OCR:** grab the key frames and read them. On macOS use the `ocr` helper (boxes are normalized with a
  bottom-left origin; pixel top = `(1 - y - h) * H`). Elsewhere, ask a vision model about the frames.
  ```bash
  for f in 15 90 200; do python3 $SK/fx.py grab ref.mp4 $f Work/ocr/f$f.png; done
  ocr Work/ocr                                              # macOS helper
  fal ask "Transcribe all on-screen text exactly" --image Work/ocr/f15.png
  ```
  Cyrillic homoglyphs and c/o can get mixed up; on a critical misread, crop the frame and check by eye.
- Work out the caption grammar: words per group, whether the highlight is fixed or follows the spoken word
  (karaoke: the highlight sits on the spoken word), whether position changes per shot.

## 3. Pixel measurement techniques (`fx.py` library)

```python
import os, sys; sys.path.insert(0, os.path.expanduser("~/.claude/skills/app-ad-video/scripts"))
from fx import *
fr, w, h = frames(REF, 150, 160, x=0, y=900, w=1080, h=400)     # cropped frames (raw RGB)
box = bbox(fr[0], w, lambda p: p[0] > 200 and p[2] < 80, 0, w, 0, h)   # box of a color condition
rows = bands(fr[0], w, lambda p: max(p) > 40, 0, w, 0, h, gap=3)       # text lines, bars
```

| What | How |
|---|---|
| Position, size | `bbox` with a color threshold. For a circle, take extreme points -> center + diameter. For text, glyph extremes (width, cap height, glyph top) |
| Rows, bars, card lists | `bands`: line spacing, height, left edges (one result list measured rows 227/218/217 px apart) |
| Scrolling, sliding | Row/column profile (`row_profile`) + `match_1d` near the previous frame. If scale is unknown, sweep candidate scales and keep the lowest error. Sub-pixel with `parabola` (a scrolling family tree measured scale 1.555, motion `41.97 + 2.952·f`, error 8 to 16) |
| Timing | Region curve (`fx.py curve`): start/end frame. For easing, normalize progress to 0 to 1 and compare with linear / `Easing.inOut(Easing.sin)`. If neither fits, keep the measured table and interpolate (a carousel needed a 62-value `CAROUSEL_Q`) |
| Scale animation | Per-frame size / base size -> keyframe table (a label pill overshoots to 1.185, dips to 0.964, settles at f102) |
| Opacity, color | On a known background `observed = α·C + (1−α)·bg`. If the ratio is equal in all three channels the color is white (a nose line had α 0.465). AE "Fill" colors come out of a regression on the pixels (#5FFD9E) |
| Motion blur | Fit the edge profile to box and Gaussian models. AE motion blur is a **box**: 180° shutter centered on the frame time, so `f−0.25 … f+0.25` |
| Complex transition | Generate candidate models (plain / mirrored tiling, different blurs) and compare error against the measured frames |
| Embedded asset fps | A 25 fps asset in a 30 fps comp is rounded like AE, every 5th frame repeats: `src = floor((f−from)·25/30 + 1e-6)` |
| Audio events | [05-audio](05-audio.md): align the music, look for SFX in the residual |

Zoom in to look: `fx.py grab ref.mp4 24 Work/z.png --crop 380,300,320,320 --scale 3` -> Read. Rounded
corners, stroke width, shadows and glows are measured on the magnified frame.

### Overlaid HUD: reveal, geometry, transparency

If the face and the shot are still in the reference, the difference between the last and the first frame
is the layer itself.

- **Are the parts animated separately, or is it one wipe?**
  1. For each group (left, bottom, face, right), find the rightmost column of cyan pixels that were not in
     the first frame, frame by frame.
  2. If the fronts lie on one line, the reveal is a single wipe.
  - Measured once: four groups at 3.28 to 3.34 px/frame (at 720 wide), x = 22 + 3.31 (f − 10), from f3 to
    f221. No per-component animation was needed: build the final state and open it with
    `clipPath: inset(0 ${W - front}px 0 0)`.
- **Edges:** in the difference image a cyan mask's projection mixes with text and thin edges. Read
  brightness peaks along text-free vertical and horizontal lines (for example between a flag and the
  text). The panel's tab, bevel and edge height show up as separate peaks.
- **Semi-transparent fill:** inside a panel, in a text-free area, fit `out = a·bg + b` per channel
  (bg = first frame). Alpha = 1 − a and color = b/alpha. Measured once: alpha 0.36 to 0.54, color
  ~(42,115,135). Do the same fit outside the HUD; alpha should come out ~0 (no global darkening).
- **Perspective:** if the outer edges of the side panels slope downward, the panels are tilted toward the
  face with `rotateY`, origin level with the top panels. Measure the slope from both ends of the edge peaks.

## 4. Font matching

1. Candidates: the brand fonts (`(Footage)` / `public/fonts`), **SF Pro** (`system-ui`) for iOS UI,
   Google fonts that fit the reference's era.
2. Measure glyph group widths in the reference.
3. In a **calibration composition** draw the same text with candidate font / weight / size
   ([02-remotion](02-remotion.md#calibration-composition)), grab with `stills.mjs`, measure the same way.
4. Once widths match, set per-line tracking (`letterSpacing`). AE allows per-line tracking: one reference
   used −0.7 and +1.5 on two lines.

Examples: a search bar matched SF Pro 52 px (mean error 0.29 px over 21 groups) while another candidate
was 8 to 15% too wide. Without the original font, pick the closest and narrow it with `scaleX` (Poppins
ExtraBold at `scaleX 0.95`, 3% off).

Stroke: measure how many px extend past the white, draw with `WebkitTextStroke: 2×stroke` and
`paint-order: stroke fill` (AE "Fill Over Stroke").

## 5. Multiple formats

Measure every master **separately**; 4:5 is often not a crop of 9:16. A common model: the stage moves as
a whole, blocks scale separately. One 4:5 master measured: stage −161 px, captions ×0.925, result block
×0.741 (−20.2), packshot ×0.757 (−69). In Remotion each format is a `LAYOUTS` key.

Face framing target (for shot placement): `python3 $SK/face_track.py ref.mp4 --stats 0 149` (`--mesh` if
there is a mesh overlay). Run it for each format. One 9:16 target: (554.2, 1378.3), d 280.9.

## 6. Using After Effects projects

- Never touch the `.aep`. Sources: `(Footage)` assets (flags, fonts, audio, images, UI animations like
  `touch.mov`), `*Report.txt` (layer/effect dump; names like "Motion Tile" or "Pan Short" tell you what to
  model) and the delivered masters in the export folder (the measurement source).
- Copy the asset and check with `cmp` whether it is identical to one used elsewhere; if so, the
  measurements carry over too.
- The reference ad = the delivered master. Its audio is measured as well; the source music and SFX are
  in `(Footage)`.

### If you only have a 16:9 packshot

Cropping the center and scaling up softens the text. In one case the block was 330×510 px and the icon
needed 1.75× to reach ~280 px in vertical. The right way is to rebuild it in Remotion
(`src/components/Packshot.tsx`):
1. **Background:** sweep scale, position and time with NCC to align the plate (in that case: no scale,
   +1.65 s). Then pick the blend mode: find the per-row base color with a grid search and compare 6 modes
   × 11 opacities (Soft Light at 60%, rmse 1.9 levels). A dust plate on black leaks into the fit; separate
   it by its black level.
2. **Element boxes** from a white pixel threshold. Fit font and size to the text box with PIL.
3. **Timing:** read how the letter columns fill frame by frame. The model that fit was "letters appear
   instantly, layer opacity rises linearly". CTA pop = measured width / final width.
4. **Intro animation:** a difference moment gives a rough estimate. The exact value comes from a
   calibration render: each frame is a (packshot frame, parameter) pair, region RMSE + parabola peak
   (icon scale f16 1.36 … f26 1.00).
5. **Shadow:** region RMSE drowns in letter-edge alignment. Look at a ring profile around the letter mask
   instead (darkening at the bottom-right and top-left offsets). Of 25 variants, 3px 3px 4px 50% won.
6. Measure the original mp4's audio track too: in that case it was silent (−70 LUFS).

## 7. Competitor references (another brand's ad)

- Replace every mention of the competitor's name with your app's (VO included; once a competitor name in
  the audio slipped through because no transcript was taken). **Tie the claim to a real feature:** never
  promise something that is not in the App Store description ("try any hairstyle on your own photo"
  instead of "face analysis and recommendations").
- Palette, fonts and packshot come from our brand; never the competitor's colors.
- Shorten a long reference: keep what makes it watchable (the style tour, the rhythm), cut the number of
  shots. One 22-shot, 66 s reference became 10 shots and 28.6 s at well under half the cost.
- Licensing: do not copy a living artist's signature style one to one (use public-domain styles like
  ukiyo-e or art nouveau instead); flag the risk with well-known music.

## 8. Output

A measurement table in `PRODUCTION.md`: panel bounds, asset scale/position, text (font, size, color,
tracking), animation keyframes, transitions, audio (music, gain, SFX frame and dB). Then scope and cost
are discussed, then audio (if there is VO), then composition.
