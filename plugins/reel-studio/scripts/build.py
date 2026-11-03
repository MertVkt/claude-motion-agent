#!/usr/bin/env python3
"""Builds a vertical (1080x1920) reel as a native Tesseract project from a declarative spec.

Usage: python3 build.py <spec.py> <project_dir>
The spec module defines SPEC (dict). Footage, fonts and audio are packaged into
<project_dir>/<name>.tsrct; layers, effects and keyframes are written through
`project commit` (media/audio layers) and one atomic `project apply` batch.
"""
import json, os, struct, subprocess, sys, importlib.util

import shutil as _sh
T = os.environ.get("TSRCT") or _sh.which("tsrct") or os.path.expanduser("~/Library/Application Support/Tesseract/bin/tsrct")
HERE = os.path.dirname(os.path.abspath(__file__))
FONTS = os.environ.get("REEL_FONTS") or os.path.join(HERE, "..", "fonts")
# SHARED (clips/, audio/, clips.json) defaults to <spec dir>/../.shared; override with REEL_SHARED.
SHARED = os.environ.get("REEL_SHARED") or ""
os.environ["TESSERACT_SKILL"] = "tesseract-video"

W, H = 1080, 1920
PAPER = [0.961, 0.949, 0.925, 1]
ORANGE = [1.0, 0.455, 0.149, 1]
INK = [0.043, 0.043, 0.047, 1]

EASE_OUT = {"type": "cubicBezier", "x1": 0.16, "y1": 1, "x2": 0.3, "y2": 1}
EASE_IN = {"type": "cubicBezier", "x1": 0.7, "y1": 0, "x2": 0.84, "y2": 0}
EASE_INOUT = {"type": "cubicBezier", "x1": 0.65, "y1": 0, "x2": 0.35, "y2": 1}
LIN = {"type": "linear"}
HOLD = {"type": "hold"}


# ---------------------------------------------------------------- font metrics
class Font:
    """Minimal TrueType reader: advance widths via cmap(4/12) + hmtx."""

    def __init__(self, path):
        b = open(path, "rb").read()
        n = struct.unpack(">H", b[4:6])[0]
        tabs = {}
        for i in range(n):
            tag, _, off, ln = struct.unpack(">4sIII", b[12 + 16 * i: 28 + 16 * i])
            tabs[tag.decode()] = (off, ln)
        self.upem = struct.unpack(">H", b[tabs["head"][0] + 18: tabs["head"][0] + 20])[0]
        nhm = struct.unpack(">H", b[tabs["hhea"][0] + 34: tabs["hhea"][0] + 36])[0]
        ho = tabs["hmtx"][0]
        self.adv = [struct.unpack(">H", b[ho + 4 * i: ho + 4 * i + 2])[0] for i in range(nhm)]
        co = tabs["cmap"][0]
        nt = struct.unpack(">H", b[co + 2: co + 4])[0]
        self.cmap = {}
        for i in range(nt):
            pid, eid, off = struct.unpack(">HHI", b[co + 4 + 8 * i: co + 12 + 8 * i])
            so = co + off
            fmt = struct.unpack(">H", b[so: so + 2])[0]
            if fmt == 4 and not self.cmap:
                segx2 = struct.unpack(">H", b[so + 6: so + 8])[0]; seg = segx2 // 2
                ends = struct.unpack(">%dH" % seg, b[so + 14: so + 14 + segx2])
                starts = struct.unpack(">%dH" % seg, b[so + 16 + segx2: so + 16 + 2 * segx2])
                deltas = struct.unpack(">%dh" % seg, b[so + 16 + 2 * segx2: so + 16 + 3 * segx2])
                ro = so + 16 + 3 * segx2
                ranges = struct.unpack(">%dH" % seg, b[ro: ro + segx2])
                for s in range(seg):
                    for c in range(starts[s], ends[s] + 1):
                        if c == 0xFFFF: continue
                        if ranges[s] == 0:
                            g = (c + deltas[s]) & 0xFFFF
                        else:
                            a = ro + 2 * s + ranges[s] + 2 * (c - starts[s])
                            g = struct.unpack(">H", b[a: a + 2])[0]
                            if g: g = (g + deltas[s]) & 0xFFFF
                        self.cmap[c] = g
            elif fmt == 12:
                ng = struct.unpack(">I", b[so + 12: so + 16])[0]
                for k in range(ng):
                    s, e, g0 = struct.unpack(">III", b[so + 16 + 12 * k: so + 28 + 12 * k])
                    for c in range(s, e + 1): self.cmap[c] = g0 + c - s

    def width(self, text, size, tracking=0):
        tot = 0
        for ch in text:
            g = self.cmap.get(ord(ch), 0)
            tot += self.adv[min(g, len(self.adv) - 1)]
        return tot * size / self.upem + tracking / 1000 * size * max(len(text) - 1, 0)


