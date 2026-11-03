#!/usr/bin/env python3
"""screen_track.py: track the green phone screen in an AI shot frame by frame and make patches for the UI overlay.

Only numpy + Pillow (for example a Work/venv in the job). ffmpeg reads raw RGB.

  python3 ~/.claude/skills/app-ad-video/scripts/screen_track.py Shots/v1_hook.mp4 --name v1 \
      --ts src/track/v1.ts --patch public/patch/v1 --debug Work/track_v1

Output:
  --ts     SCREEN_TRACK: fps, size, 4 corners per frame (TL, TR, BR, BL; shot pixels, sub-pixel) + quality
  --patch  one RGBA patch per frame (f_0000.png) around the screen quad: bezel/fingers opaque, green
           transparent, green spill suppressed. Remotion order: shot -> perspective UI -> patch.
  --debug  check frames (corners + edge lines drawn)

Method:
  - green mask: g - max(r, b) > --key0 and g > 110; small specks removed with Min/Max filters
  - region of interest: the previous frame's quad + margin (so other greens, like a plant behind, stay out)
  - edge points (mask minus eroded mask) are assigned to the four sides; the middle 14-86% of each side is
    used (rounded corners, fingers), with a TLS line fit and two rounds of MAD outlier rejection
  - corner = intersection of neighboring lines (the virtual sharp corner of a rounded screen)
  - temporal smoothing is off by default (it drifted on duplicated frames); --smooth works on unique frames
"""
import argparse, json, os, subprocess, sys
import numpy as np
from PIL import Image, ImageDraw, ImageFilter


def probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height,r_frame_rate,nb_frames", "-of", "json", path],
                         capture_output=True, text=True).stdout
    s = json.loads(out)["streams"][0]
    num, den = s["r_frame_rate"].split("/")
    return int(s["width"]), int(s["height"]), float(num) / float(den), int(s.get("nb_frames", 0) or 0)


def frames(path, w, h):
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-i", path, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
                         stdout=subprocess.PIPE)
    n = w * h * 3
    while True:
        b = p.stdout.read(n)
        if len(b) < n:
            break
        yield np.frombuffer(b, np.uint8).reshape(h, w, 3)
    p.wait()


def green_score(a):
    a = a.astype(np.int16)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    return g - np.maximum(r, b), g


def clean(mask, k=5):
    im = Image.fromarray((mask * 255).astype(np.uint8))
    im = im.filter(ImageFilter.MinFilter(k)).filter(ImageFilter.MaxFilter(k))
    return np.asarray(im) > 127


def boundary(mask):
    im = Image.fromarray((mask * 255).astype(np.uint8)).filter(ImageFilter.MinFilter(3))
    er = np.asarray(im) > 127
    ys, xs = np.where(mask & ~er)
    return np.stack([xs, ys], 1).astype(np.float64)


def fit_line(P):
    """TLS: point + unit direction; two rounds of MAD rejection."""
    keep = np.ones(len(P), bool)
    for _ in range(3):
        Q = P[keep]
        c = Q.mean(0)
        u, s, vt = np.linalg.svd(Q - c, full_matrices=False)
        d = vt[0]; nrm = np.array([-d[1], d[0]])
        res = (P - c) @ nrm
        mad = np.median(np.abs(res[keep] - np.median(res[keep]))) + 1e-6
        keep = np.abs(res - np.median(res[keep])) < max(2.5 * 1.4826 * mad, 0.8)
    Q = P[keep]; c = Q.mean(0)
    u, s, vt = np.linalg.svd(Q - c, full_matrices=False)
    d = vt[0]; nrm = np.array([-d[1], d[0]])
    rms = float(np.sqrt(np.mean(((Q - c) @ nrm) ** 2)))
    return c, d, rms, int(keep.sum())


def intersect(c1, d1, c2, d2):
    A = np.array([d1, -d2]).T
    t = np.linalg.solve(A, c2 - c1)
    return c1 + t[0] * d1


