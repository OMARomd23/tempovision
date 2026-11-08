#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy>=1.24", "soundfile>=0.12"]
# ///
"""Synthesise a test song with known structure, plus its stems and its lyrics with ground-truth word times.

  uv run tests/make_song.py OUT_DIR [--bpm 120]

Structure at 120 BPM in 4/4 (2 s per bar):
  intro   bars 1-4   pad only, quiet
  verse   bars 5-12  drums + bass + "voice"
  chorus  bars 13-20 louder: drums, bass, chords, "voice", hats doubled
  verse   bars 21-28
  chorus  bars 29-36
  outro   bars 37-40 pad only

The "voice" is a stem of pitched, vowel-like tone bursts, one per word, at the times written to truth.json.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import soundfile as sf

SR = 44100

VERSE_1 = ["paper walls around the room", "every word I never said", "folding up the afternoon", "holding on to what is left"]
CHORUS = ["light it up and let it go", "light it up and let it go", "every night I let you know", "light it up and let it go"]
VERSE_2 = ["counting cars along the street", "every sign is turning red", "waiting for the summer heat", "holding on to what is left"]


def env(n, a=0.002, r=0.12):
    t = np.arange(n) / SR
    e = np.minimum(1, t / a) * np.exp(-t / r)
    return e


def kick(n):
    t = np.arange(n) / SR
    f = 50 + 90 * np.exp(-t * 30)
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * env(n, 0.001, 0.18)


def snare(n, rng):
    return rng.standard_normal(n) * env(n, 0.001, 0.07) * 0.6


def hat(n, rng):
    x = rng.standard_normal(n)
    x = np.diff(np.r_[0, x])
    return x * env(n, 0.0005, 0.02) * 0.25


def tone(freq, n, harmonics=(1, 0.5, 0.25), vibrato=0.0):
    t = np.arange(n) / SR
    ph = 2 * np.pi * freq * t + vibrato * np.sin(2 * np.pi * 5.5 * t)
    return sum(h * np.sin((i + 1) * ph) for i, h in enumerate(harmonics))


def add(buf, start_s, sig):
    i = int(start_s * SR)
    j = min(len(buf), i + len(sig))
    if i < len(buf):
        buf[i:j] += sig[: j - i]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--bpm", type=float, default=120.0)
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(7)
    beat = 60 / a.bpm
    bar = 4 * beat
    nbars = 40
    dur = nbars * bar + 1.0
    N = int(dur * SR)
    drums, bass, other, vocals = (np.zeros(N) for _ in range(4))
    sections = [("intro", 1, 4), ("verse", 5, 12), ("chorus", 13, 20), ("verse", 21, 28), ("chorus", 29, 36), ("outro", 37, 40)]
    roots_verse = [110.0, 98.0, 87.31, 98.0]      # A2 G2 F2 G2
    roots_chorus = [130.81, 98.0, 110.0, 87.31]   # C3 G2 A2 F2
    for name, b0, b1 in sections:
        for b in range(b0, b1 + 1):
            t0 = (b - 1) * bar
            roots = roots_chorus if name == "chorus" else roots_verse
            root = roots[(b - b0) % 4]
            if name in ("intro", "outro"):
                add(other, t0, 0.08 * tone(root * 2, int(bar * SR), (1, 0.3)) * np.hanning(int(bar * SR)))
                continue
            loud = 1.0 if name == "chorus" else 0.55
            for k in range(4):
                add(drums, t0 + k * beat, loud * kick(int(0.4 * SR)))
                if k in (1, 3):
                    add(drums, t0 + k * beat, loud * snare(int(0.2 * SR), rng))
                for h in range(4 if name == "chorus" else 2):
                    add(drums, t0 + k * beat + h * beat / (4 if name == "chorus" else 2), loud * hat(int(0.05 * SR), rng))
                add(bass, t0 + k * beat, loud * 0.5 * tone(root, int(beat * 0.9 * SR), (1, 0.4)) * env(int(beat * 0.9 * SR), 0.005, 0.4))
            if name == "chorus":
                for f in (root * 2, root * 2.52, root * 3):
                    add(other, t0, 0.07 * tone(f, int(bar * SR), (1, 0.2)) * np.hanning(int(bar * SR)))

    # voice: one burst per word; each lyric line starts on a bar's 1st beat and words fall on 8th notes
    lines_by_section = {("verse", 0): VERSE_1, ("chorus", 0): CHORUS, ("verse", 1): VERSE_2, ("chorus", 1): CHORUS}
    seen = {"verse": 0, "chorus": 0}
    truth_lines = []
    lyrics_txt = []
    for name, b0, b1 in sections:
        if name not in ("verse", "chorus"):
            continue
        lines = lines_by_section[(name, seen[name])]
        seen[name] += 1
        lyrics_txt.append(f"[{name.capitalize()}]")
        for li, line in enumerate(lines):
            lyrics_txt.append(line)
            words = line.split()
            t_line = (b0 - 1 + 2 * li) * bar  # each line spans 2 bars
            wl = []
            for wi, w in enumerate(words):
                ws = t_line + wi * beat / 2 * (1.5 if name == "verse" else 1.0)
                wd = beat / 2 * 0.85 * (1.5 if name == "verse" else 1.0)
                freq = 220 * (2 ** (((wi * 3) % 7) / 12))
                n = int(wd * SR)
                add(vocals, ws, 0.35 * tone(freq, n, (1, 0.6, 0.4, 0.2), vibrato=0.4) * env(n, 0.01, wd * 0.8))
                wl.append({"text": w, "start": round(ws, 3), "end": round(ws + wd, 3)})
            truth_lines.append({"text": line, "section": name, "start": wl[0]["start"], "end": wl[-1]["end"], "words": wl})
        lyrics_txt.append("")

    mix = drums + bass + other + vocals
    peak = np.max(np.abs(mix))
    g = 0.89 / peak
    stems_dir = out / "stems"
    stems_dir.mkdir(exist_ok=True)
    for nm, sig in (("drums", drums), ("bass", bass), ("other", other), ("vocals", vocals)):
        sf.write(stems_dir / f"{nm}.wav", np.stack([sig * g] * 2, axis=1).astype(np.float32), SR, subtype="FLOAT")
    sf.write(out / "song.wav", np.stack([mix * g] * 2, axis=1).astype(np.float32), SR, subtype="PCM_24")
    (out / "lyrics.txt").write_text("\n".join(lyrics_txt).strip() + "\n", encoding="utf-8")
    truth = {"bpm": a.bpm, "beats_per_bar": 4, "bar_seconds": bar, "duration": dur,
             "sections": [{"name": n, "start": (b0 - 1) * bar, "end": b1 * bar} for n, b0, b1 in sections],
             "lines": truth_lines}
    (out / "truth.json").write_text(json.dumps(truth, indent=2), encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
