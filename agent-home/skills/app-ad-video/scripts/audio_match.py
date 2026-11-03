#!/usr/bin/env python3
"""audio_match.py: take apart a reference ad's audio: music alignment, SFX search, levels, comparison.

Everything runs on mono 8 kHz float (ffmpeg decodes; no numpy needed). Times are MIX (reference file)
times. In AAC deliveries from After Effects / Media Encoder the mix comes out about 21.3 ms (171 samples
at 8 kHz) late relative to the sources: if the music starts at 0 on the timeline, the offset `music`
finds is that delay; pass `sfx --delay <s>` to get SFX timeline positions.

  music   <reference.mp4> <music> [--out au] [--win A,B]
          Where the music sits in the mix (offset + in-point within the file), its gain, gain stability
          per window. au/res.f32 = mix - gain*music (the residual), au/music.json. Per-frame residual
          energy -> where the SFX events are.
  sfx     <au/res.f32> <sfx> --near T0,T1 [--rates 1,1.5,2.65] [--inpoints 0,0.2] [--len 1.2] [--log] [--delay S]
          Search the residual for an SFX. One rate/in-point: waveform correlation. Several: an envelope
          NCC scan first (sped up / slowed down; AE time stretch also shifts pitch), then the best three
          candidates are refined on the waveform. --log: log envelope for wide-dynamic sounds.
  level   <au/res.f32> <sfx> --at T --win A,B --floor A,B[;C,D] [--rate 1]
          When correlation is partial, take the level from ENERGY: residual power - floor = gain^2 * SFX power.
          (With partial correlation the least-squares gain came out about 4 dB low on a whoosh.)
  compare <reference.mp4> <ours.wav|mp4> <music> --events "name:t0-t1,name2:t0-t1" [--win A,B]
          Residual RMS (dB relative to the music) in each event window for both mixes; target gap <= 0.3 dB.
          Event times are TIMELINE seconds (no delay); each file's own offset is added.

Gains are also written as a ratio "relative to the music": in Remotion, sfx volume = music volume * ratio.
No volume may exceed 1: lower the music volume if needed and keep the ratios.
"""
import argparse, json, math, os, statistics, subprocess, sys
from array import array

SR = 8000
FPS = 30


