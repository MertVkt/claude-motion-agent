# Tesseract gotchas (tsrct 0.3.1)

Facts found by testing that the schema and docs don't state. `scripts/build.py` already handles all of these.

## Video and Audio layer timing (the big one)
- `playback.mapping.input` is on the **parent (composition) clock**: `input.start` must equal `playback.inputRange.start`.
- `playback.mapping.output` is on the **source clock**: `output.start` must equal `sourceRange.start`.
- If either is left at 0, the clip renders **blank** until the playhead reaches that time. It doesn't error, it just shows nothing.
- Speed is the ratio `output.duration / input.duration` (slow motion = output shorter than input).
- `sourceIntrinsicDuration` must be the `durationMs` that `project import-video` returns, not the ffprobe value.
- Source files whose audio and video stream lengths differ can render blank. `cut_clips.py` matches them exactly.
- A shot's first frame can render blank on a hard cut, so overlap every shot with the next by 2 frames (`build.py` adds a 0.067s tail).

## Units
- Keyframes for `opacity`, `scaleX`/`scaleY` and `volume` are percentages (100 = 1x), except `volume`, which is linear like the layer volume. The static `setFxLayerOpacity` action uses 0–1. Scale keyframe `1.0` means 1%, i.e. a tiny dot.
- `positionX`/`positionY` are in canvas pixels; with anchor [540,960], the centre is [540,960].
- Text `tracking` is in 1/1000 em. Point text's origin is its baseline start.
- `radialBlur`: center is UV 0–1 (0.5,0.5 = middle) and amount ~0–50. At ~40 it's a strong zoom-through.
- `chromaticAberration.amount`: 1.5 is noticeable, 4 is strong, 10 is psychedelic.
- `directionalBlur`: direction 90 = horizontal, blurLength in px (~230 for a whip).

## Effects that look available but aren't
- `primaryGrade` is reader-only and rejected on write. Use `brightnessContrast` (AE units) and `hueSaturation`.
- `gradientOverlay` paints over the layer's alpha. On an opaque rect the result stays opaque. For a fading scrim, stack thin translucent rects with exact integer edges; overlapping edges show as lines.
- An Adjustment layer affects everything below it. Put it above the footage and below all graphics.

## Workflow
- Effect parameters animate via `setFxLayerEffectParamAnimator` with `animator.type = keyframes`, and `dependencies: []` is required.
- `setFxPropertyKeyframes` upserts by key id. Merge all keys for one property into a single sorted track before sending, or overlapping events will fight.
- `project apply` is atomic: one bad action rejects the whole batch.
- `filmstrip --fx-solo` can't be combined with `--timestamps-ms`.
- Export is fast: about 10s for a 20s 1080p reel.
- The renderer is SDR only. Convert iPhone HLG sources to BT.709 first (`cut_clips.py` does this).
