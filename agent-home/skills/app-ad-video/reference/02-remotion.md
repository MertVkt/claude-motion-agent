# 02 · Frame-accurate rebuilds in Remotion

Remotion 4 + React 19 (versions pinned exactly; `npx remotion versions`). Reading code from other jobs is
allowed and encouraged; a new creative starts as a copy of the previous one's `src/`.

## Skeleton

```
src/theme.ts        C (colors), FONT, F (timeline, in frames), SFX (audio placements + volumes), content data
src/layout.ts       PLATE_SIZE / PLATE_FIT (per format), LAYOUTS (per-format block transforms),
                    face track accessors (facePoseAt)
src/faceTrack.ts    GENERATED (face_track.py), never edited by hand
src/components/     scene parts (ScanPanel, ResultRows, Packshot, Caption, BrandFonts…)
src/compositions/   <CODE>.tsx, lays the parts out on the timeline and places the audio
src/Root.tsx        one <Composition> per format, defaultProps: plate, plateOffset, plateRate, layoutKey
src/formats.ts      FORMATS, FPS, sec(), SAFE_AREA (sizes are never typed by hand)
```

**Write how each measured constant was measured, right above it.** Months later, in a variant, the
answer to "where does this 0.741 come from?" has to be there:

```ts
/** 4:5, from the 1080x1350 master: result block x0.741 (bar 493/666, row gap 167/226),
 *  top-center origin, vertical -15 px (rows -15.6, photo -14.3) -> -20.2 in design units */
portrait: { stageDy: -161, captionTop: 1116, captionScale: 0.925, resultScale: 0.741, resultDy: -20.2, ... },
```

## Stage + format model

Build the design in a 1080×1920 "stage" unit. Each format is a `LAYOUTS` key: a stage offset plus a
scale/offset per block (`transformOrigin: "540px 0px"`). Measurement shows 4:5 fits this model
(see [01](01-reference-breakdown.md#5-multiple-formats)).

```tsx
<div style={{ position: "absolute", left: 0, top: layout.stageDy, width: 1080, height: 1920 }}>
  <ScanStage ... />
</div>
<div style={{ position: "absolute", left: 0, top: 0, width: 1080, height: 1920,
  transformOrigin: "540px 0px", transform: `scale(${layout.resultScale}) translateY(${layout.resultDy}px)` }}>
  <ResultRows ... />
</div>
```

## Time

- The `F` table is in frames; `interpolate(frame, [F.a, F.b], [0, 1], clamp)`.
- For motion that fits no standard easing, keep the measured progress table and interpolate linearly:
  ```ts
  const qAt = (t: number) => { const x = t - F.motionFrom; if (x <= 0) return 0;
    if (x >= Q.length - 1) return 1; const i = Math.floor(x); return Q[i] + (Q[i + 1] - Q[i]) * (x - i); };
  ```
- **Inside `<Sequence from={X}>`, `useCurrentFrame()` already starts at 0.** Do not subtract `X` again or
  the animation freezes at the start (a set of UI screens once stayed static because of this).
- `<OffthreadVideo>` without a Sequence uses the composition frame. If it should start at a scene start,
  wrap it in `<Sequence from={s} layout="none">`.

## Talent shot: offset, speed, freeze

```tsx
const fr = Math.min(frame, plateFreeze);                       // the shot freezes once the overlay lands
const pose = facePoseAt(plateOffset + (fr / fps) * plateRate, fit);   // tracking = shot time
const video = (
  <OffthreadVideo src={plate} startFrom={Math.round(plateOffset * fps)} playbackRate={plateRate} muted
    style={{ position: "absolute", left: fit.ox, top: fit.oy, width: PLATE_SIZE.w * fit.s, height: PLATE_SIZE.h * fit.s }} />
);
return frame >= plateFreeze ? <Freeze frame={plateFreeze}>{video}</Freeze> : video;
```

`startFrom` is given in source-time frames; the speed applies after it. This mapping was verified at
0.757× to 0.99×. Tracking is 24 fps, the composition 30 fps; `facePoseAt` interpolates between two
tracking frames ([04](04-faces-and-shot-plan.md)). Do not move a crop with `translateY`, the `objectFit`
window does not move; use `objectPosition`.

## Visual techniques

**Painting an asset like AE "Fill" (CSS mask).** The asset's alpha gives the shape, the color comes from
the background. Color and opacity stay free to animate.
```tsx
const mask = `url(${staticFile("ui/nose_outline.png")})`;
<div style={{ position: "absolute", left, top, width, height, backgroundColor: col, opacity,
  WebkitMaskImage: mask, maskImage: mask, WebkitMaskSize: "100% 100%", maskSize: "100% 100%" }} />
```

**Motion blur (box like AE, 180° shutter).** N sub-samples at 1/N opacity each, `plus-lighter` in an
isolated group -> the average of the samples. A Gaussian did not match the measurement.
```tsx
const N = moving ? 16 : 1;
const layers = Array.from({ length: N }, (_, j) => {
  const t = N === 1 ? frame : frame - 0.25 + (0.5 * (j + 0.5)) / N;
  return <div key={j} style={{ position: "absolute", inset: 0, opacity: 1 / N,
    mixBlendMode: N === 1 ? undefined : "plus-lighter" }}>{renderAt(t)}</div>;
});
return <div style={{ position: "absolute", inset: 0, isolation: "isolate" }}>{layers}</div>;
```

**Whip transition (AE "Pan Short" = Motion Tile + Offset).** A table of measured per-frame offset and box
blur width `L`. The strip is laid out as `n = min(32, max(4, ceil(L/8)))` copies across `L`
(`plus-lighter`, 1/n); a horizontal Gaussian with σ = step/2 on top removes the stepping. Copies come
**mirrored** (Mirror Edges). The container is 3 screens wide because `filter: url(#…)` clips outside the
element's box. Put it in a `WhipStrip` component with a `WHIP` table. The whoosh sound matches with the
same speed-up (2.65×).

**Text.** Stroke behind the fill (`paint-order`), per-line tracking, the glyph-top vs line-box difference
as its own constant:
```tsx
<div style={{ fontFamily: FONT.display, fontWeight: 700, fontSize: 75, lineHeight: 1, whiteSpace: "nowrap",
  letterSpacing: font.tracking[i], color: "#fff", WebkitTextStroke: `${2 * font.outline}px #000`,
  paintOrder: "stroke fill", textShadow: "0 4px 14px rgba(0,0,0,0.45)" }}>{line}</div>
