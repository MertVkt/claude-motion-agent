# 03 · AI generation: talent images, shots, keying

Before every paid generation, state the model, count and estimated cost (CLAUDE.md §2.1) and keep an eye
on `fal cost` (§2.2). This file is about **which model does what well** and how to call it. All
generation runs on fal.ai through the `fal` command; the fal skill has the command reference.

## Models (defaults)

Endpoint ids change over time. Confirm the fields with `fal schema <id>` before spending, and use
`fal models <word>` if an id stops working. Never guess an id that is not in the catalog.

| Job | Default | Alternatives | Notes |
|---|---|---|---|
| Realistic talent image (selfie talent, the same person in another scene or hairstyle) | `fal-ai/nano-banana-pro` | `google/nano-banana-2-lite` (cheap, fast), `bytedance/seedream/v5/pro/text-to-image` | `aspect_ratio=9:16`, `resolution=2K` for sharper plates |
| Edit with reference images (same face, same character, new scene) | `fal-ai/nano-banana-pro/edit` (`image_urls`) | `fal-ai/nano-banana-2/edit`, `bytedance/seedream/v5/pro/edit` | or `python3 $SK/ref_edit.py` |
| Image to video (natural head motion, blinks, hair) | `bytedance/seedance-2.0/image-to-video` | `fal-ai/kling-video/v3/pro/image-to-video`, `fal-ai/veo3/fast/image-to-video`, `bytedance/seedance-2.0/fast/image-to-video` | Seedance: `duration` "4".."15", `aspect_ratio=9:16`, `generate_audio=false` (we build the audio ourselves) |
| Text to video | `bytedance/seedance-2.0/text-to-video` | `fal-ai/veo3/fast`, `fal-ai/kling-video/v3/pro/text-to-video` | |
| Reference to video (person/product consistency) | `bytedance/seedance-2.0/reference-to-video` (`image_urls`, `video_urls`, `audio_urls`) | `fal-ai/kling-video/o3/pro/reference-to-video` | |
| Talking UGC with lip sync in one go | `fal-ai/veo3/fast/image-to-video` with `generate_audio=true` | Seedance with `generate_audio=true` | put the line in quotes in the prompt |
| Voiceover | `fal-ai/minimax/speech-2.8-hd` (`output_format=url`) | `fal-ai/elevenlabs/tts/eleven-v3`, `fal-ai/minimax/speech-2.8-turbo` | [05](05-audio.md) |
| SFX / music | `fal-ai/elevenlabs/sound-effects/v2`, `fal-ai/elevenlabs/music` | | |

General lessons that hold across providers:

- **Check every output.** Look at images with Read; for videos, grab frames with ffmpeg and look. If a
  result is bad, fix the prompt and regenerate; do not build on it.
- **A wrong or unknown input field can be silently ignored** by some models: the request succeeds and the
  output is generated from the prompt alone, so a "reference" shot shows a different person. `fal run`
  validates fields against the live schema, but also look at the result: does the reference show up?
- Some models ignore `aspect_ratio` without an error. Measure the output size; if it is wrong, crop in
  Remotion or switch model.
- Failed attempts can be billed too. Add a retry margin to estimates (10 usable images took 12
  generations in one series).
- Image-to-video jobs can take minutes. For several shots, submit them all with `--no-wait`, then
  `fal wait <id>` each. Download links expire, so collect results promptly.
- Image-to-video output is usually 24 fps. Seedance and Veo at 9:16 come back at 1080×1920 or close to it
  depending on resolution; measure.

## Talent image: the recipe

Structure: **place + light -> background objects (no text) -> person (age, hair, skin, eyes, natural face,
makeup, jewelry, clothing) -> shared tail (expression, framing, skin realism).**

```text
Authentic amateur front-camera selfie, vertical 9:16, sitting at a window seat in a bright, cozy cafe
with soft daylight. Behind her, softly out of focus: warm wooden interior, a ceramic coffee cup on a
wooden table edge and a large window with blurred greenery outside (no readable text, no signs, no logos,
no letters, no other people, no faces). A naturally beautiful 23-year-old woman with long, voluminous
dark-brown natural curls falling past her shoulders, light olive skin, dark brown eyes, natural full
brows, a natural nose, soft everyday makeup: light mascara, subtle blush, tinted lip balm; wearing a
cream cable-knit sweater. Relaxed friendly expression with a soft closed-mouth smile, looking straight
into the lens. Close selfie at arm's length: her face is large in the frame and centered, the face about
half the frame width, eyes at about 42% of the frame height, the top of her hair close to the top edge,
chin and the top of her shoulders visible, nothing cropped, no phone or hand in shot. Real unretouched
skin with visible pores and natural texture, no beauty filter, no smoothing. Candid, photographic,
realistic front phone camera look.
```

