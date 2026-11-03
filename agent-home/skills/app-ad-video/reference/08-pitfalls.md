# 08 · Pitfalls: every one of these happened and was measured

## Shell and ffmpeg
- zsh `echo ======` -> `=` expansion errors out; quote it (`echo '#####'`).
- zsh `"...duration=$D:amplitude=0.5"` -> `$D:a` is read as a path modifier; write `${D}`.
- zsh `rm dir/*.png` aborts the command when nothing matches; use `rm -rf dir` + `mkdir`.
- zsh does not word-split unquoted variables: `for n in $FR` runs once -> `${=FR}`.
- ffmpeg `-t` means different things by position: `-t 1.4 -i x` limits the input, `-i x … -t 1.4` the output.
  In the wrong place it produced 48 frames once.
- Newer ffmpeg has no `-vsync` -> `-fps_mode passthrough`. Many builds lack `drawtext` -> use the `collage`
  helper or an image grid. `resampler=soxr` may be missing.
- The system python may lack numpy/PIL -> pure python + raw ffmpeg bytes (`fx.py`). For heavy image work, use
  the job's `Work/venv`.
- Using the same label twice in a filter graph **silently drops** the second use; duplicate with `asplit`.
- `-shortest` cuts 2 to 3 frames because of the AAC frame size -> `apad -t <seconds>`.
- Every extra AAC encode adds ~1024 samples of delay (42.7 ms). Encode once.

## Remotion
- Inside `<Sequence>`, `useCurrentFrame()` starts at 0; do not subtract `from` again.
- `<OffthreadVideo>` without a Sequence plays the composition frame -> `<Sequence from layout="none">`.
- `translateY` does not move the `objectFit` crop window -> `objectPosition`.
- `filter: url(#…)` clips outside the element's box -> use a wide container for content that will be blurred.
- Rotation, mask and `mixBlendMode` must be on the same element.
- If rendering starts before fonts load, the first frames use a fallback font -> `delayRender` +
  `document.fonts.load`.
- Remotion package versions must match exactly (no `^`).
- On a grid/list screen keep the card count even (2 columns leave a gap); do not repeat card names.
- `<Freeze frame={N}>` is clamped to the composition length. If N ≥ `durationInFrames` it freezes on the last
  frame. In a 25-frame calibration, `frame={100}` silently gave f24. Make calibration compositions longer than
  N+1 frames.
- An `OffthreadVideo` inside `<Freeze>` freezes too. If you compute a scroll/tab motion from outside (with the
  unfrozen frame), the motion continues while the video frame stops.
- An object that enters with an opacity ramp shows the layers below it as a ghost on its own screen. A phone
  entering at 0.4 -> 1 showed a "0:00" counter and a blurred face on its screen. Let it enter opaque and slide
  in from fully out of frame: `travel = H − T + frame + margin`. A contact sheet misses this; look at ±6 frames
  of the transition at full resolution.

## Color and delivery
- `--color-space=bt709` is wrong; re-tagging the raw render is wrong -> `deliver_png.sh` ([06](06-delivery.md)).
- Do not verify color with a whole-frame average; use a saturated region.
- `verify_delivery.py` can give ~3.5 "CHECK" on small, moving saturated elements (icons, 60 to 100 px). To tell,
  convert the source frame to lossless 4:2:0 and back and compare with the same mask.
  - A matrix error shifts color systematically by 5 to 10 levels.
  - Subsampling + compression stays within 1 level on average.
  Once: 4:2:0 alone 1.56, delivery 2.28, mean (192,121,83) -> (191,122,84). For a firm check use a large flat
  area (the CTA).
- Measure the file in `Final/`, not your intermediate. The container `colr` and the SPS VUI can disagree; read
  both.
- When measuring reference masters, keep the aspect ratio in face tracking (an old fixed 536×966 distorted 4:5
  by 1.44×).

## Audio
- Remotion's `--codec=wav` output is **16 bit**: overlapping SFX + music hits 0 dBFS and clips. Once a shutter +
  beep + music reached 0.00 dBFS at f121.
  - **Fix:** separate overlapping events (the beep was delayed until the shutter decayed).
  - Lower all volumes by the same ratio (×0.7). Loudnorm brings it to −14 anyway.
  - Measure the render's sample peak with `volumedetect`. For remaining transients, `prelimit.sh`.
- AAC delay in comparisons: correlation at zero offset makes existing audio look "absent"; sweep the offset.
- The least-squares gain comes out low under partial correlation (4.3 dB) -> energy-based `level`, then
  `compare`.
- Do not assume ducking, measure it. Choose the music segment by energy consistency.
- loudnorm can push audio that is already at −14 into dynamic mode and overshoot ->
  `deliver_png.sh --no-loudnorm`.
- Goertzel gives the wrong peak on long windows -> a Hann-windowed DFT.
- Providers limit concurrent requests. Rejected requests may not be billed but they are lost work; submit in
  batches of about 4.
- If the mix peak is above −9 dBTP, `deliver_png.sh`'s linear loudnorm cannot hold TP −1.5 while raising to −14
  and drops to dynamic mode (the music pumps). Limit the mix first at 192 kHz, then pass it with `--audio`
  (−6.1 -> −9.5, delivery −14.01 / −1.61 once).

## AI generation
- An unknown or wrong input field can be silently ignored -> the output is generated from the prompt alone
  ("reference" shots showing a different person). Check fields with `fal schema` and check the output.
