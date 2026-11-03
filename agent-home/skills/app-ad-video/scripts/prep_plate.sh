#!/bin/bash
# prep_plate.sh: get an AI shot ready for the composition (run from the project root):
#   bash ~/.claude/skills/app-ad-video/scripts/prep_plate.sh <name> <Shots/source.mp4> [--track] [--stt]
# 1) fps=30 (duplicated frames; tracking runs on this file so frame n = composition frame) -> public/shots/<name>_30.mp4
#    Generated video is usually untagged; it is tagged as BT.709, the HD default (the data is not converted).
# 2) if it has audio -> public/audio/<name>.wav (48 kHz, 24 bit)
# 3) --stt: word-level transcript on fal.ai -> Work/<name>_stt.json + word list
# 4) --track: screen_track.py -> src/track/<name>.ts + public/patch/<name>/ (needs numpy + Pillow)
set -e
HERE=$(cd "$(dirname "$0")" && pwd)
PY=${PYTHON:-python3}
[ -x Work/venv/bin/python ] && PY=Work/venv/bin/python
[ $# -ge 2 ] || { sed -n '2,8p' "$0"; exit 2; }
NAME=$1; SRC=$2; shift 2
TRACK=0; STT=0
for a in "$@"; do case $a in --track) TRACK=1;; --stt) STT=1;; esac; done
[ -f package.json ] || { echo "not in the project root (no package.json)"; exit 1; }
mkdir -p public/shots public/audio src/track Work
ffmpeg -v error -y -i "$SRC" -map 0:v -vf fps=30 -c:v libx264 -crf 10 -preset slow -pix_fmt yuv420p \
  -colorspace bt709 -color_primaries bt709 -color_trc bt709 -color_range tv "public/shots/${NAME}_30.mp4"
ffprobe -v error -select_streams v:0 -show_entries stream=width,height,nb_frames -of compact "public/shots/${NAME}_30.mp4"
if ffprobe -v error -select_streams a -show_entries stream=codec_name -of csv=p=0 "$SRC" | grep -q .; then
  ffmpeg -v error -y -i "$SRC" -map 0:a -c:a pcm_s24le -ar 48000 "public/audio/${NAME}.wav"
  echo "audio -> public/audio/${NAME}.wav"
fi
if [ $STT = 1 ]; then
  python3 "$HERE/speech.py" stt "$SRC" "Work/${NAME}_stt.json" > /dev/null
  python3 - "$NAME" <<'PYEOF'
import json, sys
d = json.load(open(f"Work/{sys.argv[1]}_stt.json"))
print("TEXT:", d.get("text"))
print(" ".join(f'{w["text"]}[{w["start"]:.2f}-{w["end"]:.2f}]' for w in d.get("words", []) if w.get("type", "word") == "word"))
PYEOF
fi
if [ $TRACK = 1 ]; then
  rm -rf "public/patch/${NAME}"
  "$PY" "$HERE/screen_track.py" "public/shots/${NAME}_30.mp4" --name "$NAME" --ts "src/track/${NAME}.ts" \
    --patch "public/patch/${NAME}" --debug "Work/track_${NAME}" --debug-every 15
fi
