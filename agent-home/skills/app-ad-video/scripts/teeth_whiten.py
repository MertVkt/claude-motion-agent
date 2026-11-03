#!/usr/bin/env python3
"""teeth_whiten.py: whiten yellowed teeth in an AI shot by a natural amount (inside the mouth only, in YUV).

    python3 teeth_whiten.py <shot.mp4> <out.mp4> [--desat 0.45] [--lift 3] [--grow 4] [--sheet Work/teeth.png]

Why YUV: AI video shots are usually untagged, so converting to RGB and back depends on a matrix guess.
Here only masked pixels change, and the operation (pull hue toward neutral, Cb/Cr -> 128, plus a small Y
lift) is matrix independent; pixels outside the mask stay identical to the source (apart from the crf 10
re-encode).
Mask: facetrack's `innerLips` polygon, scaled about its center by --sx/--sy (Vision is narrow at the
corners), grown by --grow px and feathered. When the mouth closes the polygon shrinks and the effect fades
on its own.
Tooth weight (per pixel): bright (soft threshold Y 100->150 so side teeth in shadow count too), yellowish
(Cb below 128) and not lip/gum red (Cr above 148->164 drives the weight to zero). Correction: the Cb/Cr
offset from 128 is multiplied by (1 - desat*w) and lift*w is added to Y. Defaults aim for "not too white".
Needs numpy + Pillow, ffmpeg and facetrack (macOS; see vision.py).
"""
import argparse, json, os, subprocess, sys, tempfile
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from vision import ensure_tracker, video_info  # noqa: E402


def smooth(x, a, b):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src"); ap.add_argument("out")
    ap.add_argument("--desat", type=float, default=0.45)
    ap.add_argument("--lift", type=float, default=3.0)
    ap.add_argument("--grow", type=int, default=4)
    ap.add_argument("--sx", type=float, default=1.15, help="scale the inner-lip polygon horizontally about its center (corners)")
    ap.add_argument("--sy", type=float, default=1.08)
    ap.add_argument("--feather", type=float, default=2.5)
    ap.add_argument("--crf", type=int, default=10)
    ap.add_argument("--sheet")
    a = ap.parse_args()
    W, H, fps, dur = video_info(a.src)
    tr = ensure_tracker()
    with tempfile.TemporaryDirectory() as tmp:
        fr = os.path.join(tmp, "f"); os.makedirs(fr)
        subprocess.run(["ffmpeg", "-v", "error", "-i", a.src, os.path.join(fr, "f_%05d.png")], check=True)
        tj = os.path.join(tmp, "t.json")
        subprocess.run([tr, fr, tj], check=True)
        track = json.load(open(tj))
    dec = subprocess.Popen(["ffmpeg", "-v", "error", "-i", a.src, "-f", "rawvideo", "-pix_fmt", "yuv420p", "-"],
                           stdout=subprocess.PIPE)
    fr_s = f"{int(round(fps * 1000))}/1000"
    enc = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "yuv420p", "-s", f"{W}x{H}",
                            "-r", fr_s, "-i", "-", "-c:v", "libx264", "-preset", "slow", "-crf", str(a.crf),
                            "-pix_fmt", "yuv420p", "-movflags", "+faststart", a.out], stdin=subprocess.PIPE)
    ysz, csz = W * H, (W // 2) * (H // 2)
    samples = []
    i = 0
    changed = []
    while True:
        buf = dec.stdout.read(ysz + 2 * csz)
        if len(buf) < ysz + 2 * csz:
            break
        Y = np.frombuffer(buf[:ysz], np.uint8).reshape(H, W).astype(np.float32)
        U = np.frombuffer(buf[ysz:ysz + csz], np.uint8).reshape(H // 2, W // 2).astype(np.float32)
        V = np.frombuffer(buf[ysz + csz:], np.uint8).reshape(H // 2, W // 2).astype(np.float32)
        Y0, U0, V0 = Y.copy(), U.copy(), V.copy()
        t = track[i] if i < len(track) else {"found": False}
        pts = t.get("innerLips") if t.get("found") else None
        if pts and len(pts) >= 3:
            m = Image.new("L", (W, H), 0)
            # Vision's inner-lip line is narrower than the real mouth opening at the corners: side teeth were left out
            cx0 = sum(p[0] for p in pts) / len(pts); cy0 = sum(p[1] for p in pts) / len(pts)
            poly = [(cx0 + (p[0] - cx0) * a.sx, cy0 + (p[1] - cy0) * a.sy) for p in pts]
            ImageDraw.Draw(m).polygon(poly, fill=255)
            if a.grow > 0:
                m = m.filter(ImageFilter.MaxFilter(2 * a.grow + 1))
            m = m.filter(ImageFilter.GaussianBlur(a.feather))
            M = np.asarray(m, np.float32) / 255.0
            if M.max() > 0.01:
                Mc = M.reshape(H // 2, 2, W // 2, 2).mean(axis=(1, 3))
                Yc = Y.reshape(H // 2, 2, W // 2, 2).mean(axis=(1, 3))
                wc = Mc * smooth(Yc, 100, 150) * smooth(128 - U, 1, 8) * (1 - smooth(V, 148, 164))
                wf = np.repeat(np.repeat(wc, 2, axis=0), 2, axis=1)
                U = 128 + (U - 128) * (1 - a.desat * wc)
                V = 128 + (V - 128) * (1 - a.desat * wc * 0.8)
                Y = Y + a.lift * wf * (1 - (Y - 16) / 219).clip(0, 1)
                changed.append(float(wc.sum()))
                if a.sheet and len(samples) < 6 and wc.sum() > 400 and i % 12 == 0:
                    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
                    cx, cy = int(sum(xs) / len(xs)), int(sum(ys) / len(ys))
                    samples.append((i, cx, cy, (Y0, U0, V0), (Y.copy(), U.copy(), V.copy())))
        out = np.concatenate([np.clip(Y, 0, 255).astype(np.uint8).ravel(), np.clip(U, 0, 255).astype(np.uint8).ravel(),
                              np.clip(V, 0, 255).astype(np.uint8).ravel()])
        enc.stdin.write(out.tobytes())
        i += 1
    enc.stdin.close(); enc.wait(); dec.wait()
    print(f"{i} frames, mouth mask active in {len(changed)} -> {a.out}")
    if a.sheet and samples:
        tiles = []
        for (k, cx, cy, before, after) in samples:
            for yuv in (before, after):
                Yb, Ub, Vb = yuv
                Uf = np.repeat(np.repeat(Ub, 2, 0), 2, 1); Vf = np.repeat(np.repeat(Vb, 2, 0), 2, 1)
                # BT.709 tv -> RGB, for display only
                yy = (Yb - 16) * 255 / 219; uu = (Uf - 128) * 255 / 224; vv = (Vf - 128) * 255 / 224
                r = yy + 1.5748 * vv; g = yy - 0.1873 * uu - 0.4681 * vv; b = yy + 1.8556 * uu
                rgb = np.clip(np.dstack([r, g, b]), 0, 255).astype(np.uint8)
                x0, y0 = max(0, cx - 160), max(0, cy - 90)
                tiles.append(Image.fromarray(rgb[y0:y0 + 180, x0:x0 + 320]))
        sheet = Image.new("RGB", (640, 180 * len(samples)), (20, 20, 20))
        for j, im in enumerate(tiles):
            sheet.paste(im, ((j % 2) * 320, (j // 2) * 180))
        sheet.save(a.sheet)
        print(f"before / after crops -> {a.sheet}")


if __name__ == "__main__":
    main()
