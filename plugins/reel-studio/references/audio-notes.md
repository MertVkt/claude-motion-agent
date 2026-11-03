# Audio notes

## Loudness target
Aim for about **−15 LUFS integrated** with **true peak ≤ −1 dBTP**. Measure with:

    ffmpeg -nostats -i X.mp4 -af ebur128=peak=true -f null - 2>&1 | grep -A15 Summary

Adjust the spec's `gain` (it multiplies every track), or the per-track volumes, then rebuild. Reels with sharp impact sounds peak early; −16.5 to −17 LUFS is fine for those.

## Transient offsets of the bundled SFX (seconds into the file)
These come from the HyperFrames media-use skill and are Pixabay-licensed.

| file | peak at |
|---|---|
| impact-bass-1.mp3 | 0.065 |
| impact-bass-2.mp3 | 0.37 |
| whoosh.mp3 / whoosh-short.mp3 | 0.152 |
| glitch-1.mp3 | 0.947 |
| whoosh-cinematic.mp3 | 2.54 |
| riser.mp3 | ~10.0 (end) |

A spec's sfx entry is `(file, visual_peak_time, volume, transient_offset, duration)`.

## Music placement recipe
1. Get a loudness map with `analyze.rms(path, hop=0.01)` averaged per 0.5s, which shows intro, build, break and drop. Use `analyze.onsets(...)` for beat and hit candidates.
2. Choose the trim offset so that:
   - the **largest jump** (the drop) lands on the edit's key moment;
   - a quiet **break** sits right before it;
   - the track's energy doesn't sag at the end card. Fade out the last 1.2s.
3. Check the inter-onset gaps to estimate tempo, then line up hard cuts and whip midpoints to within ~0.1s of an onset.
4. Use `sync` in the spec for strike-on-beat. Use `gate` to strip voices or crowd noise from footage audio but keep impact hits.

## Removing voices or crowd noise from footage
Busy locations have constant crowd noise and people talking, so band-energy analysis can't isolate one voice. Two options:
- Mute footage audio entirely, for reels the music carries.
- Use `"gate": {"jump": 6, "hold": 0.11}`. Footage audio is then silent except ~0.25s windows at detected hits. Verify by exporting a copy with all Audio layers at volume 0 and checking the RMS (about 2/3 of 50ms frames should be silent).
