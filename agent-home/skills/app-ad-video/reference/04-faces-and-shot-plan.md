# 04 · Face tracking, the shot window, placement, face-bound layers

A new talent means running this chain again. The rest of the code stays as it is.

Face tracking uses the `facetrack` helper (macOS, Apple Vision; build it from `scripts/macos/facetrack.swift`).

```bash
SK=~/.claude/skills/app-ad-video/scripts
python3 $SK/plate_windows.py Shots/talent_plate.mp4 --need 5.07            # 1. clean window + speed suggestion
cp Shots/talent_plate.mp4 public/plate/talent.mp4
python3 $SK/face_track.py public/plate/talent.mp4 --out src/faceTrack.ts   # 2. tracking (--mesh if there is a mesh)
python3 $SK/face_track.py <reference.mp4> --stats 0 149                    # 3. target, once per reference
python3 $SK/fit_plate.py --track src/faceTrack.ts --offset 6.2 --rate 0.757 --frames 153 \
    --target 554.2,1378.3,280.9 --canvas 1080x1920 --panel 0,953,1080,1920 # 4. placement, once per format
python3 $SK/portrait_crop.py public/plate/talent.mp4 auto --card 923x779 --eye 0.533,0.502,0.175   # 5. portrait
npx tsc --noEmit && node $SK/stills.mjs <id> Work/st 0,40,100,150,152      # 6. look
```

## 1. Clean window, slow-down, freeze

`plate_windows.py` measures every frame of the shot with face landmarks:

- **Talking:** the outer lip height/width ratio is 0.07 above the shot's lowest 20% value.
- **Looking away:** eye openness below 0.62 of the median for at least 8 frames. Anything shorter is a blink,
  which is fine.
- **Turned** (optional): the horizontal offset between the nose and the eye midpoint passes a given fraction
  of the eye distance.

For the time the composition shows the face uncovered (`--need`), it suggests the best window and, if the
window is too short, a speed: `speed = clean length / needed length`.

- Slowing down to 0.757× went unnoticed (a vision model QC said "no slow motion, freeze or artificiality").
  Below 0.75, consider another shot or a freeze.
- **Freeze:** the moment the face goes under an overlay (a result layer lands, the face darkens), the shot
  stops with `<Freeze>`. The needed length shrinks to the moment the overlay covers the face.
- **Freeze behind a shutter flash:** if no shot has a long enough clean window, make the freeze part of the
  edit. The countdown becomes a selfie timer, at 0 a white flash fires (1 -> 0, 6 frames), and the scan runs on
  "the photo just taken".
  - Since the flash hides the cut, the frozen frame can be **any good frame of the shot**; pick one with open
    eyes and a smile from the contact sheet (`<Freeze frame={source_frame}>`, pose fixed via `facePoseAt`).
  - In one series this cut the needed length from 7.07 s to 3.9 s, when the longest clean range across eight
    shots was 5.04 s. QC: "no sense of a stall, it is part of the design".
  - Use the frame the result portrait is cut from (the one `portrait_crop.py auto` picks). "The photo taken"
    then shows up on the result card.
- **Ping-pong:** if the calm part is short (in a "neutral -> surprise" shot only 0 to 1.9 s), play it forward
  + backward:
  - Do not repeat the turning frame: `trim=start_frame=0:end_frame=N` forward, `end_frame=N-1,reverse`
    backward, `concat`.
  - Put the turn on a calm moment (frames 43 to 46 were nearly identical, so it is invisible).
  - Re-extract tracking from the edited clip. Example: 89 frames, 3.71 s, 0.95×.
- **The first frame is the thumbnail.** Do not start on the edge of the clean window. Once an offset landed on
  a frame boundary at 5.567 and the first frame had closed eyes. Measuring eye openness moved it to 5.8
  (0.26 -> 0.33).
- The thresholds are rough. Look at the flagged frames: a smile also increases mouth opening. Once a 0 to 4.2 s
  window (0.83×) passed QC even though 1.4 to 2.1 s was flagged. Frames decide.
- Write the chosen `plateOffset` / `plateRate` into `Root.tsx`; the tracking mapping is `offset + t·rate`.

- **If the shot is shorter than the scene, hold the last frame:** a reaction shot ended at 10.0 s but the scene
  lasted until the packshot crossfade. In `ReactionScene`, once the local frame passes
  `(REACT_END_SEC − REACT_FROM_SEC) × fps / rate`, `<Freeze frame={last}>`. If the freeze falls inside the
  crossfade (15 frames) it is invisible. Do not let OffthreadVideo request frames past the end of the shot.