def hull(P):
    """Andrew monotone chain; counter-clockwise convex hull."""
    P = np.unique(P, axis=0)
    P = P[np.lexsort((P[:, 1], P[:, 0]))]
    def half(pts):
        h = []
        for p in pts:
            while len(h) >= 2 and (h[-1][0] - h[-2][0]) * (p[1] - h[-2][1]) - (h[-1][1] - h[-2][1]) * (p[0] - h[-2][0]) <= 0:
                h.pop()
            h.append(tuple(p))
        return h
    lo, up = half(P), half(P[::-1])
    return np.array(lo[:-1] + up[:-1], float)


def sample_poly(V, step=1.0):
    out = []
    for i in range(len(V)):
        a, b = V[i], V[(i + 1) % len(V)]
        n = max(1, int(np.ceil(np.linalg.norm(b - a) / step)))
        t = np.arange(n)[:, None] / n
        out.append(a + (b - a) * t)
    return np.concatenate(out)


MAX_JUMP = [90]  # set by --max-jump (a phone moving fast can really move more than 90 px per frame)


def quad_from_mask(mask, prev=None):
    """Sides are assigned per frame from the mask's own principal axes (PCA): u = long axis (down), v = short (right).
    It does not depend on the previous frame, so it works when the phone slides fast or tilts about 30 degrees
    (an earlier version used the previous frame's lines and lost 87 of 96 frames on motion faster than 18 px).
    Lines are fitted to the mask's CONVEX HULL: the notch, the Dynamic Island cutout and finger dents do not
    distort the hull. Fitting the raw mask edge put the top line under the notch (corner 17 px too low)."""
    B = boundary(mask)
    if len(B) < 200:
        return None
    B = sample_poly(hull(B), 1.0)
    ys, xs = np.nonzero(mask)
    P = np.stack([xs, ys], 1).astype(np.float64); c = P.mean(0)
    ev, evec = np.linalg.eigh(np.cov((P - c).T))
    u = evec[:, 1]
    if u[1] < 0:
        u = -u
    v = np.array([u[1], -u[0]])  # with u pointing down, v points right
    pu, pv = (B - c) @ u, (B - c) @ v
    hu, hv = np.percentile(np.abs(pu), 99.5), np.percentile(np.abs(pv), 99.5)
    su, sv = pu / hu, pv / hv
    horiz = np.abs(su) > np.abs(sv)
    # corner rounding: screen radius ~13% of the width -> top/bottom |sv| < 0.65, sides |su| < 0.80
    groups = [horiz & (su < 0) & (np.abs(sv) < 0.65),   # top
              ~horiz & (sv > 0) & (np.abs(su) < 0.80),  # right
              horiz & (su > 0) & (np.abs(sv) < 0.65),   # bottom
              ~horiz & (sv < 0) & (np.abs(su) < 0.80)]  # left
    lines, qual = [], []
    for sel in groups:
        if sel.sum() < 30:
            return None
        cc, dd, rms, n = fit_line(B[sel])
        lines.append((cc, dd)); qual.append((rms, n))
    # corner i = side (i-1) x side i: TL = left x top, TR = top x right, BR = right x bottom, BL = bottom x left
    Q = np.array([intersect(*lines[(i - 1) % 4], *lines[i]) for i in range(4)])
    if prev is not None and np.abs(Q - np.asarray(prev)).max() > MAX_JUMP[0]:
        return None  # jump: wrong mask (hand/reflection); fall back to the previous frame
    return Q, qual


