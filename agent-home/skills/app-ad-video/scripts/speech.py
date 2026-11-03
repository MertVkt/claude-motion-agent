#!/usr/bin/env python3
"""speech.py: speech tools on fal.ai. Reference transcripts (STT) and voiceover alignment.

    speech.py stt   <audio_or_video> <out.json> [--lang en]      word-timed transcript
    speech.py align <vo.mp3|wav> "<full script>" <out.json>       forced alignment: word timings
    speech.py words <out.json>                                    print the word list (free)

- Does the reference have speech? Do not judge by RMS, ask STT. If there is no speech (for example only
  "[upbeat music]"), the message is carried by on-screen text and music, so do not generate a VO.
- Caption timing comes from forced alignment, never typed by hand (karaoke style: the highlight follows
  the spoken word, in groups of 2-3 words). Without alignment, split word durations by syllable weight.
- Video input is converted to 16 kHz mono WAV first, then uploaded to the fal CDN.
- STT: fal-ai/elevenlabs/speech-to-text/scribe-v2 (falls back to fal-ai/wizper with word chunks).
  Alignment: fal-ai/elevenlabs/forced-alignment. Both are paid (small); cost goes to Logs/fal.csv.
- Output JSON keeps the shape {"text": ..., "words": [{"text", "start", "end", "type": "word"}, ...]}.
Needs FAL_KEY in the environment.
"""
import json, os, subprocess, sys, tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _fal import call, upload  # noqa: E402


def _audio(path, tmp):
    if path.lower().endswith((".mp3", ".wav", ".m4a")):
        return path
    out = os.path.join(tmp, os.path.splitext(os.path.basename(path))[0] + "_16k.wav")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", path, "-vn", "-ac", "1", "-ar", "16000",
                    "-c:a", "pcm_s16le", out], check=True)
    return out


def words(d):
    for w in d.get("words", []):
        if w.get("type", "word") == "word":
            print(f"  {w['start']:7.3f}-{w['end']:7.3f}  {w['text']}")


def stt(src, lang, tmp):
    url = upload(_audio(src, tmp))
    inp = {"audio_url": url, "diarize": False, "tag_audio_events": True}
    if lang:
        inp["language_code"] = lang
    try:
        d = call("fal-ai/elevenlabs/speech-to-text/scribe-v2", inp)
        if d.get("words") is not None:
            return d
    except SystemExit as e:
        print(f"  scribe-v2 failed ({e}), trying wizper", file=sys.stderr)
    inp = {"audio_url": url, "chunk_level": "word", "task": "transcribe"}
    if lang:
        inp["language"] = lang
    r = call("fal-ai/wizper", inp)
    ws = []
    for c in r.get("chunks") or []:
        ts = c.get("timestamp") or [None, None]
        if ts[0] is None:
            continue
        ws.append({"text": c.get("text", "").strip(), "start": float(ts[0]),
                   "end": float(ts[1] if ts[1] is not None else ts[0]), "type": "word"})
    return {"text": r.get("text", ""), "words": ws, "source": "wizper"}


def main():
    if len(sys.argv) < 3 or sys.argv[1] in ("-h", "--help"):
        sys.exit(__doc__)
    cmd = sys.argv[1]
    if cmd == "words":
        words(json.load(open(sys.argv[2])))
        return
    with tempfile.TemporaryDirectory() as tmp:
        if cmd == "stt" and len(sys.argv) >= 4:
            src, out = sys.argv[2], sys.argv[3]
            lang = sys.argv[sys.argv.index("--lang") + 1] if "--lang" in sys.argv else None
            d = stt(src, lang, tmp)
            json.dump(d, open(out, "w"), ensure_ascii=False, indent=1)
            print("TEXT:", d.get("text"))
            words(d)
        elif cmd == "align" and len(sys.argv) >= 5:
            src, text, out = sys.argv[2], sys.argv[3], sys.argv[4]
            d = call("fal-ai/elevenlabs/forced-alignment", {"audio_url": upload(_audio(src, tmp)), "text": text})
            for w in d.get("words", []):
                w.setdefault("type", "word")
            json.dump(d, open(out, "w"), ensure_ascii=False, indent=1)
            print(f"OK {out}  {len(d.get('words', []))} words  loss={d.get('loss')}")
            words(d)
        else:
            sys.exit(__doc__)


if __name__ == "__main__":
    main()