- **Hook + reaction from a single shot:** in a "calm -> shock" shot, the calm part goes to the hook
  (0 to 5.46, 0.9×) and the shock part to the reaction (6.85 to 10.0); the ranges do not overlap, and talent
  and place already match. $0.

- **Yellow teeth:** image-to-video models often make teeth noticeably yellow in smiling faces, which stands
  out with fair-skinned talent. `teeth_whiten.py`: Vision `innerLips` (the polygon is enlarged ×1.15/×1.08
  because it is narrow at the corners), tooth weight Y (100 -> 150) × yellowness (Cb < 128) × not red
  (Cr 148 -> 164). Cb/Cr deviation is reduced by 45%, Y +3. It works in YUV: the shots carry no color tags, so
  an RGB round trip would require guessing the matrix. Defaults aim for "not too white"; under warm lamp light
  teeth naturally stay ivory.

## 2. Tracking (`face_track.py`)

- macOS Vision `VNDetectFaceLandmarksRequest`: face box, roll/yaw and 51 points (jaw 17, eyes 6+6, outer lips
  14, nose 8). Detection runs at 536 px width with **the aspect ratio kept**. An older version squeezed every
  video to 536×966: 1.44× vertical error on a 4:5 reference, 1.4% at 1080×1920.
- Output (`faceTrack.ts`): per frame `x, y` (eye center), `d` (eye distance), `r` (eye line slope),
  `nx, ny` (nose centroid). Proportional to the shot size. Also `PLATE_FPS` and `PLATE_SIZE`. Gaps are filled
  from the neighbor frame and smoothed over a 5-frame window.
- `--mesh mesh_landmarks.json`: if the overlay is a face mesh, eyes/scale/roll come from a **Procrustes**
  (similarity) fit of the 51 points to the mesh's own landmarks, so the jaw and ear line fit too (fit error
  18.8 -> 15.6 px, the mesh grows 5%). For a new mesh image, extract its landmarks from a reference frame where
  the mesh sits on a face: transform the face points into the mesh image space.
- `--stats F0 F1`: the target from a reference (video pixels). Measure it once and write it to `layout.ts` as
  `FIT_TARGET`. When in doubt, repeat at full resolution with `--det-w 1080`.

## 3. Placement (`fit_plate.py`)

```
s = d_target / d_window      ox = tx − ex·s      oy = ty − ey·s        (stage = plate_px·s + (ox, oy))
```
The window average lands on the target. If the plate does not fully cover the panel it is shifted and the
shift is reported. A big shift means the face is that far from the target: generate a closer framing or
increase the scale. Run it once per format. In one case the 4:5 face sat ~554 px higher with the same shot and
scale; that was still found by measurement. `PLATE_FIT` per format:

```ts
export const PLATE_FIT = {
  vertical: { s: 1.3920, ox: -258.7, oy: 256.4 },
  portrait: { s: 1.3930, ox: -259.0, oy: -298.3 },
} as const;
```

## 4. TS accessor

```ts
import { FACE_TRACK, PLATE_FPS, PLATE_SIZE } from "./faceTrack";
export type Fit = { s: number; ox: number; oy: number };
export type FacePose = { eyeX: number; eyeY: number; eyeDist: number; roll: number; noseX: number; noseY: number };

/** face pose at shot time (s), in stage pixels; linear interpolation between 24 fps tracking frames */
export const facePoseAt = (tPlate: number, fit: Fit): FacePose => {
  const f = Math.max(0, tPlate * PLATE_FPS);
  const i0 = Math.min(FACE_TRACK.length - 1, Math.floor(f)), i1 = Math.min(FACE_TRACK.length - 1, i0 + 1);
  const k = f - i0, a = FACE_TRACK[i0], b = FACE_TRACK[i1], m = (u: number, v: number) => u + (v - u) * k;
  const W = PLATE_SIZE.w * fit.s, H = PLATE_SIZE.h * fit.s;
  return { eyeX: m(a.x, b.x) * W + fit.ox, eyeY: m(a.y, b.y) * H + fit.oy, eyeDist: m(a.d, b.d) * W,
           roll: m(a.r, b.r), noseX: m(a.nx, b.nx) * W + fit.ox, noseY: m(a.ny, b.ny) * H + fit.oy };
};
```
Older `faceTrack.ts` files may lack `nx/ny` and `PLATE_SIZE`; in that case the nose lives in a separate
`noseTrack.ts` and the size in `layout.ts` `PLATE`.

## 5. Face-bound layers, all in units of `d` (eye distance)

- **Scan oval:** center = eye center + `dy·d`, radii `rx·d`, `ry·d`, rotated with the eye line slope. Dashed
  line (`strokeDasharray="46 34"`), flowing with `strokeDashoffset = −t·60`.
