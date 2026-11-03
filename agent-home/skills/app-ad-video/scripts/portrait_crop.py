#!/usr/bin/env python3
"""portrait_crop.py: crop a portrait from a shot for a result card / avatar, matching the reference framing.

    portrait_crop.py <shot.mp4> <seconds|auto> --card 923x779 --eye 0.533,0.502,0.175 \
                     [--out public/plate/portrait.png] [--scale 2] [--range 0.4,9.8,0.2]

--card  pixel size of the portrait box in the reference
--eye   eye center (x/W, y/H) and eye distance (/W) in the reference portrait. Crop the reference frame
        and measure it with face_track.py ... --stats or with Vision (for example 0.533, 0.502, 0.175).
auto    scans frames in --range and picks the one with the most open eyes, most frontal (small |yaw|)
        AND closed mouth (penalty when mouth openness is more than 0.04 above the candidates' 20th
        percentile, so the portrait is not caught mid-word).
If the crop does not fit inside the shot, the eye POSITION inside the crop is kept and the crop shrinks
(the face comes out a little larger). Shifting the crop to fit instead moved the eye from 0.533 to 0.451
on a tightly framed shot.
Needs macOS for facetrack (see vision.py).
"""
import argparse, os, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from vision import eyes, openness, track, video_info


def pick(plate, t0, t1, step):
    times = []
    t = t0
    while t <= t1 + 1e-9:
        times.append(round(t, 3)); t += step
    raw, PW, PH, fps, K, KY = track(plate, det_w=100000, times=times)  # full resolution (the selection criteria are sensitive)
    found = [(t, r) for t, r in zip(times, raw) if r.get("found")]
    if not found:
        sys.exit("no face found in any frame")
    ms = sorted(openness(r["outerLips"]) for _, r in found)
    base = ms[int(0.2 * (len(ms) - 1))]
    best = None
    for t, r in found:
        op = (openness(r["leftEye"]) + openness(r["rightEye"])) / 2
        yaw = abs(r.get("yaw") or 0.0)
        mo = openness(r["outerLips"])
        score = op - 0.5 * yaw - 3.0 * max(0.0, mo - base - 0.04)
        if best is None or score > best[0]:
            best = (score, t, op, yaw, mo)
    print(f"  picked frame t={best[1]}s  eyes {best[2]:.3f} |yaw| {best[3]:.3f} mouth {best[4]:.3f} (baseline {base:.3f})")
    return best[1]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("plate"); ap.add_argument("at")
    ap.add_argument("--card", required=True); ap.add_argument("--eye", required=True)
    ap.add_argument("--out", default="public/plate/portrait.png")
    ap.add_argument("--scale", type=float, default=2)
    ap.add_argument("--range", default="0.4,9.8,0.2")
    a = ap.parse_args()
    CW, CH = map(int, a.card.lower().split("x"))
    EX, EY, ED = map(float, a.eye.split(","))
    PW, PH, fps, dur = video_info(a.plate)
    if a.at == "auto":
        t0, t1, st = map(float, a.range.split(","))
        at = pick(a.plate, t0, min(t1, dur - 0.05), st)
    else:
        at = float(a.at)
    raw, _, _, _, K, KY = track(a.plate, det_w=PW, times=[at])
    r = raw[0]
    if not r.get("found"):
        sys.exit("no face in this frame, try another second")
    ex, ey, ed, _ = eyes(r, K, KY)
    w = ed / ED; h = w * CH / CW
    w_max = min(ex / EX, (PW - ex) / (1 - EX), (ey / EY) * CW / CH, ((PH - ey) / (1 - EY)) * CW / CH)
    if w > w_max:
        w = w_max; h = w * CH / CW
    x = max(0, min(PW - w, ex - EX * w)); y = max(0, min(PH - h, ey - EY * h))
    w, h, x, y = round(w), round(h), round(x), round(y)
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    subprocess.run(["ffmpeg", "-v", "error", "-ss", str(at), "-i", a.plate, "-frames:v", "1", "-vf",
                    f"crop={w}:{h}:{x}:{y},scale={int(CW * a.scale)}:{int(CH * a.scale)}:flags=lanczos",
                    "-y", a.out], check=True)
    print(f"portrait {a.out}: t={at}s, crop {w}x{h} @ ({x},{y}), eyes ({ex:.0f},{ey:.0f}) distance {ed:.0f}px -> "
          f"in crop ({(ex - x) / w:.3f}, {(ey - y) / h:.3f}) {ed / w:.3f}  (target {EX}, {EY}, {ED})")


if __name__ == "__main__":
    main()
