# 05 · Audio: breaking down the reference, VO, caption timing, music, SFX, mix

```bash
SK=~/.claude/skills/app-ad-video/scripts
```

## 1. Break down the reference's audio (when you have the source sounds)

In references built in AE, the music and SFX sit in `(Footage)/…/Sounds`. The names are hints ("Tap Button",
"Spinning 02", "Correct Vibra", "Transition Complex 14"). Method: align and subtract the music, search for each
SFX in the **residual**, measure levels, compare your own mix with the reference.

```bash
python3 $SK/audio_match.py music ref.mp4 "Footage/Sounds/LoFi Chill.wav" --out Work/au
#  -> offset 171 samples (+21.4 ms), gain 0.70, window gains, residual events (frame ranges)
python3 $SK/audio_match.py sfx Work/au/res.f32 sfx_tap.mp3 --near 0.25,0.6 --delay 0.0214
#  -> layer start frame 11.00, correlation 0.884, 1.33 to 1.50 times the music
python3 $SK/audio_match.py sfx Work/au/res.f32 sfx_whoosh.wav --near 4.8,5.1 \
        --rates 2.4,2.5,2.65,2.8 --inpoints 0.18,0.2,0.22 --len 0.35 --delay 0.0214
#  -> speed 2.65, in-point 0.2 s, layer frame 148 (sped up = higher pitch)
python3 $SK/audio_match.py level Work/au/res.f32 sfx_whoosh.wav --at 4.955 --win 4.955,5.121 \
        --floor 3.755,4.888 --rate 2.65          # -> 1.30 times the music (+2.3 dB)
# after building the composition:
npx remotion render <id> Work/a_check.wav --codec=wav --config=remotion.audio.config.ts
python3 $SK/audio_match.py compare ref.mp4 Work/a_check.wav music.wav \
        --events "tap:0.367-0.467,spin:1.033-2.933,correct:2.967-3.333,whoosh:4.933-5.1"   # target ≤ 0.3 dB
```

- **Encoder delay:** in AE/AME AAC deliveries the mix starts ~21.3 ms late relative to the sources (171 samples
  at 8 kHz). If the music starts at 0 on the timeline, the offset `music` finds is this delay; subtract it from
  SFX times (`--delay`). Measuring correlation at zero offset misleads: an offset sweep is required.
- **Level:** with high correlation (≳0.95) the least-squares gain is reliable. With partial correlation that
  gain comes out low by the correlation ratio (4.3 dB low on one whoosh). Then measure from the residual
  energy with `level` (floor subtracted). `compare` decides.