def load(path):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-vn", "-ac", "1", "-ar", str(SR), "-f", "f32le", "-"],
                         capture_output=True).stdout
    a = array("f"); a.frombytes(raw[: len(raw) // 4 * 4]); return a


def load_f32(path):
    a = array("f"); a.frombytes(open(path, "rb").read()); return a


def env(sig, hop, log=False):
    out = []
    for i in range(0, len(sig) - hop, hop):
        s = 0.0
        for x in sig[i:i + hop]:
            s += x * x
        v = math.sqrt(s / hop)
        out.append(math.log10(v + 1e-5) if log else v)
    return out


def ncc(a, b):
    n = min(len(a), len(b))
    if n < 4:
        return -1.0
    ma = sum(a[:n]) / n; mb = sum(b[:n]) / n
    s = sa = sb = 0.0
    for i in range(n):
        x = a[i] - ma; y = b[i] - mb
        s += x * y; sa += x * x; sb += y * y
    return s / math.sqrt(sa * sb + 1e-18)


def resample(tm, rate):
    """rate > 1 speeds up (pitch rises too, like AE time stretch / ffmpeg asetrate)."""
    if abs(rate - 1) < 1e-9:
        return tm
    n = int(len(tm) / rate); out = array("f", bytes(4 * n)); L = len(tm)
    for i in range(n):
        x = i * rate; j = int(x); f = x - j
        out[i] = tm[j] * (1 - f) + (tm[j + 1] if j + 1 < L else 0.0) * f
    return out


def fit_music(mix, mus, win=None):
    """Offset (mix sample - music sample) and gain. First a coarse position over the whole file with
    envelope (10 ms) NCC, then sample-accurate on the waveform."""
    dur = len(mix) / SR
    a, b = win if win else (min(1.0, dur * 0.1), min(dur - 0.2, max(4.0, dur * 0.6)))
    HOP = 80
    Em = env(mix, HOP); Eu = env(mus, HOP)
    ia, ib = int(a * SR / HOP), int(b * SR / HOP)
    seg = Em[ia:min(ib, ia + 400)]                 # envelope search at most 4 s (speed on long music files)

    def at(k):                                     # k = music envelope index - mix envelope index
        lo = ia + k
        return ncc(seg, Eu[lo:lo + len(seg)]) if lo >= 0 and lo + len(seg) <= len(Eu) else -2.0
    best = max((at(k), k) for k in range(-ia, len(Eu) - len(seg) - ia + 1, 3))
    best = max((at(k), k) for k in range(best[1] - 3, best[1] + 4))
    base = -best[1] * HOP                          # offset estimate (samples)
    i0, i1 = int(a * SR), int(b * SR)

    def corr(shift, stride):
        s = e = rr = 0.0
        for i in range(i0, i1, stride):
            j = i - shift
            if 0 <= j < len(mus):
                m = mus[j]; x = mix[i]
                s += x * m; e += m * m; rr += x * x
        return s / math.sqrt(e * rr + 1e-18), (s / e if e > 0 else 0.0)

    cand = max(((corr(sh, 3)[0], sh) for sh in range(base - 240, base + 241, 4)))
    c, shift = max(((corr(sh, 1)[0], sh) for sh in range(cand[1] - 4, cand[1] + 5)))
    return shift, c, best[0]


def gain_at(mix, mus, shift, a, b):
    s = e = 0.0
    for i in range(max(0, int(a * SR)), min(len(mix), int(b * SR))):
        j = i - shift
        if 0 <= j < len(mus):
            m = mus[j]; s += mix[i] * m; e += m * m
    return s / e if e > 0 else float("nan")


def residual(mix, mus, shift, g):
    out = array("f", mix)
    L = len(mus)
    for i in range(len(mix)):
        j = i - shift
        if 0 <= j < L:
            out[i] = mix[i] - g * mus[j]
    return out


def frame_db(sig, fps=FPS):
    n = int(len(sig) / SR * fps); out = []
    for f in range(n):
        seg = sig[int(f * SR / fps):int((f + 1) * SR / fps)]
        out.append(20 * math.log10(math.sqrt(sum(x * x for x in seg) / max(1, len(seg))) + 1e-9))
    return out


def cmd_music(a):
    mix = load(a.ref); mus = load(a.music)
    win = tuple(map(float, a.win.split(","))) if a.win else None
    shift, c, ce = fit_music(mix, mus, win)
    dur = len(mix) / SR
    edges = [dur * k / 8 for k in range(9)]
    gains = [gain_at(mix, mus, shift, edges[k], edges[k + 1]) for k in range(8)]
    g = statistics.median([x for x in gains if x == x])
    print(f"offset {shift} samples = {shift / SR * 1000:+.1f} ms (mix t=0 <-> music file t={-shift / SR:.3f} s)"
          f"  | waveform correlation {c:.3f} (envelope {ce:.3f})")
    if abs(shift) <= 400:
        print(f"  if the music starts at 0, this offset is the encoder delay: sfx --delay {shift / SR:.4f}")
    print("window gains: " + "  ".join(f"{edges[k]:.1f}-{edges[k + 1]:.1f}s {gains[k]:.3f}" for k in range(8)))
    print(f"gain (median) {g:.4f}  -> windows without SFX give the gain closest to the real value")
    os.makedirs(a.out, exist_ok=True)
    res = residual(mix, mus, shift, g)
    open(os.path.join(a.out, "res.f32"), "wb").write(res.tobytes())
    json.dump({"ref": a.ref, "music": a.music, "shift": shift, "gain": g, "corr": c, "sr": SR},
              open(os.path.join(a.out, "music.json"), "w"), indent=1)
    db = frame_db(res)
    floor = statistics.median(db)
    print(f"residual -> {a.out}/res.f32 | per-frame residual (dBFS, floor {floor:.0f}); events above floor+10 dB:")
    ev, cur = [], None
    for f, v in enumerate(db):
        if v > floor + 10:
            cur = [f, f, v] if cur is None else [cur[0], f, max(cur[2], v)]
        elif cur is not None:
            ev.append(cur); cur = None
    if cur is not None:
        ev.append(cur)
    for f0, f1, pk in ev:
        print(f"  frames {f0:4d}-{f1:4d}  ({f0 / FPS:6.2f}-{(f1 + 1) / FPS:6.2f} s)  peak {pk:5.1f} dBFS")


def _music_gain(res_path):
    j = os.path.join(os.path.dirname(os.path.abspath(res_path)), "music.json")
    return json.load(open(j))["gain"] if os.path.exists(j) else None


def wave_search(res, T, t0, t1, coarse=2):
    e = sum(x * x for x in T)
    best = None
    L = len(T); R = len(res)
    for st in range(max(0, int(t0 * SR)), min(R - 1, int(t1 * SR)), coarse):
        s = 0.0
        for j in range(0, L, 2):
            i = st + j
            if i < R:
                s += res[i] * T[j]
        if best is None or s > best[0]:
            best = (s, st)
    out = None
    for st in range(best[1] - coarse - 1, best[1] + coarse + 2):
        s = rr = 0.0
        for j in range(L):
            i = st + j
            if 0 <= i < R:
                s += res[i] * T[j]; rr += res[i] * res[i]
        c = s / math.sqrt(e * rr + 1e-18)
        if out is None or s > out[0]:
            out = (s, st, c, s / e)
    return out[1], out[2], out[3]


def cmd_sfx(a):
    res = load_f32(a.res); tm = load(a.sfx)
    t0, t1 = map(float, a.near.split(","))
    rates = [float(x) for x in a.rates.split(",")]
    inps = [float(x) for x in a.inpoints.split(",")]
    gm = _music_gain(a.res)
    delay = a.delay or 0.0

    def report(tag, st, c, g, rate, inp):
        t = st / SR - inp / rate                   # layer start (file t=0), in-point removed
        line = f"{tag} layer start {t:.4f} s (frame {t * FPS:.2f})"
        if a.delay is not None:
            line += f" -> timeline {t - delay:.4f} s = frame {(t - delay) * FPS:.2f}"
        line += f" | rate {rate:g} in-point {inp:g} s | correlation {c:.3f}"
        ge = g / max(c, 1e-6)                      # upper bound: if all residual energy were this SFX
        if gm:
            line += (f" | gain (least squares) {g:.4f} = {g / gm:.3f}x the music ({20 * math.log10(max(g, 1e-9) / gm):+.1f} dB);"
                     f" energy upper bound {ge / gm:.3f}x ({20 * math.log10(max(ge, 1e-9) / gm):+.1f} dB)")
        else:
            line += f" | gain {g:.4f} (energy upper bound {ge:.4f})"
        print(line)

    if len(rates) == 1 and len(inps) == 1:
        T = resample(tm[int(inps[0] * SR):], rates[0])
        T = T[:int(a.len * SR)] if a.len else T
        st, c, g = wave_search(res, T, t0, t1)
        report("waveform", st, c, g, rates[0], inps[0])
        return
    HOP = 40
    R = env(res, HOP, a.log)
    cands = []
    for inp in inps:
        for rate in rates:
            T = resample(tm[int(inp * SR):], rate)
            if a.len:
                T = T[:int(a.len * SR)]
            E = env(T, HOP, a.log)
            for s in range(int(t0 * SR / HOP), int(t1 * SR / HOP) + 1):
                cands.append((ncc(R[s:s + len(E)], E), inp, rate, s * HOP))
    cands.sort(reverse=True)
    print("envelope NCC, best 5:")
    for c, inp, rate, st in cands[:5]:
        print(f"  NCC {c:.3f}  rate {rate:g}  in-point {inp:g}  start {st / SR:.3f} s (frame {st / SR * FPS:.2f})")
    seen = set()
    for c, inp, rate, st in cands:
        if (inp, rate) in seen:
            continue
        seen.add((inp, rate))
        T = resample(tm[int(inp * SR):], rate)
        if a.len:
            T = T[:int(a.len * SR)]
        s2, cw, g = wave_search(res, T, st / SR - 0.01, st / SR + 0.01, coarse=1)
        report("waveform", s2, cw, g, rate, inp)
        if len(seen) >= 3:
            break


def cmd_level(a):
    res = load_f32(a.res); tm = load(a.sfx)
    T = resample(tm, a.rate)
    st = int(a.at * SR)
    wa, wb = map(float, a.win.split(","))
    ia, ib = int(wa * SR), int(wb * SR)

    def pw(sig, i0, i1):
        i0 = max(0, i0); i1 = min(len(sig), i1)
        return sum(x * x for x in sig[i0:i1]) / max(1, i1 - i0)
    P = pw(res, ia, ib)
    fl = [tuple(map(float, w.split(","))) for w in a.floor.split(";")]
    floor = sum(pw(res, int(x * SR), int(y * SR)) for x, y in fl) / len(fl)
    Ps = pw(T, ia - st, ib - st)
    g = math.sqrt(max(P - floor, 1e-12) / max(Ps, 1e-18))
    gm = _music_gain(a.res)
    print(f"residual {10 * math.log10(P + 1e-18):.1f} dB, floor {10 * math.log10(floor + 1e-18):.1f} dB, "
          f"SFX (rate {a.rate:g}) {10 * math.log10(Ps + 1e-18):.1f} dB -> gain {g:.4f}"
          + (f" = {g / gm:.3f}x the music ({20 * math.log10(g / gm):+.1f} dB)" if gm else ""))


def cmd_compare(a):
    mus = load(a.music)
    win = tuple(map(float, a.win.split(","))) if a.win else None
    out = []
    for path in (a.ref, a.ours):
        mix = load(path)
        shift, c, _ = fit_music(mix, mus, win)
        dur = len(mix) / SR
        edges = [dur * k / 8 for k in range(9)]
        g = statistics.median([x for x in (gain_at(mix, mus, shift, edges[k], edges[k + 1]) for k in range(8)) if x == x])
        out.append((path, shift, g, residual(mix, mus, shift, g)))
        print(f"{os.path.basename(path)}: offset {shift} samples ({shift / SR * 1000:+.1f} ms), music gain {g:.4f}, correlation {c:.3f}")
    for ev in a.events.split(","):
        name, span = ev.split(":")
        t0, t1 = map(float, span.split("-"))
        vals = []
        for path, shift, g, res in out:
            i0 = int(t0 * SR) + shift; i1 = int(t1 * SR) + shift
            seg = res[max(0, i0):max(0, i1)]
            rms = math.sqrt(sum(x * x for x in seg) / max(1, len(seg)))
            vals.append(20 * math.log10(rms / g + 1e-12))
        print(f"  {name:10s} reference {vals[0]:6.1f} dB | ours {vals[1]:6.1f} dB (relative to music) | gap {vals[1] - vals[0]:+.1f} dB")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("music"); p.add_argument("ref"); p.add_argument("music")
    p.add_argument("--out", default="au"); p.add_argument("--win"); p.set_defaults(fn=cmd_music)
    p = sub.add_parser("sfx"); p.add_argument("res"); p.add_argument("sfx")
    p.add_argument("--near", required=True); p.add_argument("--rates", default="1"); p.add_argument("--inpoints", default="0")
    p.add_argument("--len", type=float, default=1.2); p.add_argument("--log", action="store_true")
    p.add_argument("--delay", type=float); p.set_defaults(fn=cmd_sfx)
    p = sub.add_parser("level"); p.add_argument("res"); p.add_argument("sfx")
    p.add_argument("--at", type=float, required=True); p.add_argument("--win", required=True)
    p.add_argument("--floor", required=True); p.add_argument("--rate", type=float, default=1.0); p.set_defaults(fn=cmd_level)
    p = sub.add_parser("compare"); p.add_argument("ref"); p.add_argument("ours"); p.add_argument("music")
    p.add_argument("--events", required=True); p.add_argument("--win"); p.set_defaults(fn=cmd_compare)
    a = ap.parse_args(); a.fn(a)


if __name__ == "__main__":
    main()
