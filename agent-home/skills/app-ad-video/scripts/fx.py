#!/usr/bin/env python3
"""fx.py: pixel and timing measurements on reference / delivered videos (no numpy or PIL needed).

Everything runs on ffmpeg's raw RGB/gray output, so it works with a bare system Python.

As a library:
    import os, sys; sys.path.insert(0, os.path.expanduser("~/.claude/skills/app-ad-video/scripts"))
    from fx import *
    fr, w, h = frames(REF, 100, 140, x=0, y=900, w=1080, h=300)   # frames 100-140, cropped
    r, g, b = px(fr[0], w, 540, 20)
    box = bbox(fr[0], w, lambda p: p[0] > 200 and p[2] < 80, 0, w, 0, h)

Command line:
    fx.py probe <video>                                   size, fps, frames, duration, color, audio, LUFS
    fx.py cuts  <video> [--k 6]                           hard cuts (small gray frame difference)
    fx.py sheet <video> <out_prefix> [--fps 2 --cols 5 --rows 2 --w 360]   contact sheets
    fx.py curve <video> <x,y,w,h> [--from 0 --to N]       per-frame mean color of a crop + difference
    fx.py grab  <video> <frame> <out.png> [--crop x,y,w,h] [--scale 2]     single frame PNG (zoom in)
"""
import argparse, json, math, os, re, subprocess, sys

__all__ = ["probe", "frames", "frame", "all_frames", "load_png", "px", "row_profile", "col_profile",
           "bbox", "bands", "parabola", "match_1d", "mad", "chroma"]


def _run(a, text=False):
    return subprocess.run(a, capture_output=True, text=text)


def probe(path):
    """Basic measurements of a video (ffprobe). The frame count is found by counting (nb_read_frames)."""
    j = json.loads(_run(["ffprobe", "-v", "error", "-count_frames", "-show_entries",
                         "stream=codec_type,codec_name,profile,width,height,r_frame_rate,nb_read_frames,"
                         "duration,pix_fmt,color_range,color_space,color_primaries,color_transfer,"
                         "sample_rate,channels:format=duration,size,bit_rate", "-of", "json", path],
                        text=True).stdout)
    v = next((s for s in j["streams"] if s["codec_type"] == "video"), None)
    a = next((s for s in j["streams"] if s["codec_type"] == "audio"), None)
    out = {"format_duration": float(j["format"].get("duration", 0)), "size_mb": int(j["format"].get("size", 0)) / 1048576}
    if v:
        n, d = v["r_frame_rate"].split("/")
        out.update(w=int(v["width"]), h=int(v["height"]), fps=int(n) / int(d),
                   frames=int(v.get("nb_read_frames") or 0), video_duration=float(v.get("duration") or 0),
                   codec=v.get("codec_name"), profile=v.get("profile"), pix_fmt=v.get("pix_fmt"),
                   color="/".join(v.get(k, "?") for k in ("color_range", "color_primaries", "color_transfer", "color_space")))
    if a:
        out.update(audio=f"{a.get('codec_name')}/{a.get('sample_rate')}/{a.get('channels')}",
                   audio_duration=float(a.get("duration") or 0))
    return out


