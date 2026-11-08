#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy>=1.24", "scipy>=1.10", "pyloudnorm>=0.1.1", "pillow>=10"]
# ///
"""Measured QA on a render. Each check is PASS / WARN / FAIL with its numbers; exit code 1 on any FAIL.

  tempovision qa RENDER                         inside a project (master = input/song.*)
  tempovision qa RENDER --master SONG           outside a project
  tempovision qa RENDER --range 48.2-80.5       the render is an excerpt of the song starting at 48.2 s
  tempovision qa RENDER --size 1080x1920 --fps 30

Checks: format, audio_present, av_offset, loudness, black, freeze, first_frame, cuts_vs_beats, lyric_cues.
Writes qa/<render>.json and qa/<render>.md in a project (or next to the render).
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (Fail, decode_audio, detect_cuts, extract_frame, find_project, fmt_time, info, load_json,  # noqa: E402
                     load_state, media_summary, now_iso, parse_range, save_json, song_path, table)

ORDER = {"PASS": 0, "INFO": 0, "WARN": 1, "FAIL": 2}


def check(name, status, summary, **data):
    return {"check": name, "status": status, "summary": summary, **data}


def lufs(y: np.ndarray, sr: int) -> float:
    import pyloudnorm as pyln

    return float(pyln.Meter(sr).integrated_loudness(y.astype(np.float64)))


def av_offset(render: Path, master: Path, start: float, dur: float) -> tuple[float, float]:
    """Lag (s) of the render's audio relative to the master, by cross-correlation over up to 60 s. + = render late."""
    from scipy.signal import correlate

    sr = 8000
    seg = min(60.0, dur)
    mid = max(0.0, dur / 2 - seg / 2)
    r = decode_audio(render, sr=sr, start=mid, duration=seg)
    m = decode_audio(master, sr=sr, start=start + mid, duration=seg)
    n = min(len(r), len(m))
    if n < sr:
        return 0.0, 0.0
    r, m = r[:n] - r[:n].mean(), m[:n] - m[:n].mean()
    c = correlate(r, m, mode="full", method="fft")
    lags = np.arange(-n + 1, n)
    win = np.abs(lags) <= sr  # search ±1 s
    c, lags = c[win], lags[win]
    k = int(np.argmax(np.abs(c)))
    norm = float(np.abs(c[k]) / (np.sqrt((r ** 2).sum() * (m ** 2).sum()) + 1e-12))
    return lags[k] / sr, norm


def ffmpeg_detect(render: Path, vf: str) -> str:
    proc = subprocess.run(["ffmpeg", "-hide_banner", "-nostdin", "-i", str(render), "-an", "-vf", vf, "-f", "null", "-"],
                          capture_output=True, text=True)
    return proc.stderr


def intervals(text: str, key: str):
    starts = [float(x) for x in re.findall(rf"{key}_start:\s*([\d.]+)", text)]
    ends = [float(x) for x in re.findall(rf"{key}_end:\s*([\d.]+)", text)]
    out = []
    for i, s in enumerate(starts):
        e = ends[i] if i < len(ends) else None
        out.append((s, e))
    return out


def frame_stats(render: Path, t: float, width: int = 160):
    from PIL import Image

    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "f.png"
        if not extract_frame(render, t, p, width):
            return None
        a = np.asarray(Image.open(p).convert("L"), dtype=np.float32)
    return a


