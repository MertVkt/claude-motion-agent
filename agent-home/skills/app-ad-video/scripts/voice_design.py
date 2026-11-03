#!/usr/bin/env python3
"""voice_design.py: design a voice from a text description on fal.ai (MiniMax Voice Design).

    voice_design.py --desc "..." --text-file Work/vo_script.txt --out-dir Audio/design [--count 3] [--tag v1]

- Calls fal-ai/minimax/voice-design. The preview text is the ad's own VO script, so every preview is the
  same script read by a different designed voice. Run it --count times and compare.
- Each preview returns a `custom_voice_id`. Use it with fal-ai/minimax/speech-2.8-hd
  (voice_setting={"voice_id": "<id>", ...}) to read the final script in that voice.
- Output: <out-dir>/<tag>_p1..pN.<ext> + <tag>_design.json (voice ids, description, text).
- Paid. The cost of each call goes to Logs/fal.csv. Needs FAL_KEY in the environment.
"""
import argparse, json, os, sys, urllib.parse

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _fal import call, fetch  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--desc", required=True, help="voice description: age, gender, accent, tone, pace")
    ap.add_argument("--text-file", required=True, help="preview text, ideally the real VO script")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--count", type=int, default=3, help="number of voices to design")
    ap.add_argument("--tag", default="design")
    a = ap.parse_args()
    text = open(a.text_file).read().strip()
    if not text:
        sys.exit("the preview text is empty")
    os.makedirs(a.out_dir, exist_ok=True)
    meta = {"endpoint": "fal-ai/minimax/voice-design", "desc": a.desc, "text": text, "previews": []}
    for i in range(1, a.count + 1):
        d = call("fal-ai/minimax/voice-design", {"prompt": a.desc, "preview_text": text})
        audio = (d.get("audio") or {}).get("url")
        vid = d.get("custom_voice_id")
        entry = {"voice_id": vid, "file": None}
        if audio:
            ext = os.path.splitext(urllib.parse.urlparse(audio).path)[1] or ".mp3"
            entry["file"] = fetch(audio, os.path.join(a.out_dir, f"{a.tag}_p{i}{ext}"))
        meta["previews"].append(entry)
        print(f"{entry['file'] or '(no audio)'}  voice_id {vid}")
    json.dump(meta, open(os.path.join(a.out_dir, f"{a.tag}_design.json"), "w"), ensure_ascii=False, indent=1)
    print(f"-> {os.path.join(a.out_dir, a.tag + '_design.json')}")


if __name__ == "__main__":
    main()
