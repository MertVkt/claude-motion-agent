#!/bin/bash
# deliver_png.sh: deliver a Remotion composition with CORRECT COLOR and a SINGLE audio encode.
#
#   bash ~/.claude/skills/app-ad-video/scripts/deliver_png.sh <composition> <Final/out.mp4> <duration_s> \
#        [--fps 30] [--work Work] [--ref 225,440] [--crf 17] [--audio mix.wav] [--no-loudnorm] [--limit]
#   Run from the PROJECT ROOT (the folder with package.json + src/index.ts).
#
# Pipeline:
#  1. Remotion -> lossless PNG sequence; frame count = duration*fps is checked (missing frames = error)
#  2. audio: Remotion -> WAV (remotion.audio.config.ts, created if missing, because the main config's
#     CRF/pix_fmt are invalid for WAV) or a mix built elsewhere with --audio (VO + music made in ffmpeg)
#  3. two-pass loudnorm I=-14 TP=-1.5 LRA=11 linear (--no-loudnorm: if the mix is already about -14;
#     --limit: peak limiter at 192 kHz, since AAC can overshoot by up to 3 dB on dense transient material)
#  4. ffmpeg: RGB -> REAL BT.709 matrix, limited range, four tags (setparams) -> libx264 High,
#     ONE AAC 320k/48k stereo encode, apad + -t <duration> (NOT -shortest: the AAC frame cuts 2-3 frames),
#     +faststart. A .part file is written first; an older delivery is moved to Work/previous/, never overwritten.
#  5. reference frames for checking -> <work>/ref_<name>/f_<n>.png (used by verify_delivery.py)
#
# WHY this pipeline: Remotion's `--color-space=bt709` encodes the data with the BT.601 matrix and stamps a
# bt709 tag (measured: CTA 176,64,19 -> 183,72,15; neon green 18,255,40 -> 1,218,34). A raw mp4 render is
# yuvj420p (BT.601 full range); re-tagging it as bt709/tv with h264_metadata is also wrong (the data is not
# converted, error ~4-11/255). The right way: lossless frames -> a real matrix conversion in ffmpeg.
set -euo pipefail
[ $# -ge 3 ] || { sed -n '2,8p' "$0"; exit 2; }
COMP=$1; OUT=$2; DUR=$3; shift 3
FPS=30; WORK=Work; REF=""; CRF=17; EXT_AUDIO=""; LOUD=1; LIMIT=0
while [ $# -gt 0 ]; do
  case $1 in
    --fps) FPS=$2; shift 2;;
    --work) WORK=$2; shift 2;;
    --ref) REF=$2; shift 2;;
    --crf) CRF=$2; shift 2;;
    --audio) EXT_AUDIO=$2; shift 2;;
    --no-loudnorm) LOUD=0; shift;;
    --limit) LIMIT=1; shift;;
    *) echo "unknown option: $1"; exit 2;;
  esac
done
[ -f package.json ] && [ -f src/index.ts ] || { echo "ERROR: not in the project root (no package.json + src/index.ts)"; exit 1; }
NFR=$(python3 -c "print(round($DUR*$FPS))")
TAG=$(basename "$OUT" .mp4)
FR="$WORK/frames_$TAG"; A="$WORK/a_$TAG.wav"; AN="$WORK/a_${TAG}_norm.wav"
mkdir -p "$(dirname "$OUT")" "$WORK/ref_$TAG"
rm -rf "$FR"; mkdir -p "$FR"

echo "== $COMP -> $OUT ($DUR s, $NFR frames)"
npx remotion render "$COMP" "$FR" --sequence --image-format=png --image-sequence-pattern='f_[frame].[ext]' --log=error
N=$(ls "$FR" | grep -c '\.png$' || true)
[ "$N" -eq "$NFR" ] || { echo "   ERROR: $N frames (expected $NFR): the composition duration does not match <duration_s>"; exit 1; }

if [ -n "$EXT_AUDIO" ]; then
  ffmpeg -hide_banner -v error -y -i "$EXT_AUDIO" -ar 48000 -ac 2 -c:a pcm_s24le "$A"