def local_change(a: np.ndarray, b: np.ndarray, blocks: int = 8) -> float:
    """Largest mean absolute difference over a blocks x blocks grid: sensitive to a word appearing anywhere."""
    d = np.abs(a - b)
    h, w = d.shape
    best = 0.0
    for i in range(blocks):
        for j in range(blocks):
            tile = d[i * h // blocks:(i + 1) * h // blocks, j * w // blocks:(j + 1) * w // blocks]
            if tile.size:
                best = max(best, float(tile.mean()))
    return best


def find_cues(project: Path) -> Path | None:
    for rel in ("video/assets/tempovision/cues.json", "video/src/tempovision/cues.json", "video/public/tempovision/cues.json"):
        if (project / rel).exists():
            return project / rel
    return None


def main(argv=None):
    ap = argparse.ArgumentParser(prog="tempovision qa", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("render")
    ap.add_argument("--master")
    ap.add_argument("--range")
    ap.add_argument("--size")
    ap.add_argument("--fps", type=float)
    ap.add_argument("--json", action="store_true", help="print the JSON report")
    a = ap.parse_args(argv)

    render = Path(a.render).expanduser()
    if not render.exists():
        raise Fail(f"no such file: {render}")
    project = find_project(required=False)
    state = load_state(project) if project else {}
    master = Path(a.master).expanduser() if a.master else (song_path(project, state) if project else None)
    if master is None:
        raise Fail("outside a project, pass --master SONG")
    start, end = (parse_range(a.range) if a.range else (0.0, None))
    mmeta = media_summary(master)
    song_dur = mmeta["duration"]
    expect_dur = (end if end else song_dur) - start
    fps_expect = a.fps or float(state.get("fps", 0) or 0) or None
    if a.size:
        size_expect = tuple(int(x) for x in a.size.lower().split("x"))
    elif state.get("aspect"):
        size_expect = {"16:9": (1920, 1080), "9:16": (1080, 1920), "1:1": (1080, 1080), "4:5": (1080, 1350)}.get(str(state["aspect"]))
    else:
        size_expect = None

    meta = media_summary(render)
    results = []
    v = meta.get("video")
    if not v:
        raise Fail("the render has no video stream")
    fps = v["fps"] or 30.0
    frame = 1 / fps

    # format
    problems = []
    if size_expect and (v["width"], v["height"]) != size_expect:
        if (v["width"] * size_expect[1]) == (v["height"] * size_expect[0]):
            problems.append(f"size {v['width']}x{v['height']} (same aspect as {size_expect[0]}x{size_expect[1]}: a draft?)")
        else:
            problems.append(f"size {v['width']}x{v['height']}, expected {size_expect[0]}x{size_expect[1]}")
    if fps_expect and abs(fps - fps_expect) > 0.01:
        problems.append(f"{fps:g} fps, expected {fps_expect:g}")
    ddiff = v["duration"] - expect_dur
    if abs(ddiff) > frame * 1.01:
        problems.append(f"duration {v['duration']:.3f} s vs song {expect_dur:.3f} s ({ddiff:+.3f} s)")
    status = "PASS" if not problems else ("WARN" if all("draft" in p for p in problems) else "FAIL")
    results.append(check("format", status, "; ".join(problems) or f"{v['width']}x{v['height']} · {fps:g} fps · {v['duration']:.3f} s",
                         width=v["width"], height=v["height"], fps=fps, duration=v["duration"], expected_duration=expect_dur))

    # audio
    au = meta.get("audio")
    if not au:
        results.append(check("audio_present", "FAIL", "no audio stream"))
    else:
        y = decode_audio(render, sr=16000)
        rms_db = 20 * np.log10(np.sqrt(np.mean(y ** 2)) + 1e-10)
        results.append(check("audio_present", "PASS" if rms_db > -60 else "FAIL", f"{au['codec']} {au['sample_rate']} Hz, RMS {rms_db:.1f} dB",
                             rms_db=round(float(rms_db), 1)))
        lag, corr = av_offset(render, master, start, min(v["duration"], expect_dur))
        frames_off = lag / frame
        st = "PASS" if abs(frames_off) <= 1.0 and corr > 0.3 else ("WARN" if corr <= 0.3 else "FAIL")
        summ = f"render audio {'late' if lag > 0 else 'early'} by {abs(lag) * 1000:.0f} ms ({frames_off:+.2f} frames), correlation {corr:.2f}"
        if corr <= 0.3:
            summ += " (low correlation: is the render's audio the master?)"
        results.append(check("av_offset", st, summ, seconds=round(lag, 4), frames=round(frames_off, 2), correlation=round(corr, 3)))
        sr = 48000
        rr = decode_audio(render, sr=sr, mono=False).T
        mm = decode_audio(master, sr=sr, mono=False, start=start or None, duration=expect_dur if end else None).T
        lr, lm = lufs(rr, sr), lufs(mm, sr)
        d = lr - lm
        results.append(check("loudness", "PASS" if abs(d) <= 0.5 else "FAIL",
                             f"render {lr:.2f} LUFS vs master {lm:.2f} LUFS ({d:+.2f} LU)" + ("" if abs(d) <= 0.5 else ": the audio was altered"),
                             render_lufs=round(lr, 2), master_lufs=round(lm, 2)))

    # black and freeze
    # a frame counts as black only when ≥ 99.8% of it is black: a lyric on a dark ground is not a black frame
    bl = intervals(ffmpeg_detect(render, "blackdetect=d=0.03:pix_th=0.06:pic_th=0.998"), "black")
    bad = [(s_, e) for s_, e in bl if (e or v["duration"]) - s_ > 2 * frame]
    severe = [(s_, e) for s_, e in bad if (e or v["duration"]) - s_ >= 3.0 or s_ < frame]
    desc = ", ".join(f"{fmt_time(s_)}–{fmt_time(e or v['duration'])}" for s_, e in bad[:12])
    if severe:
        status, summ = "FAIL", "black ≥ 3 s or on the first frame: " + ", ".join(
            f"{fmt_time(s_)}–{fmt_time(e or v['duration'])}" for s_, e in severe) + (f" (+{len(bad) - len(severe)} shorter)" if len(bad) > len(severe) else "")
    elif bad:
        status, summ = "WARN", f"short black stretches (deliberate? say so in REVIEW.md): {desc}"
    else:
        status, summ = "PASS", "no black stretches"
    results.append(check("black", status, summ, intervals=[[s_, e] for s_, e in bad]))
    fr = intervals(ffmpeg_detect(render, "freezedetect=n=0.001:d=1"), "lavfi.freezedetect.freeze")
    spans = [((e if e is not None else v["duration"]) - st_, st_, e) for st_, e in fr]
    long_ = sorted([x for x in spans if x[0] >= 3.0], reverse=True)
    total = sum(x[0] for x in spans)
    if long_:
        summ = (f"{len(long_)} stretch(es) with nothing changing for ≥ 3 s: " +
                ", ".join(f"{fmt_time(st_)}–{fmt_time(e if e is not None else v['duration'])} ({d:.1f} s)" for d, st_, e in long_[:6]) +
                " (fine only if deliberate holds)")
        status = "WARN"
    else:
        summ = f"no stretch ≥ 3 s without change ({len(spans)} holds of 1-3 s, {total:.0f} s in all)"
        status = "PASS"
    results.append(check("freeze", status, summ, intervals=[[st_, e] for _, st_, e in spans]))

    # first frame
    f0 = frame_stats(render, 0.0)
    if f0 is None:
        results.append(check("first_frame", "WARN", "could not read frame 0"))
    else:
        mean, std = float(f0.mean()), float(f0.std())
        empty = mean < 10 and std < 4
        flat = std < 2
        results.append(check("first_frame", "FAIL" if empty else ("WARN" if flat else "PASS"),
                             f"mean luma {mean:.0f}, detail {std:.1f}" + (": empty or black (it is the thumbnail)" if empty else
                                                                            (": a flat colour (it is the thumbnail)" if flat else "")),
                             mean=round(mean, 1), std=round(std, 1)))

    # cuts vs beats and words
    cuts = detect_cuts(render)
    audio_json = load_json(project / "analysis" / "audio.json") if project and (project / "analysis" / "audio.json").exists() else None
    timing = load_json(project / "lyrics" / "timing.json") if project and (project / "lyrics" / "timing.json").exists() else None
    if audio_json and cuts:
        grid = np.array([b - start for b in audio_json.get("grid", audio_json["beats"])])
        downs = np.array([b - start for b in audio_json["downbeats"]])
        on_beat = sum(1 for c in cuts if len(grid) and np.min(np.abs(grid - c["t"])) <= frame * 1.01)
        on_bar = sum(1 for c in cuts if len(downs) and np.min(np.abs(downs - c["t"])) <= frame * 1.01)
        mid_word = []
        if timing:
            for c in cuts:
                for l in timing["lines"]:
                    for w in l["words"]:
                        ws, we = w["start"] - start, w["end"] - start
                        if ws + 0.06 < c["t"] < we - 0.06:
                            mid_word.append({"t": c["t"], "word": w.get("text") or w.get("norm"), "line": l["id"]})
        n = len(cuts)
        results.append(check("cuts_vs_beats", "INFO",
                             f"{n} cuts · {on_beat / n:.0%} within ±1 frame of a beat · {on_bar / n:.0%} on a downbeat · "
                             f"{len(mid_word)} inside a sung word", cuts=cuts, mid_word=mid_word,
                             on_beat=on_beat, on_downbeat=on_bar))
    else:
        results.append(check("cuts_vs_beats", "INFO", f"{len(cuts)} cuts" + ("" if audio_json else " (no analysis to compare)"), cuts=cuts))

    # lyric cues
    cues_path = find_cues(project) if project else None
    if timing and cues_path:
        cues = load_json(cues_path)
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        from timing import timing_hash  # noqa: E402

        stale = cues.get("timing_hash") != timing_hash(timing)
        overrides = {o.get("id"): o for o in cues.get("overrides", [])}
        off = cues.get("offset", 0.0)
        cue_lines = {c["id"]: c for c in cues["cues"] if c["kind"] == "line"}
        mismatch = []
        for l in timing["lines"]:
            c = cue_lines.get(f"l{l['id']}")
            if not c or f"l{l['id']}" in overrides:
                continue
            d = c["t"] - (l["start"] - off)
            if d < -2 * frame - 1e-6 or d > frame + 1e-6:
                mismatch.append({"line": l["id"], "delta_s": round(d, 3)})
        # visual change where each line starts being sung
        silent = []
        for c in list(cue_lines.values())[:120]:
            t = c["t"]
            if t - 4 * frame < 0 or t + 2 * frame > v["duration"]:
                continue
            fa, fb = frame_stats(render, t - 4 * frame), frame_stats(render, t + 3 * frame)
            if fa is not None and fb is not None and fa.shape == fb.shape and local_change(fa, fb) < 1.5:
                silent.append({"line": c["id"], "t": round(t, 3), "text": c.get("text", "")[:40]})
        st = "FAIL" if (stale or mismatch) else ("WARN" if silent else "PASS")
        parts = []
        if stale:
            parts.append("cue export is stale: lyrics/timing.json changed since `tempovision timing` ran; re-export and rebuild")
        if mismatch:
            parts.append(f"{len(mismatch)} line cues differ from the alignment")
        if silent:
            parts.append(f"{len(silent)} line starts with no visible change on screen (−4/+3 frames)")
        results.append(check("lyric_cues", st, "; ".join(parts) or f"{len(cue_lines)} line cues match the alignment and each shows a change",
                             stale=stale, mismatch=mismatch, no_visual_change=silent, manifest=str(cues_path)))
    else:
        results.append(check("lyric_cues", "INFO", "no cue manifest (run `tempovision timing`) or no lyric timing; skipped"))

    worst = max((r["status"] for r in results), key=lambda s: ORDER[s])
    report = {"schema": 1, "render": str(render), "master": str(master), "at": now_iso(), "status": worst, "checks": results}
    qa_dir = (project / "qa") if project else render.parent
    stem = render.stem
    save_json(qa_dir / f"{stem}.json", report)
    md = [f"# QA: {render.name}", "", f"{now_iso()} · overall **{worst}**", "",
          table([[r["check"], {"PASS": "✅ PASS", "WARN": "⚠️ WARN", "FAIL": "❌ FAIL", "INFO": "ℹ️ INFO"}[r["status"]], r["summary"]]
                 for r in results], ["Check", "Status", "Result"]), ""]
    for r in results:
        if r.get("mid_word"):
            md.append("Cuts inside sung words: " + ", ".join(f"{fmt_time(m['t'])} ({m['word']})" for m in r["mid_word"][:20]))
        if r.get("no_visual_change"):
            md.append("Line starts with no visible change: " + ", ".join(f"{m['line']} at {fmt_time(m['t'])}" for m in r["no_visual_change"][:20]))
        if r.get("mismatch"):
            md.append("Cue mismatches: " + ", ".join(f"line {m['line']} {m['delta_s']:+.3f} s" for m in r["mismatch"][:20]))
    (qa_dir / f"{stem}.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    if a.json:
        print(json.dumps(report, indent=2))
    else:
        print("\n".join(md))
        print(f"report: {qa_dir / (stem + '.md')}")
    sys.exit(1 if worst == "FAIL" else 0)


if __name__ == "__main__":
    main()