GOTHIC = Font(os.path.join(FONTS, "LeagueGothic.ttf"))
MONO = Font(os.path.join(FONTS, "SpaceMono-Bold.ttf"))


def fit_size(lines, max_w, cap):
    return min(cap, min(max_w / max(GOTHIC.width(l, 1), 1e-6) for l in lines))


# ---------------------------------------------------------------- helpers
def ms(t):
    return int(round(t * 1000))


def tf(pos=(0, 0), anchor=(0, 0), scale=(100, 100), rot=0, op=100):
    return {"anchorPoint": list(anchor), "position": list(pos), "scale": list(scale), "rotation": rot, "opacity": op}


def run(*args, capture=True):
    r = subprocess.run([T, *args], capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit("tsrct %s failed:\n%s\n%s" % (args[:2], r.stdout, r.stderr))
    return r.stdout


class Build:
    def __init__(self, spec, pdir):
        self.s = spec
        self.pdir = pdir
        self.proj = os.path.join(pdir, spec["name"] + ".tsrct")
        self.work = os.path.join(pdir, ".tesseract-work")
        self.actions = []
        self.tracks = {}  # (layerId, prop) -> list of keys
        self.etracks = {}  # (effectId, param) -> list of keys
        self.next_id = 1000
        self.kid = 0

    def nid(self):
        self.next_id += 1
        return self.next_id

    # keyframe accumulation -------------------------------------------------
    def key(self, layer, prop, t_layer, v, ease=LIN):
        self.kid += 1
        self.tracks.setdefault((layer, prop), []).append(
            {"id": "k%d" % self.kid, "layerTime": ms(t_layer), "value": {"type": "float", "value": float(v)}, "easing": ease})

    def ekey(self, eff, param, t, v, ease=LIN):
        self.kid += 1
        self.etracks.setdefault((eff, param), []).append(
            {"id": "e%d" % self.kid, "layerTime": ms(t), "value": {"type": "float", "value": float(v)}, "easing": ease})

    def flush_keys(self):
        for (layer, prop), keys in self.tracks.items():
            keys = dedupe(keys)
            self.actions.append({"type": "setFxPropertyKeyframes", "compositionId": "main",
                                 "property": {"layerId": layer, "propertyType": prop}, "keyframes": keys})
        for (eff, param), keys in self.etracks.items():
            keys = dedupe(keys)
            self.actions.append({"type": "setFxLayerEffectParamAnimator", "compositionId": "main", "layerId": FX_LAYER,
                                 "effectId": eff, "paramName": param, "dependencies": [],
                                 "animator": {"type": "keyframes", "enabled": True, "keyframes": keys}})

    # ---------------------------------------------------------------- build
    def build(self):
        s = self.s
        os.makedirs(self.work, exist_ok=True)
        if os.path.exists(self.proj):
            os.replace(self.proj, os.path.join(self.work, "previous.tsrct"))
        run("project", "create", "--project", self.proj)
        clips = json.load(open(os.path.join(SHARED, "clips.json")))
        used = sorted({sh["clip"] for sh in s["shots"]})
        self.vdur = {}
        for c in used:
            out = run("project", "import-video", "--project", self.proj, "--file", os.path.join(SHARED, "clips", c + ".mp4"), "--asset-id", c)
            self.vdur[c] = json.loads(out.strip().splitlines()[-1])["durationMs"]
        for f in ("LeagueGothic.ttf", "SpaceMono-Bold.ttf", "SpaceMono-Regular.ttf"):
            subprocess.run([T, "project", "import-font", "--project", self.proj, "--file", os.path.join(FONTS, f)], capture_output=True)
        audio_files = {s["music"][0]} | {x[0] for x in s.get("sfx", [])}
        aid = {}
        for f in sorted(audio_files):
            a = os.path.splitext(f)[0].replace(".", "-")
            run("project", "import-asset", "--project", self.proj, "--file", os.path.join(SHARED, "audio", f), "--asset-id", a, "--kind", "audio")
            aid[f] = a

        # ---- media + audio layers via editable JSON
        ed = os.path.join(self.work, "editable.json")
        run("project", "checkout", "--project", self.proj, "--output", ed)
        doc = json.load(open(ed))
        doc["duration"] = s["duration"]
        layers = []
        # footage: later shots in front (index 0 = front)
        for i, sh in reversed(list(enumerate(s["shots"]))):
            meta = clips[sh["clip"]]
            rate = sh.get("rate", 1.0)
            # each shot (but the last) overlaps the next by 2 frames, hiding the incoming decoder's first-frame gap
            tail = 0.067 if i < len(s["shots"]) - 1 else 0.0
            dur = ms(sh["dur"] + tail)
            src_start = ms(meta["handle"] + sh.get("off", 0.0))
            src_dur = ms((sh["dur"] + tail) * rate)
            layer = {"type": "Video", "id": 1 + i, "name": "%02d %s" % (i + 1, sh["clip"]),
                     "playback": {"type": "windowed", "inputRange": {"start": ms(sh["t"]), "duration": dur},
                                  "mapping": {"type": "linear", "input": {"start": ms(sh["t"]), "duration": dur},
                                              "output": {"start": src_start, "duration": src_dur}}, "inputOffsetMs": 0},
                     "sourceRange": {"start": src_start, "duration": src_dur},
                     "sourceIntrinsicDuration": self.vdur[sh["clip"]],
                     "volume": round(sh.get("vol", s.get("footageVol", 0.3)) * s.get("gain", 1.0), 4),
                     "transform": tf((W / 2, H / 2), (W / 2, H / 2)),
                     "source": {"assetId": sh["clip"], "fit": "cover"}}
            layers.append(layer)
        mfile, mvol = s["music"]
        mdur = ms(s["duration"])
        audio = [{"type": "Audio", "id": 900, "name": "Music", "source": {"assetId": aid[mfile]},
                  "playback": {"type": "windowed", "inputRange": {"start": 0, "duration": mdur},
                               "mapping": {"type": "linear", "input": {"start": 0, "duration": mdur}, "output": {"start": 0, "duration": mdur}},
                               "inputOffsetMs": 0},
                  "sourceRange": {"start": 0, "duration": mdur}, "sourceIntrinsicDuration": mdur, "volume": round(mvol * s.get("gain", 1.0), 4),
                  "metadata": {"modality": "music", "source": "stock", "sourceName": s.get("musicName")}}]
        for k, (f, peak, vol, offset, dur) in enumerate(s.get("sfx", [])):
            st = max(0.0, peak - offset)
            d = ms(dur)
            audio.append({"type": "Audio", "id": 901 + k, "name": "SFX %s @%.2f" % (f, peak), "source": {"assetId": aid[f]},
                          "playback": {"type": "windowed", "inputRange": {"start": ms(st), "duration": d},
                                       "mapping": {"type": "linear", "input": {"start": ms(st), "duration": d}, "output": {"start": 0, "duration": d}},
                                       "inputOffsetMs": 0},
                          "sourceRange": {"start": 0, "duration": d}, "sourceIntrinsicDuration": ms(SFX_LEN[f]), "volume": round(vol * s.get("gain", 1.0), 4),
                          "metadata": {"modality": "soundEffect", "source": "stock"}})
        doc["composition"]["layers"] = layers + audio
        json.dump(doc, open(ed, "w"))
        run("project", "commit", "--project", self.proj, "--file", ed)

        if s.get("sync"):
            self.sync_hits(clips)
        if s.get("gate"):
            self.gate_footage(clips)
        self.fx_stack()
        self.footage_motion()
        self.overlays()
        self.texts()
        self.endcard()
        self.flush_keys()
        self.actions.append({"type": "setFxCompositionMotionBlur", "compositionId": "main",
                             "settings": {"enabled": True, "shutterAngle": 200, "shutterPhase": -100,
                                          "samplesPerFrame": 12, "adaptiveSampleLimit": 64}})
        for i in range(len(s["shots"])):
            self.actions.append({"type": "setFxLayerMotionBlur", "compositionId": "main", "layerId": 1 + i, "enabled": True})
        af = os.path.join(self.work, "edits.json")
        json.dump(self.actions, open(af, "w"), ensure_ascii=False, indent=0)
        print(run("project", "apply", "--project", self.proj, "--actions", af).strip())

    # ---------------------------------------------------------------- music sync
    def sync_hits(self, clips):
        """Slide each shot's source in-point (within its handles) so a real strike in the
        clip lands on a strong music onset; then put the punch/RGB hit on that beat."""
        sys.path.insert(0, HERE)
        import analyze
        cfg = self.s["sync"]
        mfile = os.path.join(SHARED, "audio", self.s["music"][0])
        mv = analyze.rms(mfile)
        beats = analyze.onsets(mv, jump=cfg.get("beatJump", 5), gap=0.12)
        if cfg.get("grid"):
            g0, gp = cfg["grid"]
            k = 0
            while g0 + k * gp < self.s["duration"]:
                bt = round(g0 + k * gp, 3)
                if all(abs(bt - b) > 0.06 for b, _ in beats):
                    beats.append((bt, 3.0))
                k += 1
        beats.sort()
        skip = set(cfg.get("skip", []))
        maxs = cfg.get("maxShift", 0.35)
        nshots = len(self.s["shots"])
        orig = self.s["events"]
        events = [e for e in orig if not (e[0] == "punch" and e[1] not in skip)]
        manual = {}
        for e in orig:
            if e[0] == "punch":
                manual.setdefault(e[1], []).append(e)
        # per-shot safe windows: keep punches clear of transitions that move the same layer
        busy_in, busy_out = set(), set()
        for e in orig:
            if e[0] == "whip": busy_out.add(e[1]); busy_in.add(e[2])
            if e[0] == "zoom": busy_out.add(e[1]); busy_in.add(e[2])
            if e[0] in ("snap", "glitch"): busy_in.add(e[1])
        report = []
        for i, sh in enumerate(self.s["shots"]):
            if i in skip:
                continue
            meta = clips[sh["clip"]]
            rate = sh.get("rate", 1.0)
            tail = 0.067 if i < nshots - 1 else 0.0
            s0 = meta["handle"] + sh.get("off", 0.0)
            span = (sh["dur"] + tail) * rate
            hits = analyze.onsets(analyze.rms(os.path.join(SHARED, "clips", sh["clip"] + ".mp4")), jump=cfg.get("hitJump", 5))
            lo_t = sh["t"] + (cfg.get("edgeIn", 0.3) if i in busy_in else 0.06)
            hi_t = sh["t"] + sh["dur"] - (cfg.get("edgeOut", 0.62) if i in busy_out else 0.38)
            cands = []
            for h, hs in hits:
                for b, bs in beats:
                    if not (lo_t <= b <= hi_t):
                        continue
                    ns0 = h - (b - sh["t"]) * rate
                    d = ns0 - s0
                    if abs(d) > maxs or ns0 < 0.0 or ns0 + span > meta["fileDur"] - 0.02:
                        continue
                    cands.append((hs + bs - 8 * abs(d), ns0, b, h, hs, bs))
            if not cands:
                # keep the hand-placed punches, snapped to the nearest beat when one is close
                kept = []
                for e in manual.get(i, []):
                    nb = min(beats, key=lambda x: abs(x[0] - e[2]))[0] if beats else e[2]
                    tt = nb if abs(nb - e[2]) <= 0.15 and lo_t <= nb <= hi_t else e[2]
                    events.append(("punch", i, round(tt, 3), e[3])); kept.append(round(tt, 2))
                report.append((i, sh["clip"], "no strike match; manual punch on %s" % kept))
                continue
            cands.sort(reverse=True)
            _, ns0, b, h, hs, bs = cands[0]
            sh["off"] = round(ns0 - meta["handle"], 3)
            amt = round(min(1.4, 0.8 + 0.03 * (hs + bs)), 2)
            events.append(("punch", i, round(b, 3), amt))
            # a second strike in the same shot that also sits on a beat (no further shift)
            for h2, hs2 in hits:
                t2 = sh["t"] + (h2 - ns0) / rate
                if abs(t2 - b) > 0.45 and lo_t <= t2 <= hi_t and any(abs(t2 - bb) < 0.05 for bb, _ in beats):
                    events.append(("punch", i, round(t2, 3), round(amt * 0.85, 2)))
                    break
            report.append((i, sh["clip"], "beat %.2f (shift %+.2fs)" % (b, ns0 - s0)))
        self.s["events"] = events
        json.dump(report, open(os.path.join(self.work, "sync-report.json"), "w"), ensure_ascii=False)
        for r in report:
            print("sync", r)

    # ---------------------------------------------------------------- audio gate
    def gate_footage(self, clips):
        """Footage audio stays silent except a short window around each detected hit
        (a strike, slam or hit). Sustained voices and crowd noise never open the gate."""
        sys.path.insert(0, HERE)
        import analyze
        g = self.s.get("gate")
        base = round(self.s.get("footageVol", 1.0) * self.s.get("gain", 1.0), 4)
        report = []
        for i, sh in enumerate(self.s["shots"]):
            meta = clips[sh["clip"]]
            rate = sh.get("rate", 1.0)
            a = meta["handle"] + sh.get("off", 0.0)
            b = a + sh["dur"] * rate
            hits = [t for t, _ in analyze.onsets(analyze.rms(os.path.join(SHARED, "clips", sh["clip"] + ".mp4")), jump=g.get("jump", 6))
                    if a + 0.01 < t < b - 0.05]
            L = 1 + i
            self.key(L, "volume", 0, 0)
            for t in hits:
                lt = (t - a) / rate
                self.key(L, "volume", lt - 0.02, 0)
                self.key(L, "volume", lt, base, LIN)
                self.key(L, "volume", lt + g.get("hold", 0.11), base)
                self.key(L, "volume", lt + g.get("hold", 0.11) + 0.12, 0, LIN)
            report.append((sh["clip"], [round(sh["t"] + (t - a) / rate, 2) for t in hits]))
        json.dump(report, open(os.path.join(self.work, "gate-hits.json"), "w"))
        print("gate hits:", report)

    # ---------------------------------------------------------------- FX
    def fx_stack(self):
        s = self.s
        dur = ms(s["duration"])
        # Adjustment above all footage, below every graphic.
        self.actions += [
            {"type": "createFxAdjustmentLayer", "compositionId": "main", "layerId": FX_LAYER, "name": "FX hits & transitions",
             "insertIndex": 0, "activeRange": {"start": 0, "duration": dur}, "transform": tf()},
            {"type": "addFxLayerEffect", "compositionId": "main", "layerId": FX_LAYER, "effectId": E_GRADE,
             "effect": {"type": "brightnessContrast", "brightness": -4, "contrast": 16}},
            {"type": "addFxLayerEffect", "compositionId": "main", "layerId": FX_LAYER, "effectId": E_GRADE2,
             "effect": {"type": "hueSaturation", "hue": 0, "saturation": 10, "lightness": 0, "colorize": False, "colorizeHue": 0, "colorizeSaturation": 0, "colorizeLightness": 0}},
            {"type": "addFxLayerEffect", "compositionId": "main", "layerId": FX_LAYER, "effectId": E_DBLUR,
             "effect": {"type": "directionalBlur", "direction": 90, "blurLength": 0}},
            {"type": "addFxLayerEffect", "compositionId": "main", "layerId": FX_LAYER, "effectId": E_RBLUR,
             "effect": {"type": "radialBlur", "centerX": 0.5, "centerY": 0.5, "amount": 0}},
            {"type": "addFxLayerEffect", "compositionId": "main", "layerId": FX_LAYER, "effectId": E_CA,
             "effect": {"type": "chromaticAberration", "amount": 0, "direction": 0}},
            {"type": "addFxLayerEffect", "compositionId": "main", "layerId": FX_LAYER, "effectId": E_VIG,
             "effect": {"type": "vignette", "amount": s.get("vignette", 0.35), "feather": 0.6, "radius": 0.75}},
            {"type": "addFxLayerEffect", "compositionId": "main", "layerId": FX_LAYER, "effectId": E_GRAIN,
             "effect": {"type": "grain", "amount": s.get("grain", 0.12), "size": 1.2, "softness": 0.2, "seed": 7}},
        ]
        for p in ("blurLength",):
            self.ekey(E_DBLUR, p, 0, 0)
        self.ekey(E_RBLUR, "amount", 0, 0)
        self.ekey(E_CA, "amount", 0, 0)

    def ca(self, t, amt, rise=0.035, fall=0.28):
        self.ekey(E_CA, "amount", t - rise - 0.001, 0)
        self.ekey(E_CA, "amount", t, amt, EASE_IN)
        self.ekey(E_CA, "amount", t + fall, 0, EASE_OUT)

    def footage_motion(self):
        s = self.s
        shots = s["shots"]
        for ev in s.get("events", []):
            kind = ev[0]
            if kind == "punch":
                _, i, t, amt = ev
                self.punch(i, t, amt)
                self.ca(t, 1.6 * amt)
            elif kind == "whip":
                _, a, b, t, d, direction = ev
                self.whip(a, b, t, d, direction)
            elif kind == "zoom":  # zoom-through: outgoing pushes in, incoming lands oversized
                _, a, b, t = ev
                la, lb = 1 + a, 1 + b
                ta = t - shots[a]["t"]; tb = t - shots[b]["t"]
                for p in ("scaleX", "scaleY"):
                    self.key(la, p, ta - 0.24, 100)
                    self.key(la, p, ta, 165, EASE_IN)
                    self.key(lb, p, tb, 145)
                    self.key(lb, p, tb + 0.5, 100, EASE_OUT)
                self.ekey(E_RBLUR, "amount", t - 0.25, 0)
                self.ekey(E_RBLUR, "amount", t, 42, EASE_IN)
                self.ekey(E_RBLUR, "amount", t + 0.38, 0, EASE_OUT)
                self.ca(t, 4.0, 0.2, 0.4)
            elif kind == "snap":  # incoming shot lands oversized and slams to frame
                _, i, t, frm = ev
                tl = t - shots[i]["t"]
                for p in ("scaleX", "scaleY"):
                    self.key(1 + i, p, tl, frm)
                    self.key(1 + i, p, tl + 0.3, 100, EASE_OUT)
                self.ekey(E_RBLUR, "amount", t, 22)
                self.ekey(E_RBLUR, "amount", t + 0.22, 0, EASE_OUT)
            elif kind == "push":  # slow push-in across a shot
                _, i, frm, to = ev
                for p in ("scaleX", "scaleY"):
                    self.key(1 + i, p, 0, frm)
                    self.key(1 + i, p, shots[i]["dur"], to, LIN)
            elif kind == "glitch":  # stepped lateral tear + RGB split
                _, i, t, d, amt = ev
                tl = t - shots[i]["t"]
                steps = [0, -1, 0.6, -0.35, 0.8, 0]
                for k, v in enumerate(steps):
                    self.key(1 + i, "positionX", tl + d * k / (len(steps) - 1), W / 2 + v * amt, HOLD if 0 < k < len(steps) - 1 else LIN)
                self.ca(t + d * 0.4, 5.0, d * 0.4, d * 0.9)
            elif kind == "ca":
                _, t, amt = ev
                self.ca(t, amt)
            elif kind == "flash":
                self.flash_ev.append(ev[1:])
            elif kind == "dip":
                self.dip_ev.append(ev[1:])

    def punch(self, i, t, amt):
        tl = t - self.s["shots"][i]["t"]
        L = 1 + i
        seq = [(-0.001, 100, 0, 0, 0, LIN), (0.04, 100 + 13 * amt, -24 * amt, 10 * amt, -1.6 * amt, EASE_OUT),
               (0.085, 100 + 9 * amt, 20 * amt, -8 * amt, 1.2 * amt, LIN), (0.135, 100 + 5 * amt, -11 * amt, 5 * amt, -0.6 * amt, LIN),
               (0.185, 100 + 2 * amt, 5 * amt, -2 * amt, 0.25 * amt, LIN), (0.36, 100, 0, 0, 0, EASE_OUT)]
        for dt, sc, x, y, r, e in seq:
            self.key(L, "scaleX", tl + dt, sc, e); self.key(L, "scaleY", tl + dt, sc, e)
            self.key(L, "positionX", tl + dt, W / 2 + x, e); self.key(L, "positionY", tl + dt, H / 2 + y, e)
            self.key(L, "rotation", tl + dt, r, e)

    def whip(self, a, b, t, d, direction):
        sh = self.s["shots"]
        sign = -1 if direction == "left" else 1
        la, lb = 1 + a, 1 + b
        ta = t - sh[a]["t"]; tb = t - sh[b]["t"]
        self.key(la, "positionX", ta, W / 2)
        self.key(la, "positionX", ta + d, W / 2 + sign * W, EASE_INOUT)
        self.key(lb, "positionX", tb, W / 2 - sign * W)
        self.key(lb, "positionX", tb + d, W / 2, EASE_INOUT)
        self.ekey(E_DBLUR, "blurLength", t, 0)
        self.ekey(E_DBLUR, "blurLength", t + d / 2, 230, EASE_IN)
        self.ekey(E_DBLUR, "blurLength", t + d, 0, EASE_OUT)
        self.ca(t + d / 2, 3.0, d / 2, d / 2 + 0.12)

    # ---------------------------------------------------------------- overlays
    flash_ev = None
    dip_ev = None

    def overlays(self):
        dur = ms(self.s["duration"])
        self.actions.append({"type": "createFxRectLayer", "compositionId": "main", "layerId": DIP, "name": "Dip to black", "insertIndex": 0,
                             "activeRange": {"start": 0, "duration": dur}, "transform": tf((0, 0), (0, 0), op=0),
                             "rect": {"size": [W, H], "fillColor": [0, 0, 0, 1]}})
        self.actions.append({"type": "createFxRectLayer", "compositionId": "main", "layerId": FLASH, "name": "Flash", "insertIndex": 0,
                             "activeRange": {"start": 0, "duration": dur}, "transform": tf((0, 0), (0, 0), op=0),
                             "rect": {"size": [W, H], "fillColor": [1, 0.992, 0.98, 1]}})
        self.key(FLASH, "opacity", 0, 0)
        for t, peak in self.flash_ev:
            self.key(FLASH, "opacity", t - 0.05, 0)
            self.key(FLASH, "opacity", t, peak * 100, EASE_IN)
            self.key(FLASH, "opacity", t + 0.3, 0, EASE_OUT)
        self.key(DIP, "opacity", 0, 0)
        for t, in self.dip_ev:
            self.key(DIP, "opacity", t - 0.12, 0)
            self.key(DIP, "opacity", t, 100, EASE_IN)
            self.key(DIP, "opacity", t + 0.4, 0, EASE_OUT)
        # top legibility scrim + brand label
        bs, be = self.s["brand"]
        self.text_layer(BRAND, self.s.get("brandLabel", "YOUR BRAND"), "Space Mono", "Bold", 30, PAPER, (112, 268), bs, be - bs, tracking=180, shadow=True)
        self.actions.append({"type": "createFxRectLayer", "compositionId": "main", "layerId": BRAND + 1, "name": "Brand dot", "insertIndex": 0,
                             "activeRange": {"start": ms(bs), "duration": ms(be - bs)}, "transform": tf((80, 248), (0, 0)),
                             "rect": {"size": [18, 18], "fillColor": ORANGE, "roundness": 9}})
        for L in (BRAND, BRAND + 1):
            self.key(L, "opacity", 0, 0)
            self.key(L, "opacity", 0.5, 100, EASE_OUT)
            self.key(L, "opacity", be - bs - 0.3, 100)
            self.key(L, "opacity", be - bs, 0, LIN)

    def text_layer(self, lid, text, fam, style, size, color, pos, start, dur, tracking=0, shadow=True, anchor=(0, 0)):
        self.actions.append({"type": "createFxTextLayer", "compositionId": "main", "layerId": lid, "name": text[:40], "insertIndex": 0,
                             "activeRange": {"start": ms(start), "duration": ms(dur)}, "transform": tf(pos, anchor),
                             "sourceText": {"text": text, "fontFamily": fam, "fontStyle": style, "fontSize": size, "fillColor": color,
                                            "strokeWidth": 0, "justification": "left", "tracking": tracking}})
        if shadow:
            self.actions.append({"type": "addFxLayerEffect", "compositionId": "main", "layerId": lid, "effectId": lid * 10 + 1,
                                 "effect": {"type": "dropShadow", "enabled": True, "blendMode": "multiply", "blurRadius": max(12, size * 0.16),
                                            "color": [0, 0, 0, 0.6], "offset": [0, max(3, size * 0.03)], "spreadRadius": 0}})

    # ---------------------------------------------------------------- copy
    def texts(self):
        for c in self.s["cards"]:
            lines = c["lines"]
            size = c.get("size") or fit_size([l for l, _ in lines], W - 160, c.get("cap", 230))
            lh = size * 0.9
            y0 = c.get("top", 420) + size * 0.78
            dur = c["end"] - c["start"]
            for k, (txt, accent) in enumerate(lines):
                lid = self.nid()
                y = y0 + k * lh
                self.text_layer(lid, txt, "League Gothic", "Regular", size, ORANGE if accent else PAPER, (80, y), c["start"], dur)
                d0 = c.get("delay", 0.06) + k * 0.09
                style = c.get("style", "rise")
                if style == "rise":
                    self.key(lid, "positionY", 0, y + size * 0.55)
                    self.key(lid, "positionY", d0, y + size * 0.55)
                    self.key(lid, "positionY", d0 + 0.42, y, EASE_OUT)
                    self.key(lid, "opacity", 0, 0)
                    self.key(lid, "opacity", d0, 0)
                    self.key(lid, "opacity", d0 + 0.16, 100, LIN)
                else:  # slam
                    for p in ("scaleX", "scaleY"):
                        self.key(lid, p, d0, 155)
                        self.key(lid, p, d0 + 0.17, 100, EASE_OUT)
                    self.key(lid, "opacity", 0, 0)
                    self.key(lid, "opacity", d0, 0)
                    self.key(lid, "opacity", d0 + 0.08, 100, LIN)
                self.key(lid, "opacity", dur - 0.14, 100)
                self.key(lid, "opacity", dur - 0.01, 0, LIN)
            # orange underline bar wipes in under the last line
            bar = self.nid()
            by = y0 + (len(lines) - 1) * lh + size * 0.16
            self.actions.append({"type": "createFxRectLayer", "compositionId": "main", "layerId": bar, "name": "Bar", "insertIndex": 0,
                                 "activeRange": {"start": ms(c["start"]), "duration": ms(dur)}, "transform": tf((80, by), (0, 0)),
                                 "rect": {"size": [240, 14], "fillColor": ORANGE}})
            dl = c.get("delay", 0.06) + len(lines) * 0.09 + 0.08
            self.key(bar, "scaleX", 0, 0)
            self.key(bar, "scaleX", dl, 0)
            self.key(bar, "scaleX", dl + 0.3, 100, EASE_OUT)
            self.key(bar, "opacity", dur - 0.14, 100)
            self.key(bar, "opacity", dur - 0.01, 0)
            if c.get("label"):
                lab = self.nid()
                self.text_layer(lab, c["label"], "Space Mono", "Bold", 30, ORANGE, (84, c.get("top", 420) - 18), c["start"], dur, tracking=200)
                self.key(lab, "opacity", 0, 0); self.key(lab, "opacity", 0.25, 0); self.key(lab, "opacity", 0.5, 100, EASE_OUT)
                self.key(lab, "opacity", dur - 0.14, 100); self.key(lab, "opacity", dur - 0.01, 0)

    def endcard(self):
        e = self.s["endcard"]
        st, dur = e["start"], self.s["duration"] - e["start"]
        # bottom-up darkening built from translucent bands (a gradient overlay would keep the rect opaque)
        bands = 40
        top = H * 0.32
        edges = [int(round(top + (H - top) * k / bands)) for k in range(bands + 1)]
        for k in range(bands):
            f = (k + 1) / bands
            y0 = edges[k]
            sc = self.nid()
            self.actions.append({"type": "createFxRectLayer", "compositionId": "main", "layerId": sc, "name": "End scrim %d" % k, "insertIndex": 0,
                                 "activeRange": {"start": ms(st), "duration": ms(dur)}, "transform": tf((0, y0)),
                                 "rect": {"size": [W, edges[k + 1] - y0], "fillColor": [0, 0, 0, round(0.1 + 0.8 * f ** 1.4, 3)]}})
            self.key(sc, "opacity", 0, 0); self.key(sc, "opacity", 0.5, 100, EASE_OUT)
        y = 1010
        tag = self.nid()
        self.text_layer(tag, e["tag"], "Space Mono", "Bold", 34, ORANGE, (84, y), st, dur, tracking=160)
        name = self.nid()
        self.text_layer(name, e.get("name", "BRAND"), "League Gothic", "Regular", 300, PAPER, (74, y + 280), st, dur)
        sub = self.nid()
        self.text_layer(sub, e.get("sub", "STUDIO"), "Space Mono", "Bold", 30, PAPER, (84, y + 345), st, dur, tracking=220)
        cta_txt = e["cta"]
        cw = MONO.width(cta_txt, 34, 60) + 68
        cta_bg = self.nid()
        self.actions.append({"type": "createFxRectLayer", "compositionId": "main", "layerId": cta_bg, "name": "CTA pill", "insertIndex": 0,
                             "activeRange": {"start": ms(st), "duration": ms(dur)}, "transform": tf((80, y + 400), (0, 0)),
                             "rect": {"size": [cw, 92], "fillColor": ORANGE}})
        cta = self.nid()
        self.text_layer(cta, cta_txt, "Space Mono", "Bold", 34, INK, (114, y + 458), st, dur, tracking=60, shadow=False)
        handle = self.nid()
        self.text_layer(handle, e.get("handle", ""), "Space Mono", "Bold", 30, PAPER, (84, y + 560), st, dur, tracking=120)
        seq = [(tag, 0.1, "slide"), (name, 0.2, "rise"), (sub, 0.45, "fade"), (cta_bg, 0.62, "pop"), (cta, 0.62, "pop"), (handle, 0.85, "fade")]
        for lid, d0, kind in seq:
            self.key(lid, "opacity", 0, 0); self.key(lid, "opacity", d0, 0); self.key(lid, "opacity", d0 + 0.2, 100, LIN)
            if kind == "rise":
                self.key(lid, "positionY", d0, y + 280 + 160); self.key(lid, "positionY", d0 + 0.5, y + 280, EASE_OUT)
            if kind == "slide":
                self.key(lid, "positionX", d0, 40); self.key(lid, "positionX", d0 + 0.35, 84, EASE_OUT)
            if kind == "pop":
                base = y + 400 if lid == cta_bg else y + 458
                self.key(lid, "positionY", d0, base + 40)
                self.key(lid, "positionY", d0 + 0.45, base, {"type": "cubicBezier", "x1": 0.34, "y1": 1.56, "x2": 0.64, "y2": 1})


def dedupe(keys):
    keys = sorted(keys, key=lambda k: k["layerTime"])
    out = []
    for k in keys:
        if out and out[-1]["layerTime"] == k["layerTime"]:
            out[-1] = k  # later author wins
        else:
            out.append(k)
    return out


FX_LAYER, FLASH, DIP, BRAND = 500, 510, 511, 520
E_GRADE, E_DBLUR, E_RBLUR, E_CA, E_VIG, E_GRAIN, E_GRADE2 = 5001, 5002, 5003, 5004, 5005, 5006, 5007
SFX_LEN = {}

if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit("usage: build.py <spec.py> <project_dir>")
    spec_path, pdir = sys.argv[1], sys.argv[2]
    if not SHARED:
        SHARED = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(spec_path)), "..", ".shared"))
    if not os.path.exists(T):
        sys.exit("tsrct not found - run plugins/reel-studio/install.sh or set TSRCT=/path/to/tsrct")
    sp = importlib.util.spec_from_file_location("spec", spec_path)
    m = importlib.util.module_from_spec(sp); sp.loader.exec_module(m)
    for f in os.listdir(os.path.join(SHARED, "audio")):
        SFX_LEN[f] = float(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
                                                    os.path.join(SHARED, "audio", f)]).decode())
    b = Build(m.SPEC, pdir)
    b.flash_ev, b.dip_ev = [], []
    b.build()
