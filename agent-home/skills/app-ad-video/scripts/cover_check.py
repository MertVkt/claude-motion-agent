#!/usr/bin/env python3
"""cover_check.py: does the UI fully cover the phone screen in the composite? Measures the share of dark
(<120) pixels 1-3 px inside the middle of each quad edge (top edge minus the notch). A good fit leaves only
edge anti-aliasing (under about 5%). Needs numpy.
  python3 ~/.claude/skills/app-ad-video/scripts/cover_check.py <composite.mp4> src/track/v1.ts --start 9 --skip 28:78"""
import re, subprocess, sys, argparse, numpy as np
ap = argparse.ArgumentParser(); ap.add_argument("video"); ap.add_argument("ts"); ap.add_argument("--start", type=int, default=0)
ap.add_argument("--skip", default=""); ap.add_argument("--w", type=int, default=1080); ap.add_argument("--h", type=int, default=1920)
a = ap.parse_args()
txt = open(a.ts).read()
q = np.array([list(map(float, l.strip().strip("[],").split(","))) for l in re.findall(r"^\s+\[[-\d\.]+(?:, [-\d\.]+){7}\],$", txt, re.M)]).reshape(-1, 4, 2)
s0, s1 = (int(v) for v in a.skip.split(":")) if a.skip else (-1, -1)
W, H = a.w, a.h
p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", a.video, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
def band(Q, lo, hi):
    pts = []
    c = Q.mean(0)
    for i in range(4):
        P0, P1 = Q[i], Q[(i + 1) % 4]; d = (P1 - P0) / np.linalg.norm(P1 - P0); n = np.array([-d[1], d[0]])
        n = n if np.dot(n, c - (P0 + P1) / 2) > 0 else -n
        for t in np.linspace(0.2, 0.8, 120):
            if i == 0 and 0.3 < t < 0.7: continue
            for s in np.arange(lo, hi + 0.01, 0.5): pts.append(P0 + (P1 - P0) * t + n * s)
    P = np.round(np.array(pts)).astype(int); return P[:, 1].clip(0, H - 1), P[:, 0].clip(0, W - 1)
res = []
f = 0
while True:
    b = p.stdout.read(W * H * 3)
    if len(b) < W * H * 3: break
    if not (s0 < f < s1) and f + a.start < len(q):
        fr = np.frombuffer(b, np.uint8).reshape(H, W, 3).astype(int)
        ys, xs = band(q[f + a.start], 1.0, 3.0); lum = fr[ys, xs].mean(axis=1)
        res.append((f, float((lum < 120).mean())))
    f += 1
p.wait()
r = np.array([v for _, v in res])
print(f"{len(res)} frames | dark share in the inner band: mean {100*r.mean():.2f}%, median {100*np.median(r):.2f}%, worst {100*r.max():.1f}% "
      f"(frame {res[int(r.argmax())][0]}) | frames above 5%: {[f for f, v in res if v > 0.05]}")
