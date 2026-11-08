#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Export measured timing (lyrics, beats, bars, sections, hits) into the render engine, snapped to frames.

  tempovision timing --engine hyperframes      video/assets/tempovision/*.json + video/compositions/lyrics.html (+ host snippet)
  tempovision timing --engine remotion         video/src/tempovision/timing.ts + tempovision.ts helpers
  tempovision timing ... --range 48.2-80.5     an excerpt: keeps what falls inside and shifts time to start at 0
  tempovision timing ... --video-dir DIR       engine project folder (default: video/)
  tempovision timing ... --no-composition      HyperFrames: data only, no lyrics.html scaffold

Always writes a cue manifest (cues.json) that `tempovision qa` checks against lyrics/timing.json, so stale exports are
caught after any re-alignment.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (PLUGIN_ROOT, Fail, find_project, info, load_json, load_state, now_iso, parse_range,  # noqa: E402
                     project_fps, save_json, snap, to_frame)


def timing_hash(timing: dict) -> str:
    core = [[(w["text"], w["start"], w["end"]) for w in l["words"]] for l in timing["lines"]]
    return hashlib.sha256(json.dumps(core).encode()).hexdigest()[:16]


def collect(project: Path, fps: float, rng: tuple[float, float] | None):
    timing = load_json(project / "lyrics" / "timing.json")
    audio = load_json(project / "analysis" / "audio.json")
    sm_path = project / "analysis" / "songmap.json"
    songmap = load_json(sm_path) if sm_path.exists() else {}
    t0, t1 = rng if rng else (0.0, audio["duration"])

    def inside(t):
        return t0 - 1e-6 <= t < t1

    def sh(t):
        return snap(t - t0, fps)

    lines = []
    for l in timing["lines"]:
        if not (inside(l["start"]) or inside(l["end"])):
            continue
        words = []
        for w in l["words"]:
            if not w.get("text"):
                continue
            words.append({"id": f"l{l['id']}w{len(words)}", "text": w["text"], "start": sh(max(w["start"], t0)),
                          "end": sh(min(w["end"], t1)), "adlib": w.get("adlib", False)})
        if not words:
            continue
        lines.append({"id": l["id"], "text": l["text"], "section": l.get("section"), "start": words[0]["start"],
                      "end": words[-1]["end"], "adlib": l.get("adlib", False), "words": words})
    beats = [sh(b) for b in audio.get("grid", audio["beats"]) if inside(b)]
    downbeats = [sh(b) for b in audio["downbeats"] if inside(b)]
    sections = []
    for s in songmap.get("sections", audio["sections"]):
        if s["end"] <= t0 or s["start"] >= t1:
            continue
        sections.append({"id": s.get("id", s["label"]), "name": s.get("display", s["label"]),
                         "start": sh(max(s["start"], t0)), "end": sh(min(s["end"], t1)), "energy_db": s.get("energy_db")})
    hits = [{**{k: v for k, v in h.items() if k not in ("t", "frame")}, "t": sh(h["t"])}
            for h in songmap.get("hits", []) if inside(h["t"])]
    meta = {"fps": fps, "duration": snap(t1 - t0, fps), "offset": t0, "bpm": audio["tempo"]["bpm"],
            "beats_per_bar": audio.get("beats_per_bar", 4), "frames_per_beat": round(fps * 60 / audio["tempo"]["bpm"], 4),
            "lyrics_method": timing.get("method"), "word_level": timing.get("word_level", True),
            "timing_hash": timing_hash(timing), "exported": now_iso()}
    return meta, lines, beats, downbeats, sections, hits


def cues(meta, lines):
    out = []
    for l in lines:
        out.append({"kind": "line", "id": f"l{l['id']}", "t": l["start"], "end": l["end"], "text": l["text"]})
        for w in l["words"]:
            out.append({"kind": "word", "id": w["id"], "t": w["start"], "end": w["end"], "text": w["text"]})
    return {"schema": 1, **meta, "cues": out, "overrides": []}


def hyperframes(project, vdir, meta, lines, beats, downbeats, sections, hits, composition: bool, w: int, h: int):
    data_dir = vdir / "assets" / "tempovision"
    data_dir.mkdir(parents=True, exist_ok=True)
    save_json(data_dir / "lyrics.json", {"meta": meta, "lines": lines})
    save_json(data_dir / "beats.json", {"meta": meta, "beats": beats, "downbeats": downbeats})
    save_json(data_dir / "sections.json", {"meta": meta, "sections": sections, "hits": hits})
    save_json(data_dir / "cues.json", cues(meta, lines))
    written = [data_dir / n for n in ("lyrics.json", "beats.json", "sections.json", "cues.json")]
    if composition:
        comp_dir = vdir / "compositions"
        comp_dir.mkdir(parents=True, exist_ok=True)
        dest = comp_dir / "lyrics.html"
        if dest.exists():
            dest = comp_dir / "lyrics.generated.html"
            info(f"compositions/lyrics.html exists (your styled version is kept); wrote {dest.name} to diff against")
        frame = 1 / meta["fps"]
        els, tl = [], []
        for l in lines:
            dur = round(max(frame, l["end"] - l["start"] + 0.35), 4)
            spans = " ".join(
                f'<span id="{wd["id"]}" class="w{" adlib" if wd["adlib"] else ""}" data-word-start="{wd["start"]}" data-word-end="{wd["end"]}">'
                f'{html.escape(wd["text"])}</span>' for wd in l["words"])
            els.append(f'    <p id="l{l["id"]}" class="clip line" data-start="{l["start"]}" data-duration="{dur}" '
                       f'data-track-index="1" data-section="{html.escape(str(l.get("section") or ""))}">{spans}</p>')
            for wd in l["words"]:
                tl.append(f'    tl.set("#{wd["id"]}", {{ opacity: 1 }}, {wd["start"]});')
        doc = f"""<template>
  <!-- Generated by `tempovision timing` from lyrics/timing.json ({meta['lyrics_method']}, hash {meta['timing_hash']}).
       A functional scaffold: every line and word is timed from the alignment. Restyle it to SPEC.md and replace
       the reveal below with the film's lyric treatment, but keep the ids, data-start and data-duration values
       (re-export after any re-alignment and diff against lyrics.generated.html). -->
  <style>
    #root {{ position: absolute; inset: 0; }}
    #root .line {{ position: absolute; left: 0; right: 0; bottom: 12%; margin: 0; text-align: center;
                   font-family: Inter, sans-serif; font-weight: 700; font-size: {int(h * 0.06)}px; color: #fff; }}
    #root .w {{ opacity: 0.25; }}
    #root .w.adlib {{ font-size: 0.6em; }}
  </style>
  <div id="root" data-composition-id="lyrics" data-width="{w}" data-height="{h}">
{chr(10).join(els)}
  </div>
  <script>
    const tl = gsap.timeline({{ paused: true }});
{chr(10).join(tl)}
    window.__timelines["lyrics"] = tl;
  </script>
</template>
"""
        dest.write_text(doc, encoding="utf-8")
        written.append(dest)
        host = (f'<div id="lyrics" data-composition-id="lyrics" data-composition-src="compositions/lyrics.html" '
                f'data-start="0" data-duration="{meta["duration"]}" data-track-index="9" data-track-kind="captions" '
                f'data-width="{w}" data-height="{h}"></div>')
        (data_dir / "lyrics-host.html").write_text(host + "\n", encoding="utf-8")
        written.append(data_dir / "lyrics-host.html")
    return written


def ts_literal(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, indent=2)


def remotion(project, vdir, meta, lines, beats, downbeats, sections, hits):
    out_dir = vdir / "src" / "tempovision"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = [
        "// Generated by `tempovision timing` from lyrics/timing.json and analysis/. Do not edit by hand: re-export.",
        f"// lyrics method: {meta['lyrics_method']} · timing hash {meta['timing_hash']} · exported {meta['exported']}",
        "",
        "export type Word = { id: string; text: string; start: number; end: number; adlib: boolean };",
        "export type Line = { id: number; text: string; section: string | null; start: number; end: number; adlib: boolean; words: Word[] };",
        "export type Section = { id: string; name: string; start: number; end: number; energy_db: number | null };",
        "export type Hit = { t: number; kind: string; label?: string; strength: number; also?: string };",
        "",
        f"export const FPS = {meta['fps']};",
        f"export const DURATION_S = {meta['duration']};",
        f"export const DURATION_FRAMES = {to_frame(meta['duration'], meta['fps'])};",
        f"export const BPM = {meta['bpm']};",
        f"export const BEATS_PER_BAR = {meta['beats_per_bar']};",
        f"export const FRAMES_PER_BEAT = {meta['frames_per_beat']};",
        f"export const WORD_LEVEL = {str(bool(meta['word_level'])).lower()};",
        f"export const LYRICS: Line[] = {ts_literal(lines)};",
        f"export const BEATS: number[] = {json.dumps(beats)};",
        f"export const DOWNBEATS: number[] = {json.dumps(downbeats)};",
        f"export const SECTIONS: Section[] = {ts_literal(sections)};",
        f"export const HITS: Hit[] = {ts_literal(hits)};",
        "",
    ]
    (out_dir / "timing.ts").write_text("\n".join(ts), encoding="utf-8")
    helpers = PLUGIN_ROOT / "templates" / "engines" / "remotion" / "tempovision.ts"
    shutil.copy2(helpers, out_dir / "tempovision.ts")
    save_json(out_dir / "cues.json", cues(meta, lines))
    return [out_dir / "timing.ts", out_dir / "tempovision.ts", out_dir / "cues.json"]


def main(argv=None):
    ap = argparse.ArgumentParser(prog="tempovision timing", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--engine", choices=["hyperframes", "remotion"])
    ap.add_argument("--range")
    ap.add_argument("--video-dir")
    ap.add_argument("--no-composition", action="store_true")
    ap.add_argument("--size", default=None, help="W x H, e.g. 1920x1080 (default from the project aspect)")
    a = ap.parse_args(argv)
    project = find_project()
    state = load_state(project)
    engine = a.engine or state.get("engine") or "hyperframes"
    fps = project_fps(project, state)
    for need in ("lyrics/timing.json", "analysis/audio.json"):
        if not (project / need).exists():
            raise Fail(f"missing {need}: run `tempovision analyze` and `tempovision align` first")
    rng = parse_range(a.range) if a.range else None
    meta, lines, beats, downbeats, sections, hits = collect(project, fps, rng)
    vdir = Path(a.video_dir) if a.video_dir else project / "video"
    if a.size:
        w, h = (int(x) for x in a.size.lower().split("x"))
    else:
        w, h = (1080, 1920) if str(state.get("aspect")) == "9:16" else ((1080, 1080) if str(state.get("aspect")) == "1:1" else (1920, 1080))
    if engine == "hyperframes":
        written = hyperframes(project, vdir, meta, lines, beats, downbeats, sections, hits, not a.no_composition, w, h)
    else:
        written = remotion(project, vdir, meta, lines, beats, downbeats, sections, hits)
    if not meta["word_level"]:
        info("note: lyric timing is line-level only (heuristic or line import); animate lines, not words.")
    for p in written:
        print(p.relative_to(project) if p.is_relative_to(project) else p)
    print(f"{len(lines)} lines · {sum(len(l['words']) for l in lines)} words · {len(beats)} beats · {len(sections)} sections · "
          f"{len(hits)} hits · {meta['fps']:g} fps · {meta['duration']} s")


if __name__ == "__main__":
    main()
