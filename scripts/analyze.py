#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy>=1.24", "scipy>=1.10", "librosa>=0.10", "soundfile>=0.12", "matplotlib>=3.7", "pyloudnorm>=0.1.1"]
# ///
"""Analyse the song: tempo, beats, downbeats, bars, sections, energy, onsets per stem, key, loudness.

  tempovision analyze                        full analysis of the project's song -> analysis/audio.json + plots/overview.png
  tempovision analyze --quick                fast summary (tempo, sections, energy) printed for the interview
  tempovision analyze --file SONG            analyse any file (no project needed); prints JSON
  tempovision analyze --beats-per-bar 3      for songs in 3/4 or 6/8
  tempovision analyze --downbeat-offset 1    shift the bar grid by N beats if the downbeats are off
  tempovision analyze --bpm 75               force the tempo when the detected one is a related tempo (x2, x3/4 ...)

The detected tempo is checked against its related tempi (x2, x1/2, x3/4, x4/3, x3/2, x2/3): each is scored by how
much more onset strength (drum stem when present) lands on its beats than between them, window by window. A
clearly better relative replaces the detection (tempo.corrected_from says so), and a close one is reported as
tempo.ambiguous with the candidates, so a wrong grid is caught before any cut is timed to it.

Uses stems from analysis/stems/ when present (tempovision stems), for per-stem onsets and energy.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import Fail, decode_audio, find_project, fmt_time, info, load_state, save_json, song_path  # noqa: E402

SR = 22050
HOP = 512
STEMS = ("vocals", "drums", "bass", "other")
KEY_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
# Krumhansl–Kessler key profiles
MAJOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
MINOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])


def db(x, floor=-80.0):
    return np.maximum(20 * np.log10(np.maximum(x, 1e-10)), floor)


def r3(x):
    return [round(float(v), 3) for v in x]


# ---------------------------------------------------------------- core features


def low_band_onsets(y, sr):
    """Onset strength of the low band (< ~150 Hz): kicks and bass notes, which mark bar starts."""
    import librosa

    S = librosa.feature.melspectrogram(y=y, sr=sr, hop_length=HOP, n_mels=32, fmax=2000)
    low = S[:5]  # lowest mel bands (~0-150 Hz with fmax=2000)
    return librosa.onset.onset_strength(S=librosa.power_to_db(low), sr=sr, hop_length=HOP)


RELATED = (1.0, 2.0, 0.5, 0.75, 4 / 3, 1.5, 2 / 3)


def grid_score(env: np.ndarray, period_f: float, win_f: int) -> float:
    """How strongly onsets land on a beat grid of this period (frames) rather than halfway between its beats.

    Per window (so a slightly drifting tempo still fits), the best phase's mean onset strength on the beats minus
    the mean halfway between them, normalised by the window's mean; averaged over windows weighted by loudness.
    A tempo twice too fast puts its "between" points on real beats; one too slow or a 3:4 relative misses half of
    them: both score lower than the true tempo.
    """
    if period_f < 2 or len(env) < 2 * period_f:
        return 0.0
    n_ph = 16
    scores, weights = [], []
    for w0 in range(0, max(1, len(env) - win_f // 2), max(1, win_f // 2)):
        w = env[w0: w0 + win_f]
        if len(w) < 4 * period_f:
            continue
        m = float(w.mean())
        if m <= 1e-9:
            continue
        best = -np.inf
        for k in range(n_ph):
            ph = k * period_f / n_ph
            on = np.arange(ph, len(w) - 1, period_f)
            off = on + period_f / 2
            off = off[off < len(w) - 1]
            if len(on) < 3 or len(off) < 3:
                continue
            best = max(best, (w[np.round(on).astype(int)].mean() - w[np.round(off).astype(int)].mean()) / m)
        if np.isfinite(best):
            scores.append(best)
            weights.append(m)
    return float(np.average(scores, weights=weights)) if scores else 0.0


def tempo_candidates(env: np.ndarray, sr: int, bpm: float, lo: float = 55.0, hi: float = 200.0) -> list[dict]:
    fps = sr / HOP
    win_f = int(round(12 * fps))
    out = []
    for r in RELATED:
        b = bpm * r
        if lo <= b <= hi:
            out.append({"bpm": round(b, 2), "ratio": round(r, 3), "score": round(grid_score(env, 60.0 * fps / b, win_f), 4)})
    return sorted(out, key=lambda c: -c["score"])


def rhythm(y, sr, beats_per_bar: int, downbeat_offset: int, bass_y=None, drums_y=None, force_bpm: float | None = None):
    import librosa

    duration = len(y) / sr
    onset_env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=HOP, aggregate=np.median)
    kw = {"bpm": force_bpm, "tightness": 400} if force_bpm else {}
    tempo_est, beat_frames = librosa.beat.beat_track(onset_envelope=onset_env, sr=sr, hop_length=HOP, units="frames", **kw)
    tempo = float(np.atleast_1d(tempo_est)[0])
    # check the detection against its related tempi on the drum stem when there is one (the beat lives there)
    check_env = librosa.onset.onset_strength(y=drums_y, sr=sr, hop_length=HOP) if drums_y is not None else onset_env
    cands = tempo_candidates(check_env, sr, tempo) if tempo > 0 else []
    corrected_from, ambiguous = None, False
    if cands and not force_bpm:
        mine = next(c for c in cands if c["ratio"] == 1.0)
        best = cands[0]
        if best is not mine and best["score"] > 1.15 * max(mine["score"], 1e-6) and best["score"] > 0.05:
            corrected_from = round(tempo, 2)
            tempo_est, beat_frames = librosa.beat.beat_track(onset_envelope=onset_env, sr=sr, hop_length=HOP, units="frames",
                                                             bpm=best["bpm"], tightness=400)
            tempo = float(np.atleast_1d(tempo_est)[0])
        top = cands[0]["score"]
        ambiguous = len(cands) > 1 and cands[1]["score"] > 0.9 * top
    beat_times = librosa.frames_to_time(beat_frames, sr=sr, hop_length=HOP)

    ibi = np.diff(beat_times)
    stable, conf, period = False, 0.0, (60.0 / tempo if tempo > 0 else 0.5)
    if len(ibi) > 8:
        med = float(np.median(ibi))
        near = ibi[np.abs(ibi - med) < 0.1 * med]  # mean of the regular intervals: immune to hop quantisation
        period = float(near.mean()) if len(near) else med
        tempo = 60.0 / period
        dev = np.abs(ibi - period) / period
        stable = bool(np.percentile(dev, 90) < 0.12)
        regularity = float(np.clip(1.0 - np.mean(np.minimum(dev, 1.0)) * 4, 0.0, 1.0))
        lag = int(round(period * sr / HOP))
        clarity = 0.0
        if 1 < lag < len(onset_env) // 2:
            oe = onset_env - onset_env.mean()
            ac = np.correlate(oe, oe, mode="full")[len(oe) - 1:]
            ac = ac / (ac[0] + 1e-9)
            clarity = float(np.max(ac[max(1, lag - 2): lag + 3]))
        conf = float(np.clip(0.5 * regularity + clarity, 0.0, 1.0))

    # downbeats: the bar phase whose beats carry the most low-band attack and harmonic change
    phase = 0
    if len(beat_frames) >= beats_per_bar * 2:
        low = low_band_onsets(bass_y if bass_y is not None else y, sr)
        bf = np.minimum(beat_frames, len(low) - 1)
        win = 2
        low_at = np.array([low[max(0, f - win): f + win + 1].max() for f in bf])
        chroma = librosa.feature.chroma_cqt(y=bass_y if bass_y is not None else y, sr=sr, hop_length=HOP)
        bc = librosa.util.sync(chroma, beat_frames, aggregate=np.median, pad=False)
        change = np.r_[0.0, np.linalg.norm(np.diff(bc, axis=1), axis=0)]
        change = np.pad(change, (0, max(0, len(beat_frames) - len(change))))[: len(beat_frames)]
        z = lambda v: (v - v.mean()) / (v.std() + 1e-9)  # noqa: E731
        lz, cz = z(low_at), z(change)
        score = []
        for ph in range(beats_per_bar):
            idx = np.arange(ph, len(beat_frames), beats_per_bar)
            score.append(float(lz[idx].mean() + cz[idx].mean()))
        phase = (int(np.argmax(score)) + downbeat_offset) % beats_per_bar

    # a continuous grid over the whole song: detected beats, extended at the median period through
    # beat-less stretches (intros, breaks, outros) so every second of the song has a bar
    detected = list(beat_times)
    grid = []
    if detected:
        t = detected[0]
        back = []
        while t - period > -1e-6:
            t -= period
            back.append(t)
        grid = sorted(back) + detected
        t = detected[-1]
        while t + period < duration - 1e-6:
            t += period
            grid.append(t)
    grid = np.array(grid)
    first_det = int(np.searchsorted(grid, detected[0] - 1e-6)) if detected else 0
    down_idx = np.arange((first_det + phase) % beats_per_bar, len(grid), beats_per_bar)
    downbeats = grid[down_idx] if len(grid) else np.array([])
    det_lo, det_hi = (detected[0] - 1e-6, detected[-1] + 1e-6) if detected else (0, 0)
    bars = []
    for i, start in enumerate(downbeats):
        end = float(downbeats[i + 1]) if i + 1 < len(downbeats) else min(duration, float(start) + beats_per_bar * period)
        bars.append({"index": i + 1, "start": round(float(start), 3), "end": round(end, 3),
                     "extrapolated": bool(start < det_lo or start > det_hi)})
    return {
        "tempo": {"bpm": round(tempo, 2), "confidence": round(conf, 2), "stable": stable, "period": round(period, 4),
                  "candidates": cands, "ambiguous": bool(ambiguous), "corrected_from": corrected_from,
                  "forced": bool(force_bpm), "checked_on": "drums" if drums_y is not None else "mix"},
        "beats": r3(detected),
        "grid": r3(grid),
        "beat_frames": beat_frames,
        "downbeats": r3(downbeats),
        "downbeat_phase": phase,
        "beats_per_bar": beats_per_bar,
        "bars": bars,
        "onset_env": onset_env,
    }


def onsets_for(y, sr, max_n=4000):
    import librosa

    env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=HOP)
    frames = librosa.onset.onset_detect(onset_envelope=env, sr=sr, hop_length=HOP, backtrack=False, units="frames")
    if len(frames) == 0:
        return [], env
    strength = env[frames]
    strength = strength / (strength.max() + 1e-9)
    times = librosa.frames_to_time(frames, sr=sr, hop_length=HOP)
    order = np.argsort(-strength)[:max_n]
    keep = np.sort(order)
    return [{"t": round(float(times[i]), 3), "s": round(float(strength[i]), 3)} for i in keep], env


def energy_curve(y, sr, rate=10):
    import librosa

    hop = int(sr / rate)
    rms = librosa.feature.rms(y=y, frame_length=hop * 2, hop_length=hop)[0]
    e = db(rms)
    k = max(1, rate)  # 1 s smoothing
    smooth = np.convolve(e, np.ones(k) / k, mode="same")
    return e, smooth, rate


def checkerboard_novelty(feat, kernel_beats=16):
    """Foote novelty on a beat-synchronous self-similarity matrix."""
    X = feat / (np.linalg.norm(feat, axis=0, keepdims=True) + 1e-9)
    S = X.T @ X
    n = S.shape[0]
    L = max(2, min(kernel_beats // 2, n // 4))
    g = np.outer(np.hanning(2 * L), np.hanning(2 * L))
    sign = np.ones((2 * L, 2 * L))
    sign[:L, L:] = -1
    sign[L:, :L] = -1
    K = g * sign
    pad = np.pad(S, L, mode="edge")
    nov = np.zeros(n)
    for i in range(n):
        nov[i] = np.sum(pad[i:i + 2 * L, i:i + 2 * L] * K)
    nov = np.maximum(nov, 0)
    return nov / (nov.max() + 1e-9)


def sections(y, sr, rh, duration, min_bars=4):
    """Boundaries from novelty on a z-scored beat-grid feature matrix (timbre, harmony, loudness), snapped to
    downbeats; labels A, B, C… by similarity of each section's feature profile."""
    import librosa
    from scipy.signal import find_peaks

    grid = np.array(rh["grid"])
    if len(grid) < 16:
        return [{"start": 0.0, "end": round(duration, 3), "label": "A"}]
    gf = librosa.time_to_frames(grid, sr=sr, hop_length=HOP)
    mfcc = librosa.feature.mfcc(y=y, sr=sr, hop_length=HOP, n_mfcc=14)[1:]
    chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=HOP)
    lrms = np.log(librosa.feature.rms(y=y, hop_length=HOP) + 1e-6)
    F = np.vstack([librosa.util.sync(mfcc, gf, aggregate=np.mean),
                   librosa.util.sync(chroma, gf, aggregate=np.median),
                   librosa.util.sync(lrms, gf, aggregate=np.mean) * 3])
    # sync column k covers [grid[k-1], grid[k]) (column 0 is the stretch before the first grid point)
    starts = np.r_[0.0, grid]
    Z = (F - F.mean(axis=1, keepdims=True)) / (F.std(axis=1, keepdims=True) + 1e-9)
    bpb = rh["beats_per_bar"]
    nov = checkerboard_novelty(Z, kernel_beats=bpb * 8)
    period = rh["tempo"]["period"]
    min_gap = max(4, bpb * min_bars)
    peaks, _ = find_peaks(nov, distance=min_gap, height=0.15, prominence=0.08)
    downs = np.array(rh["downbeats"]) if rh["downbeats"] else grid
    bounds = [0.0]
    for pk in peaks:
        t = float(starts[min(pk, len(starts) - 1)])
        nb = float(downs[np.argmin(np.abs(downs - t))])
        if nb - bounds[-1] >= min_gap * period * 0.75 and duration - nb >= 2 * period:
            bounds.append(round(nb, 3))
    bounds.append(round(duration, 3))

    secs, vecs = [], []
    for i in range(len(bounds) - 1):
        s, e = bounds[i], bounds[i + 1]
        idx = np.where((starts >= s) & (starts < e))[0]
        v = Z[:, idx].mean(axis=1) if len(idx) else Z.mean(axis=1)
        secs.append({"start": s, "end": e})
        vecs.append(v / (np.linalg.norm(v) + 1e-9))
    labels, protos = [], []
    for v in vecs:
        sims = [float(v @ p) for p in protos]
        j = int(np.argmax(sims)) if sims else -1
        if j >= 0 and sims[j] > 0.75:
            labels.append(chr(65 + j))
        else:
            protos.append(v)
            labels.append(chr(65 + min(len(protos) - 1, 25)))
    for sec, lab in zip(secs, labels):
        sec["label"] = lab
    return secs


