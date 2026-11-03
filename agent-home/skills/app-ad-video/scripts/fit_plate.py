#!/usr/bin/env python3
"""fit_plate.py: place a talent shot in the composition frame: PLATE_FIT {s, ox, oy}.

    fit_plate.py --track src/faceTrack.ts --offset 6.2 --rate 0.757 --frames 153 \
                 --target 554.2,1378.3,280.9 --canvas 1080x1920 [--panel 0,953,1080,1920] \
                 [--plate-size 1072x1928] [--fps 30]

For composition frames 0..frames-1 the shot time is offset + f/fps * rate (the same mapping as
OffthreadVideo startFrom + playbackRate). The mean eye center (ex, ey) and eye distance (d) in that
window are fitted to the target measured from the reference (tx, ty, td):
    s = td / d ;  ox = tx - ex * s ;  oy = ty - ey * s        (scene = shot_px * s + (ox, oy))
If the shot does not fully cover the panel (--panel x0,y0,x1,y1; default the whole frame) it is
shifted and the shift is reported, so no black edge shows. Target: face_track.py <reference> --stats F0 F1.
--track: output of face_track.py (contains PLATE_FPS / PLATE_SIZE; give --plate-size for older files).
"""
import argparse, json, re, sys


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--track", required=True)
    ap.add_argument("--offset", type=float, default=0.0)
    ap.add_argument("--rate", type=float, default=1.0)
    ap.add_argument("--frames", type=int, required=True, help="number of composition frames in which the face must sit on the target")
    ap.add_argument("--target", required=True, help="tx,ty,td (composition pixels)")
    ap.add_argument("--canvas", default="1080x1920")
    ap.add_argument("--panel", help="x0,y0,x1,y1: the area the shot must cover")
    ap.add_argument("--plate-size")
    ap.add_argument("--fps", type=float, default=30)
    a = ap.parse_args()

    src = open(a.track).read()
    ft = json.loads(re.search(r"FACE_TRACK[^=]*= (\[.*\]);", src, re.S).group(1))
    pfps = float(re.search(r"PLATE_FPS = ([0-9.]+)", src).group(1))
    m = re.search(r"PLATE_SIZE = \{ w: (\d+), h: (\d+) \}", src)
    if a.plate_size:
        PW, PH = map(int, a.plate_size.lower().split("x"))
    elif m:
        PW, PH = int(m.group(1)), int(m.group(2))
    else:
        sys.exit("no PLATE_SIZE in the track file: pass --plate-size WxH")
    CW, CH = map(int, a.canvas.lower().split("x"))
    x0, y0, x1, y1 = map(float, a.panel.split(",")) if a.panel else (0, 0, CW, CH)
    tx, ty, td = map(float, a.target.split(","))

    idx = [min(len(ft) - 1, int(round((a.offset + f / a.fps * a.rate) * pfps))) for f in range(a.frames)]
    w = [ft[i] for i in idx]
    ex = sum(p["x"] for p in w) / len(w) * PW
    ey = sum(p["y"] for p in w) / len(w) * PH
    d = sum(p["d"] for p in w) / len(w) * PW
    last = a.offset + (a.frames - 1) / a.fps * a.rate
    over = last > len(ft) / pfps
    print(f"shot {PW}x{PH} @ {pfps:g} fps, {len(ft) / pfps:.2f} s | window {a.offset:.2f}-{last:.2f} s"
          f"{'  !! SHOT RUNS OUT: the last frame repeats' if over else ''}")
    print(f"mean eye position in the window ({ex:.1f}, {ey:.1f}), eye distance {d:.1f} px")

    s = td / d
    ox = tx - ex * s
    oy = ty - ey * s
    if PW * s < x1 - x0 or PH * s < y1 - y0:
        print(f"!! at this scale the shot does not cover the panel ({PW * s:.0f}x{PH * s:.0f} < {x1 - x0:.0f}x{y1 - y0:.0f}): "
              "use a tighter framed image or a larger scale")
    ox2 = min(x0, max(x1 - PW * s, ox))
    oy2 = min(y0, max(y1 - PH * s, oy))
    note = "" if (abs(ox2 - ox) < 1e-6 and abs(oy2 - oy) < 1e-6) else \
        f"  (shifted to cover: dx {ox2 - ox:+.1f} dy {oy2 - oy:+.1f}, so the face is off target by that much)"
    print(f"PLATE_FIT s {s:.4f} ox {ox2:.1f} oy {oy2:.1f}{note}")
    print(f"visible shot area x {(x0 - ox2) / s:.0f}-{(x1 - ox2) / s:.0f} / y {(y0 - oy2) / s:.0f}-{(y1 - oy2) / s:.0f}"
          f"  (scale {s:.3f}x: more upscaling means a softer shot; generate the face larger in frame to reduce it)")
    print(f"{{ s: {s:.4f}, ox: {ox2:.1f}, oy: {oy2:.1f} }}")


if __name__ == "__main__":
    main()