else
  if [ ! -f remotion.audio.config.ts ]; then
    cp "$(dirname "$0")/../assets/remotion.audio.config.ts" remotion.audio.config.ts
    echo "   created remotion.audio.config.ts"
  fi
  npx remotion render "$COMP" "$A" --codec=wav --config=remotion.audio.config.ts --log=error
fi

POST=""
[ "$LIMIT" -eq 1 ] && POST=",aresample=192000,alimiter=limit=0.95:level=disabled:latency=1,aresample=48000"
J=$(ffmpeg -hide_banner -i "$A" -af loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json -f null - 2>&1 | sed -n '/^{/,/^}/p')
read -r MI MTP MLRA MTH OFF <<< "$(echo "$J" | python3 -c "import sys,json;d=json.load(sys.stdin);print(d['input_i'],d['input_tp'],d['input_lra'],d['input_thresh'],d['target_offset'])")"
if [[ "$MI" == -inf* ]]; then
  echo "   WARNING: the audio is completely silent, writing silent AAC"
  ffmpeg -hide_banner -v error -y -f lavfi -t "$DUR" -i anullsrc=r=48000:cl=stereo -c:a pcm_s24le "$AN"
elif [ "$LOUD" -eq 1 ]; then
  ffmpeg -hide_banner -v error -y -i "$A" \
    -af "loudnorm=I=-14:TP=-1.5:LRA=11:measured_I=$MI:measured_TP=$MTP:measured_LRA=$MLRA:measured_thresh=$MTH:offset=$OFF:linear=true$POST" \
    -ar 48000 -c:a pcm_s24le "$AN"
else
  if [ -n "$POST" ]; then ffmpeg -hide_banner -v error -y -i "$A" -af "${POST#,}" -ar 48000 -c:a pcm_s24le "$AN"
  else cp "$A" "$AN"; fi
fi

ffmpeg -hide_banner -v error -y -framerate "$FPS" -pattern_type glob -i "$FR/f_*.png" -i "$AN" \
  -map 0:v:0 -map 1:a:0 \
  -vf "scale=out_color_matrix=bt709:out_range=tv:flags=accurate_rnd+full_chroma_int,format=yuv420p,setparams=range=tv:color_primaries=bt709:color_trc=bt709:colorspace=bt709" \
  -c:v libx264 -preset slow -crf "$CRF" -profile:v high -level 4.2 -g $((FPS * 2)) \
  -af apad -c:a aac -b:a 320k -ar 48000 -ac 2 -t "$DUR" \
  -movflags +faststart -f mp4 "$OUT.part"

# check frames (Remotion zero-pads frame numbers; match any padding)
[ -n "$REF" ] || REF="$((NFR / 2)),$((NFR - 10))"
for n in ${REF//,/ }; do
  f=$(ls "$FR" | grep -E "^f_0*${n}\.png$" | head -1 || true)
  [ "$n" -eq 0 ] && f=$(ls "$FR" | grep -E "^f_0+\.png$" | head -1 || true)
  if [ -n "$f" ]; then cp "$FR/$f" "$WORK/ref_$TAG/f_$n.png"; else echo "   warning: frame $n not found"; fi
done

if [ -f "$OUT" ]; then
  mkdir -p "$WORK/previous"
  mv "$OUT" "$WORK/previous/${TAG}_$(date +%Y%m%d-%H%M%S).mp4"
  echo "   previous delivery -> $WORK/previous/"
fi
mv "$OUT.part" "$OUT"
rm -rf "$FR" "$A"
GOT=$(ffprobe -v error -count_frames -select_streams v:0 -show_entries stream=nb_read_frames -of csv=p=0 "$OUT")
echo "   raw audio $MI LUFS | $GOT frames | -> $OUT"
echo "   verify: python3 $(dirname "$0")/verify_delivery.py \"$OUT\" --dur $DUR --ref-dir \"$WORK/ref_$TAG\""