def describe_sections(secs, y, sr, onsets_full, vocal_y):
    ons = np.array([o["t"] for o in onsets_full]) if onsets_full else np.array([])
    voc_active = None
    if vocal_y is not None:
        e, _, rate = energy_curve(vocal_y, sr)
        thr = max(np.percentile(e, 60) - 12, -45)
        voc_active = (e > thr, rate)
    for s in secs:
        a, b = int(s["start"] * sr), int(s["end"] * sr)
        seg = y[a:b]
        s["energy_db"] = round(float(db(np.sqrt(np.mean(seg ** 2)) if len(seg) else 0)), 1)
        dur = max(s["end"] - s["start"], 1e-3)
        s["density"] = round(float(((ons >= s["start"]) & (ons < s["end"])).sum() / dur), 2) if len(ons) else 0.0
        if voc_active is not None:
            act, rate = voc_active
            sl = act[int(s["start"] * rate): int(s["end"] * rate)]
            s["vocal_presence"] = round(float(sl.mean()) if len(sl) else 0.0, 2)
        s["duration"] = round(dur, 3)
    return secs


def moments(energy, smooth, rate, secs, rh):
    out = []
    if len(smooth) == 0:
        return out
    loud_i = int(np.argmax(smooth))
    out.append({"t": round(loud_i / rate, 2), "kind": "loudest", "energy_db": round(float(smooth[loud_i]), 1)})
    # breaks: energy falls > 15 dB within 0.5 s to well below the song's typical level, after a loud stretch
    e = energy
    w = int(0.5 * rate)
    typical = float(np.median(e))
    for i in range(2 * w, len(e) - w):
        before = float(np.median(e[i - 2 * w: i - w // 2]))
        if before > typical - 6 and before - e[i] > 15 and e[i] < typical - 12 \
                and np.all(e[i:i + max(1, int(0.4 * rate))] < before - 12):
            if not out or abs(out[-1]["t"] - i / rate) > 2:
                out.append({"t": round(i / rate, 2), "kind": "break"})
    # drops: biggest energy rises at section starts
    for s in secs[1:]:
        i = int(s["start"] * rate)
        before = float(np.mean(smooth[max(0, i - 2 * rate): i])) if i > 0 else smooth[0]
        after = float(np.mean(smooth[i: i + 2 * rate])) if i < len(smooth) else smooth[-1]
        if after - before > 6:
            out.append({"t": s["start"], "kind": "lift", "delta_db": round(after - before, 1)})
        elif before - after > 6:
            out.append({"t": s["start"], "kind": "fall", "delta_db": round(before - after, 1)})
    return sorted(out, key=lambda m: m["t"])


def key_estimate(y, sr):
    import librosa

    chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=HOP).mean(axis=1)
    best = (None, -2.0)
    for i in range(12):
        for name, prof in (("major", MAJOR), ("minor", MINOR)):
            c = float(np.corrcoef(np.roll(prof, i), chroma)[0, 1])
            if c > best[1]:
                best = (f"{KEY_NAMES[i]} {name}", c)
    return {"name": best[0], "confidence": round(best[1], 2)}


def loudness(path):
    import pyloudnorm as pyln
    from scipy.signal import resample_poly

    y = decode_audio(path, sr=48000, mono=False)
    data = y.T.astype(np.float64)
    meter = pyln.Meter(48000)
    lufs = float(meter.integrated_loudness(data))
    tp = 0.0
    for ch in range(data.shape[1]):
        up = resample_poly(data[:, ch], 4, 1)
        tp = max(tp, float(np.max(np.abs(up))))
    return {"integrated_lufs": round(lufs, 2), "true_peak_db": round(float(db(tp)), 2),
            "sample_peak_db": round(float(db(np.max(np.abs(data)))), 2)}


# ---------------------------------------------------------------- plot


def plot(path_png, duration, energies, rh, secs, onsets, rate):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    names = [n for n in ("full",) + STEMS if n in energies]
    fig, axes = plt.subplots(len(names) + 1, 1, figsize=(18, 2.0 * (len(names) + 1)), sharex=True)
    colours = {"full": "#222222", "vocals": "#C2185B", "drums": "#1565C0", "bass": "#2E7D32", "other": "#EF6C00"}
    for ax, n in zip(axes, names):
        e = energies[n]
        t = np.arange(len(e)) / rate
        ax.fill_between(t, -80, e, color=colours[n], alpha=0.35, linewidth=0)
        ax.plot(t, e, color=colours[n], linewidth=0.8)
        ax.set_ylim(max(-70, np.percentile(e, 2) - 3), max(e.max() + 3, -10))
        ax.set_ylabel(n, rotation=0, ha="right", va="center")
        if n in onsets:
            ot = [o["t"] for o in onsets[n] if o["s"] > 0.35]
            ax.vlines(ot, ax.get_ylim()[0], ax.get_ylim()[0] + 3, color=colours[n], linewidth=0.5)
    ax = axes[-1]
    for i, b in enumerate(rh["beats"]):
        ax.axvline(b, color="#999999", linewidth=0.3)
    for d in rh["downbeats"]:
        ax.axvline(d, color="#333333", linewidth=0.8)
    ax.set_yticks([])
    ax.set_ylabel("beats\nbars", rotation=0, ha="right", va="center")
    for a in axes:
        for s in secs:
            a.axvline(s["start"], color="#D32F2F", linewidth=1.4, alpha=0.8)
    for s in secs:
        axes[0].text(s["start"] + 0.3, axes[0].get_ylim()[1] - 2, f"{s['label']} {fmt_time(s['start'])}", fontsize=9,
                     color="#D32F2F", va="top")
    ax.set_xlim(0, duration)
    ticks = np.arange(0, duration + 1, 10)
    ax.set_xticks(ticks)
    ax.set_xticklabels([fmt_time(t)[:-3] for t in ticks])
    fig.suptitle(f"{rh['tempo']['bpm']} BPM · {len(rh['downbeats'])} bars · sections in red", x=0.01, ha="left")
    fig.tight_layout()
    Path(path_png).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path_png, dpi=90)
    plt.close(fig)


# ---------------------------------------------------------------- main


def analyse(path: Path, stems_dir: Path | None, beats_per_bar: int, downbeat_offset: int, quick: bool,
            force_bpm: float | None = None):
    info(f"decoding {path.name} …")
    y = decode_audio(path, sr=SR)
    duration = len(y) / SR
    if duration < 2:
        raise Fail("audio is shorter than 2 seconds")
    stems = {}
    if stems_dir and stems_dir.exists():
        for n in STEMS:
            f = stems_dir / f"{n}.wav"
            if f.exists():
                stems[n] = decode_audio(f, sr=SR)
                stems[n] = stems[n][: len(y)] if len(stems[n]) >= len(y) else np.pad(stems[n], (0, len(y) - len(stems[n])))
    bass_y = (stems.get("drums", 0) + stems.get("bass", 0)) if ("drums" in stems or "bass" in stems) else None
    info("tempo and beats …")
    rh = rhythm(y, SR, beats_per_bar, downbeat_offset, bass_y, stems.get("drums"), force_bpm)
    info("energy …")
    energies, smooths = {}, {}
    e, sm, rate = energy_curve(y, SR)
    energies["full"], smooths["full"] = e, sm
    for n, sy in stems.items():
        energies[n], smooths[n], _ = energy_curve(sy, SR)
    info("onsets …")
    onsets = {}
    onsets["full"], _ = onsets_for(y, SR)
    if not quick:
        for n, sy in stems.items():
            onsets[n], _ = onsets_for(sy, SR)
    info("sections …")
    secs = sections(y, SR, rh, duration)
    secs = describe_sections(secs, y, SR, onsets["full"], stems.get("vocals"))
    result = {
        "schema": 1,
        "file": str(path),
        "duration": round(duration, 3),
        "sample_rate": SR,
        "tempo": rh["tempo"],
        "beats_per_bar": rh["beats_per_bar"],
        "downbeat_phase": rh["downbeat_phase"],
        "beats": rh["beats"],
        "grid": rh["grid"],
        "downbeats": rh["downbeats"],
        "bars": rh["bars"],
        "sections": secs,
        "moments": moments(e, sm, rate, secs, rh),
        "energy": {"rate_hz": rate, **{n: [round(float(v), 1) for v in arr] for n, arr in energies.items()},
                   "smooth": [round(float(v), 1) for v in smooths["full"]]},
        "onsets": onsets,
        "stems_used": sorted(stems),
    }
    if not quick:
        info("key and loudness …")
        result["key"] = key_estimate(y, SR)
        result["loudness"] = loudness(path)
    return result, energies, rate


def quick_summary(r) -> str:
    t = r["tempo"]
    lines = [f"Duration {fmt_time(r['duration'])} · {t['bpm']} BPM (confidence {t['confidence']}, "
             f"{'steady' if t['stable'] else 'variable'} tempo) · {len(r['bars'])} bars of {r['beats_per_bar']}"]
    if t.get("forced"):
        lines.append("  tempo forced with --bpm")
    if t.get("corrected_from"):
        lines.append(f"  ⚠️ tempo corrected from {t['corrected_from']} BPM: its beats missed the onsets that "
                     f"{t['bpm']} BPM hits (checked on the {t.get('checked_on', 'mix')})")
    if t.get("ambiguous"):
        alts = ", ".join(f"{c['bpm']} ({c['score']:.2f})" for c in (t.get("candidates") or [])[:3])
        lines.append(f"  ⚠️ tempo ambiguous: {alts}. Tap along or check the drum stem; force with --bpm")
    if r.get("key"):
        lines.append(f"Key (estimate): {r['key']['name']}")
    if r.get("loudness"):
        lo = r["loudness"]
        lines.append(f"Loudness: {lo['integrated_lufs']} LUFS integrated, true peak {lo['true_peak_db']} dBTP")
    lines.append("Sections (letters = similar material):")
    emax = max(s["energy_db"] for s in r["sections"])
    for s in r["sections"]:
        bar = "█" * max(1, int(round(12 + (s["energy_db"] - emax) / 2)))
        vp = f" · vocals {int(s['vocal_presence'] * 100)}%" if "vocal_presence" in s else ""
        lines.append(f"  {s['label']}  {fmt_time(s['start'])}–{fmt_time(s['end'])}  {s['energy_db']:>6} dB {bar:<12} "
                     f"{s['density']} onsets/s{vp}")
    for m in r["moments"]:
        extra = f" (+{m['delta_db']} dB)" if m["kind"] == "lift" else (f" (−{m['delta_db']} dB)" if m["kind"] == "fall" else "")
        lines.append(f"  moment: {m['kind']} at {fmt_time(m['t'])}{extra}")
    return "\n".join(lines)


def main(argv=None):
    p = argparse.ArgumentParser(prog="tempovision analyze", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--file", help="analyse this file instead of the project's song (prints JSON unless --out)")
    p.add_argument("--out", help="write JSON here")
    p.add_argument("--quick", action="store_true", help="fast summary for the interview")
    p.add_argument("--beats-per-bar", type=int, default=None)
    p.add_argument("--downbeat-offset", type=int, default=0)
    p.add_argument("--bpm", type=float, help="force the tempo (when the detection picked a related tempo)")
    p.add_argument("--no-plot", action="store_true")
    a = p.parse_args(argv)

    project = None if a.file else find_project()
    state = load_state(project) if project else {}
    path = Path(a.file).expanduser() if a.file else song_path(project, state)
    bpb = a.beats_per_bar or int(state.get("beats_per_bar", 4) or 4)
    stems_dir = (project / "analysis" / "stems") if project else None
    result, energies, rate = analyse(path, stems_dir, bpb, a.downbeat_offset, a.quick, a.bpm)

    if a.quick:
        print(quick_summary(result))
        if project:
            save_json(project / "analysis" / "quick.json", {k: v for k, v in result.items() if k not in ("energy", "onsets")})
        return
    out = Path(a.out) if a.out else ((project / "analysis" / "audio.json") if project else None)
    if out:
        save_json(out, result)
        info(f"wrote {out}")
        if not a.no_plot:
            png = (project / "analysis" / "plots" / "overview.png") if project else out.with_suffix(".png")
            plot(png, result["duration"], energies, result, result["sections"], result["onsets"], rate)
            info(f"wrote {png}")
        if project:
            state = load_state(project)
            state["beats_per_bar"] = bpb
            from _common import save_state
            save_state(project, state)
        print(quick_summary(result))
    else:
        print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
