---
name: fal
description: All image, video, voice (TTS), transcription and reference-video analysis runs on fal.ai through the `fal` command. Read this before any generation, model choice or cost question, and for "analyze this ad and make one like it" requests.
---

# Generating with fal.ai (the `fal` command)

The `FAL_KEY` is already in the environment. Do not ask the user for it and never print it.

## Commands

    fal models <search> [--category image-to-video]   # find endpoint ids: fal models seedance
    fal schema <endpoint_id>                           # fields, required fields, options, price
    fal run <endpoint_id> key=value ... [--out DIR] [--name NAME] [--no-wait]
    fal wait <request_id> [--out DIR] [--name NAME]
    fal upload <file>                                  # local file -> fal CDN URL
    fal analyze <video> [--prompt "extra request"] [--model google/gemini-2.5-pro]
    fal ask "<question>" --image frame.jpg             # quick vision question
    fal cost                                           # estimated spend for this job

- Every `run` checks the live schema first. A wrong field name, a missing required field or an
  invalid option fails before any money is spent. When unsure, run `fal schema <endpoint_id>`.
- Outputs download automatically: video to Shots/, images to Asset/, audio to Audio/. Use `--out`
  to change that. Output lines look like `SAVED <path>`, `url: <fal CDN>`, `cost: $X (est.)`.
- Spend is logged to Logs/fal.csv. LLM calls log their exact cost; media costs are estimates from
  fal's unit prices. Do not ask for approval over cost.
- Video takes 1 to 10 minutes. The command waits on its own (up to ~9.5 min). If it says "Still
  running", run the `fal wait ...` line it printed. For several shots at once, submit each with
  `--no-wait`, then `fal wait` each request id.

## Files and URLs

Models take input files as URLs (`image_url`, `image_urls`, `video_urls`, `audio_url`).
- Pass a local path (`image_url=Asset/talent.png`) and `fal` uploads it to the fal CDN.
- Files that `fal` produced reuse their CDN URL, so chains like image -> video need no upload.
- Several values are comma separated: `image_urls=Asset/a.png,Asset/b.png`.
- JSON-shaped fields go through `--json '{"voice_setting": {"voice_id": "Wise_Woman"}}'`.

## Default models (unless the user asks for something else)

| Job | Default | Alternatives |
|---|---|---|
| Talent or scene still | `fal-ai/nano-banana-pro` | `google/nano-banana-2-lite` (cheap), `bytedance/seedream/v5/pro/text-to-image` |
| Edit with reference images | `fal-ai/nano-banana-pro/edit` (image_urls) | `fal-ai/nano-banana-2/edit`, `bytedance/seedream/v5/pro/edit` |
| Image to video | `bytedance/seedance-2.0/image-to-video` | `fal-ai/kling-video/v3/pro/image-to-video`, `fal-ai/veo3/fast/image-to-video`, `bytedance/seedance-2.0/fast/image-to-video` |
| Text to video | `bytedance/seedance-2.0/text-to-video` | `fal-ai/veo3/fast`, `fal-ai/kling-video/v3/pro/text-to-video` |
| Reference to video (same person or product) | `bytedance/seedance-2.0/reference-to-video` | `fal-ai/kling-video/o3/pro/reference-to-video` |
| Voiceover | `fal-ai/minimax/speech-2.8-hd` (output_format=url) | `fal-ai/elevenlabs/tts/eleven-v3`, `fal-ai/minimax/speech-2.8-turbo` |
| Voice design | `fal-ai/minimax/voice-design` | |
| Word-timed transcript | `fal-ai/elevenlabs/speech-to-text/scribe-v2` | `fal-ai/wizper` (chunk_level=word) |
| Forced alignment (script to audio) | `fal-ai/elevenlabs/forced-alignment` | |
| Sound effects | `fal-ai/elevenlabs/sound-effects/v2` | |
| Music bed | `fal-ai/elevenlabs/music` | |
| Reference ad breakdown | `fal analyze` | `--model google/gemini-2.5-pro` for a deeper read |

Notes:
- Seedance 2.0: `duration` is "4" to "15" or "auto", `resolution` 480p/720p/1080p/4k,
  `aspect_ratio=9:16` for vertical. Pass `generate_audio=false`: we build the audio ourselves.
- Not every image model offers 9:16. Check `aspect_ratio` in `fal schema`; if missing, make 3:4 or
  4:5 and crop in Remotion.
- If an endpoint id fails, find the current one with `fal models <word>`. Never guess an id that is
  not in the catalog.

## "Analyze this ad and make one like it"

1. Run `fal analyze Ref.Videos/<file>`. The breakdown goes to Brief/reference-analysis.md and contact
   sheets to Work/analysis-*/. Look at the contact sheets yourself with Read.
2. Merge the user's changes (app, talent, language, length, tone) with the breakdown into a short
   shot plan: per shot the duration, AI shot or Remotion layer, and the model. Show the plan in a
   few lines and move straight on to production.
3. Generate: talent and scene stills first, then image-to-video, then VO if needed. Check every
   output yourself (Read for images; for video grab frames with ffmpeg and Read them). Fix the
   prompt and regenerate anything that is off.
4. Assemble in Remotion: text, UI, transitions, captions and the packshot are built in code (see the
   app-ad-video skill). Run `npm install` in the job folder before the first render.
5. Deliver to Final/: H.264, yuv420p, BT.709, AAC, following the app-ad-video delivery rules. Then
   report the file name in Final/, its duration and the total cost (`fal cost`).

Never copy licensed music, a competitor's logo or original characters. Take the concept and the
structure, not the brand.
