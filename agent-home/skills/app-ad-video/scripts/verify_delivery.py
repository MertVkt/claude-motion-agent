#!/usr/bin/env python3
"""verify_delivery.py: measure the DELIVERED file (not what you think you rendered).

    verify_delivery.py <Final/a.mp4> [<b.mp4> ...] [--dur 15] [--fps 30] [--ref-dir DIR]
                       [--platform meta|tiktok|youtube|google] [--lufs -14] [--tp -1]

Checks (all must pass):
  video   H.264 High, yuv420p, four tags tv/bt709/bt709/bt709, mp4 colr nclx 1/1/1 full-range 0,
          SPS VUI 1/1/1/0 (trace_headers), frame count = duration*fps, video and container duration = --dur
  audio   AAC 48 kHz stereo, integrated loudness --lufs +-0.5, true peak <= --tp, NOT SILENT
  file    +faststart (moov before mdat), platform size limit (meta 250, tiktok 280, google 200 MB)
  color   if --ref-dir exists (deliver_png.sh writes f_<n>.png): each reference frame is decoded by the
          file's TAGS; whole-frame mean absolute difference < 2.5 and <= 3.5 in the SATURATED region
          (chroma >= 100, at least 2000 pixels). A whole-frame mean hides matrix errors (an error that
          showed as 1.3 overall was 6.8 on the CTA); the correct pipeline gives about 2.5 on the CTA.
          Small saturated areas (thin flag stripes, 4:2:0 edge softening ~3.7) are reported for info only.
Without --dur, frame count / video / container durations are checked against each other.
Exit code 0 = everything passed.
"""
import argparse, glob, json, os, re, statistics as st, subprocess, sys

LIMITS = {"meta": 250, "tiktok": 280, "google": 200, "youtube": None}


def sh(*a):
    return subprocess.run(a, capture_output=True, text=True).stdout.strip()


def raw(a):
    return subprocess.run(a, capture_output=True).stdout


def colr(p):
    d = open(p, "rb").read(); i = d.find(b"colr")
    if i < 0 or d[i + 4:i + 8] != b"nclx":
        return "none"
    g = lambda o: int.from_bytes(d[i + o:i + o + 2], "big")
    return f"{g(8)}/{g(10)}/{g(12)}/full{d[i + 14] >> 7}"


def vui(p):
    t = subprocess.run(["ffmpeg", "-v", "debug", "-i", p, "-c", "copy", "-bsf:v", "trace_headers", "-frames:v", "1",
                        "-f", "null", "-"], capture_output=True, text=True).stderr
    v = {k: (re.search(k + r"\s+\S+\s+=\s+(\d+)", t) or [None, "?"])[1]
         for k in ("colour_primaries", "transfer_characteristics", "matrix_coefficients", "video_full_range_flag")}
    return f"{v['colour_primaries']}/{v['transfer_characteristics']}/{v['matrix_coefficients']}/full{v['video_full_range_flag']}"


def dec(f, n):
    return raw(["ffmpeg", "-v", "error", "-i", f, "-vf", f"select='eq(n\\,{n})',format=rgb24", "-fps_mode", "passthrough",
                "-frames:v", "1", "-f", "rawvideo", "-"])


