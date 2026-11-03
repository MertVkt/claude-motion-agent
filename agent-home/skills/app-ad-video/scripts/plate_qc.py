#!/usr/bin/env python3
"""plate_qc.py: measure inner-voice UGC talent shots (no lip movement wanted). Run from the job root:
  python3 ~/.claude/skills/app-ad-video/scripts/plate_qc.py public/shots/k1_night_30.mp4 [... more shots]
For every shot, every frame (crop sheets every 5th frame):
  - face tracking (facetrack, macOS; see vision.py)
  - SPEECH OSCILLATION: outer lip h/w ratio minus its 15-frame moving average -> std of the remainder.
    In testing, accepted shots measured 0.008-0.012 and a talking shot 0.018 (peak to peak 0.105).
    The raw range misleads (a smile also widens the mouth).
  - face box (shot coords 1072x1928 -> composition 1080x1920: x*1.00746, y*1.00746-11.2), eye center
  - outer lip height/width ratio: a small std within the shot means no speaking movement
  - mouth crops -> Work/qc/<shot>_mouth.jpg (braces / teeth check), frames -> Work/qc/<shot>_sheet.jpg
Output: Work/qc/plates.json (for layout: face center, top of head, chin, relative to the frame)
Needs numpy + Pillow.
"""
import json, os, subprocess, sys
import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from vision import ensure_tracker  # noqa: E402

if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
    sys.exit(__doc__)
K = 1080 / 1072
TOP = (1920 - 1928 * K) / 2
FT = ensure_tracker()
os.makedirs("Work/qc", exist_ok=True)
out = {}
for plate in sys.argv[1:]:
    name = os.path.basename(plate).replace("_30.mp4", "")
    d = f"Work/qc/{name}_f"
    os.makedirs(d, exist_ok=True)
    for f in os.listdir(d):
        os.remove(os.path.join(d, f))
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", plate, "-fps_mode", "passthrough", f"{d}/f_%03d.png"], check=True)
    subprocess.run([FT, d, f"Work/qc/{name}.json"], check=True, capture_output=True)
    D = json.load(open(f"Work/qc/{name}.json"))
    rows, crops, frames = [], [], []
    series = [np.ptp(np.array(fr["outerLips"])[:, 1]) / np.ptp(np.array(fr["outerLips"])[:, 0]) if fr and "outerLips" in fr else np.nan for fr in D]
    for i, fr in enumerate(D):
        if i % 5:
            continue
        im = Image.open(f"{d}/f_{i + 1:03d}.png").convert("RGB")
        frames.append(im.resize((216, 388)))
        if not fr or not fr.get("found", True) or "outerLips" not in fr:
            rows.append(None); continue
        o = np.array(fr["outerLips"]); c = np.array(fr["contour"]) if fr.get("contour") else o
        le, re_ = np.array(fr["leftEye"]).mean(0), np.array(fr["rightEye"]).mean(0)
        bx = fr.get("bbox")  # [x, y, w, h] shot pixels (facetrack)
        w = np.ptp(o[:, 0]); h = np.ptp(o[:, 1])
        rows.append({"k": i, "eye": ((le + re_) / 2).tolist(), "iod": float(np.linalg.norm(le - re_)), "mouth": o.mean(0).tolist(),
                     "ratio": float(h / w), "bbox": bx, "roll": fr.get("roll"), "yaw": fr.get("yaw")})
        cx, cy = o.mean(0); hw = max(w, h) * 0.9
        crops.append(im.crop((int(cx - hw), int(cy - hw * 0.6), int(cx + hw), int(cy + hw * 0.6))).resize((200, 120)))
    ok = [r for r in rows if r]
    comp = lambda x, y: (x * K, y * K + TOP)
    eyes = np.array([comp(*r["eye"]) for r in ok]); mouths = np.array([comp(*r["mouth"]) for r in ok])
    rat = np.array([r["ratio"] for r in ok])
    bb = np.array([r["bbox"] for r in ok if r["bbox"]]) if ok and ok[0]["bbox"] else None
    r = np.array(series); kk = 15
    trend = np.convolve(np.nan_to_num(r, nan=np.nanmean(r)), np.ones(kk) / kk, mode="same")
    res = (r - trend)[kk:-kk]
    info = {"frames": len(D), "found": int(np.sum(~np.isnan(r))),
            "speech_osc_std": round(float(np.nanstd(res)), 4), "speech_osc_pp": round(float(np.nanmax(res) - np.nanmin(res)), 3),
            "eye_mid": np.median(eyes, 0).round(1).tolist(), "eye_range_y": [float(eyes[:, 1].min().round(1)), float(eyes[:, 1].max().round(1))],
            "mouth_mid": np.median(mouths, 0).round(1).tolist(),
            "ratio": {"min": round(float(rat.min()), 3), "max": round(float(rat.max()), 3), "std": round(float(rat.std()), 3)},
            "iod_px": round(float(np.median([r["iod"] for r in ok]) * K), 1)}
    if bb is not None and len(bb):
        # bbox: facetrack shot pixels, top-left origin (check: the eyes must be inside this box)
        x0, y0 = comp(bb[:, 0].min(), bb[:, 1].min()); x1, y1 = comp((bb[:, 0] + bb[:, 2]).max(), (bb[:, 1] + bb[:, 3]).max())
        info["face_box_union"] = [round(x0), round(y0), round(x1), round(y1)]
    out[name] = info
    print(name, json.dumps(info))
    sheet = Image.new("RGB", (200 * 16, 120 * ((len(crops) + 15) // 16)), (40, 40, 40))
    for j, t in enumerate(crops): sheet.paste(t, ((j % 16) * 200, (j // 16) * 120))
    sheet.save(f"Work/qc/{name}_mouth.jpg", quality=88)
    fs = Image.new("RGB", (216 * 11, 388 * ((len(frames) + 10) // 11)), (20, 20, 20))
    for j, t in enumerate(frames): fs.paste(t, ((j % 11) * 216, (j // 11) * 388))
    fs.save(f"Work/qc/{name}_sheet.jpg", quality=85)
# earlier measurements are kept: only the shots in this run are updated (measuring one shot used to wipe the others)
prev = json.load(open("Work/qc/plates.json")) if os.path.exists("Work/qc/plates.json") else {}
prev.update(out)
json.dump(prev, open("Work/qc/plates.json", "w"), indent=1)
