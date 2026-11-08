#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Tempovision project state: create the project, track phases, gates, decisions, spend and sections.

  tempovision project init "<Title>" --song FILE [--lyrics FILE] [--dir DIR] [--fps 30] [--light]
  tempovision project status [--json]
  tempovision project import FILE --as song|lyrics|refs|brand
  tempovision project phase <name>                  open interview setup songmap treatment assets build review deliver done
  tempovision project gate <G1..G5> pass|reset [--note "..."]
  tempovision project set <key> <value>             engine, autonomy, fps, aspect, title, next, budget
  tempovision project decide "<what>" --why "<why>"  log a decision made without the artist
  tempovision project wait "<question>"             mark that you are waiting on the artist (stops autopilot)
  tempovision project resume                        clear the wait
  tempovision project spend <usd> "<what>"          log paid generation; refuses beyond the cap unless --over
  tempovision project section <name> todo|building|locked
  tempovision project autopilot pause|resume|reset
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (AUTONOMY, GATES, PHASES, TEMPLATES, Fail, find_project, fmt_time, info,  # noqa: E402
                     load_state, now_iso, save_state, slug)

TREE = [
    "input/refs", "input/brand", "analysis/stems", "analysis/plots", "lyrics",
    "assets/fonts", "assets/images", "assets/footage", "assets/textures", "assets/sfx", "assets/generated",
    "assets/refs", "prompts", "frames/styleframes", "frames/sheets", "video", "renders/drafts", "renders/final", "qa",
]
LIGHT_TREE = ["input", "analysis/stems", "analysis/plots", "lyrics", "qa"]

GITIGNORE = """# Tempovision: large or derived files stay out of git
input/
analysis/stems/
renders/
frames/sheets/
lyrics/preview.mp4
video/node_modules/
video/out/
*.tmp
.DS_Store
"""


def new_state(title: str, fps: float, light: bool) -> dict:
    return {
        "schema": 1,
        "title": title,
        "created": now_iso(),
        "updated": now_iso(),
        "phase": "interview" if not light else "songmap",
        "light": light,
        "autonomy": "checkpoints",
        "engine": os.environ.get("CLAUDE_PLUGIN_OPTION_DEFAULT_ENGINE") or "hyperframes",
        "fps": fps,
        "aspect": "16:9",
        "inputs": {},
        "gates": {g: {"status": "open", "label": label} for g, label in GATES.items()},
        "sections": {},
        "decisions": [],
        "budget": {"cap_usd": 0.0, "spent_usd": 0.0, "log": []},
        "waiting_on_user": None,
        "next": None,
        "autopilot": {"continues": 0, "max_continues": 40, "paused": False},
        "history": [{"at": now_iso(), "event": "created"}],
    }


def copy_input(project: Path, src: Path, kind: str) -> str:
    if not src.exists():
        raise Fail(f"file not found: {src}")
    if kind == "song":
        dest = project / "input" / ("song" + src.suffix.lower())
    elif kind == "lyrics":
        dest = project / "input" / ("lyrics" + (src.suffix.lower() or ".txt"))
    elif kind in ("refs", "brand"):
        dest = project / "input" / kind / src.name
    else:
        raise Fail(f"unknown --as {kind!r}: use song, lyrics, refs or brand")
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        info(f"replacing {dest.relative_to(project)} (the previous file is kept as .prev)")
        dest.replace(dest.with_name(dest.name + ".prev"))
    shutil.copy2(src, dest)
    try:
        os.chmod(dest, 0o444)  # read-only: originals are never modified
    except OSError:
        pass
    return str(dest.relative_to(project))


def cmd_init(a) -> None:
    root_opt = os.environ.get("CLAUDE_PLUGIN_OPTION_PROJECTS_ROOT") or ""
    base = Path(a.dir) if a.dir else (Path(root_opt).expanduser() if root_opt else Path.cwd())
    project = base / slug(a.title)
    if (project / "tempovision.json").exists():
        raise Fail(f"a project already exists at {project}. `cd` there and run `tempovision project status`.")
    project.mkdir(parents=True, exist_ok=True)
    for d in (LIGHT_TREE if a.light else TREE):
        (project / d).mkdir(parents=True, exist_ok=True)
    state = new_state(a.title, a.fps, a.light)
    if a.song:
        state["inputs"]["song"] = copy_input(project, Path(a.song).expanduser(), "song")
    if a.lyrics:
        state["inputs"]["lyrics"] = copy_input(project, Path(a.lyrics).expanduser(), "lyrics")
    (project / ".gitignore").write_text(GITIGNORE, encoding="utf-8")
    if not a.light:
        for doc in ("BRIEF.md",):
            tpl = TEMPLATES / "docs" / doc
            if tpl.exists() and not (project / doc).exists():
                (project / doc).write_text(tpl.read_text(encoding="utf-8").replace("{{title}}", a.title), encoding="utf-8")
        (project / "assets" / "LEDGER.json").write_text('{\n  "schema": 1,\n  "assets": []\n}\n', encoding="utf-8")
    save_state(project, state)
    if shutil.which("git") and not (project / ".git").exists():
        subprocess.run(["git", "init", "-q"], cwd=project)
        subprocess.run(["git", "add", "-A"], cwd=project)
        subprocess.run(["git", "-c", "user.name=tempovision", "-c", "user.email=tempovision@localhost", "commit", "-q",
                        "-m", "tempovision: project created"], cwd=project)
    print(project)