- **The face should be realistic for the result the ad promises.** Write features with natural variety
  that fit the claim (ethnicity, hair type, skin). No caricature: "a natural nose", "real unretouched
  skin", fine lines and laugh lines appropriate to age.
- **Variants should differ:** age, hair (color/length/texture), skin tone, clothing color, place (car,
  kitchen, cafe, living room, bedroom), light (daylight, golden hour, lamp), accessories. Fill the
  demographic gaps within a series.
- **Fit the features to the rest of the creative:** if the VO says "Bangs, bob, pixie", pick hairstyles
  that match those labels. Then VO, alignment and labels stay as they are (no new TTS needed). Dark,
  textured hair turns into a silhouette on a light background; pick tones for the background.
- **Ask for a close framing** (face half the frame, eyes at ~42%). The shot then needs less scaling later
  and stays sharper: 1.47× with a wider framing, 1.18 to 1.25× with a close one.
- No readable text, logos or other faces in the background; "no readable text…" is there for that.
- Other scenes with the same face: generate the main portrait, then derive with references
  (`fal-ai/nano-banana-pro/edit` with `image_urls`, or `ref_edit.py`). "The attached photo is the
  REFERENCE for the woman's IDENTITY: the exact same woman, same face, same skin tone…" + "only her
  HAIRSTYLE changes". Verify consistency with face tracking (face center within ±2 px across three scenes
  in one case).
- Generate in parallel (`--no-wait` for each, then `fal wait`), and present results as a **labeled
  collage**: `collage Work/casting.png 3 480 853 80 'Asset/a.png|A\n~23, cafe' …` (macOS helper; elsewhere
  a quick ffmpeg `xstack` grid).
- Emotional expression prompts are risky: "almost tearful / visibly moved" gave a frowning sad face; use
  "brow completely smooth, absolutely NOT furrowed, positive wonder". If the expression is not right after
  three tries, **solve it in the edit**: split the scene and put the expression on the beat that fits
  (free, and it worked better).

### Night / low-light talent

If the face should be lit only by the screen, do not turn the phone toward the camera. Lay the person on
their side, phone ~30 cm in front of the face; the camera sits just beside and slightly behind the phone,
at pillow level. The back of the phone is blurred in the foreground ("plain black case, no logo") and its
screen is not visible, so no other app is shown. nano-banana-pro got this right first time in all three
candidates at 9:16. The same setup as a 5 s image-to-video shot: thumb scrolling, slow blinks, stable
identity. Leave the top area (headboard/wall) empty for POV text.

## Shot (image to video): the recipe

```text
Static front-camera selfie video, the camera held perfectly still at arm's length, framing never changes.
She looks into the lens with a calm, relaxed expression and a soft closed-mouth smile, making small natural
head movements: slow blinks, gentle breathing, a slight head tilt now and then, a couple of natural soft
smiles. Her lips stay closed the whole time: she does not speak, does not mouth words, does not laugh with
an open mouth. Subtle and realistic; no big gestures, no hands or objects entering the frame. Lighting and
background stay exactly the same throughout.
```
Negative prompt (where the model supports one): `talking, mouth opening, lips parting, teeth showing,
speaking, hair changing length, hair changing colour, identity change, morphing face, warping background,
extra limbs, camera shake, text, watermark, logo, subtitles`. If the pose drifts: "head stays level and
upright, does NOT tilt back".

- **Models often ignore "mouth closed".** Before using a shot, measure the clean window
  ([04](04-faces-and-shot-plan.md)): if it is short, slow it down or freeze, do not regenerate.
- 24 -> 30 fps: in Remotion, `OffthreadVideo` already picks the right frame; tracking maps with
  interpolation. If you need real in-between frames in ffmpeg, use
  `minterpolate=fps=30:mi_mode=mci:mc_mode=aobmc:vsbmc=1`. For abstract/fluid/drawn material use
  `mi_mode=blend` (mci deforms flames and lines).
