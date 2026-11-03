#!/bin/bash
# slow_clip.sh: smooth slow motion (motion interpolation) from the closed-mouth window of an AI talent shot.
#   bash ~/.claude/skills/app-ad-video/scripts/slow_clip.sh <name> <Shots/source.mp4> <t0_s> <t1_s> <rate>   (from the project root)
# t0/t1 are source seconds (shot frame k at 30 fps -> k/30 s). Output public/shots/<name>.mp4, 30 fps, tagged BT.709.
# Find the window with plate_windows.py; rates down to about 0.75 stay unnoticeable.
set -e
[ $# -ge 5 ] || { sed -n '2,5p' "$0"; exit 2; }
NAME=$1; SRC=$2; T0=$3; T1=$4; RATE=$5
DUR=$(python3 -c "print($T1-$T0)")
mkdir -p public/shots
ffmpeg -v error -y -ss "$T0" -t "$DUR" -i "$SRC" -map 0:v \
  -vf "setpts=PTS/$RATE,minterpolate=fps=30:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1" \
  -c:v libx264 -crf 10 -preset slow -pix_fmt yuv420p -colorspace bt709 -color_primaries bt709 -color_trc bt709 -color_range tv \
  "public/shots/${NAME}.mp4"
ffprobe -v error -select_streams v:0 -show_entries stream=width,height,nb_frames,duration -of compact "public/shots/${NAME}.mp4"
