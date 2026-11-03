#!/bin/bash
# prelimit.sh: iterative peak limiting before loudnorm (-14). Run from the project root:
#   bash ~/.claude/skills/app-ad-video/scripts/prelimit.sh Work/mix_raw.wav Work/mix_pre.wav [target_tp=-1.8] [max_passes=6]
# The measurement is the SAME one deliver_png's two-pass loudnorm uses (input_i, input_tp; 2 decimals). To stay
#   linear, loudnorm needs input_tp + (-14 - input_i) <= -1.5 (otherwise it silently switches to dynamic mode);
#   the -1.8 target leaves 0.3 dB of headroom.
# Do not measure with ebur128: the peak matches, but on a mix with speech the integrated loudness differs by
#   0.2-0.3 LU (gating), which was enough to push loudnorm into dynamic mode (delivery at -14.29 LUFS).
# Every limiter pass runs on the RAW mix (192 kHz; latency=1 is required, or the audio is delayed by 5 ms). The
#   first limit is TP - (-14 - I_raw) dB; then Q (the peak after normalizing to -14) is corrected with a secant step
#   until it reaches the target. Limiting also lowers I: 1 dB of limit is about 0.6 dB of Q, so plain iteration
#   converged slowly. It stops at the target. I is measured from the LIMITED mix every pass.
# (1) If the peak is already under the target after normalizing to -14, no limiting: float copy.
# (2) A raw mix can exceed full scale (amix normalize=0, float WAV): then L > 1 and alimiter reports "out of
#   range", so the raw mix is first scaled by -6 dB (loudnorm undoes it later). Output is float.
set -euo pipefail
IN=$1; OUT=$2; TP=${3:--1.8}; N=${4:-6}
meas() { ffmpeg -hide_banner -i "$1" -af loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json -f null - 2>&1 | sed -n '/^{/,/^}/p' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['input_i'], d['input_tp'])"; }
q() { python3 -c "print(round($2 + (-14 - ($1)), 2))"; }          # peak after normalizing to -14
le() { python3 -c "import sys; sys.exit(0 if $1 <= $2 else 1)"; }
read -r I P <<< "$(meas "$IN")"
echo "raw: I $I LUFS, peak $P dBTP (loudnorm measurement)"
if le "$(q "$I" "$P")" "$TP"; then
  ffmpeg -hide_banner -v error -y -i "$IN" -c:a pcm_f32le "$OUT"
  echo "peak at -14 would be ~$(q "$I" "$P") dBTP <= $TP: no limiting needed, copied (float)"
  exit 0
fi
if python3 -c "import sys; sys.exit(0 if $P > -1.0 else 1)"; then
  TMP="${OUT%.wav}_scaled.wav"
  ffmpeg -hide_banner -v error -y -i "$IN" -af "volume=-6dB" -c:a pcm_f32le "$TMP"
  IN=$TMP; read -r I P <<< "$(meas "$IN")"
  echo "raw peak near or above full scale: scaled by -6 dB: I $I LUFS, peak $P dBTP"
fi
LDB=$(python3 -c "print(round($TP - (-14 - ($I)), 3))"); PREV=""; Q=""
for k in $(seq 1 "$N"); do
  L=$(python3 -c "print(round(10**($LDB/20), 5))")
  ffmpeg -hide_banner -v error -y -i "$IN" -af "aresample=192000,alimiter=limit=$L:level=disabled:latency=1,aresample=48000" -c:a pcm_f32le "$OUT"
  read -r I P <<< "$(meas "$OUT")"; Q=$(q "$I" "$P")
  echo "pass $k: limit $L ($LDB dB) -> I $I LUFS, peak $P dBTP (peak at -14 ~$Q dBTP)"
  if le "$Q" "$TP"; then break; fi
  # secant: slope dQ/dL (0.6 on the first step), clamped to 0.3-1.2; aims 0.03 dB under the target
  NEW=$(python3 -c "
prev, l, q = '$PREV', $LDB, $Q
s = 0.6
if prev:
    pl, pq = map(float, prev.split())
    if abs(l - pl) > 1e-6: s = min(1.2, max(0.3, (q - pq) / (l - pl)))
print(round(l + ($TP - 0.03 - q) / s, 3))")
  PREV="$LDB $Q"; LDB=$NEW
done
le "$Q" "$TP" || echo "WARNING: did not reach the target in $N passes (peak at -14 ~$Q dBTP > $TP): loudnorm may switch to dynamic mode"
[ -n "${TMP:-}" ] && rm -f "$TMP"
exit 0