def poly_mask(shape, quad, grow):
    h, w = shape
    c = quad.mean(0)
    q = c + (quad - c) * (1 + grow / max(np.linalg.norm(quad - c, axis=1).min(), 1))
    im = Image.new("L", (w, h), 0)
    ImageDraw.Draw(im).polygon([tuple(p) for p in q], fill=255)
    return np.asarray(im) > 127


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--name", required=True)
    ap.add_argument("--ts", required=True)
    ap.add_argument("--patch", default="")
    ap.add_argument("--debug", default="")
    ap.add_argument("--key0", type=int, default=60, help="mask threshold: g - max(r,b)")
    ap.add_argument("--soft", type=str, default="30,110", help="patch alpha ramp: g - max(r,b) range")
    ap.add_argument("--pad", type=int, default=16, help="patch region margin (px)")
    ap.add_argument("--debug-every", type=int, default=12)
    ap.add_argument("--smooth", action="store_true", help="[1,2,1] over unique frames (off by default)")
    ap.add_argument("--feather", type=float, default=0.8, help="patch alpha Gaussian radius (px); 0 = off")
    ap.add_argument("--fill-from", type=int, default=-1, help="from this frame on, paint the trail (no tracking)")
    ap.add_argument("--fill-color", default="125,106,205", help="trail paint color (the screen's mean color)")
    ap.add_argument("--fill-ymin", type=int, default=0, help="paint the trail only below this y (keeps plants etc.)")
    ap.add_argument("--fill-soft", default="15,90", help="trail paint alpha ramp (around the core green)")
    ap.add_argument("--max-jump", type=float, default=90, help="limit on corner jump between frames (px)")
    ap.add_argument("--despike", type=int, default=0, help="corner local median window (+-frames); 0 = off (for shots where the phone is held still)")
    ap.add_argument("--despike-px", type=float, default=6, help="allowed deviation from the median (px)")
    ap.add_argument("--spill", type=float, default=6, help="spill limit: g <= max(r,b) + spill")
    ap.add_argument("--spill-box", action="store_true", help="apply spill suppression to the whole patch box, not only around the quad")
    a = ap.parse_args()

    W, H, fps, nb = probe(a.video)
    MAX_JUMP[0] = a.max_jump
    s0, s1 = [float(v) for v in a.soft.split(",")]
    if a.patch:
        os.makedirs(a.patch, exist_ok=True)
    if a.debug:
        os.makedirs(a.debug, exist_ok=True)

    quads, quals, boxes, prev, failed = [], [], [], None, []
    raw = []
    for i, fr in enumerate(frames(a.video, W, H)):
        gs, g = green_score(fr)
        m = (gs > a.key0) & (g > 110)
        if prev is not None:
            m &= poly_mask((H, W), np.array(prev), 140)  # region of interest: keep other greens (plants) out
        m = clean(m)
        r = quad_from_mask(m, prev)
        if r is None:
            if prev is None:
                sys.exit(f"frame {i}: screen not found")
            Q, ql = np.array(prev), [(-1, 0)] * 4
            failed.append(i)
        else:
            Q, ql = r
        quads.append(Q); quals.append(ql); prev = Q
        raw.append(None)
    quads = np.array(quads)
    N = len(quads)
    if a.despike > 0:
        # When fingers cover a corner the top line can tilt and leave a green wedge in the opposite corner.
        # For a phone held still, a corner further than despike_px from its +-despike frame local median is replaced by it.
        fixed = 0; qf = quads.copy()
        for i in range(N):
            lo, hi = max(0, i - a.despike), min(N, i + a.despike + 1)
            med = np.median(quads[lo:hi], axis=0)
            bad = np.linalg.norm(quads[i] - med, axis=1) > a.despike_px
            if bad.any():
                qf[i][bad] = med[bad]; fixed += 1
        quads = qf
        print(f"despike: corners fixed in {fixed} frames")

    # temporal smoothing is OFF BY DEFAULT: the patch carries that frame's own bezel, so the UI must lock to that frame.
    # In a shot converted from 24 to 30 fps, frames repeat (A, A, B); a plain [1,2,1] shifts by (B-A)/4 at the
    # repeat boundary (about 10 px on a 40 px jump, leaving dark gaps). --smooth smooths only the unique
    # frames and then spreads the result back over the repeats.
    sm = quads.copy()
    if a.smooth and N > 2:
        same = np.r_[False, np.all(np.abs(np.diff(quads, axis=0)) < 1e-6, axis=(1, 2))]
        uid = np.cumsum(~same) - 1
        U = np.array([quads[uid == k][0] for k in range(uid.max() + 1)])
        Us = U.copy()
        if len(U) > 2:
            Us[1:-1] = (U[:-2] + 2 * U[1:-1] + U[2:]) / 4
        sm = Us[uid]

    # patches: second pass (with the smoothed quad)
    boxes, fills = [], []
    fill_rgb = np.array([float(v) for v in a.fill_color.split(",")], np.float32)
    for i, fr in enumerate(frames(a.video, W, H)):
        Q = sm[i]
        if a.fill_from >= 0 and i >= a.fill_from:
            # TRAIL PAINTING (the phone is lowered fast and leaves the frame, so no quad can be built): green is
            # painted with the screen's mean color (a fast-moving screen is a colored blur anyway). The patch meaning
            # flips: non-green is transparent, green = fill color. The UI is not drawn on these frames (track.fill).
            gs, _ = green_score(fr)
            f0, f1 = [float(v) for v in a.fill_soft.split(",")]
            am = np.clip((gs - f0) / (f1 - f0), 0, 1)
            am[: a.fill_ymin] = 0
            # only within 24 px of the core green (gs > 60): even though the ramp starts at 15, plants (gs <= 33) are
            # untouched and the edge fringe (gs 15-45) gets painted (otherwise a thin green outline remains)
            cy_, cx_ = np.nonzero(gs > 60)
            reg = np.zeros_like(am)
            if len(cx_):
                reg[max(0, cy_.min() - 24):cy_.max() + 25, max(0, cx_.min() - 24):cx_.max() + 25] = 1
            am *= reg
            ys, xs = np.nonzero(am > 0.02)
            fills.append(i)
            if len(xs) == 0:
                boxes.append([0, 0, 1, 1])
                if a.patch:
                    Image.new("RGBA", (1, 1), (0, 0, 0, 0)).save(os.path.join(a.patch, f"f_{i:04d}.png"))
                continue
            x0, x1 = max(0, xs.min() - 4), min(W, xs.max() + 5); y0, y1 = max(0, ys.min() - 4), min(H, ys.max() + 5)
            boxes.append([int(x0), int(y0), int(x1 - x0), int(y1 - y0)])
            if a.patch:
                crop = fr[y0:y1, x0:x1].astype(np.float32); al = am[y0:y1, x0:x1][..., None]
                rr, gg, bb = crop[..., 0], crop[..., 1], crop[..., 2]
                desp = np.dstack([rr, np.minimum(gg, np.maximum(rr, bb)), bb])
                rgb = fill_rgb * al + desp * (1 - al)
                alpha = np.where(am[y0:y1, x0:x1] > 0.02, 255, 0)
                out = np.dstack([rgb, alpha]).clip(0, 255).astype(np.uint8)
                Image.fromarray(out, "RGBA").save(os.path.join(a.patch, f"f_{i:04d}.png"), optimize=False)
            continue
        x0 = int(max(0, np.floor(Q[:, 0].min() - a.pad))); x1 = int(min(W, np.ceil(Q[:, 0].max() + a.pad)))
        y0 = int(max(0, np.floor(Q[:, 1].min() - a.pad))); y1 = int(min(H, np.ceil(Q[:, 1].max() + a.pad)))
        boxes.append([x0, y0, x1 - x0, y1 - y0])
        if a.patch:
            crop = fr[y0:y1, x0:x1].astype(np.float32)
            gs, _ = green_score(fr[y0:y1, x0:x1])
            alpha = 1 - np.clip((gs - s0) / (s1 - s0), 0, 1)
            inside = poly_mask((H, W), Q, a.pad - 2)[y0:y1, x0:x1]
            alpha = np.where(inside, alpha, 1.0)
            # edge softening: the generated green/black border is stair-stepped on slanted edges; the UI carried those
            # steps and a zoom enlarged them. Alpha gets a ~0.8 px Gaussian (inside 0 and outside 1 stay the same).
            if a.feather > 0:
                al = Image.fromarray((alpha * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(a.feather))
                alpha = np.where(inside, np.asarray(al) / 255.0, 1.0)
            # spill suppression: clamp green when it exceeds red/blue (only around the quad)
            rr, gg, bb = crop[..., 0], crop[..., 1], crop[..., 2]
            lim = np.maximum(rr, bb) + a.spill
            gg = np.where((inside | a.spill_box) & (gg > lim), lim, gg)  # light green halo on finger edges
            out = np.dstack([rr, gg, bb, alpha * 255]).clip(0, 255).astype(np.uint8)
            Image.fromarray(out, "RGBA").save(os.path.join(a.patch, f"f_{i:04d}.png"), optimize=False)
        if a.debug and (i % a.debug_every == 0 or i == N - 1):
            im = Image.fromarray(fr.copy()); d = ImageDraw.Draw(im)
            d.polygon([tuple(p) for p in sm[i]], outline=(255, 0, 255), width=3)
            for p in sm[i]:
                d.ellipse((p[0] - 6, p[1] - 6, p[0] + 6, p[1] + 6), outline=(255, 255, 0), width=3)
            im.crop((max(0, boxes[i][0] - 120), max(0, boxes[i][1] - 120),
                     min(W, boxes[i][0] + boxes[i][2] + 120), min(H, boxes[i][1] + boxes[i][3] + 120))
                    ).save(os.path.join(a.debug, f"d_{i:04d}.png"))

    rms = np.array([[q[0] for q in ql] for ql in quals])
    jit = np.abs(np.diff(sm, axis=0)).max(axis=(1, 2)) if N > 1 else np.zeros(1)
    fails = int((rms < 0).any(axis=1).sum())
    os.makedirs(os.path.dirname(os.path.abspath(a.ts)), exist_ok=True)
    with open(a.ts, "w") as f:
        f.write(f"// screen_track.py {os.path.basename(a.video)} | {N} frames @ {fps:g} | edge RMS median "
                f"{np.median(rms[rms >= 0]):.2f} px | failed {fails}\n")
        f.write("/** corner order TL, TR, BR, BL (shot pixels); box = patch crop [x, y, w, h] */\n")
        f.write(f"export const TRACK_{a.name.upper()} = {{ fps: {fps:g}, w: {W}, h: {H}, n: {N},\n  q: [\n")
        for i in range(N):
            f.write("    [" + ", ".join(f"{v:.2f}" for v in sm[i].reshape(-1)) + "],\n")
        f.write("  ] as number[][],\n  box: [\n")
        for b in boxes:
            f.write(f"    [{b[0]}, {b[1]}, {b[2]}, {b[3]}],\n")
        f.write(f"  ] as number[][],\n  fill: [{', '.join(str(v) for v in fills)}] as number[],\n}};\n")
    wd = np.linalg.norm(sm[:, 1] - sm[:, 0], axis=1); ht = np.linalg.norm(sm[:, 3] - sm[:, 0], axis=1)
    print(f"{N} frames @ {fps:g} | {W}x{H} | edge RMS median {np.median(rms[rms >= 0]):.2f} px, worst "
          f"{rms.max():.2f} | failed {fails} | top edge {wd.min():.1f}-{wd.max():.1f} px, left edge "
          f"{ht.min():.1f}-{ht.max():.1f} px | largest corner move between frames {jit.max():.1f} px | dropped frames {failed}")


if __name__ == "__main__":
    main()
