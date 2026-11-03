#!/usr/bin/env python3
"""face_track.py: track the face in a video frame by frame (facetrack) -> TS track file / measurement.

    face_track.py <video.mp4> [--out src/faceTrack.ts] [--mesh mesh_landmarks.json]
                  [--det-w 536] [--smooth 5] [--stats F0 F1] [--json raw.json]

Per frame: eye center (x, y), eye distance (d), eye-line tilt (r, radians), nose centroid (nx, ny).
x, d, nx are written as fractions of the shot WIDTH; y, ny as fractions of the shot HEIGHT.

--mesh  landmarks of a mesh image (facetrack group names: contour 17, leftEye 6, rightEye 6,
        outerLips 14, nose 8 points, in the image's pixel space). When given, x/y/d/r come from a
        Procrustes (similarity) fit of all 51 points: wherever the mesh's eye center lands under that
        transform. Compared with eyes-only alignment, the jaw and ear line also sit right (in one
        test the fit error dropped from 18.8 to 15.6 px). Without it, Vision's eye centers are used.
--stats F0 F1  mean eye center and eye distance over frames [F0, F1] (VIDEO PIXELS).
        Use it to measure the framing target (FIT_TARGET) from a reference video; --out is not written.
        Use --det-w 1080 (full resolution) when measuring a reference.
Gaps are filled from the neighboring frame and smoothed with a --smooth frame window.
Needs macOS for facetrack (see vision.py).
"""
import argparse, json, math, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from vision import GROUPS, ctr, eyes, fill_gaps, similarity_fit, smooth, track


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video")
    ap.add_argument("--out", default="src/faceTrack.ts")
    ap.add_argument("--mesh")
    ap.add_argument("--det-w", type=int, default=536)
    ap.add_argument("--smooth", type=int, default=5)
    ap.add_argument("--stats", nargs=2, type=int, metavar=("F0", "F1"))
    ap.add_argument("--json")
    a = ap.parse_args()

    raw, PW, PH, fps, K, KY = track(a.video, a.det_w)
    if a.json:
        json.dump({"w": PW, "h": PH, "fps": fps, "K": K, "KY": KY, "frames": raw}, open(a.json, "w"))

    mesh = None
    if a.mesh:
        ml = json.load(open(a.mesh))
        M = [tuple(p) for g in GROUPS for p in ml[g]]
        le, re_ = ctr(ml["leftEye"]), ctr(ml["rightEye"])
        mesh = (M, ((le[0] + re_[0]) / 2, (le[1] + re_[1]) / 2), math.hypot(re_[0] - le[0], re_[1] - le[1]))

    recs = []
    for r in raw:
        if not r.get("found") or not r.get("leftEye") or not r.get("rightEye"):
            recs.append(None); continue
        nx, ny = ctr(r["nose"]) if r.get("nose") else (None, None)
        if mesh:
            M, (mex, mey), med = mesh
            Fp = [(p[0] * K, p[1] * KY) for g in GROUPS for p in r[g]]
            s, th, mu, fu = similarity_fit(M, Fp)
            cs, sn = math.cos(th), math.sin(th)
            ux, uy = mex - mu[0], mey - mu[1]
            ex, ey, d, roll = fu[0] + s * (cs * ux - sn * uy), fu[1] + s * (sn * ux + cs * uy), s * med, th
        else:
            ex, ey, d, roll = eyes(r, K, KY)
        recs.append(dict(ex=ex, ey=ey, d=d, r=roll,
                         nx=(nx * K if nx is not None else ex), ny=(ny * KY if ny is not None else ey)))
    missing = sum(1 for x in recs if x is None)
    if missing == len(recs):
        sys.exit("no face found in any frame")
    recs = fill_gaps(recs)
    sm = {k: smooth([x[k] for x in recs], a.smooth) for k in ("ex", "ey", "d", "r", "nx", "ny")}

    if a.stats:
        f0, f1 = a.stats
        f1 = min(f1, len(recs) - 1)
        n = f1 - f0 + 1
        m = {k: sum(sm[k][f0:f1 + 1]) / n for k in sm}
        print(f"{os.path.basename(a.video)} {PW}x{PH} frames {f0}-{f1}: eye center ({m['ex']:.1f}, {m['ey']:.1f})"
              f"  eye distance {m['d']:.1f}  tilt {m['r']:+.3f} rad  nose ({m['nx']:.1f}, {m['ny']:.1f})"
              f"  [no face: {missing} frames]{'  (Procrustes/mesh)' if mesh else ''}")
        return

    track_pts = [dict(x=round(sm["ex"][i] / PW, 6), y=round(sm["ey"][i] / PH, 6), d=round(sm["d"][i] / PW, 6),
                      r=round(sm["r"][i], 5), nx=round(sm["nx"][i] / PW, 6), ny=round(sm["ny"][i] / PH, 6))
                 for i in range(len(recs))]
    body = (
        "// GENERATED FILE, do not edit by hand.\n"
        f"// Source: {os.path.basename(a.video)} ({PW}x{PH}, {fps:g} fps)"
        f"{', mesh Procrustes: ' + os.path.basename(a.mesh) if a.mesh else ''}\n"
        "// Made with: python3 ~/.claude/skills/app-ad-video/scripts/face_track.py <shot.mp4> --out <this file>\n"
        "// One record per SHOT frame. x, d, nx are fractions of the shot width; y, ny of the shot height.\n\n"
        "export type TrackPoint = {\n"
        "  /** eye center */\n  x: number;\n  y: number;\n"
        "  /** distance between the eyes */\n  d: number;\n"
        "  /** eye-line tilt (radians) */\n  r: number;\n"
        "  /** nose centroid (Vision 'nose', 8 points) */\n  nx: number;\n  ny: number;\n};\n\n"
        f"export const PLATE_FPS = {fps:g};\n"
        f"export const PLATE_SIZE = {{ w: {PW}, h: {PH} }} as const;\n\n"
        "export const FACE_TRACK: TrackPoint[] = " + json.dumps(track_pts, separators=(",", ":")) + ";\n"
    )
    os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
    open(a.out, "w").write(body)
    print(f"{len(track_pts)} frames -> {a.out}  (no face found: {missing})")


if __name__ == "__main__":
    main()
