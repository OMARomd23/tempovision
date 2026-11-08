#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Join the audio analysis and the lyric timing into the song map the film is built on.

  tempovision songmap            -> SONGMAP.md and analysis/songmap.json

Names sections from the lyric tags (or from repetition when there are none), lists each section's bars, energy,
density, vocal presence and lyric lines with frame numbers, the hook lines, the hit list, and the instrumental
gaps where the picture has to carry the film alone.
"""
from __future__ import annotations

import argparse
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (Fail, find_project, fmt_time, info, load_json, load_state, project_fps, save_json,  # noqa: E402
                     table, to_frame)


def norm(s: str) -> str:
    return re.sub(r"[^\w\s]", "", s.lower()).strip()


def name_sections(secs, lines, duration):
    """Give each analysed section a name from the lyric tags of the lines it contains."""
    by_letter_text = {}
    for s in secs:
        inside = [l for l in lines if s["start"] - 0.3 <= l["start"] < s["end"] - 0.3]
        s["line_ids"] = [l["id"] for l in inside]
        tags = [l.get("section") for l in inside if l.get("section")]
        s["tag"] = Counter(tags).most_common(1)[0][0] if tags else None
        by_letter_text.setdefault(s["label"], []).extend(norm(l["text"]) for l in inside)
    # without tags: the letter whose lines repeat most is the chorus
    repeat_score = {k: (sum(c - 1 for c in Counter(v).values() if c > 1) / max(1, len(v))) for k, v in by_letter_text.items()}
    chorus_letter = max(repeat_score, key=repeat_score.get) if repeat_score and max(repeat_score.values()) > 0 else None
    counts: Counter = Counter()
    first_vocal = next((i for i, s in enumerate(secs) if s["line_ids"]), None)
    last_vocal = max((i for i, s in enumerate(secs) if s["line_ids"]), default=None)
    for i, s in enumerate(secs):
        if s["tag"]:
            base = re.sub(r"\s*\d+$", "", s["tag"]).strip()
        elif not s["line_ids"]:
            if first_vocal is not None and i < first_vocal:
                base = "Intro"
            elif last_vocal is not None and i > last_vocal:
                base = "Outro"
            else:
                base = "Instrumental"
        elif s["label"] == chorus_letter:
            base = "Chorus"
        else:
            base = "Verse"
        counts[base] += 1
        s["name"] = base
        s["n"] = counts[base]
    for s in secs:
        s["display"] = f"{s['name']} {s['n']}" if counts[s["name"]] > 1 else s["name"]
        s["id"] = re.sub(r"[^a-z0-9]+", "-", s["display"].lower()).strip("-")
    return secs


def hit_list(audio, secs, lines, hooks, fps):
    hits = []
    for s in secs:
        hits.append({"t": s["start"], "kind": "section", "label": s["display"], "strength": 1.0})
    downs = audio.get("downbeats", [])
    for s in secs:
        if s["name"].lower().startswith("chorus") or s["name"].lower() in ("hook", "drop"):
            for d in downs:
                if s["start"] < d < s["end"] - 0.05:
                    hits.append({"t": d, "kind": "chorus-downbeat", "label": s["display"], "strength": 0.8})
    # strong drum onsets in the loudest sections, at most one per beat
    drums = audio.get("onsets", {}).get("drums") or audio.get("onsets", {}).get("full", [])
    if drums and secs:
        loud = sorted(secs, key=lambda s: s.get("energy_db", -99), reverse=True)[: max(1, len(secs) // 3)]
        thr = sorted((o["s"] for o in drums), reverse=True)[max(0, int(len(drums) * 0.15) - 1)]
        period = audio["tempo"].get("period") or 0.5
        last = -9.0
        for o in drums:
            if o["s"] >= thr and any(s["start"] <= o["t"] < s["end"] for s in loud) and o["t"] - last > period * 0.9:
                hits.append({"t": o["t"], "kind": "drum-hit", "strength": round(o["s"], 2)})
                last = o["t"]
    hook_texts = {h["norm"] for h in hooks}
    for l in lines:
        if norm(l["text"]) in hook_texts:
            hits.append({"t": l["start"], "kind": "hook-line", "label": l["text"][:40], "strength": 0.7})
    for m in audio.get("moments", []):
        if m["kind"] in ("break", "lift", "fall"):
            hits.append({"t": m["t"], "kind": m["kind"], "strength": 0.9})
    hits.sort(key=lambda h: (h["t"], -h["strength"]))
    dedup = []
    for h in hits:
        if dedup and abs(h["t"] - dedup[-1]["t"]) < 0.06:
            if h["strength"] > dedup[-1]["strength"]:
                dedup[-1] = {**h, "also": dedup[-1]["kind"]}
            continue
        dedup.append(h)
    for h in dedup:
        h["t"] = round(h["t"], 3)
        h["frame"] = to_frame(h["t"], fps)
    return dedup


def gaps(lines, audio, duration):
    period = audio["tempo"].get("period") or 0.5
    bar = period * audio.get("beats_per_bar", 4)
    out = []
    cursor = 0.0
    for l in lines + [{"start": duration, "end": duration, "id": None}]:
        if l["start"] - cursor >= 2 * bar:
            out.append({"start": round(cursor, 3), "end": round(l["start"], 3), "bars": round((l["start"] - cursor) / bar, 1)})
        cursor = max(cursor, l.get("end", l["start"]))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(prog="tempovision songmap", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.parse_args(argv)
    project = find_project()
    state = load_state(project)
    fps = project_fps(project, state)
    ap_ = project / "analysis" / "audio.json"
    if not ap_.exists():
        raise Fail("run `tempovision analyze` first")
    audio = load_json(ap_)
    tp = project / "lyrics" / "timing.json"
    timing = load_json(tp) if tp.exists() else {"lines": [], "method": None}
    lines = timing["lines"]
    duration = audio["duration"]
    secs = [dict(s) for s in audio["sections"]]
    secs = name_sections(secs, lines, duration)

    counts = Counter(norm(l["text"]) for l in lines)
    hooks = []
    seen = set()
    for l in lines:
        k = norm(l["text"])
        if counts[k] > 1 and k not in seen:
            seen.add(k)
            hooks.append({"text": l["text"], "norm": k, "times": [fmt_time(x["start"]) for x in lines if norm(x["text"]) == k], "count": counts[k]})
    hooks.sort(key=lambda h: -h["count"])
    hits = hit_list(audio, secs, lines, hooks, fps)
    gp = gaps(lines, audio, duration)
    bars = audio.get("bars", [])

    for s in secs:
        s["frames"] = [to_frame(s["start"], fps), to_frame(s["end"], fps)]
        bi = [b["index"] for b in bars if s["start"] - 0.05 <= b["start"] < s["end"] - 0.05]
        s["bars"] = [bi[0], bi[-1]] if bi else None
        s["lines"] = [{"id": l["id"], "t": l["start"], "frame": to_frame(l["start"], fps), "text": l["text"]}
                      for l in lines if l["id"] in s["line_ids"]]

    data = {"schema": 1, "fps": fps, "duration": duration, "tempo": audio["tempo"],
            "frames_per_beat": round(fps * (audio["tempo"].get("period") or 60 / audio["tempo"]["bpm"]), 3),
            "beats_per_bar": audio.get("beats_per_bar", 4),
            "sections": [{k: v for k, v in s.items() if k not in ("line_ids",)} for s in secs],
            "hooks": hooks, "hits": hits, "gaps": gp, "lyrics_method": timing.get("method")}
    save_json(project / "analysis" / "songmap.json", data)

    fpb = data["frames_per_beat"]
    md = [f"# Song map: {state.get('title')}", "",
          f"{fmt_time(duration)} · {audio['tempo']['bpm']} BPM ({'steady' if audio['tempo']['stable'] else 'variable'}, confidence "
          f"{audio['tempo']['confidence']}) · {data['beats_per_bar']}/4 · {fps:g} fps · {fpb} frames per beat · "
          f"{round(fpb * data['beats_per_bar'], 2)} frames per bar · lyrics timed by `{timing.get('method')}`", ""]
    if audio.get("key"):
        md.append(f"Key (estimate): {audio['key']['name']} · loudness {audio.get('loudness', {}).get('integrated_lufs')} LUFS")
        md.append("")
    md += ["## Sections", "", "Rename sections and add notes here; the shot list is built from this table.", ""]
    rows = []
    for s in secs:
        rows.append([s["display"], s["label"], f"{fmt_time(s['start'])}–{fmt_time(s['end'])}", f"{s['frames'][0]}–{s['frames'][1]}",
                     f"{s['bars'][0]}–{s['bars'][1]}" if s.get("bars") else "—", s.get("energy_db"), s.get("density"),
                     f"{int(s['vocal_presence'] * 100)}%" if "vocal_presence" in s else "—", len(s["lines"])])
    md.append(table(rows, ["Section", "Sound", "Time", "Frames", "Bars", "Energy dB", "Onsets/s", "Vocals", "Lines"]))
    md += ["", "## Lyrics by section", ""]
    for s in secs:
        md.append(f"### {s['display']} · {fmt_time(s['start'])} · frame {s['frames'][0]}")
        if not s["lines"]:
            md.append("_instrumental_")
        for l in s["lines"]:
            md.append(f"- `{fmt_time(l['t'])}` f{l['frame']} · {l['text']}")
        md.append("")
    md += ["## Hooks (repeated lines)", ""]
    md += [f"- **{h['text']}** ×{h['count']} at {', '.join(h['times'])}" for h in hooks] or ["_none_"]
    md += ["", "## Hit list", "", "Moments that may get a visual hit, strongest first within each kind. Not every one should.", ""]
    kinds = Counter(h["kind"] for h in hits)
    md.append(", ".join(f"{k}: {v}" for k, v in kinds.items()))
    md.append("")
    md.append(table([[fmt_time(h["t"]), h["frame"], h["kind"], h.get("label", ""), h["strength"]]
                     for h in hits if h["kind"] != "drum-hit"], ["Time", "Frame", "Kind", "What", "Strength"]))
    md.append("")
    md.append(f"Drum hits ({kinds.get('drum-hit', 0)}) are in `analysis/songmap.json`.")
    md += ["", "## Gaps (no vocals for 2+ bars: the picture carries the film)", ""]
    md += [f"- {fmt_time(g['start'])}–{fmt_time(g['end'])} ({g['bars']} bars)" for g in gp] or ["_none_"]
    md += ["", "## Notes", "", "- "]
    (project / "SONGMAP.md").write_text("\n".join(md) + "\n", encoding="utf-8")
    info(f"wrote {project / 'SONGMAP.md'}")
    print(" · ".join(f"{s['display']} {fmt_time(s['start'])}" for s in secs))


if __name__ == "__main__":
    main()
