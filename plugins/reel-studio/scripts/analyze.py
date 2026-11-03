#!/usr/bin/env python3
"""Loudness and onset helpers for music and clip audio.

Import them:   from analyze import rms, onsets
Or run them:   python3 analyze.py music <track.wav> [...]        beat/drop candidates in music
               python3 analyze.py clips <shared_dir> <clip> [...]  real hits inside cut clips
"""
import json, os, re, subprocess, sys


def rms(path, hop=0.01):
    """RMS level in dB per `hop` seconds."""
    out = subprocess.run(['ffmpeg', '-v', 'error', '-i', path, '-ac', '1', '-ar', '48000', '-af',
                          f'asetnsamples={int(48000 * hop)},astats=metadata=1:reset=1,ametadata=print:key=lavfi.astats.Overall.RMS_level:file=-',
                          '-f', 'null', '-'], capture_output=True, text=True).stdout
    v = []
    for l in out.splitlines():
        m = re.search(r'RMS_level=(-?[\d.inf]+)', l)
        if m:
            v.append(-90.0 if 'inf' in m.group(1) else float(m.group(1)))
    return v


def onsets(v, hop=0.01, jump=6, gap=0.12, floor=None):
    """(time, jump_dB) where the level rises more than `jump` dB above the previous 50 ms."""
    if not v:
        return []
    med = sorted(v)[len(v) // 2]
    floor = med + 3 if floor is None else floor
    res = []
    for i in range(5, len(v)):
        prev = sum(v[i - 5:i]) / 5
        if v[i] - prev > jump and v[i] > floor and (not res or i * hop - res[-1][0] > gap):
            res.append((round(i * hop, 2), round(v[i] - prev, 1)))
    return res


def main():
    if len(sys.argv) < 3 or sys.argv[1] not in ('music', 'clips'):
        sys.exit(__doc__)
    if sys.argv[1] == 'music':
        for f in sys.argv[2:]:
            o = onsets(rms(f), jump=5)
            print(os.path.basename(f), 'onsets:', ' '.join(f'{t:.2f}' for t, _ in o[:80]))
    else:
        shared = sys.argv[2]
        for c in sys.argv[3:]:
            o = onsets(rms(os.path.join(shared, 'clips', c + '.mp4')), jump=7)
            print(c, 'hits (file time):', ' '.join(f'{t:.2f}/{s}' for t, s in o))


if __name__ == '__main__':
    main()