def cmd_status(a) -> None:
    project = find_project()
    s = load_state(project)
    if a.json:
        print(json.dumps(s, indent=2, ensure_ascii=False))
        return
    lines = [f"# {s['title']}", "", f"Folder: {project}",
             f"Phase: **{s['phase']}** · autonomy: {s['autonomy']} · engine: {s['engine']} · {s['fps']} fps · {s.get('aspect')}"]
    lines.append("Inputs: " + (", ".join(f"{k} → {v}" for k, v in s.get("inputs", {}).items()) or "none"))
    lines.append("")
    lines.append("Gates: " + " · ".join(f"{g} {'✅' if v['status'] == 'pass' else '⬜'} {v['label']}" for g, v in s["gates"].items()))
    if s.get("sections"):
        lines.append("Sections: " + " · ".join(f"{k} [{v}]" for k, v in s["sections"].items()))
    b = s.get("budget", {})
    if b.get("cap_usd") or b.get("spent_usd"):
        lines.append(f"Generation budget: ${b.get('spent_usd', 0):.2f} spent of ${b.get('cap_usd', 0):.2f}")
    if s.get("waiting_on_user"):
        lines.append(f"Waiting on the artist: {s['waiting_on_user']}")
    if s.get("next"):
        lines.append(f"Next: {s['next']}")
    present = [f for f in ("BRIEF.md", "SETUP.md", "SONGMAP.md", "TREATMENT.md", "SPEC.md", "SHOTLIST.md", "REVIEW.md")
               if (project / f).exists()]
    lines.append("Documents: " + (", ".join(present) or "none"))
    for label, rel in (("analysis", "analysis/audio.json"), ("lyric timing", "lyrics/timing.json"), ("ledger", "assets/LEDGER.json")):
        lines.append(f"{label}: {'yes' if (project / rel).exists() else 'no'}")
    drafts = sorted((project / "renders" / "drafts").glob("*.mp4"), key=lambda p: p.stat().st_mtime) if (project / "renders" / "drafts").exists() else []
    if drafts:
        lines.append(f"Latest draft: {drafts[-1].relative_to(project)}")
    if s.get("decisions"):
        lines.append(f"Decisions logged: {len(s['decisions'])} (last: {s['decisions'][-1]['what']})")
    print("\n".join(lines))


def cmd_import(a) -> None:
    project = find_project()
    s = load_state(project)
    rel = copy_input(project, Path(a.file).expanduser(), a.as_)
    if a.as_ in ("song", "lyrics"):
        s["inputs"][a.as_] = rel
    else:
        s["inputs"].setdefault(a.as_, [])
        if rel not in s["inputs"][a.as_]:
            s["inputs"][a.as_].append(rel)
    s["history"].append({"at": now_iso(), "event": f"imported {a.as_}: {rel}"})
    save_state(project, s)
    print(rel)


def cmd_phase(a) -> None:
    if a.name not in PHASES:
        raise Fail(f"unknown phase {a.name!r}; one of: {', '.join(PHASES)}")
    project = find_project()
    s = load_state(project)
    s["phase"] = a.name
    s["autopilot"]["continues"] = 0
    s["history"].append({"at": now_iso(), "event": f"phase → {a.name}"})
    save_state(project, s)
    print(f"phase: {a.name}")


def cmd_gate(a) -> None:
    g = a.gate.upper()
    if g not in GATES:
        raise Fail(f"unknown gate {a.gate!r}; one of {', '.join(GATES)}")
    project = find_project()
    s = load_state(project)
    if a.action == "pass":
        s["gates"][g].update({"status": "pass", "at": now_iso(), "note": a.note})
        if s.get("waiting_on_user"):
            s["waiting_on_user"] = None
        follow = {"G1": "setup", "G2": "songmap", "G4": "assets", "G5": "deliver"}
        if g in follow and PHASES.index(s["phase"]) < PHASES.index(follow[g]):
            s["phase"] = follow[g]
    else:
        s["gates"][g] = {"status": "open", "label": GATES[g]}
    s["history"].append({"at": now_iso(), "event": f"gate {g} {a.action}" + (f": {a.note}" if a.note else "")})
    save_state(project, s)
    print(f"{g} {a.action} · phase: {s['phase']}")


def cmd_set(a) -> None:
    project = find_project()
    s = load_state(project)
    key, val = a.key, a.value
    if key == "autonomy" and val not in AUTONOMY:
        raise Fail(f"autonomy must be one of {', '.join(AUTONOMY)}")
    if key == "engine" and val not in ("hyperframes", "remotion"):
        raise Fail("engine must be hyperframes or remotion")
    if key == "fps":
        val = float(val)
    if key == "budget":
        s["budget"]["cap_usd"] = float(val)
    else:
        s[key] = val
    s["history"].append({"at": now_iso(), "event": f"set {key} = {val}"})
    save_state(project, s)
    print(f"{key} = {val}")


