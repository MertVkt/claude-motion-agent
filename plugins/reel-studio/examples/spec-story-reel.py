# Example: "From the ring to the studio" (20.4s). Music beat grid every 0.3s; the drop at 12.0 is the location reveal.
SPEC = {
    "brandLabel": "NORTHSIDE TRAINING STUDIO",
    "name": "Reel1",
    "duration": 20.4,
    "footageVol": 0.0,
    "gain": 0.52,
    "music": ("track-a.wav", 0.9),
    "musicName": "your-track.wav (user supplied, licensed) from 24.07s",
    "sync": {"skip": [0, 1, 11, 12], "grid": [0.27, 0.3], "edgeIn": 0.3, "edgeOut": 0.62, "maxShift": 0.35},
    "shots": [
        {"clip": "r1a", "t": 0.0, "dur": 2.4},                    # 0 stairs, punch to camera
        {"clip": "r1b", "t": 2.4, "dur": 2.525},                  # 1 walkout
        {"clip": "r1c", "t": 4.675, "dur": 1.325},                # 2 sparring
        {"clip": "r1d", "t": 6.0, "dur": 1.2},                    # 3 sparring
        {"clip": "r1e", "t": 7.2, "dur": 1.35},                   # 4 pads
        {"clip": "r1f", "t": 8.3, "dur": 1.3},                    # 5 sparring
        {"clip": "r1g", "t": 9.6, "dur": 1.2},                    # 6 switch kick (hit ~10.4)
        {"clip": "r1h", "t": 10.8, "dur": 1.25},                  # 7 pads
        {"clip": "r1i", "t": 12.0, "dur": 1.2},                   # 8 the studio
        {"clip": "r1j", "t": 13.2, "dur": 1.2},                   # 9 the studio
        {"clip": "r1k", "t": 14.4, "dur": 1.8, "rate": 0.625},    # 10 slow-motion kick (~15.04)
        {"clip": "r1l", "t": 16.2, "dur": 1.2},                   # 11 turns to camera
        {"clip": "r1m", "t": 17.4, "dur": 3.0, "rate": 0.38, "off": -0.05},      # 12 swinging bag, end card
    ],
    "events": [
        ("punch", 0, 1.2, 0.9),
        ("flash", 2.4, 0.95), ("glitch", 1, 2.4, 0.25, 70),
        ("whip", 1, 2, 4.675, 0.25, "left"),
        ("punch", 2, 5.4, 1.0),
        ("snap", 3, 6.0, 1.3), ("punch", 3, 6.6, 1.1),
        ("snap", 4, 7.2, 1.3), ("punch", 4, 7.8, 1.1),
        ("whip", 4, 5, 8.3, 0.25, "right"),
        ("punch", 5, 9.0, 1.1),
        ("snap", 6, 9.6, 1.25), ("punch", 6, 10.4, 1.3),
        ("punch", 7, 11.4, 1.0),
        ("zoom", 7, 8, 12.0), ("flash", 12.0, 0.95), ("flash", 12.3, 0.5),
        ("punch", 8, 12.75, 0.9),
        ("snap", 9, 13.2, 1.25), ("punch", 9, 13.8, 1.0),
        ("flash", 14.97, 0.35), ("ca", 14.97, 3.0),
        ("flash", 16.2, 0.8), ("glitch", 11, 16.2, 0.25, 60),
        ("dip", 17.4), ("push", 12, 108, 100),
    ],
    "brand": (0.0, 17.3),
    "cards": [
        {"start": 0.15, "end": 4.6, "top": 420, "lines": [("THIS STUDIO'S", 0), ("STORY STARTED", 0), ("IN THE RING.", 1)]},
        {"start": 4.85, "end": 8.3, "top": 420, "lines": [("YEARS OF", 0), ("HARD LESSONS,", 1)]},
        {"start": 8.45, "end": 11.95, "top": 420, "lines": [("NOW TAUGHT", 0), ("IN A STUDIO", 0), ("OF ITS OWN.", 1)]},
        {"start": 12.15, "end": 17.3, "top": 420, "label": "YOUR CITY", "lines": [("TRAINING FOR", 0), ("EVERY", 0), ("LEVEL.", 1)]},
    ],
    "endcard": {"start": 17.4, "tag": "TRAINING", "cta": "DM US TO BOOK A FREE CLASS", "name": "NORTHSIDE", "sub": "TRAINING STUDIO", "handle": "@yourhandle"},
    # (file, visual peak time, volume, transient offset in file, duration)
    "sfx": [
        ("impact-bass-2.mp3", 2.4, 0.85, 0.37, 2.0), ("glitch-1.mp3", 2.4, 0.3, 0.947, 1.6),
        ("whoosh-short.mp3", 4.8, 0.8, 0.152, 0.57),
        ("whoosh.mp3", 8.425, 0.75, 0.152, 0.57),
        ("impact-bass-1.mp3", 10.4, 0.55, 0.065, 1.2),
        ("glitch-1.mp3", 12.0, 0.45, 0.947, 2.0), ("impact-bass-2.mp3", 12.0, 0.6, 0.37, 2.2),
        ("impact-bass-2.mp3", 14.97, 0.7, 0.37, 1.2),
        ("whoosh-short.mp3", 16.2, 0.7, 0.152, 0.57), ("glitch-1.mp3", 16.2, 0.3, 0.947, 1.2),
        ("impact-bass-2.mp3", 17.4, 0.8, 0.37, 2.5),
    ],
}