- Slowing down: generate the source deliberately fast and stretch with `setpts` (1.41 to 1.94× in one
  series) or use Remotion `playbackRate` (0.757 to 0.99× went unnoticed).
- **Slow motion synced to contact** (a phone landing face down on a table):
  - Command: `setpts=PTS/0.685,minterpolate=fps=30:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1`.
    A 24 fps source at 0.685× repeats each frame ~1.8 times; mci makes in-between frames.
  - Find the contact frame from the frame-difference curve and crops. The dark-pixel centroid gets
    confused by the table's shadow.
  - Put the SFX in the gap between two VO sentences ("…minutes." f42.6 -> click f44 -> "Can you?" f54.6).

## Keying / cut-outs (plain background generation)

Key a cut-out generated on a light background (wig, product, person) by flood-filling from the edges:
background = above a brightness threshold **and** connected to the border. Soften the alpha with a 2 px box
blur, keep the largest component if needed. Use the job's `Work/venv` for numpy/PIL. Report the fill ratio
(77.4% in one case); when compositing, zoom in to check for white halos and shadow remnants. To fit it into
a series, crop the image to the reference's face width and center ratio.

## Talking UGC with a real UI on the phone screen

Edit: the talent talks while showing the phone to the camera. The screen shows the real app screen, not an
invented UI. Pipeline:

