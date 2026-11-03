#!/usr/bin/env python3
"""sat_diag.py: when verify_delivery.py reports "saturated region difference > 3.5", separate a measurement
artifact from a real delivery problem (method from the skill's 07-qc.md).
  python3 ~/.claude/skills/app-ad-video/scripts/sat_diag.py <Final/x.mp4> <Work/ref_x/f_N.png> <N>
Four numbers (same saturated mask: chroma >= 100 in the reference):
  1 lossless 4:2:0: reference PNG -> the delivery matrix (bt709, tv) -> yuv420p -> verify's decoder (format=rgb24)
  2 delivered file, verify's decoder (what verify reported)
  3 delivered file, correct decoder (in_color_matrix=bt709:in_range=tv, accurate_rnd+full_chroma_int)
  4 lossless 4:2:0, correct decoder: the gap between 3 and 4 is the encoder's share
If 1 and 2 are close and 3 is small, the color path is right and the alarm comes from the measurement or
from 4:2:0. A matrix error stays large in 3 as well."""
import subprocess, sys
if len(sys.argv) < 4 or sys.argv[1] in ("-h", "--help"):
    sys.exit(__doc__)
f, rp, n = sys.argv[1], sys.argv[2], int(sys.argv[3])
raw = lambda cmd: subprocess.run(cmd, capture_output=True, check=True).stdout
ref = raw(["ffmpeg", "-v", "error", "-i", rp, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"])
PIPE = "scale=out_color_matrix=bt709:out_range=tv:flags=accurate_rnd+full_chroma_int,format=yuv420p"
GOOD = "scale=in_color_matrix=bt709:in_range=tv:flags=accurate_rnd+full_chroma_int,format=rgb24"
yuv = raw(["ffmpeg", "-v", "error", "-i", rp, "-vf", PIPE, "-f", "rawvideo", "-pix_fmt", "yuv420p", "-"])
w, h = map(int, raw(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "csv=p=0", rp]).decode().strip().split(","))
dy = lambda vf: subprocess.run(["ffmpeg", "-v", "error", "-f", "rawvideo", "-pix_fmt", "yuv420p", "-s", f"{w}x{h}", "-color_range", "tv", "-colorspace", "bt709",
                    "-i", "-", "-vf", vf, "-f", "rawvideo", "-"], input=yuv, capture_output=True, check=True).stdout
p = dy("format=rgb24"); p_good = dy(GOOD)
sel = f"select='eq(n\\,{n})'"
d_ver = raw(["ffmpeg", "-v", "error", "-i", f, "-vf", f"{sel},format=rgb24", "-fps_mode", "passthrough", "-frames:v", "1", "-f", "rawvideo", "-"])
d_good = raw(["ffmpeg", "-v", "error", "-i", f, "-vf", f"{sel},{GOOD}", "-fps_mode", "passthrough", "-frames:v", "1", "-f", "rawvideo", "-"])
idx = [i for i in range(0, len(ref) - 2, 3) if max(ref[i:i + 3]) - min(ref[i:i + 3]) >= 100]
def m(got):
    s = sum(abs(ref[i + k] - got[i + k]) for i in idx for k in range(3)) / (3 * len(idx))
    sg = [sum(got[i + k] - ref[i + k] for i in idx) / len(idx) for k in range(3)]
    return f"{s:.2f} (signed R/G/B {sg[0]:+.1f} / {sg[1]:+.1f} / {sg[2]:+.1f})"
print(f"f{n} saturated n={len(idx)}")
print("  1 lossless 4:2:0, verify decoder: ", m(p))
print("  2 delivered, verify decoder:      ", m(d_ver))
print("  3 delivered, correct decoder:     ", m(d_good))
print("  4 lossless 4:2:0, correct decoder:", m(p_good))
