# claude-motion-agent

A motion design agent for app ads, built on Claude and fal.ai.

Drop a reference ad into the dashboard and describe what you want. The agent breaks the ad down shot by
shot, generates the live-action shots, voiceover and sound on fal.ai, builds the text, UI and transitions
in Remotion code, checks its own work and delivers a platform-ready master.

```
reference ad ──► fal analyze ──► shot plan ──► fal run (stills, video, VO, SFX)
                                                     │
            Final/master.mp4 ◄── deliver + QC ◄── Remotion composition
```

It runs on your own machine. Your footage stays local; only the files a model needs are uploaded to fal.

## What is inside

| Part | What it does |
|---|---|
| `dashboard/` | Local web app (Node, Claude Agent SDK). One chat per job, live tool log, drag-and-drop uploads, a media panel with every shot, still and render, and the job's estimated fal spend. |
| `tools/fal.py` | The `fal` command the agent uses: search the model catalog, read live input schemas, run and wait for jobs, upload files, analyze reference videos, ask vision questions, track cost. Standard library only. |
| `agent-home/` | The agent's brain: working rules, the `app-ad-video` skill (reference breakdown, Remotion craft, AI generation recipes, faces and shot plans, audio, delivery, QC, known pitfalls) and the `fal` skill. |
| `project-template/` | Remotion project every new job starts from: formats, safe areas, smoke test. |
| `plugins/reel-studio/` | A separate Claude Code plugin for effect-heavy vertical reels from raw footage. See below. |

## Requirements

- Node 18+, Python 3.9+, ffmpeg
- An Anthropic API key for the agent ([console.anthropic.com](https://console.anthropic.com/settings/keys))
- A fal.ai key for generation ([fal.ai/dashboard/keys](https://fal.ai/dashboard/keys))

macOS and Linux both work. Three optional face, OCR and collage helpers use Apple's Vision framework and
only build on macOS; everything else falls back to ffmpeg and vision models.

## Quick start

```bash
git clone https://github.com/MertVkt/claude-motion-agent.git
cd claude-motion-agent/dashboard
npm install
npm start
```

The dashboard opens at http://localhost:3333. Paste your fal.ai and Anthropic keys in the top right; they
are tested and saved to `.env` in the repo root (never committed).

Then:

1. Click **New job** and give it an app name. A job folder with the Remotion template is created under
   `projects/`.
2. Drop a reference ad onto the page.
3. Tell the agent what you want, for example:
   *"Analyze this and make a similar 20 second ad for MyApp. The talent is a woman in her thirties, voiceover in English, end on the app's paywall."*
4. Watch it work. Shots, stills and renders show up on the right; the delivery lands in `Final/`.

## The `fal` command

The agent calls it on its own, but it works from any terminal too (`export FAL_KEY=...`):

```bash
python3 tools/fal.py models seedance                       # find endpoint ids
python3 tools/fal.py schema bytedance/seedance-2.0/image-to-video
python3 tools/fal.py run fal-ai/nano-banana-pro prompt="a runner at dawn, 35mm" aspect_ratio=9:16
python3 tools/fal.py run bytedance/seedance-2.0/image-to-video \
    image_url=Asset/runner.png prompt="slow push in" duration=5 aspect_ratio=9:16 generate_audio=false
python3 tools/fal.py analyze Ref.Videos/reference.mp4
python3 tools/fal.py cost
```

Every run is validated against the model's live schema before it is submitted, so a typo in a field
name or an invalid option fails before you pay for it. Local files passed to `*_url` fields are uploaded
to the fal CDN automatically, and anything `fal` generated reuses its URL, so image to video chains need
no extra upload.

Default models, all swappable:

| Job | Default |
|---|---|
| Stills | `fal-ai/nano-banana-pro` |
| Edits with references | `fal-ai/nano-banana-pro/edit` |
| Image to video | `bytedance/seedance-2.0/image-to-video` |
| Text to video | `bytedance/seedance-2.0/text-to-video` |
| Reference to video | `bytedance/seedance-2.0/reference-to-video` |
| Voiceover | `fal-ai/minimax/speech-2.8-hd` |
| Word-timed transcripts | `fal-ai/elevenlabs/speech-to-text/scribe-v2` |
| Video analysis | `openrouter/router/video` with `google/gemini-2.5-flash` |

## How a job is organized

```
projects/MyApp/APP101-AI/
├── Brief/        brief and reference-analysis.md
├── Ref.Videos/   reference ads you uploaded
├── Asset/        generated stills
├── Shots/        generated video shots
├── Audio/        VO, music, SFX
├── Work/         renders and intermediate cuts
├── Final/        delivery masters
├── Logs/         fal.csv spend log
└── src/          Remotion compositions
```

## reel-studio plugin

A Claude Code plugin that turns raw action footage (sports, fitness, dance, events, product demos) into
punchy 1080x1920 reels for Instagram, TikTok and Shorts. Each reel is a short Python spec of shots, effects
(whip pans, RGB split, glitch, impact punches, zoom-through, flashes, slow motion), text cards and an end
card. The spec becomes an editable Mirage Tesseract project that renders locally. It finds real hits in
the clip audio and slides each shot so they land on the music's beats, and if a shot is missing it can
generate one on fal.ai.

Install it as a Claude Code plugin straight from this repo:

```bash
claude plugin marketplace add MertVkt/claude-motion-agent
claude plugin install reel-studio@claude-motion-agent
```

Or run `bash plugins/reel-studio/install.sh` to also install its tools (ffmpeg, Tesseract, HyperFrames).

## Configuration

All optional, in `.env`:

| Variable | Default | Purpose |
|---|---|---|
| `MA_PORT` | `3333` | Dashboard port |
| `MA_LANGUAGE` | `English` | Language of reference analyses |
| `MA_ANALYSIS_MODEL` | `google/gemini-2.5-flash` | Model behind `fal analyze` and `fal ask` |
| `MA_THINKING` | `off` | Extended thinking for the agent |
| `ANTHROPIC_BASE_URL`, `ANTHROPIC_AUTH_TOKEN` | | Use a gateway instead of a direct key |

## Costs and safety

- Generation is billed by fal.ai to your account. The dashboard shows an estimated per-job total from
  fal's price list; your fal dashboard has the exact figure.
- The agent only writes inside the current job's folder and the temp folder.
- Keys live in `.env` with `600` permissions and are passed to the agent as environment variables.
  Nothing in this repo contains or logs a key.
- The agent is told never to copy a competitor's logo, licensed music or original characters. It takes
  the structure of a reference, not the brand.

## License

MIT. Fonts in `plugins/reel-studio/fonts` are under the SIL Open Font License.