1. **Start frame (nano-banana-pro):** for the phone screen use "completely filled edge to edge with a flat,
   uniform, bright chroma-key green (pure #00FF00), matte and evenly lit, no reflections, no glare, no icons,
   no text; only the thin black bezel and a small black notch". Fingers only hold the edges.
   - 5/5 frames came out clean: green box fill 0.90 to 0.97, aspect 0.455 to 0.495 (UI 0.462).
   - Other frames of the same person are made with reference images (table above).
2. **Video:** image-to-video models kept the green screen across all frames. The phone is not held still;
   it moves naturally. "Scroll with the thumb" was ignored.
3. **Prep:** `prep_plate.sh`: `fps=30` (repeated frames; tracking runs on this file) + audio + STT + tracking.
4. **Tracking** (`screen_track.py`, numpy + PIL):
   - Edge assignment comes from the **mask's PCA axes on every frame**. A first version that looked at the
     previous frame's lines dropped 87 of 96 frames once motion passed 18 px/frame.
   - Lines are fitted to the mask's **convex hull**. Fitted to the mask itself, the top line sat under the
     notch and the corners ended up 17 px low.
   - **Temporal smoothing off:** on repeated 24 -> 30 fps frames a [1,2,1] filter shifted things ~10 px.
5. **Patch (RGBA):** frame, fingers and notch opaque; green transparent. Spill suppression:
   `g ≤ max(r,b)+6`. Alpha softened with a 0.8 px Gaussian; the green/black border was stepped on slanted
   edges.
6. **Remotion order** (`ScreenComposite`): shot -> dark screen backing (+9 px) -> perspective UI
   (Heckbert `matrix3d`, +2 px) -> patch.
   - Backing + UI are **clipped to the patch box**. Unclipped, a sliding UI showed as a line outside the
     phone.
   - Without the backing, 1 to 4 px of green stayed on the bottom edge (281 px); with it, 0.
7. **Motion blur:**
   - Draw the UI with sub-samples along the corner velocity of the two neighboring source frames × **0.3**
     (1/(k+1) opacity).
   - 0.3 was measured from the generated video's own blur: edge 10 to 90 width 3.75 px when still, 13 px
     at 35 px/frame. 180° (0.5) was too much.
   - The sub-sample spacing scales with zoom: ~1 px on screen, at most 16.
8. **Sharpness:** `blur(1.6px)` on the UI in UI units (the filter is in local space). Invisible at 1×,
   ~0.65 px at 2.9× zoom.
9. **Zoom timing:** extract the phone's speed profile and put the full zoom in a window where the phone is
   calm. The first timing once hit a fast moment and the shot's blur spread to the UI.
10. **If tracking drops (phone leaves the frame):** `--fill-from N` paints the green with the current
    screen's average color. A fast-dropping phone looked natural as a colored trail.

Measurement:
- Count pure chroma green in the delivered file (`g > 180`, `r, b < 90`). It should be 0 on every frame.
- The inner-edge dark ratio metric (`cover_check.py`) misleads when the quad is larger than the green.
  Zoom in at pixel level.

Audio:
- Match clips to −24 LUFS: generated clips differ by ±2 dB.
- Cut at pauses. A long pause is trimmed behind an insert shot; on return, video and audio continue
  together and lip sync holds.

Measured over talent variants of the same flow:
- **A model can burn in subtitles despite the negative prompt.** In one clip 203 of 240 frames had a
  broken, outlined two-line caption; the other 8 clips were clean.
  - Detection: per row, count "black stroke (<45) next to white fill (>235)" pairs. The text's top edge
    sat at y 1613 to 1615 on every frame.
  - Free fix: a top-focused 1.25× zoom on the 9:16 selfie (focus y 290; the face drops to 46%), and a
    240 to 1590 crop for 4:5. The text is out of frame everywhere. Regenerating would have cost far more.
  - Check every talking clip for this. It shows on a contact sheet.
- **"keeping it … up beside her face until the very end of the clip; she does not lower the phone"** held
  in every clip: 0 dropped tracking frames. Without it, the phone came down at 5.0 s.
- **A scroll did happen, but with the second hand** (index finger from below, fingers from the right).
  - When a finger passes in front of the screen the patch keeps it opaque; the UI stays behind the finger
    and looks like real use.
  - Tie the home scroll to the finger motion with keyframes.
  - Where the finger covered the edge, edge RMS rose to 41 px, but the hull bridged it and the quad stayed
    correct. A visual check is still required.
- Even with the same voice description in every clip, the F0 median moves 2 to 3 semitones from clip to
  clip (203/225/246 Hz).
- The model sometimes adds a word before the line ("And I spend…"). STT shows it; trim the start.
- **If a finger covers a screen corner, the hull edge bends.**
  - In one shot a green wedge opened at the opposite corner of the screen over 7 frames (30,689 px). It
    was caught by the green count on the delivered file.
  - The first fix, a despike filter that pulled the corner to the median, **was wrong.** It erased a real
    hand movement on 76 frames and the UI slid off the phone; the user noticed.
  - The right way: **use the window where no hand or finger enters in front of the screen.** Users also
    find a second hand reaching into the screen odd. Use the shot outside those frames and scroll the UI
    by itself.
- **Fit metric** (for the used frames of every tracked shot):
  - The count of green mask pixels outside the quad dilated by 2 px. A good fit has a median < 50, max ~200
    (edge softening).
  - The non-green ratio inside the screen shows hand/finger entry. The baseline is the notch or Dynamic
    Island and is constant.
- **verify's "saturated region" warning can fire on zoomed skin** (3.5 to 4.5).
  - To tell: convert the reference PNG losslessly (`-qp 0`) to yuv420p on the same path, decode back and
    measure the difference.
  - If the lossless frame also gives 1.5 to 2.3, the source is 4:2:0; CRF 17 adds ~2 on top. If the CTA and
    UI colors are ~2, the matrix is right.
  - Decode the lossless frame **with verify's own decoder** so the comparison is on the same scale (the
    decoder alone once added 3.4): see [07-qc](07-qc.md), checklist.
- **A model can reject the start frame** for usage-policy reasons.
  - The same face was rejected three times with different clothing, so the reason was not the clothing but
    the face: the prompt said "cute, young, mid-twenties" and the result looked very young.
  - The same scene with a **clearly adult** talent passed first time: "about 30, clearly a grown adult with
    mature facial features, side part, no bangs", with no "cute / young / sweet" in the prompt.
  - Do not try to get around the filter with small edits or another model. Make the talent clearly adult.
  - Whether rejected requests are billed is not always clear; note it in `PRODUCTION.md` and check the fal
    dashboard.