- **Speed changes:** AE time-stretching also changes pitch. Find speed and in-point by envelope sweep, then
  render the file with `asetrate` beforehand ([02](02-remotion.md#audio-layer)). For wide-dynamic, repetitive
  sounds use `--log` (one spin sound: 0.85×, log-envelope NCC 0.75).
- Volumes are "N times the music" ratios: in Remotion `sfx = music × ratio`, none above 1.
- Measured examples: music 0.70, tap f11 +3.6 dB, spin f27 0.85× +1.3 dB, correct f89 −7.1 dB, whoosh f148
  2.65× +2.3 dB. Another: music 0.553, scan beeps f25.5 / f70.5 / f114.7 +6.3 dB.

Without the source sounds (a competitor's ad) we choose the music ourselves. From the reference measure only
the structure: music level during speech, whether there is ducking, SFX moments.

## 2. Voiceover: made first

Shot lengths and caption timing come from the VO; the composition is built after it.

```bash
fal run fal-ai/minimax/speech-2.8-hd prompt="Don't risk a bad haircut." output_format=url \
    --name vo_01 --out Audio
fal run fal-ai/elevenlabs/tts/eleven-v3 text="Don't risk a bad haircut." voice=Rachel --name vo_01 --out Audio
```
- Check the voice options with `fal schema` (`voice_setting.voice_id` for MiniMax, `voice` for ElevenLabs v3).
- Generate lines **one by one**, trim leading and trailing silence, place them at scene starts.
- If one sentence lands on two screen events ("Wait… Spanish?" on a card, "21% Mexican?!" on the result screen),
  split it into two lines and delay the second half by a few frames: the result screen was then readable for 14
  frames before "21%" instead of 8.5.
- To get close to a reference voice, measure the F0 median (a reference at 85 Hz -> pick a deep, calm male
  voice).
- Match the reference's pace: speed the VO up with `atempo`, trim silences. 22.71 s became 16.70 s at 1.27×;
  intelligibility confirmed with STT.
- TTS is billed per character and is cheap.
- For localization redo VO + alignment + captions; if lip sync is needed, use a lip-sync model on fal
  (`fal models lipsync`).
- Picking takes without a reference: 2 takes per line, all laid out back to back in one file with timestamps.
  Check text/pronunciation with one STT call. For tone, ask a vision/audio model once "which take sounds more
  natural". For pronunciation, write the brand name phonetically in the TTS text and keep the correct spelling
  in the captions ("Lumo" -> "Loomo").
- TTS output can come out quiet and peaky (−30 to −35 LUFS, peak/loudness 14 to 18 dB once). Per line apply a
  highpass at 70 + a 3:1 compressor, match to −20 LUFS, limit at −8 dBTP at 192 kHz. The music bed sits
  ~11 dB under the VO (−31 LUFS), −25 in breaths/gaps.

### Music level under VO without a reference

Without a reference, intelligibility decides the ducking question, not measurement.

- **Method:** at word moments in the speech band (300 to 3400 Hz), compare the VO with the background, which you
  get from the Remotion WAV by energy difference.
- **Measured once:**
  - With a lo-fi bed fixed at 0.3, the VO was +5.7 dB on average; short words sank under the music.
  - Pulling the music from 0.28 to 0.09 during lines with `<Audio volume={(f) => …}>` gave +15.1 dB. 6-frame ramp;
    the dip starts 6 frames before the first word and ends 8 frames after the last.
- **When the level drops:** the mix goes down to −19 LUFS; bring it to −14 with `prelimit.sh` +
  `deliver_png.sh --audio`.
- **TTS notes:**
  - In ElevenLabs v3, `[gasps]` is not read aloud; it produces a breath (STT writes it as a `[gasps]` event).
    `…` gives a dramatic pause.
  - Different voices come in 4 to 11 dB apart in the same setup. To keep the series' measured VO/music balance,
    measure lines with ebur128 and bring them to −18 LUFS with line gain (a final whispered line −19/−20)
    (`SFX.voGain`). Remotion `volume` cannot go above 1: if you need a boost, write the gain into the file
    (ffmpeg `volume=+4.5dB`), keeping peaks ≤ −1.5 dBFS.

### A new voice: voice design previews

```bash
python3 $SK/voice_design.py --desc "A 27-year-old woman from Los Angeles, casual American English \
  with a light, warm accent, bright, expressive, ... selfie video for TikTok. Natural, close-mic, clean audio." \
  --text-file Work/vo_script.txt --out-dir Audio/design --tag v1
```
- It runs voice design on fal (`fal-ai/minimax/voice-design`). **Use the ad's whole VO script as the preview
  text**, so a preview can become the VO itself.
- **Choosing:** compare the previews in one model request (naturalness, accent/age fit, surprise, breath,
  pronunciation). Confirm the words with STT.
- Write foreign words phonetically in the preview text ("Babcha" -> "BAHB-cha"), with the correct spelling in
  captions ("Babcia…").
- **A preview can change words:** once all previews read "scanned" as "scan". Captions follow the audio, not the
  script.
- **Splitting into lines:** find silences with 50 ms RMS (`astats` + `ametadata`), cut in the middle of the
  silence, 5 ms edge fades, 48 kHz WAV. Run STT on the preview once, shift the word times per cut and write a
  line JSON (no extra cost). Place lines on the timeline with VO_AT: gaps between lines are chosen in the edit.
  To shorten a long pause, split the sentence into two lines (0.8 -> 0.44 s).
- Level moves inside a preview too (−14.7 to −24.0 LUFS once): use line gain as above.

## 3. Caption timing

```bash
python3 $SK/speech.py align Audio/vo.mp3 "Don't risk a bad haircut. Find your perfect look…" Work/align.json
```
- `speech.py align` uses fal forced alignment (`fal-ai/elevenlabs/forced-alignment`); `speech.py stt` uses
  word-level speech-to-text.
- `src/captions.ts` is generated from the word times (never edited by hand). Groups of 2 to 3 words; the karaoke
  highlight follows the spoken word.
- Without alignment, split word durations **by syllable weight**. Fixed durations drifted out of sync on short
  and long words.
- If backgrounds change a lot (poster -> white page -> night), put the text in a rounded white box; readability
  becomes independent of the background.
- Assume sound off: the message must read from the text alone. Captions stay inside `SAFE_AREA`.

## 4. Music

- **Pick a segment:** scan the track in 16 s windows and take one with consistent, strong energy (low std). One
  16 to 20 s window was uneven (std 8.0 dB); a later window was punchier and steadier (std 2.3 dB).
- **Do not assume ducking, measure it.** One reference had none (music −21.3 dB under speech, −22.5 dB in the
  music-only part); a sidechain I added buried the music by 8 dB. A robust metric: broadband RMS difference of the
  music-only part vs the speech part (reference −4.7, ours −4.2 dB). Measure intelligibility in the speech band
  (300 to 3400 Hz): the VO was +16.7 dB over the music.
- Bed level and fades in the mix script:
  ```bash
  ffmpeg -ss 56.0 -t 19.6 -i music.mp4 -af "afade=t=in:st=0:d=0.25,afade=t=out:st=18.85:d=0.75,volume=-9dB" …
  ffmpeg -i music_track.wav -i vo_track.wav -filter_complex "[0:a][1:a]amix=inputs=2:duration=longest:normalize=0[o]" …
  ```
  Keep it in `Work/tools/build_audio.sh` and pass the mix with `deliver_png.sh --audio mix.wav`.
- A binaural bed is built in ffmpeg (no cost): two sines 6 Hz apart (for example 429/435 -> center 432).
  Measure the source's resonance in the carrier band first; if it falls between the carriers it produces a
  wrong beat. Measure frequency with a Hann-windowed direct DFT; Goertzel accumulates error on long windows.
- Need new music? `fal-ai/elevenlabs/music` or another music model (`fal models music`). Check the license
  terms for ad use.

## 5. Generating SFX

`fal-ai/elevenlabs/sound-effects/v2` (`fal schema` for duration). For stochastic textures (fireplace, brush)
generate 10 s and loop it by layering time-shifted windows: cheap and dense, the loop is inaudible. For short UI
sounds, check `(Footage)` and earlier jobs first.

## 5b. Level of a new SFX without a reference

In an original piece there is no mix to measure. Set levels **relative to the series' own measured events**:

1. Measure each SFX file's 50 ms peak RMS.
2. Multiply by its gain and compare with the music's average RMS (dB).
3. Set the target relative to the series' events.
4. Subtract the music from the Remotion WAV and measure again.

- **One measured family** (relative to the music): beep −8.0, correct −8.5, whoosh −7.6 dB.
- **Targets used for a quiz piece:**
  - answer "pop" −12 dB (many of them, keep them low);
  - timer tick −10 dB;
  - shutter −6 dB (let the flash moment stand out).
- **A very quiet file:** do not push gain above 1; boost the file beforehand (`volume=8dB`, peak < −1 dBFS
  with `volumedetect`).
- **Sounds with a transient** (shutter peak at 110 ms): start the `Sequence` early enough that the peak lands on
  the visual event.

## 6. Mix -> delivery audio

- Remotion WAV or ffmpeg mix -> two-pass loudnorm (−14 LUFS, TP −1.5, linear) -> **single AAC**. All of it in
  `deliver_png.sh`. For dense transient material, `--limit` (limiter at 192 kHz).
- **Pre-limiting:** run the Remotion WAV through
  `aresample=192000,alimiter=limit=L:level=disabled:latency=1,aresample=48000`, then `deliver_png.sh --audio`.
  - Limit: `L = 10^((−1.8 − (−14 − I))/20)`. I is the measured loudness of the limited mix; compute it in two
    passes. In each pass, measure I again **from that pass's limited mix**. Computing the second pass from the
    raw mix's I once left the peak at −1.40 at −14 (target ≤ −1.5). Three passes settled at −1.80.
  - **`latency=1` is required.** Otherwise alimiter's look-ahead buffer (default attack 5 ms) delays the whole
    signal: cross-correlation between raw and limited mix gave exactly 240 samples = 5.00 ms; with `latency=1`, 0.
- Never use the same label twice in an ffmpeg filter graph. The second use **is silently dropped**; once the VO
  never made it into the delivery. Duplicate with `asplit=2[vo][vokey]`.
- Every extra AAC encode adds delay (42.7 ms measured). `-shortest` cuts 2 to 3 frames; use `apad -t <seconds>`.
- After delivery, confirm the VO is **in the file** with a shift-tolerant correlation (0.984 once).

## Synthesized tension audio: the phone speaker rule

- **50 to 60 Hz drone, hits and heartbeats:**
  - They barely count toward loudness (K-weighting); raising the drone +6 dB raised the section only +1.4 dB.
  - They inflate sample peaks and give the limiter 5 dB of work.
  - A phone speaker cannot play 60 Hz at all.
- **The fix:**
  - Add a mid-frequency dissonant pad to the drone (110 / 116.5 / 165 / 220 Hz, a small second rubbing) and
    150 to 600 Hz band-passed noise.
  - Add a short click with the 2nd and 3rd harmonics to hits and heartbeats.
  - Turn down very low hits (−12 dB).
- **Normalization trap:** do not normalize a synth file to a fixed peak each time; use a fixed gain. Peak
  normalization undoes turning one component down: when the hit was lowered, normalization raised everything
  else.
- **Dynamic rise:** a tension section does not have to stay level. One rose from −30 to −26 LUFS and dropped to
  full silence (speech at −23).
- **Generated video audio can start with a mouth click** (0.80 s, −2 dBFS once). Mute the frames before the
  first word with a `volume` curve; sync is unaffected.

## Pre-limiting with the script

- `scripts/prelimit.sh <mix_raw.wav> <mix_pre.wav> [tp=-1.8] [max_passes=6]`: each pass measures I from the
  previous **limited** mix and runs the limiter on the **raw** mix (192 kHz, `latency=1`). Example: 0.2455 ->
  0.2399, settled in two passes, delivery −14.00 / −1.74 dBTP.
- **Measure with loudnorm itself:** `input_i` and `input_tp`. The delivery's linear loudnorm decides with these
  numbers. ebur128's I came out 0.2 to 0.3 LU high on speech ([08](08-pitfalls.md)). The limit is corrected by
  secant: 1 dB in the limit is ~0.6 dB of peak at −14, because limiting also lowers I. It stops on target;
  usually two passes are enough (−14.00 / −1.81).

## A tense hook opens straight into tension

- **Rejected:** "video audio leaking from the phone" in the hook (lo-fi snippets, 350 to 2500 Hz, cut at every
  scroll). Despite the narrow band it still read as music. The user: "there is music at the start, start
  straight into tension".
- **The right way:** the drone is there from the first frame (3-frame fade in). In the hook the envelope is
  ~3 dB higher than under the VO, with an early heartbeat. At the event (battery dies) a bass hit and a 2-frame
  gap in the drone; then a steady level under the VO.
- **Level:** hook section −28.6 LUFS, body between −23 and −25. A first try stayed at −31.3 and the start was
  weak.
- **Measurement:** correlation with the removed snippet. The old delivery 0.75 to 0.87, the new one 0.05 to 0.18.
- A tension bed under speech: −2.5 dB during each VO line (a `volume` function), back to full level after the
  line so the climax holds.

## A cut from existing deliveries: continuous music, SFX extracted from the source

Five deliveries from the same template back to back: their audio was identical (md5), so a plain join would
restart the music every 11 s.

- **Unpick the mix (48 kHz stereo, per channel):** in AME/AAC deliveries audio arrives **1024 samples
  (21.33 ms)** late (AAC priming). Sweep the offset sample by sample: correlation 0.99998 at 1024, 0.998 at ±1.
  At 8/16 kHz this difference is invisible and the ~0.90 correlation there makes the music look "different".
  The music gain in the AE mix came out 0.707 (−3.01 dB).
- **SFX layer = source(t + 1024) − gain × music(t)** (`amerge` + `pan`, f32). Use this instead of rebuilding from
  an estimated SFX list: one estimated list (beep, correct, whoosh) left a −7.6 dB residual against the source,
  and card, bar, packshot and CTA sounds were missing from it. With the extracted layer the first section matched
  the source with a −130 dB residual.
- **New mix:** the music as one piece from start to end + at the start of each section the matching part of the
  layer. The layer must be silent at the cut point (−53 to −61 dBFS once). A short fade at the end (0.15 s) if
  the music ends abruptly in the source.
- Same audio path: `prelimit.sh` (copies through if not needed) -> two-pass loudnorm -> single AAC. Keep it as
  `Work/tools/build_montage.sh` with `SEG`/`LEN` arrays for variable section counts and lengths, a total frame
  check and a float raw mix.
- Measure the music gain over time (0.25 s windows): if it is not constant (automation), extraction with a
  single gain breaks. Once it held at 0.70 to 0.71 over 11 s. If the layer has sound at the cut, fade the section
  end over 0.1 s and put the cut at the layer's lowest point.
- **Different source families in one cut:** measure each family separately. AME deliveries are 1024 samples
  late; deliveries from an older path (Remotion AAC encoded a second time) **2048** (AAC twice). Gains differ too
  (0.7069 / 0.5496). One bed level; each family's SFX scaled by its own music ratio.
- **If the extraction residual is high, rebuild the SFX:** with a residual at −40 to −55 dBFS (resampling +
  double AAC), the layer placed at another time becomes a ghost of another part of the music. If the mix is known
  (Remotion code: which file, which frame, which volume), build the layer from those files. Check: bed + rebuilt
  layer should match the original down to the AAC floor (−34 dB).