```
iOS UI text: `fontFamily: "system-ui, -apple-system, 'SF Pro Text', sans-serif"` (SF Pro).
Brand fonts load with `@font-face`; `delayRender` holds rendering until all of them are loaded. Without it
the first frames render in a fallback font. Keep this in a `BrandFonts.tsx` component.

**Combining + rotating masks.** Face envelope ∩ reveal disc:
```tsx
WebkitMaskImage: `${envelope}, ${disc}`, maskImage: `${envelope}, ${disc}`,
WebkitMaskComposite: "source-in", maskComposite: "intersect",
```
Rotation (`transform`), masks and `mixBlendMode` must be **on the same element**. Split across elements,
the blend or the mask drifted.

**Glass button:** `background: "rgba(112,84,64,0.5)", backdropFilter: "blur(14px)"`.
**Frame-sequence UI animation** (`touch.mov` -> PNG frames): use each frame as a mask and color it, map
25 -> 30 fps with AE-style rounding ([01](01-reference-breakdown.md#3-pixel-measurement-techniques-fxpy-library)).
**Side-by-side panels:** each panel is an `overflow: hidden` box; the content stays in full-frame
coordinates and the box is shifted with `top: -splitY`. Measurements map directly to frame pixels.

**Opening a UI screen full-screen and pulling it back into the phone.** If the screen's background is a
vertical linear gradient, fill the frame with the linear extension of the same gradient
(`y_ui = (y − T) / S`). The screen edge disappears and the screen "becomes the ad". Moving elements
(counter, cloud, text) are cut out of the screen and play on their own layer; in the base image those
regions are erased with the row color. Then S/X/T interpolate to the phone layout in one move, and the
frame and Dynamic Island appear. For scaled crops like a cloud no mask is needed: with a gradient slope of
0.009 levels/px, the edge difference at 12% scale-up is under 1 level.

**Feed hook.** Use unbranded, UI-free cards (our own AI shots). Three flicks, vertical-only SVG blur
(`feGaussianBlur stdDeviation="0 σ"`, σ = 0.22 × speed). At the freeze, `<Freeze>` + a 26 px damped
bounce-back. Then the feed blurs and darkens.

**Hook variant.** Change only the hook without touching body frames:
- The hook must end in the state where the body starts: same background color, same object in the same
  box. The handover happens on the body's existing transition (a light burst, in the case measured).
- Split the hook component into background and foreground: background under the body layers, object on
  top.
- Cut the bridge sentence from the existing VO. Only the new hook line is newly generated.
- In a chaos -> calm hook, the first frame must be full: show the first elements already in place by
  starting their spring animation early. Generate the audio events from the same formula as the visual
  events (one formula shared by the TSX and the audio script).

**Camera zoom + zoom motion blur.**
- Apply the camera to the whole scene: focus point F, target position P, scale Z with
  `translate(P − F·Z) scale(Z)`, transform-origin 0 0. Interpolate scale in log space, otherwise the zoom
  looks slow at the start and abrupt at the end.
- For a fast zoom, sub-sample within the frame: 180° shutter, 1/N opacity with `plus-lighter`.
  - 8 sub-samples leave visible steps (a line of text appeared stacked).
  - 16 sub-samples + speed-dependent Gaussian (`blur = min(10, 55·|ln(Z₊/Z₋)|)` px) leave no steps.
- For a clean full-screen hook (white background + close-up), use a separate cover: it carries the
  camera-bound crop and lines up exactly with the scene below.
  - Fade the cover in 4 to 5 frames in the fastest middle part of the zoom.
  - Fade it at the start of the zoom and you get huge, readable in-between frames (status bar, title).
- Behind a system sheet there is usually a flat darkening; measure it (× 0.400 in the case measured).
  Build the sheet closing as "screen below + fading black cover + shrinking card crop". Fading a
  screenshot that includes the sheet shows the card twice.

**Quiz layer.**
- **Parts:** answer tiles (A/B/C), a timer badge, a flash. All appear with the series' overshoot curve
  (a 13-frame `popAt`).
- **Timer badge:** an SVG ring that empties via `strokeDashoffset`. The digit overshoots 1.4 -> 1 every
  second.
- **State changes are not done with opacity** (the shot shows through like a ghost). The correct tile
  turns green with `mixHex` and gets a tick; its scale goes 1 -> 1.1 -> 0.97 -> 1. A wrong tile gets
  `grayscale()` + a white veil **inside** the tile, which stays opaque. The hook text switches instantly
  with a small overshoot.
- **Design choice:** let all three answers appear in the result, with the right one getting the biggest
  share. The result screen closes on "everyone was a little right".

**Karaoke captions from STT.** A small `Work/tools/build_captions.py` merges the word times from STT on
the VO lines with the line starts in `theme.ts VO_AT` and writes `src/captions.ts`. `Captions.tsx`:
- Groups of 2 to 3 words; the spoken word turns to the accent color with a small overshoot.
- A group appears 3 frames before its first word and stays until the next group, or 12 frames after its
  last word.
- The first group shows from f0, so the cover frame has text.
- It sits outside the whip, on the top layer. If line starts change, rerun the script.

## Calibration composition

To fit a parameter like font, tracking, stroke or scale by measurement, build a temporary composition.
**Each frame is one variant**; grab them all at once:

```tsx
const V = [{ size: 74, tr: -1 }, { size: 75, tr: -0.7 }, { size: 75, tr: 0 } /* ... */];
export const Cal: React.FC = () => { const f = useCurrentFrame(); const v = V[f];
  return <AbsoluteFill style={{ background: "#000" }}><Caption font={{ ...CAPTION_FONT, ...v }} forceVisible /></AbsoluteFill>; };