- **If the image prompt says "tripod", the model draws a tripod** ("filmed by a phone camera on a small
  tripod").
  - Use "filmed from her eye level with a perfectly still camera that is not visible", and end with
    "no tripod or camera equipment anywhere in the frame".
  - Regenerating the frame with itself as the reference brought the same person back without the tripod.
- **A second hand arrived despite "no other hand enters the frame"** (a hand pointing at the screen).
  - Detection: count skin pixels in the region right of the phone. Baseline 28 to 35k, 96 to 107k when the
    hand came in.
  - Take the shot from the window without the hand.
- A reference-based frame can copy the reference's wide framing even when the prompt says "tight medium
  close-up". Say it explicitly: "the camera is much closer than in the reference, do not reuse the
  reference's wide framing".
- **A talking-video model can invent braces.** The start frame had clean but slightly uneven teeth; while
  talking, the model completed them with brackets and later metal wire. The same talent's other clips were
  clean, so the talent had braces in some shots and not in others. The user noticed; the QC at the time
  (green, tracking, audio) did not look at the face.
  - **Default:** add "braces, dental braces, orthodontic brackets, retainer, metal wires on teeth" to the
    negative. Write "her teeth are natural, straight and white, with no braces" in the prompt. Make the start
    frame show clean teeth (or a closed mouth).
  - **Add to QC:** in every talking clip, compute mouth opening (height/width) from the outer lip points;
    crop the 12 to 60 most open frames onto one sheet and check: braces, missing or changing teeth, lip
    distortion.

## Inner-voice UGC: the talent does not speak

A cheaper, more controllable sibling of talking UGC. The talent lives with a closed mouth; the audio is
their inner voice (TTS VO), shown with word-by-word captions. No lip sync is needed, so a plain
image-to-video shot does the job. A 3-scene piece came out at less than half the cost of the talking UGC
flow. Keep timings in `src/timeline.ts`.

- **Generation:** talent -> reference-based scene frames (`ref_edit.py`) -> image-to-video. Prompt: "her lips
  stay closed the whole time: she does not speak and does not mouth words".
  - Negative: `talking, mouth opening, lips parting, teeth showing, speaking, mouthing words, braces,
    phone screen visible, second person`.
  - It held in all three shots. The in-shot std of the outer lip h/w ratio was ≤ 0.044, no speech motion.
  - One exception: lips parted slightly as the head lifted toward the sun. Teeth natural, no braces.
- **The phone screen should never be visible in the shot** (back to the camera, or held at the side). The UI
  comes in a separate phone mockup; no tracking or green screen needed.
- **Edit patterns (all in code, no cost):**
  - *UI moment:* the shot freezes (last frame as PNG, `Img`) and blurs (blur 22, scaled ×1.09 along with the
    blur so the edge does not darken). An opaque phone rises from out of frame. Inner screens change with an
    iOS push (`PhoneMock.tsx` `ScreenPush`).
  - *Time cut:* the blurred night frame crossfades into the blurred morning shot (warm light leak, screen
    blend). As the phone drops, the shot sharpens. The morning shot must already be playing underneath so it
    does not look frozen when it sharpens.
  - *Selection interaction:* the unselected state of the selected card is copied from the **neighboring
    unselected card** on the same screen (+264 px). The text box comes from the card itself. On tap it
    switches to the selected state in 3 frames. No invented UI, just two states of the real screen.
  - *Screen light on the face:* a face-centered radial gradient, soft-light 0.42. It changes color with each
    "new video", on the same frame as the scroll sound. At 0.55 an orange tone painted the face like lamp light.
  - *Time-skip gag:* a clock chip 2:07 AM -> 4:13 AM (32 frames, ease-in). A synthesized tick-tock in the
    night audio speeds up over the same span.
- **Caption placement:** top while the phone is on screen, bottom otherwise. If a sentence must be split,
  split it in two and switch zones between the parts ("And honestly?" top, "I feel so much better." bottom
  after the phone leaves).
- **Message trap:** do not show the phone during "my mornings start like this"; it reads as "my morning
  starts with my phone". Show the app's "Good morning" screen in the night -> morning transition, and keep
  the morning shot phone-free.
- **"Mouth closed" does not always hold** (the same prompt and negative worked in two series and failed in a
  third).
  - One night shot: the talent fell asleep after frame 60 and opened her mouth. One morning shot: she moved
    her mouth as if talking over frames 30 to 100.
  - On retry, night prompt: "wide awake… keeps her eyes open, fixed on the screen… never falls asleep… does
    not yawn". Morning prompt: "her lips stay gently pressed together… breathes in slowly through her nose".
    Added to the negative: `open mouth, lip movement, lip sync, smiling with teeth, yawning, falling asleep,
    sleeping, drinking`.
  - **Telling talking from smiling:** compute the outer lip h/w ratio per frame, subtract a 15-frame moving
    average and look at the std of the rest. Speech oscillates at 3 to 6 Hz; a smile is a slow trend.

    | Shot | Residual std | Peak to peak |
    |---|---|---|
    | Accepted shots | 0.0079 to 0.0115 | 0.04 to 0.055 |
    | A talking shot | 0.0184 | 0.105 |

    The raw ratio range misleads: a smiling retake ranged 0.31 to 0.58, the same as the accepted ones.
  - **The metric only works on an upright face.** On faces lying sideways at night the landmarks are noisy:
    closed-mouth night shots gave 0.0165 to 0.0178, an open-mouth sleeping shot 0.0137. Check lying faces by
    eye on `plate_qc.py`'s face/mouth crop sheet (every 5 frames).
  - `scripts/plate_qc.py` does all of this: face box (4:5 crop, light/push center), ratio, oscillation and
    crop sheets.
- **The mouth often opens after a while; the first second is clean** (4 of 5 shots in one series). Opening
  frames: 20 (at a table, 3/4 face), 33 (breakfast), 44 (park, a "wow" mouth), 59 slightly / 78 open (night).
  One bus shot stayed closed throughout.
  - Before regenerating, try a **rescue window**: find the closed range from `plate_qc.py`'s per-frame ratio
    and mouth crops. If it is short, stretch it with motion-interpolated slow motion from the 24 fps source:
    `scripts/slow_clip.sh <name> <source> <t0> <t1> <speed>`. 0.5 to 0.6× caused no face distortion.
  - Build the edit around this: short cuts that use the start of each shot (1 to 1.3 s), longer moments in
    slow motion.
- **Hand-object actions often fail** ("turns the phone face down and puts it down": the hand hovered over the
  phone, the phone stayed face up, the mouth opened as if talking). Build such actions in code
  ([02-remotion](02-remotion.md#flipping-the-phone-over-in-code)) and show only the result in the shot; keep
  the face-up phone out of frame with a zoom.
- **A "phone's point of view" frame:** with "she holds the phone above her face" the image model draws the
  phone and the hands. Describe the camera position without a phone: "extreme close-up taken from directly
  above her face… lit only by a cold glow coming from exactly where the camera is… nothing is between her face
  and the camera: no phone, no screen, no hands, no arms".
  - The video model may still add a phone (one came down from the top with a fake UI). Measure the top and
    bottom edges with frame differences on every shot and choose the usable window and zoom from that.
- **A better closed-mouth wording:** "Her lips stay softly pressed together the whole time… she breathes slowly
  through her nose… does not react / does not laugh / does not gasp", negative `smiling with teeth, surprised
  expression, gasping`. 3 of 10 shots were closed throughout (oscillation 0.004 to 0.007); the others were
  closed for 1 to 3 s. Smiles while looking out of a window turn into toothy laughs.

## Mascot story: the app's 3D mascot -> scene -> video

The app's own 3D mascot (the renders in its UI) becomes the story's lead. Cost: 5 scenes × one image +
5 short shots.

- **Reference cut-outs:** cut every pose of the mascot from UI screenshots.
  - A white cloud on a cream background cannot be found automatically by color difference (< 20). Pick boxes
    by hand from a frame with a 100 px grid.
  - On a purple background a density threshold works: > 90 white pixels per row/column. With a threshold of 12
    the sparkles inflated the box.
- **Scene frame:** give the edit model two references and say which is which.
  - Reference 1 is identity (the mascot's clearest, largest render), reference 2 the pose.
  - "Keep the character's proportions, face and colors exactly like the references; do not add a nose,
    eyebrows, teeth, fingers…"
  - The same style sentence (pastel 3D world, clay material) in all five frames; the top third left empty for
    text.
  - The mascot stayed consistent with the UI design in all five frames.
- **Video:** the mascot was not distorted in any of the five shots (dot eyes, cheeks, number of lobes kept).
  - Negative: `morphing, melting, deformation, shape change, extra limbs, extra eyes, nose, eyebrows, teeth,
    fingers, human hands`.
  - A timed instruction ("lifts its head at ~3 s") arrived ~1.2 s late. Align by shifting the source start.
- **From the scene to the real UI screen:**
  - Measure the mascot box in the shot and in the UI screen. Screen scale S0 = width ratio; position makes the
    two centers coincide.
  - The phone pulls back from this pose, then shrinks into the packshot icon.
  - If the poses are not identical (arms up in the video), switch at the peak of a transition (a puff).
- **Cloud puff transition (`PuffWipe`):** 15 cloud silhouettes on a 3×5 grid (4 circles each: main + two
  sides + top).
  - Scale `1.3 t^1.5`, t = 1 − |u|/5. The frame is fully covered for only 3 frames, cut in the middle.
  - In the first version single circles looked like bubbles and the frame stayed flat white for 8 frames.
- **Music ducking:** with dense, playful music (−15 LUFS) about 6 dB under the speech, the VO correlation
  dropped to 0.77 to 0.92.
  - −4 dB ducking under every VO line (4-frame ramp) keeps speech ~9 dB on top; between lines the music stays
    lively.

## Talking selfie with native audio, in two parts

- Single-pass talking video with lip sync: use a model that generates audio (Veo with
  `generate_audio=true`, check `fal schema`). If a model caps duration (8 s for Veo), split long speech into
  two parts: **the first frame of part two is the last frame of part one** (that frame is skipped when
  joining). Identity, place and light stayed continuous.
- Write the dialogue **in quotes** and put the gestures between the sentences in order ("touches her
  eyebrow… says: '…'"). STT returned the text verbatim both times. Gesture timing can shift 1 to 2 s from
  the words. Tie UI events to STT word starts, not to gestures.
- Add "music" to the negative prompt. The output then has speech + room tone, no music.
- **Voice consistency:** the two parts are generated separately, so the voice can change. Measure it: speech
  band envelope correlation between halves within a part (0.871 / 0.898 -> the same voice). If it changes,
  pull both onto one voice with a voice changer (for example `fal-ai/elevenlabs/voice-changer`).
  - **The whole part misleads.** Part two had laughter and excitement, which raises the F0 of the whole part
    by 11 to 22%. Compare **similar sentences, outside laughter**, for example "Okay, this app says…" with
    "Okay, that's scary accurate"; cut by STT word times. Approved example: F0 214 -> 203 Hz, envelope 0.926.
    Variants: F0 −6% to +11%, envelope 0.924 to 0.955. All the same voice.
  - Method: 4096 FFT, 1/3 octave (100 Hz to 8 kHz), frames in the upper half of energy, dB envelope. F0 by
    autocorrelation (75 to 400 Hz). With 1/6 octave and a 1920 FFT the low bands are empty and the result is NaN.
- **Lock frames:** since part two's first frame is skipped, the composition time of a word in part two is
  `8 − 1/24 + t` s. Frame = `round(time × 30)` (all four locks landed within ±0.5 frame of the STT word start).
- **Variants in parallel:** submit all part ones together (`--no-wait`). When each finishes, submit its part
  two from its last frame. All parts were usable first time; ~10 minutes in total.
- It may add extra audio at the end ("Um"): find it with STT and cut it. Level differences between parts
  (2.5 dB) and laughter peaks: match per part, `prelimit.sh` -> `deliver_png.sh --audio`.

## Expressive look with lip motion, no speech (10 s image-to-video)

- Worked first time. Prompt body:
  - a fixed front camera, framing never changes;
  - throughout, a "sultry, confident, smoldering gaze" into the lens, chin slightly down, eyelids slightly
    lowered;
  - in order: "soft pout -> relaxes -> gently bites her lower lip -> slow kiss-pout -> small confident smirk with
    closed lips", "no talking";
  - small natural movements (blinks, head tilt, breathing).
- Negative: talking, mouth wide open, wide smile, camera movement, hands, phone, text. **Do not write "teeth"**:
  the lip bite needs teeth to show.
- Resulting timeline (24 fps, 10.04 s):
  - 0 to 2.5 s tilted head and pout;
  - 3 to 5 s bite;
  - 6 to 7.5 s kiss;
  - smirk after 8.5 s.
  - Two blinks, no speech.
- In the start image write "lips closed in a soft relaxed pout, no smile". The video model starts the motion
  from that pose, and the first frame becomes the hook.