def _size(path):
    st = json.loads(_run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height", "-of", "json", path], text=True).stdout)["streams"][0]
    return int(st["width"]), int(st["height"])


def _bpp(fmt):
    return {"rgb24": 3, "rgba": 4, "gray": 1}[fmt]


def frames(path, n0, n1, x=0, y=0, w=None, h=None, fmt="rgb24", scale=None):
    """Return frames n0..n1 (inclusive) as raw bytes: (list, w, h).
    fmt: rgb24 | rgba | gray. The crop (x,y,w,h) is applied BEFORE scaling; scale=(W,H) is optional.
    Color: ffmpeg decodes by the file's OWN tags (the right thing when verifying a delivered file)."""
    vf = f"select='between(n\\,{n0}\\,{n1})'"
    if w is not None:
        vf += f",crop={w}:{h}:{x}:{y}"
    else:
        w, h = _size(path)
    if scale:
        vf += f",scale={scale[0]}:{scale[1]}:flags=area"
        w, h = scale
    raw = _run(["ffmpeg", "-v", "error", "-i", path, "-vf", vf, "-fps_mode", "passthrough",
                "-f", "rawvideo", "-pix_fmt", fmt, "-"]).stdout
    sz = w * h * _bpp(fmt)
    return [raw[i:i + sz] for i in range(0, len(raw) - sz + 1, sz)], w, h


def frame(path, n, **kw):
    fr, w, h = frames(path, n, n, **kw)
    return fr[0], w, h


def all_frames(path, fmt="gray", scale=(48, 85)):
    """The whole video at a small size (cut detection, quick curves)."""
    w, h = scale
    raw = _run(["ffmpeg", "-v", "error", "-i", path, "-vf", f"scale={w}:{h}:flags=area",
                "-f", "rawvideo", "-pix_fmt", fmt, "-"]).stdout
    sz = w * h * _bpp(fmt)
    return [raw[i:i + sz] for i in range(0, len(raw) - sz + 1, sz)], w, h


def load_png(path, fmt="rgb24"):
    w, h = _size(path)
    return _run(["ffmpeg", "-v", "error", "-i", path, "-f", "rawvideo", "-pix_fmt", fmt, "-"]).stdout, w, h


def px(buf, w, x, y, bpp=3):
    i = (y * w + x) * bpp
    return tuple(buf[i:i + bpp])


def row_profile(buf, w, y0, y1, x0=0, x1=None, step=4, bpp=1, ch=0):
    """Mean value of each row (gray or one channel), for vertical scroll / position matching."""
    x1 = w if x1 is None else x1
    xs = range(x0, x1, step)
    return [sum(buf[(y * w + x) * bpp + ch] for x in xs) / len(xs) for y in range(y0, y1)]


def col_profile(buf, w, x0, x1, y0, y1, step=4, bpp=1, ch=0):
    ys = range(y0, y1, step)
    return [sum(buf[(y * w + x) * bpp + ch] for y in ys) / len(ys) for x in range(x0, x1)]


def bbox(buf, w, cond, x0, x1, y0, y1, bpp=3, step=1):
    """Box of the pixels where cond(pixel) is True: (xmin, xmax, ymin, ymax, count) or None."""
    xs, ys, n = [], [], 0
    for y in range(y0, y1, step):
        row = y * w
        for x in range(x0, x1, step):
            i = (row + x) * bpp
            if cond(buf[i:i + bpp]):
                xs.append(x); ys.append(y); n += 1
    return (min(xs), max(xs), min(ys), max(ys), n) if xs else None


def bands(buf, w, cond, x0, x1, y0, y1, gap=3, minn=50, bpp=3):
    """Group the rows that satisfy cond by gaps (text lines, bars, cards):
    [(xmin, xmax, ymin, ymax), ...]"""
    rows = {}
    for y in range(y0, y1):
        for x in range(x0, x1):
            i = (y * w + x) * bpp
            if cond(buf[i:i + bpp]):
                rows.setdefault(y, []).append(x)
    if not rows:
        return []
    ys = sorted(rows); groups = [[ys[0]]]
    for y in ys[1:]:
        (groups.append([y]) if y - groups[-1][-1] > gap else groups[-1].append(y))
    out = []
    for g in groups:
        xs = [x for y in g for x in rows[y]]
        if len(xs) >= minn:
            out.append((min(xs), max(xs), g[0], g[-1]))
    return out


def parabola(c0, c1, c2):
    """Sub-pixel correction from three neighboring costs (c1 smallest), -0.5..0.5: best + parabola(...)"""
    den = c0 - 2 * c1 + c2
    return 0.5 * (c0 - c2) / den if den > 0 else 0.0


def match_1d(P, T, lo, hi, stride=2):
    """Search profile P inside T at integer offsets [lo, hi) (mean squared error).
    Returns (sub-pixel offset, error). T[off + j] ~ P[j]."""
    def cost(off):
        e = k = 0
        for j in range(0, len(P), stride):
            t = off + j
            if 0 <= t < len(T):
                d = P[j] - T[t]; e += d * d; k += 1
        return e / k if k > len(P) // (4 * stride) else float("inf")
    best = min((cost(o), o) for o in range(lo, hi))
    o = best[1]
    return o + parabola(cost(o - 1), best[0], cost(o + 1)), best[0]


def mad(a, b, stride=1):
    """Mean absolute difference of two buffers."""
    n = min(len(a), len(b))
    return sum(abs(a[i] - b[i]) for i in range(0, n, stride)) / max(1, len(range(0, n, stride)))


def chroma(p):
    """Rough saturation: max - min (to pick saturated pixels for color checks)."""
    return max(p[:3]) - min(p[:3])


# ---------------------------------------------------------------- command line

def _cmd_probe(a):
    info = probe(a.video)
    for k, v in info.items():
        print(f"{k:16s} {v:.3f}" if isinstance(v, float) else f"{k:16s} {v}")
    if "audio" in info:
        ln = _run(["ffmpeg", "-hide_banner", "-i", a.video, "-af", "loudnorm=print_format=json", "-f", "null", "-"],
                  text=True).stderr
        m = re.findall(r"\{[^{}]*input_i[^{}]*\}", ln, re.S)
        if m:
            j = json.loads(m[-1])
            print(f"{'loudness':16s} {j['input_i']} LUFS  peak {j['input_tp']} dBTP  LRA {j['input_lra']}")


def _cmd_cuts(a):
    info = probe(a.video)
    sw = 48; sh = max(2, round(48 * info["h"] / info["w"] / 2) * 2)
    fr, w, h = all_frames(a.video, "gray", (sw, sh))
    d = [mad(fr[i - 1], fr[i]) for i in range(1, len(fr))]
    mean = sum(d) / len(d)
    print(f"{len(fr)} frames, mean frame difference {mean:.2f}; threshold {a.k}x = {a.k * mean:.1f}")
    for i, v in enumerate(d, start=1):
        if v > a.k * mean:
            print(f"  cut -> frame {i:5d}  {i / info['fps']:8.3f} s   diff {v:6.1f} ({v / mean:5.1f}x)")
    # whip / blur transition: 2-4 high frames in a row. Also show runs above half the threshold.
    runs, cur = [], []
    for i, v in enumerate(d, start=1):
        if a.k * mean / 2 < v <= a.k * mean:
            cur.append(i)
        elif cur:
            runs.append(cur); cur = []
    for r in runs:
        if len(r) >= 2:
            print(f"  soft transition? frames {r[0]}-{r[-1]} ({r[0] / info['fps']:.2f}-{r[-1] / info['fps']:.2f} s)")


def _cmd_sheet(a):
    per = a.cols * a.rows
    out = f"{a.prefix}_%02d.png"
    _run(["ffmpeg", "-v", "error", "-y", "-i", a.video, "-vf",
          f"fps={a.fps},scale={a.w}:-2,tile={a.cols}x{a.rows}:margin=4:padding=4", out])
    base = os.path.dirname(os.path.abspath(a.prefix)); stem = os.path.basename(a.prefix)
    made = sorted(f for f in os.listdir(base) if f.startswith(stem + "_") and f.endswith(".png"))
    for k, f in enumerate(made):
        t0 = k * per / a.fps
        print(f"{os.path.join(base, f)}  cell j (left to right, row by row) -> t = {t0:.2f} + j/{a.fps} s")


def _cmd_curve(a):
    x, y, w, h = map(int, a.crop.split(","))
    info = probe(a.video)
    n1 = a.to if a.to is not None else info["frames"] - 1
    fr, w, h = frames(a.video, a.frm, n1, x, y, w, h)
    prev = None
    for k, b in enumerate(fr):
        n = w * h
        r = sum(b[0::3]) / n; g = sum(b[1::3]) / n; bb = sum(b[2::3]) / n
        dd = mad(b, prev, 7) if prev is not None else 0.0
        f = a.frm + k
        print(f"{f:5d} {f / info['fps']:7.3f}  R{r:6.1f} G{g:6.1f} B{bb:6.1f}  diff {dd:6.2f}")
        prev = b


def _cmd_grab(a):
    vf = f"select='eq(n\\,{a.frame})'"
    if a.crop:
        x, y, w, h = map(int, a.crop.split(","))
        vf += f",crop={w}:{h}:{x}:{y}"
    if a.scale and a.scale != 1:
        vf += f",scale=iw*{a.scale}:ih*{a.scale}:flags=neighbor"
    _run(["ffmpeg", "-v", "error", "-y", "-i", a.video, "-vf", vf, "-fps_mode", "passthrough",
          "-frames:v", "1", a.out])
    print(a.out)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("probe"); p.add_argument("video"); p.set_defaults(fn=_cmd_probe)
    p = sub.add_parser("cuts"); p.add_argument("video"); p.add_argument("--k", type=float, default=6.0)
    p.set_defaults(fn=_cmd_cuts)
    p = sub.add_parser("sheet"); p.add_argument("video"); p.add_argument("prefix")
    p.add_argument("--fps", type=float, default=2); p.add_argument("--cols", type=int, default=5)
    p.add_argument("--rows", type=int, default=2); p.add_argument("--w", type=int, default=360)
    p.set_defaults(fn=_cmd_sheet)
    p = sub.add_parser("curve"); p.add_argument("video"); p.add_argument("crop")
    p.add_argument("--from", dest="frm", type=int, default=0); p.add_argument("--to", type=int)
    p.set_defaults(fn=_cmd_curve)
    p = sub.add_parser("grab"); p.add_argument("video"); p.add_argument("frame", type=int)
    p.add_argument("out"); p.add_argument("--crop"); p.add_argument("--scale", type=float, default=1)
    p.set_defaults(fn=_cmd_grab)
    a = ap.parse_args(); a.fn(a)


if __name__ == "__main__":
    main()
