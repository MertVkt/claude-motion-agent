#!/usr/bin/env python3
"""Create a reel workspace:  <root>/.shared/{clips,audio}  and copy the bundled SFX.

usage: python3 init_project.py <root>
The SFX come from the HyperFrames media-use skill (Pixabay-licensed), installed by this plugin's install.sh.
"""
import os, shutil, sys, glob
root = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else ".")
sh = os.path.join(root, ".shared")
for d in ("clips", "audio"):
    os.makedirs(os.path.join(sh, d), exist_ok=True)
sfx = os.path.expanduser("~/.claude/skills/media-use/audio/assets/sfx")
n = 0
for f in glob.glob(os.path.join(sfx, "*.mp3")):
    dst = os.path.join(sh, "audio", os.path.basename(f))
    if not os.path.exists(dst):
        shutil.copy(f, dst); n += 1
print(f"workspace ready: {sh}  (copied {n} SFX{'' if n else ' - media-use skill not found or already copied'})")