- Some models ignore `aspect_ratio` without an error; measure the output size.
- Image-to-video models often ignore "mouth closed" -> measure the window. Pose drift -> "head stays level and
  upright".
- "Mouth closed" usually holds for the first second, then lets go -> first a rescue window + `slow_clip.sh`, then
  a retry.
- Hand-object actions (flipping a phone over) usually fail -> build the action in code, show the result in the
  shot.
- A prompt like "holds the phone above her face" draws the phone and the hands into the frame -> describe the
  camera without a phone.
- `plate_qc.py` used to delete the other entries in `plates.json` when measuring one shot -> fixed, it merges now.
- Video jobs can take many minutes and download links expire -> submit with `--no-wait`, collect with
  `fal wait` promptly, do not resubmit a job that is still running.
- Failed attempts can be billed; add a retry margin to estimates.
- Emotional expression prompts can produce a frown; describe the face precisely or solve it in the edit.
- Say explicitly that you want no readable text, logos or faces in the background.
- If a UI screen has a close (X) button, remove it when used full screen: it reads as the ad's close button
  (Meta's fake UI policy). If the background is flat or a vertical gradient, filling the row with the edge color
  leaves no trace.

## Measurement
- The eye line slope is not the face midline; do not rotate offsets with it.
- Prove "the picture did not change" with framemd5. Elements with CSS 3D transforms (perspective + rotateY) can
  differ in antialiasing between renders in Chrome (mean 0.2, at most 23 levels over 14 frames at 9:16; 4:5 was
  identical). Invisible, but do not claim "bit-identical".
- Python `wave` with 24-bit WAV: reading 3-byte samples as `<i4`/`<i2` produces noise (a measurement said −31 LUFS
  where the truth was −35). Join bytes by hand and sign-extend, or convert to 16 bit with ffmpeg.
- verify's "saturated region difference > 3.5" alarm -> four numbers with `scripts/sat_diag.py`; on thin,
  contrasting edges lossless 4:2:0 alone is already 3 to 5.
- Clean window thresholds are rough: look at the flagged frames (smiles get flagged too).
- When picking a portrait, also measure mouth opening (a first pick once landed on a speaking moment).
- Do not reuse numbers from earlier summaries without checking. Some timings in an old summary turned out wrong;
  all of them were measured again.
- Template matching can underestimate motion. Derive it from start and rest positions and cross-check (a carousel
  path was 3688, not 3584).

## Vision models
- They are good at content, not at numbers: frequency/pitch, level, color and timing measurements are never left
  to them.
- If the reference has speech, always get a transcript (STT). A competitor's name in the audio once slipped
  through because no transcript was taken.

## Process
- Producing into the wrong folder is the most expensive mistake to undo; check `pwd` and the app code before
  starting.
- Do not write into another job's files. If you need to fix a shared tool or its copy in another job, say so
  separately.
- Do not change an approved look on your own; report the difference from the reference.

## Check the talent when copying assets from another job

Jobs made "with the talent we already have" do not number their talent in order: one job used a different
creative's talent than the code suggested. When a portrait was copied from the wrong job, another person
appeared on the result screen; the first style contact sheet caught it. Read the talent mapping from the target
job's `Brief/BRIEF.md` ("Talent:" line); the safest is to cut the portrait again from its own shot with
`portrait_crop.py auto`. After every copy, look at a frame of the result screen.

## `prelimit.sh`: mixes that need no limiting and mixes over full scale

- If the raw mix is louder than −14 (−9.7 LUFS, peak −0.1 once), the threshold exceeds 1 (1.33) and `alimiter`
  says "out of range". The script now checks first whether the peak stays under target once the mix is brought
  to −14; if so it copies the mix as float.
- **Write the mix as float after summing.** `amix=normalize=0` can exceed full scale (a touch sound landed on the
  music's peak, +2.8 dBTP). Written to s24 WAV it is silently clipped, and the measurement reads the clipped file
  and shows +0.8. Write `pcm_f32le`; `prelimit.sh` scales input near or above full scale by −6 dB before limiting.
- The risk is big in cuts from deliveries: in the source the SFX were mixed against a particular moment of the
  music; in continuous music they land on another moment.

## `prelimit.sh`: ebur128 and loudnorm do not read the same I

- loudnorm needs `input_tp + (−14 − input_i) ≤ −1.5` to stay linear. If that fails it **silently** drops to
  dynamic mode. The delivery then comes out at −14.2 to −14.3, and the audio itself moves with a time-varying gain
  (the residual between delivery and mix is −26 dB; linear gives −44).
- An older `prelimit.sh` measured with ebur128. The peak was the same in both measurements (−11.5), but on a
  speech-heavy mix I differed: ebur128 −23.8, loudnorm −24.05. The cause is gating; 0.25 LU on other mixes too.
  - By ebur128, −1.7 dBTP was "safe"; by loudnorm it was −1.45.
  - Deliveries at −14.29 and −14.20 went out.
  - Another (−1.53) just passed.
- The script now uses loudnorm's own measurement ([05](05-audio.md#pre-limiting-with-the-script)).
- **Check at delivery:** if LUFS is not −14.00 ± 0.02, loudnorm went dynamic. Measure correlation and residual
  between the delivered AAC and `mix_pre.wav`: linear gives 0.9999+ and −44 dB.
