#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy>=1.24"]
# ///
"""Swap in a new mix or master without losing sync: measure it against the song the film was timed to, and line it up.

  tempovision master compare NEW                 NEW vs the project's song: offset per window, verdict
  tempovision master compare NEW --against OLD   any two files
  tempovision master align NEW [--out FILE]      write NEW shifted onto the project's timeline (24-bit WAV), padded or
                                                 trimmed to the old length; then `tempovision deliver ... --master FILE`
  tempovision master locate CLIP                 where CLIP's audio starts inside the project's song (an excerpt render)

Why: a new mix is "the same song", but MP3 encoders add ~20-60 ms of silence at the start (encoder delay), and a
bounce can start a few ms off. Every word, cut and hit in the film was timed to the old file, so a few tens of ms
matter. The comparison uses onset envelopes (1 ms resolution), which match across different mixes of one song.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import Fail, decode_audio, find_project, info, load_state, media_summary, song_path  # noqa: E402

SR = 16000
HOP = 16  # 1 kHz envelope: 1 ms resolution
Z_MATCH = 8.0  # peak prominence that counts as "the same performance" (see prominence())


def envelope(y: np.ndarray) -> np.ndarray:
    """Onset envelope at 1 kHz: rectified rise of the 1 ms mean absolute slope. Mix-independent enough to match a
    remix or remaster of the same performance, sharp enough for 1 ms lags."""
    d = np.abs(np.diff(y, prepend=y[:1]))
    n = len(d) // HOP * HOP
    e = d[:n].reshape(-1, HOP).mean(axis=1)
    e = np.maximum(np.diff(e, prepend=e[:1]), 0.0)
    return (e - e.mean()).astype(np.float64)


def _xcorr(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    """Full cross-correlation of a against b (index k = lag of a's start in b, from -(len(a)-1))."""
    n = 1 << int(np.ceil(np.log2(len(a) + len(b))))
    return np.fft.irfft(np.fft.rfft(b, n) * np.conj(np.fft.rfft(a, n)), n)


def prominence(c: np.ndarray, keep: np.ndarray, k: int, guard: int = 25) -> float:
    """How far the best lag stands above the rest of the searched lags, in standard deviations (a clear match of the
    same performance scores well above 8 even across different mixes; unrelated audio stays near 4-5)."""
    v = c[keep]
    idx = np.flatnonzero(keep)
    pos = int(np.searchsorted(idx, k))
    rest = np.r_[v[: max(0, pos - guard)], v[pos + guard + 1:]]
    if len(rest) < 10:
        return 0.0
    return float((c[k] - rest.mean()) / (rest.std() + 1e-12))


def env_of(path: Path, start: float | None = None, duration: float | None = None) -> np.ndarray:
    return envelope(decode_audio(path, sr=SR, start=start, duration=duration))


def offset_between(new: Path, old: Path, windows: int = 3, win_s: float = 30.0, search_s: float = 1.0) -> dict:
    """How much later (+) or earlier (-) NEW plays the same material as OLD, measured in several windows."""
    dur = min(media_summary(new)["duration"], media_summary(old)["duration"])
    if dur < 4:
        raise Fail("the files are too short to compare")
    win_s = min(win_s, dur / 2)
    starts = np.linspace(0.1 * dur, 0.9 * dur - win_s, windows) if dur > 3 * win_s else [max(0.0, dur / 2 - win_s / 2)]
    res = []
    for s in starts:
        a = env_of(old, s, win_s)
        b = env_of(new, max(0.0, s - search_s), win_s + 2 * search_s)
        c = _xcorr(a, b)
        n = 1 << int(np.ceil(np.log2(len(a) + len(b))))
        lags = np.arange(n)
        lags[lags > n // 2] -= n
        keep = (lags >= 0) & (lags <= len(b) - len(a))
        k = int(np.argmax(np.where(keep, c, -np.inf)))
        lag = lags[k] / 1000.0 - (s - max(0.0, s - search_s))  # seconds NEW is late vs OLD
        seg = b[lags[k]: lags[k] + len(a)]
        corr = float(c[k] / (np.sqrt((a ** 2).sum() * (seg ** 2).sum()) + 1e-12))
        res.append({"at": round(float(s), 2), "offset_ms": round(lag * 1000, 1), "corr": round(corr, 3),
                    "z": round(prominence(c, keep, k), 1)})
    offs = np.array([r["offset_ms"] for r in res])
    good = [r for r in res if r["z"] >= Z_MATCH]
    med = float(np.median([r["offset_ms"] for r in good])) if good else float(np.median(offs))
    spread = float(offs.max() - offs.min())
    return {"new": str(new), "old": str(old), "offset_ms": round(med, 1), "spread_ms": round(spread, 1), "windows": res,
            "same_song": len(good) >= max(1, len(res) - 1), "drift": spread > 3.0,
            "new_duration": media_summary(new)["duration"], "old_duration": media_summary(old)["duration"]}


def locate(clip: Path, song: Path, max_s: float = 40.0) -> tuple[float, float]:
    """Where CLIP's audio starts inside SONG (seconds) and how clearly it matches (peak prominence, >= Z_MATCH)."""
    cd = media_summary(clip)["duration"]
    take = min(max_s, cd)
    mid = max(0.0, cd / 2 - take / 2)
    a = env_of(clip, mid, take)
    b = env_of(song)
    if len(a) < 500 or len(b) < len(a):
        return 0.0, 0.0
    c = _xcorr(a, b)
    n = 1 << int(np.ceil(np.log2(len(a) + len(b))))
    lags = np.arange(n)
    lags[lags > n // 2] -= n
    keep = (lags >= 0) & (lags <= len(b) - len(a))
    k = int(np.argmax(np.where(keep, c, -np.inf)))
    return lags[k] / 1000.0 - mid, prominence(c, keep, k)


def verdict(r: dict, fps: float = 30.0) -> str:
    if not r["same_song"]:
        return "these don't look like the same performance (low correlation): check the file"
    o = r["offset_ms"]
    if r["drift"]:
        return f"the offset changes along the song (spread {r['spread_ms']} ms): a different edit or tempo, not a simple shift"
    if abs(o) < 1.0:
        return "in sync (under 1 ms)"
    frame = 1000.0 / fps
    hint = " (typical MP3 encoder delay)" if -70 <= o <= -15 and str(r["old"]).lower().endswith(".mp3") else ""
    return (f"NEW plays {abs(o):.1f} ms {'later' if o > 0 else 'earlier'} than the film's timing{hint}; "
            f"that is {abs(o) / frame:.2f} frames: align it with `tempovision master align`")


def write_aligned(new: Path, offset_ms: float, length_s: float, out: Path):
    """Shift NEW by -offset (pad silence at the start if it plays early, trim if late), fix the length, 24-bit WAV."""
    out.parent.mkdir(parents=True, exist_ok=True)
    sr = int((media_summary(new).get("audio") or {}).get("sample_rate") or 48000)
    shift = -offset_ms / 1000.0
    af = []
    if shift > 0:
        af.append(f"adelay=delays={int(round(shift * sr))}S:all=1")
    elif shift < 0:
        af.append(f"atrim=start_sample={int(round(-shift * sr))},asetpts=PTS-STARTPTS")
    af.append(f"apad=whole_dur={length_s:.6f}")
    cmd = ["ffmpeg", "-v", "error", "-y", "-i", str(new), "-af", ",".join(af), "-t", f"{length_s:.6f}",
           "-c:a", "pcm_s24le", "-ar", str(sr), str(out)]
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0:
        raise Fail("ffmpeg failed: " + p.stderr[-400:])


def main(argv=None):
    ap = argparse.ArgumentParser(prog="tempovision master", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("compare")
    c.add_argument("new")
    c.add_argument("--against")
    c.add_argument("--json", action="store_true")
    al = sub.add_parser("align")
    al.add_argument("new")
    al.add_argument("--against")
    al.add_argument("--out")
    al.add_argument("--length", type=float, help="output length in seconds (default: the old file's)")
    lo = sub.add_parser("locate")
    lo.add_argument("clip")
    lo.add_argument("--against")
    a = ap.parse_args(argv)

    project = find_project(required=False)
    old = Path(a.against) if getattr(a, "against", None) else (song_path(project, load_state(project)) if project else None)
    if old is None:
        raise Fail("outside a project, pass --against OLD")
    if a.cmd == "locate":
        t, corr = locate(Path(a.clip), old)
        print(json.dumps({"clip": a.clip, "song": str(old), "starts_at": round(t, 3), "z": round(corr, 1), "match": corr >= Z_MATCH}))
        return
    new = Path(a.new)
    r = offset_between(new, old)
    if a.cmd == "compare":
        if a.json:
            print(json.dumps(r, indent=1))
        else:
            for w in r["windows"]:
                print(f"  at {w['at']:7.2f} s: {w['offset_ms']:+7.1f} ms (match {w['z']})")
            print(f"{new.name} vs {old.name}: {verdict(r)}")
        return
    if not r["same_song"] or r["drift"]:
        raise Fail(verdict(r))
    out = Path(a.out) if a.out else ((project / "audio" / f"{new.stem}.aligned.wav") if project else new.with_suffix(".aligned.wav"))
    length = a.length or r["old_duration"]
    write_aligned(new, r["offset_ms"], length, out)
    check = offset_between(out, old)
    info(f"aligned: {r['offset_ms']:+.1f} ms → {check['offset_ms']:+.1f} ms after the shift")
    if abs(check["offset_ms"]) > 2.0:
        raise Fail(f"the aligned file is still {check['offset_ms']:+.1f} ms off; check it by ear")
    print(out)


if __name__ == "__main__":
    main()