def png(p):
    return raw(["ffmpeg", "-v", "error", "-i", p, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"])


def check(f, a):
    tag = os.path.basename(f)[:-4]
    v = json.loads(sh("ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames", "-show_entries",
                      "stream=pix_fmt,color_range,color_primaries,color_transfer,color_space,nb_read_frames,duration,profile,r_frame_rate",
                      "-of", "json", f))["streams"][0]
    aus = json.loads(sh("ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries",
                        "stream=codec_name,sample_rate,channels", "-of", "json", f))["streams"]
    cont = float(sh("ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", f))
    vdur = float(v["duration"]); nfr = int(v["nb_read_frames"])
    num, den = v["r_frame_rate"].split("/"); fps = int(num) / int(den)
    fails = []
    tags = "/".join(v.get(k, "?") for k in ("color_range", "color_primaries", "color_transfer", "color_space"))
    c, u = colr(f), vui(f)
    if v["pix_fmt"] != "yuv420p": fails.append(f"pix_fmt {v['pix_fmt']}")
    if tags != "tv/bt709/bt709/bt709": fails.append(f"tags {tags}")
    if c != "1/1/1/full0": fails.append(f"colr {c}")
    if u != "1/1/1/full0": fails.append(f"VUI {u}")
    if v.get("profile") != "High": fails.append(f"profile {v.get('profile')}")
    if abs(fps - a.fps) > 1e-3: fails.append(f"fps {fps:g}")
    if a.dur is not None:
        want = round(a.dur * a.fps)
        if nfr != want: fails.append(f"frames {nfr} (expected {want})")
        if abs(vdur - a.dur) > 1e-3: fails.append(f"video duration {vdur:.6f}")
        if abs(cont - a.dur) > 0.002: fails.append(f"container duration {cont:.6f}")
    else:
        if abs(nfr / a.fps - vdur) > 1e-3 or abs(cont - vdur) > 0.022:
            fails.append(f"durations disagree: {nfr} frames, video {vdur:.6f}, container {cont:.6f}")
    au = f"{aus[0]['codec_name']}/{aus[0]['sample_rate']}/{aus[0]['channels']}" if aus else "NONE"
    lufs = tp = None
    if au != "aac/48000/2": fails.append(f"audio {au}")
    if aus:
        ln = subprocess.run(["ffmpeg", "-hide_banner", "-i", f, "-af", "loudnorm=I=-14:TP=-1:LRA=11:print_format=json",
                             "-f", "null", "-"], capture_output=True, text=True).stderr
        j = json.loads(re.findall(r"\{[^{}]*input_i[^{}]*\}", ln, re.S)[-1])
        lufs, tp = float(j["input_i"]), float(j["input_tp"])
        if lufs < -60: fails.append("audio is SILENT")
        elif abs(lufs - a.lufs) > 0.5: fails.append(f"LUFS {lufs:.2f}")
        if tp > a.tp: fails.append(f"peak {tp:.2f} dBTP")
    head = open(f, "rb").read(400000); mo, md = head.find(b"moov"), head.find(b"mdat")
    fast = mo != -1 and (md == -1 or mo < md)
    if not fast: fails.append("no faststart")
    mb = os.path.getsize(f) / 1048576
    lim = LIMITS.get(a.platform) if a.platform else None
    if lim and mb > lim: fails.append(f"size {mb:.1f} MB > {lim} MB")
    print(f"{os.path.basename(f)}")
    print(f"   {v['pix_fmt']} {tags} | colr {c} | VUI {u} | {v.get('profile')} | {nfr} frames @ {fps:g} | video {vdur:.6f} "
          f"container {cont:.6f} | {au} | " + (f"LUFS {lufs:.2f} peak {tp:.2f}" if lufs is not None else "no audio")
          + f" | faststart {'yes' if fast else 'NO'} | {mb:.2f} MB")
    rdir = a.ref_dir or f"Work/ref_{tag}"
    refs = sorted(glob.glob(os.path.join(rdir, "f_*.png"))) if os.path.isdir(rdir) else []
    for rp in refs:
        n = int(re.search(r"f_0*(\d+)\.png$", rp).group(1))
        ref = png(rp); got = dec(f, n); m = min(len(ref), len(got))
        if not m:
            fails.append(f"f{n} could not be decoded"); continue
        full = sum(abs(ref[i] - got[i]) for i in range(0, m, 97)) / len(range(0, m, 97))
        idx = [i for i in range(0, m - 2, 3) if max(ref[i:i + 3]) - min(ref[i:i + 3]) >= 100]
        sat = sum(abs(ref[i + k] - got[i + k]) for i in idx for k in range(3)) / (3 * len(idx)) if idx else 0.0
        med = lambda b: [int(st.median(b[i + k] for i in idx)) for k in range(3)] if idx else None
        big = len(idx) >= 2000
        if full >= 2.5: fails.append(f"f{n} whole-frame difference {full:.2f}")
        if big and sat > 3.5: fails.append(f"f{n} saturated region difference {sat:.2f}")
        print(f"   color f{n}: whole frame {full:.2f} | saturated {sat:.2f} (n {len(idx)}{'' if big else ', small area: info only'}) "
              f"{med(ref)} -> {med(got)}")
    if not refs:
        print(f"   color: no reference frames ({rdir}), color path not measured")
    print("   ->", "OK" if not fails else "CHECK: " + "; ".join(fails))
    return not fails


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="*")
    ap.add_argument("--dur", type=float); ap.add_argument("--fps", type=float, default=30)
    ap.add_argument("--ref-dir"); ap.add_argument("--platform", choices=list(LIMITS))
    ap.add_argument("--lufs", type=float, default=-14); ap.add_argument("--tp", type=float, default=-1)
    a = ap.parse_args()
    files = a.files or sorted(glob.glob("Final/*.mp4"))
    if not files:
        sys.exit("no files")
    ok = all([check(f, a) for f in files])
    print("RESULT:", "ALL OK" if ok else "SOMETHING NEEDS A LOOK")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
