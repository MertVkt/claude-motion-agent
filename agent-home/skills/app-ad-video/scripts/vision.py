"""vision.py: shared face-landmark helpers (used by face_track, plate_windows, portrait_crop,
plate_qc, teeth_whiten). Not run on its own.

Landmarks come from `facetrack`, a small Swift tool on Apple's Vision framework (scripts/macos/facetrack.swift).
It is found in this order: $MA_FACETRACK, `facetrack` on PATH, scripts/macos/bin/facetrack. On macOS it is
compiled on first use with swiftc (Xcode Command Line Tools). On other systems these scripts cannot run;
use ffmpeg frames plus `fal ask` for a visual check instead.
Coordinates: pixels, TOP-LEFT origin, at detection-frame size -> video pixels via K/KY.
"""
import json, math, os, shutil, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
MACOS = os.path.join(HERE, "macos")
GROUPS = ("contour", "leftEye", "rightEye", "outerLips", "nose")


def find_helper(name, env=None):
    """Find (or on macOS, compile) one of the Swift helpers in scripts/macos/. Returns its path."""
    cands = [os.environ.get(env) if env else None, shutil.which(name), os.path.join(MACOS, "bin", name)]
    for c in cands:
        if c and os.path.isfile(c) and os.access(c, os.X_OK):
            return c
    src = os.path.join(MACOS, name + ".swift")
    if sys.platform == "darwin" and shutil.which("swiftc") and os.path.isfile(src):
        out = os.path.join(MACOS, "bin", name)
        os.makedirs(os.path.dirname(out), exist_ok=True)
        print(f"compiling {name} (first use)...", file=sys.stderr, flush=True)
        r = subprocess.run(["swiftc", "-O", src, "-o", out], capture_output=True, text=True)
        if r.returncode == 0:
            return out
        sys.exit(f"could not compile {src}:\n{r.stderr[-800:]}")
    sys.exit(f"{name} is not available. It needs macOS (Apple Vision) and swiftc: "
             f"swiftc -O {src} -o {os.path.join(MACOS, 'bin', name)}. "
             "On Linux, check faces visually instead (ffmpeg frames + `fal ask`).")


def ensure_tracker():
    return find_helper("facetrack", "MA_FACETRACK")


def video_info(path):
    st = json.loads(subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                                    "stream=width,height,r_frame_rate,duration", "-of", "json", path],
                                   capture_output=True, text=True).stdout)["streams"][0]
    n, d = st["r_frame_rate"].split("/")
    return int(st["width"]), int(st["height"]), int(n) / int(d), float(st.get("duration") or 0)


def track(path, det_w=536, times=None):
    """Run facetrack on every frame of the video (or at the given seconds).
    Returns (records, PW, PH, fps, K, KY). A record is facetrack's JSON (found, bbox, roll, yaw, contour,
    leftEye, rightEye, outerLips, nose), in detection-frame coordinates; video pixel = (x*K, y*KY).
    The aspect ratio is KEPT (a fixed 536x966 size distorted 4:5 video vertically by 1.44x)."""
    PW, PH, fps, dur = video_info(path)
    det_w = min(det_w, PW)
    det_h = int(round(det_w * PH / PW / 2)) * 2
    tr = ensure_tracker()
    with tempfile.TemporaryDirectory() as tmp:
        if times is None:
            subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-vf", f"scale={det_w}:{det_h}",
                            "-fps_mode", "passthrough", "-y", f"{tmp}/f_%05d.png"], check=True)
        else:
            for i, t in enumerate(times):
                subprocess.run(["ffmpeg", "-v", "error", "-ss", f"{t:.4f}", "-i", path, "-frames:v", "1",
                                "-vf", f"scale={det_w}:{det_h}", "-y", f"{tmp}/f_{i + 1:05d}.png"], check=True)
        subprocess.run([tr, tmp, f"{tmp}/t.json"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        raw = json.load(open(f"{tmp}/t.json"))
    return raw, PW, PH, fps, PW / det_w, PH / det_h


def ctr(pts):
    return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))


def openness(pts):
    """height / width: how open an eye or the lips are"""
    xs = [p[0] for p in pts]; ys = [p[1] for p in pts]
    return (max(ys) - min(ys)) / max(1e-6, max(xs) - min(xs))


def eyes(r, K=1.0, KY=1.0):
    """(eye_mid_x, eye_mid_y, eye_distance, tilt_radians) in video pixels."""
    le = ctr(r["leftEye"]); re_ = ctr(r["rightEye"])
    lx, ly, rx, ry = le[0] * K, le[1] * KY, re_[0] * K, re_[1] * KY
    return (lx + rx) / 2, (ly + ry) / 2, math.hypot(rx - lx, ry - ly), math.atan2(ry - ly, rx - lx)


def turn(r):
    """head turn: horizontal offset of the nose centroid from the eye midpoint / eye distance"""
    ex, ey, d, _ = eyes(r)
    return abs(ctr(r["nose"])[0] - ex) / max(1e-6, d)


def similarity_fit(src, dst):
    """2D similarity least-squares fit (scale + rotation + translation), closed form (Procrustes).
    Maps src -> dst. Returns (scale, angle, src_center, dst_center)."""
    n = len(src)
    sx = sum(p[0] for p in src) / n; sy = sum(p[1] for p in src) / n
    dx = sum(p[0] for p in dst) / n; dy = sum(p[1] for p in dst) / n
    a = b = nrm = 0.0
    for (mx, my), (fx, fy) in zip(src, dst):
        cx, cy = mx - sx, my - sy
        ux, uy = fx - dx, fy - dy
        a += ux * cx + uy * cy
        b += uy * cx - ux * cy
        nrm += cx * cx + cy * cy
    return math.hypot(a, b) / nrm, math.atan2(b, a), (sx, sy), (dx, dy)


def fill_gaps(recs):
    """Fill None records with the nearest previous record (or the next one if there is none)."""
    for i, r in enumerate(recs):
        if r is None:
            prev = next((recs[j] for j in range(i - 1, -1, -1) if recs[j] is not None), None)
            recs[i] = prev if prev is not None else next((recs[j] for j in range(i + 1, len(recs)) if recs[j] is not None), None)
    return recs


def smooth(vals, win=5):
    n = len(vals); h = win // 2
    return [sum(vals[max(0, i - h):min(n, i + h + 1)]) / (min(n, i + h + 1) - max(0, i - h)) for i in range(n)]