// Root.tsx: <Composition id="Cal" component={Cal} durationInFrames={V.length} fps={30} width={1080} height={1920} />
```
```bash
node $SK/stills.mjs Cal Work/cal $(python3 -c "print(','.join(map(str,range(23))))")
```
Run each PNG through the same `fx.py` measurement as the reference and write the best variant into the
constants. Remove the composition from `Root.tsx` before delivery.

## Audio layer

```tsx
<Audio src={staticFile("audio/music.wav")} volume={SFX.music} />
<Sequence from={SFX.tapAt} name="SFX tap"><Audio src={staticFile("audio/sfx_tap.mp3")} volume={SFX.tap} /></Sequence>
```
Volumes come from `audio_match.py`'s "N times the music" ratios: `sfx = music × ratio`. None may exceed
1; if one does, lower the music and keep the ratios (music 0.70 -> 0.6585 in one case). Do not leave a
speed-changed SFX to Remotion; render it beforehand with its pitch, like AE:
`ffmpeg -i in.wav -af "asetrate=<source_SR>*2.65,aresample=48000" public/audio/sfx_x265.wav`.
If you built VO and music in ffmpeg, keep the composition silent and pass the mix with
`deliver_png.sh --audio`.

## Rendering

| Purpose | Command |
|---|---|
| Preview / timeline | `npm run studio` |
| Check a few frames | `node $SK/stills.mjs <id> Work/st 0,45,150,300` (bundles once) |
| Intermediate render (not a delivery) | `npx remotion render <id> Work/preview.mp4`, raw output is `yuvj420p`, **never delivered** |
| Delivery | `bash $SK/deliver_png.sh <id> Final/<name>.mp4 <seconds>` ([06](06-delivery.md)) |
| Type check | `npx tsc --noEmit` |

The "npm notice" lines at the top of `npx remotion render` are harmless.

## Match cut from a number in the UI to typography

A deep zoom into a number on a tracked phone screen, then in the same place and size, white typography on
a dark background. The dark number on a white card suddenly becomes a white number in the dark.

- **Scale:** measure the screen's width in the shot from the tracking corners (≈ 175 px TL–TR in the
  case measured). Compute the zoom needed to reach the width of the number in the typography.
  - "5h 45m" was 28% of the UI width; at 16× it was ~780 px.
  - 8× was not enough: the number stayed 390 px and the match did not read.
- **Focus:** give the zoom camera `smax = s` (k = 1: the focus is exactly on target every frame). Move the
  focus first (done at t 0.6), accelerate the zoom after.
  - With both on the same curve, the number did not reach the target even on the last frame.
- **Jitter:** turn off focus smoothing for deep zooms (`smoothFocus(..., r = 1)`). A ±6 frame average at
  16× amplified the lag and shifted the number.
- **Completion:** the target must be reached on the hook's last frame (interpolate over
  `[deep0, deep1 − 1]`). The cut comes on the next frame.
- **Stay within valid tracking frames:** near the end of a shot the tracker may have dropped.
  - Identical corners on consecutive frames in the track file = a frozen frame.
  - In one shot the corners froze after frame 114. When the deep zoom landed there, the camera zoomed into
    a hood instead of the phone.
  - Pull the zoom range back into valid frames.
- **Same edit, different talent:** generalize the composition once; everything talent-specific lives in
  `timeline.ts` (`VARIANT` crop / target / selfie zoom, HOOK, EDIT, screens, focus points).
  - Screen width varies from talent to talent (123 to 216 px); `zdeep = 780 / (0.28 × W)`.

## A dimming screen and its reflection

- A night shot taken from the phone's point of view (the face looks at the screen), mirrored and darkened,
  becomes the reflection in the phone's black glass. No extra generation needed.
  - Inside `PhoneFrame`: black background + mirrored shot (`scaleX(-1)`), filter
    `brightness 0.36 · contrast 1.18 · saturate 0.18 · blur 2.5`.
  - The shot's top edge leaves a line in the glass. Fade it into black with
    `maskImage: linear-gradient(transparent 0%, black 22%)`.
  - What sells the glass: a sliding glare band (30 to 57% diagonal gradient), a gray frame edge, an empty
    battery icon on **the phone's own screen**.
  - The light going out: a last flash on the shot (×1.25) and ×0.08 over 3 frames; the glass appears in
    6 frames, the reflection over 1 second.
- Do not show a low-battery warning as a system notification on the viewer's screen; Meta's rules on fake
  notifications and functionality forbid it. Show it inside the framed phone.

## Flipping the phone over in code

- Image-to-video models often fail at this action ([03](03-ai-generation.md)). In the mockup:
  `perspective` (2400) + `rotateY(0 -> 180)`, ease-in-out cubic, 14 frames.
  - It lifts and lowers (`−46·sin(πu) + 34·e`), tilts −7°, shrinks 7%. On landing, a 2-frame squash and a
    "thock".
- Instead of `backface-visibility`, pick the face by angle: if `deg < 90` the front with `rotateY(deg)`,
  otherwise the back with `rotateY(deg − 180)`. The back is drawn in its own orientation, camera island top
  left. More reliable in nested transforms.
- Darken the screen while turning (`0.45·deg/90`); it reads as a light angle.
- The back: graphite gradient, inner edge, three lenses + flash, a diagonal glare band. No logo.
- Product tie-in: right before the flip, the app's own screen that tells the user to flip the phone is on
  screen.