- **Face mesh:** scale `eyeDist / MESH.eyeDist × overscale`, position from the mesh's eye point, rotated with
  roll. Style: `mixBlendMode: "screen"`, a sepia tone (`sepia(1) saturate(2.2) hue-rotate(-28deg)
  brightness(1.25)`) and a radial face-envelope mask. **Reveal:** a hard-edged disc from the nose bridge.
  Radius in `d`, from the hit: +3 frames 0.15, +6 0.35, +8 0.54, +9 0.8, +10 1.3, +11 2.2 (full face). Stays
  full until +19, fades out by opacity until +29. While opening, opacity 0.95 and a light glow
  (`drop-shadow(0 0 3px …)`). Mask combining and the "same element" rule:
  [02](02-remotion.md#visual-techniques).
- **Tracked wireframe:** if the talent moves the lips and tilts the head, use a wireframe drawn every frame
  from the landmark points instead of a fixed mesh image.
  1. Convert the shot to 30 fps with frame repeats (`-vf fps=30`). That is the frame pattern Remotion will
     show; composition frames map one to one to shot frames, no in-betweens or interpolation needed.
  2. Run `facetrack` at full resolution. It also writes `leftEyebrow`, `rightEyebrow`, `noseCrest`,
     `medianLine`, `leftPupil`, `rightPupil`.
  3. Smooth the points with [1,2,3,2,1] weights.
  - **Vision's 65-point order:**
    - brow: 0 to 2 top edge, 3 to 5 bottom edge -> the line is the midpoint of the two edges;
    - eye: 0 outer, 3 inner corner;
    - nose: 1/7 sides, 2/6 wings;
    - outer lips: 13 / 7 corners, 3 top middle, 10 bottom middle;
    - contour: 0 -> 8 chin -> 16.
  - Put the builder in `Work/tools/build_track.py` and draw it in `src/components/FaceMesh.tsx`. Vision QC said
    "no drift or jitter".
- **Face brackets are built from the face's own bounds, not eye ratios.** Measure the reference's bracket box
  relative to its own landmark points. One measured set: top = brow top − 0.52d, bottom = chin − 0.062d,
  contour ± 0.06 to 0.07d.
  - A fixed ratio to the eye center does not hold, because face length varies from person to person. In one
    case the chin-to-eye distance was 1.93d on the talent and 1.55d on the reference, and the brackets ended
    at mouth level.
  - For the same reason the chin can overlap the panel below: move the shot up or the panel down.
- **Placement is set by three conditions together:** the reference face size, coverage and chin clearance.
  If the reference scale does not cover the frame (the face is large in the shot) or conflicts with chin
  clearance (the face sits low in the shot), go to the smallest scale that satisfies both. The face grows a
  little, but no gap is left and the chin does not overlap the panel.
  - Put the solver in `Work/tools/fit_hud.py`.
  - Measured: reference scale 0.945 did not cover, the chin at 67% of the shot -> 1.1055, face 17% larger.
    Another: 0.939 -> 1.0405.
- **In 4:5 the shot and the HUD can be separate stages.** Once the shot + HUD shrank together ×0.92 in one
  stage; shots with large faces do not cover the frame at that scale and an edge was left open.
  - The shot stage (shot + mesh + brackets) takes the smallest covering scale; the HUD stage (panels, title)
    stays ×0.92.
  - The mesh is drawn in the shot stage and stays fitted to the shot.
  - The wipe front must sit at the same screen x in both layers:
    `front_shot = (hud.tx + hud.k·front − shot.tx) / shot.k`.
- **Nose line:** tie it to the nose centroid, apply the offset on the image axis (`strokeDy·d`), size `k·d`.
  **Do not rotate it with the eye line slope.** An eye line slope of ~0.2 rad is not the face midline:
  rotating the offset by that angle moved the line ~20 px left of the nose, and a `roll − ref` rotation once
  tilted it 13°.
- **Result portrait:** `portrait_crop.py` picks the frame with the most open eyes, facing forward, mouth
  closed. It crops with the reference's eye position and scale. If the crop does not fit inside the shot, the
  eye position is kept and the crop shrinks. Fitting by shifting once moved the eye from 0.533 to 0.451.

## 6. Check

In stills, check that the overlays sit on the face: the oval wraps the face, the mesh lines up with the eyes
and chin, the nose line sits on the nose. Take check frames from the start, middle and freeze frame of the
window. Make a side-by-side collage with the reference. Tracking errors are most often a mismatch between the
shot offset and the tracking time: `startFrom` and `offset + t·rate` must agree.