def cmd_decide(a) -> None:
    project = find_project()
    s = load_state(project)
    s["decisions"].append({"at": now_iso(), "phase": s["phase"], "what": a.what, "why": a.why})
    save_state(project, s)
    print(f"decision {len(s['decisions'])} logged")


def cmd_wait(a) -> None:
    project = find_project()
    s = load_state(project)
    s["waiting_on_user"] = a.question
    s["history"].append({"at": now_iso(), "event": f"waiting: {a.question}"})
    save_state(project, s)
    print("waiting on the artist")


def cmd_resume(a) -> None:
    project = find_project()
    s = load_state(project)
    s["waiting_on_user"] = None
    s["autopilot"]["continues"] = 0
    save_state(project, s)
    print("resumed")


def cmd_spend(a) -> None:
    project = find_project()
    s = load_state(project)
    b = s["budget"]
    new_total = b.get("spent_usd", 0.0) + a.usd
    cap = b.get("cap_usd", 0.0)
    if new_total > cap + 1e-9 and not a.over:
        raise Fail(f"this spend (${a.usd:.2f}) takes the total to ${new_total:.2f}, over the cap of ${cap:.2f}. "
                   f"Ask the artist; if they approve, re-run with --over and log their approval with `tempovision project decide`.")
    b["spent_usd"] = round(new_total, 4)
    b["log"].append({"at": now_iso(), "usd": a.usd, "what": a.what, "over_cap": new_total > cap})
    save_state(project, s)
    print(f"spent ${b['spent_usd']:.2f} of ${cap:.2f}")


def cmd_section(a) -> None:
    if a.status not in ("todo", "building", "locked"):
        raise Fail("status must be todo, building or locked")
    project = find_project()
    s = load_state(project)
    s["sections"][a.name] = a.status
    s["history"].append({"at": now_iso(), "event": f"section {a.name} → {a.status}"})
    save_state(project, s)
    locked = sum(1 for v in s["sections"].values() if v == "locked")
    print(f"{a.name}: {a.status} ({locked}/{len(s['sections'])} locked)")


def cmd_autopilot(a) -> None:
    project = find_project()
    s = load_state(project)
    ap = s.setdefault("autopilot", {"continues": 0, "max_continues": 40, "paused": False})
    if a.action == "pause":
        ap["paused"] = True
    elif a.action == "resume":
        ap["paused"] = False
    elif a.action == "reset":
        ap["continues"] = 0
    save_state(project, s)
    print(f"autopilot: {'paused' if ap['paused'] else 'on'} · continues {ap['continues']}/{ap['max_continues']}")


def main(argv=None) -> None:
    p = argparse.ArgumentParser(prog="tempovision project", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    x = sub.add_parser("init")
    x.add_argument("title")
    x.add_argument("--song")
    x.add_argument("--lyrics")
    x.add_argument("--dir")
    x.add_argument("--fps", type=float, default=30.0)
    x.add_argument("--light", action="store_true", help="minimal workspace (lyric sync only)")
    x.set_defaults(fn=cmd_init)

    x = sub.add_parser("status")
    x.add_argument("--json", action="store_true")
    x.set_defaults(fn=cmd_status)

    x = sub.add_parser("import")
    x.add_argument("file")
    x.add_argument("--as", dest="as_", required=True, choices=["song", "lyrics", "refs", "brand"])
    x.set_defaults(fn=cmd_import)

    x = sub.add_parser("phase")
    x.add_argument("name")
    x.set_defaults(fn=cmd_phase)

    x = sub.add_parser("gate")
    x.add_argument("gate")
    x.add_argument("action", choices=["pass", "reset"])
    x.add_argument("--note")
    x.set_defaults(fn=cmd_gate)

    x = sub.add_parser("set")
    x.add_argument("key", choices=["engine", "autonomy", "fps", "aspect", "title", "next", "budget"])
    x.add_argument("value")
    x.set_defaults(fn=cmd_set)

    x = sub.add_parser("decide")
    x.add_argument("what")
    x.add_argument("--why", required=True)
    x.set_defaults(fn=cmd_decide)

    x = sub.add_parser("wait")
    x.add_argument("question")
    x.set_defaults(fn=cmd_wait)

    x = sub.add_parser("resume")
    x.set_defaults(fn=cmd_resume)

    x = sub.add_parser("spend")
    x.add_argument("usd", type=float)
    x.add_argument("what")
    x.add_argument("--over", action="store_true", help="the artist approved going over the cap")
    x.set_defaults(fn=cmd_spend)

    x = sub.add_parser("section")
    x.add_argument("name")
    x.add_argument("status")
    x.set_defaults(fn=cmd_section)

    x = sub.add_parser("autopilot")
    x.add_argument("action", choices=["pause", "resume", "reset"])
    x.set_defaults(fn=cmd_autopilot)

    a = p.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
