#!/usr/bin/env python3
"""Cut source footage into light 1080x1920 SDR H.264 clips with handles, and write clips.json.

usage: python3 cut_clips.py <segments.json> <raw_footage_dir> <shared_dir> [--handle 0.5]

segments.json: {"<group>": [["<clip_name>", "<source file>", <in_seconds>, <duration>, {optional: "eq": "<ffmpeg eq args>"}], ...]}
- Every clip gets `handle` seconds of extra source before/after (needed for whips, shifts and hit-sync).
- iPhone HLG/HDR sources are detected and tagged/graded as BT.709 so Tesseract renders them SDR.
- Audio and video lengths are matched exactly (Tesseract renders mismatched files blank).
"""
import json, os, subprocess, sys

def probe(path, entries):
    out = subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", entries, "-of", "csv=p=0", path]).decode()
    return out.strip().splitlines()[0].strip().strip(",") if out.strip() else ""

def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    handle = float(sys.argv[sys.argv.index("--handle") + 1]) if "--handle" in sys.argv else 0.5
    if len(args) < 3:
        sys.exit(__doc__)
    segs = json.load(open(args[0])); raw = args[1]; shared = args[2]
    out = os.path.join(shared, "clips"); os.makedirs(out, exist_ok=True)
    info = {}
    meta = {}
    jobs = []
    for group, lst in segs.items():
        for item in lst:
            name, src, t, d = item[:4]
            opts = item[4] if len(item) > 4 else {}
            path = os.path.join(raw, src)
            if src not in info:
                dur = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path]).decode())
                fr = probe(path, "stream=r_frame_rate"); num, den = (fr.split("/") + ["1"])[:2]
                fps = 60 if float(num) / float(den) > 45 else 30
                hlg = "arib-std-b67" in probe(path, "stream=color_transfer")
                has_audio = bool(subprocess.check_output(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index", "-of", "csv=p=0", path]).decode().strip())
                info[src] = (dur, fps, hlg, has_audio)
            dur, fps, hlg, has_audio = info[src]
            a = max(0.0, t - handle); b = min(dur - 0.05, t + d + handle)
            n = int((b - a) * fps); L = n / fps
            vf = "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1"
            if opts.get("eq"): vf += ",eq=" + opts["eq"]
            if hlg: vf += ",eq=contrast=1.06:saturation=1.08"
            vf += ",setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709,fps=%d" % fps
            cmd = ["ffmpeg", "-v", "error", "-y", "-ss", str(a), "-i", path, "-t", "%.6f" % L, "-map", "0:v:0"]
            if has_audio:
                cmd += ["-map", "0:a:0", "-af", "apad,atrim=0:%.6f" % L, "-c:a", "aac", "-b:a", "192k", "-ac", "2", "-ar", "48000"]
            cmd += ["-vf", vf, "-frames:v", str(n), "-c:v", "libx264", "-preset", "fast", "-crf", "17", "-pix_fmt", "yuv420p", "-bf", "0",
                    "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", os.path.join(out, name + ".mp4")]
            jobs.append(cmd)
            meta[name] = {"src": src, "srcIn": t, "dur": d, "handle": round(t - a, 3), "fileDur": round(L, 3)}
    procs = []
    for c in jobs:
        procs.append(subprocess.Popen(c))
        if len(procs) >= 4: procs.pop(0).wait()
    for p in procs: p.wait()
    path = os.path.join(shared, "clips.json")
    old = json.load(open(path)) if os.path.exists(path) else {}
    old.update(meta)
    json.dump(old, open(path, "w"), indent=1)
    print(f"{len(meta)} clips -> {out}")

if __name__ == "__main__":
    main()
