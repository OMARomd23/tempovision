#!/usr/bin/env python3
"""SessionStart: pass the stock-search keys from the plugin settings to Bash, and when the session opens inside a
Tempovision project, put its state in context so work resumes."""
from __future__ import annotations

import json
import os
import re
import shlex
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _state import find_project, load_state, read_hook_input  # noqa: E402

PHASES = ["open", "interview", "setup", "songmap", "treatment", "assets", "build", "review", "deliver", "done"]

# plugin settings pexels_api_key / pixabay_api_key reach hooks as CLAUDE_PLUGIN_OPTION_<KEY>; `tempovision assets
# search` reads them under the same name without the prefix
KEYS = ("PEXELS_API_KEY", "PIXABAY_API_KEY")


def export_keys() -> None:
    """Hooks receive plugin settings, Bash commands do not; CLAUDE_ENV_FILE carries them into every Bash command."""
    env_file = os.environ.get("CLAUDE_ENV_FILE")
    if not env_file:
        return
    lines = []
    for var in KEYS:
        value = os.environ.get(f"CLAUDE_PLUGIN_OPTION_{var}", "").strip()
        if value:
            # plain assignments only, so PowerShell commands receive them too
            lines.append(f"export {var}={value if re.fullmatch(r'[A-Za-z0-9_.-]+', value) else shlex.quote(value)}\n")
    if lines:
        with open(env_file, "a", encoding="utf-8") as f:
            f.writelines(lines)


def main() -> int:
    data = read_hook_input()
    try:
        export_keys()
    except OSError:
        pass  # never block the session over a key
    project = find_project(data.get("cwd"))
    if not project:
        return 0
    state = load_state(project)
    if not state:
        return 0
    gates = state.get("gates", {})
    passed = [g for g, v in sorted(gates.items()) if v.get("status") == "pass"]
    open_gates = [g for g, v in sorted(gates.items()) if v.get("status") != "pass"]
    sections = state.get("sections", {})
    locked = [s for s, v in sections.items() if v == "locked"]
    lines = [
        f"Tempovision project open: {state.get('title', '?')} at {project}",
        f"Phase: {state.get('phase', '?')} · autonomy: {state.get('autonomy', '?')} · engine: {state.get('engine', '?')}",
        f"Gates passed: {', '.join(passed) or 'none'} · open: {', '.join(open_gates) or 'none'}",
    ]
    if sections:
        lines.append(f"Sections locked: {len(locked)}/{len(sections)} ({', '.join(locked) or '—'})")
    waiting = state.get("waiting_on_user")
    if waiting:
        lines.append(f"Waiting on the artist: {waiting}")
    budget = state.get("budget", {})
    if budget.get("cap_usd"):
        lines.append(f"Generation spend: ${budget.get('spent_usd', 0):.2f} of ${budget['cap_usd']:.2f}")
    nxt = state.get("next")
    if nxt:
        lines.append(f"Next step recorded: {nxt}")
    lines.append("Use the tempovision:music-video skill to continue; `tempovision project status` for details.")
    out = {"hookSpecificOutput": {"hookEventName": "SessionStart", "additionalContext": "\n".join(lines)}}
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
