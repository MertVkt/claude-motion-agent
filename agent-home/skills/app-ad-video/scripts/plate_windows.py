#!/usr/bin/env python3
"""plate_windows.py: find the "clean" stretches of an AI talent shot: looking at camera, mouth closed.

    plate_windows.py <shot.mp4> --need 5.07 [--talk 0.07] [--glance 0.62] [--glance-frames 8]
                     [--turn 0.30] [--from 0] [--to END]

Video models often ignore "lips closed, not speaking" in the prompt; measure the shot before you use it.
Criteria (Vision, every shot frame):
  t  talking : outer lip height/width > (the shot's 20th percentile + --talk)
  g  glance  : eye openness < median * --glance, lasting at least --glance-frames frames
               (shorter is a blink, which is fine)
  r  turned  : |nose x - eye mid x| / eye distance > --turn  (only if --turn is given)
Output: problem stretches, the longest clean stretch, the best --need second window (fewest problem
frames) and, if the clean stretch is short, a suggested slow-down: rate = clean / needed. In the
composition, shot time = offset + t * rate (same as OffthreadVideo playbackRate); down to about 0.75x
a vision model did not notice the slow-down. While the shot sits under an overlay it can be frozen
with <Freeze>, which shortens the time you need.
Needs macOS for facetrack (see vision.py).
"""
import argparse, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from vision import openness, track, turn


def segments(flags):
    out, i = [], 0
    while i < len(flags):
        if flags[i]:
            j = i
            while j < len(flags) and flags[j]:
                j += 1
            out.append((i, j)); i = j
        else:
            i += 1
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("plate")
    ap.add_argument("--need", type=float, required=True, help="seconds of the shot the composition uses")
    ap.add_argument("--talk", type=float, default=0.07)
    ap.add_argument("--glance", type=float, default=0.62)
    ap.add_argument("--glance-frames", type=int, default=8)
    ap.add_argument("--turn", type=float)
    ap.add_argument("--from", dest="t0", type=float, default=0.0)
    ap.add_argument("--to", dest="t1", type=float)
    a = ap.parse_args()

    raw, PW, PH, fps, K, KY = track(a.plate)
    M, E, T = [], [], []
    for r in raw:
        if not r.get("found"):
            M.append(1.0); E.append(0.0); T.append(1.0); continue
        M.append(openness(r["outerLips"]))
        E.append((openness(r["leftEye"]) + openness(r["rightEye"])) / 2)
        T.append(turn(r))
    n = len(M)
    mb = sorted(M)[n // 5]
    eb = sorted(E)[n // 2]
    talk = [m > mb + a.talk for m in M]
    low = [e < eb * a.glance for e in E]
    glance = [False] * n
    for i, j in segments(low):
        if j - i >= a.glance_frames:
            for k in range(i, j):
                glance[k] = True
    turned = [a.turn is not None and t > a.turn for t in T]
    lost = [not r.get("found") for r in raw]
    bad = [x or y or z or w for x, y, z, w in zip(talk, glance, turned, lost)]
    i0 = int(round(a.t0 * fps)); i1 = n if a.t1 is None else min(n, int(round(a.t1 * fps)))
    for k in range(n):
        if k < i0 or k >= i1:
            bad[k] = True

    print(f"{os.path.basename(a.plate)}: {n} frames, {fps:g} fps, {n / fps:.2f} s | mouth baseline {mb:.3f}, eye median {eb:.3f}")
    segs = []
    for i, j in segments(bad):
        if i < i0 or j > i1:
            continue
        tag = ("t" if any(talk[i:j]) else "") + ("g" if any(glance[i:j]) else "") + \
              ("r" if any(turned[i:j]) else "") + ("?" if any(lost[i:j]) else "")
        segs.append(f"{i / fps:.2f}-{j / fps:.2f}{tag}")
    print("problem stretches (t talking, g glance, r turned, ? no face):", ", ".join(segs) or "none")
    clean = [(j - i, i, j) for i, j in segments([not b for b in bad])]
    if not clean:
        sys.exit("no clean frames")
    L, ci, cj = max(clean)
    print(f"longest clean stretch: {ci / fps:.2f}-{cj / fps:.2f} s ({L / fps:.2f} s)")
    need = int(round(a.need * fps))
    if need <= n:
        cnt, s = min((sum(bad[s:s + need]), s) for s in range(0, n - need + 1))
        print(f"best {a.need:g} s window (rate 1): {s / fps:.2f}-{(s + need) / fps:.2f} s, problem frames {cnt}")
    if L < need:
        rate = L / need
        print(f"suggestion: offset {ci / fps:.2f} s, rate {rate:.3f} (clean {L / fps:.2f} s / needed {a.need:g} s)"
              + ("  (below 0.75: consider another shot or a Freeze)" if rate < 0.75 else ""))
    else:
        print(f"suggestion: offset {ci / fps:.2f} s, rate 1 (the clean stretch is long enough)")


if __name__ == "__main__":
    main()
