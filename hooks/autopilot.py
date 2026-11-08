#!/usr/bin/env python3
"""Stop: in full autonomy, keep a production going until delivery or a real question.

Blocks the stop (once per continuation, up to a budget) only when all of these hold:
- the session is inside a Tempovision project with autonomy == "full";
- gates G1 (brief) and G2 (setup) have passed, so the artist's required checkpoints are behind us;
- the phase is not "done", nothing is recorded in waiting_on_user, and autopilot is not paused;
- the continuation budget (autopilot.max_continues, default 40) is not spent.
Otherwise it lets Claude stop normally.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _state import find_project, load_state, read_hook_input, save_state  # noqa: E402

NEXT_BY_PHASE = {
    "songmap": "finish the song map (stems, analyze, align, songmap, preview) and check the alignment QA",
    "treatment": "write the treatments, pick one, then SPEC.md, SHOTLIST.md and the style frames",
    "assets": "source, make or generate the assets in the shot list and record each in the ledger",
    "build": "build and lock the next unlocked section",
    "review": "render a draft, run tempovision qa, the sheets and the critic, and fix P0/P1 notes",
    "deliver": "final render, tempovision deliver, and REVIEW.md",
}


def main() -> int:
    data = read_hook_input()
    project = find_project(data.get("cwd"))
    if not project:
        return 0
    state = load_state(project)
    if not state or state.get("autonomy") != "full":
        return 0
    gates = state.get("gates", {})
    if gates.get("G1", {}).get("status") != "pass" or gates.get("G2", {}).get("status") != "pass":
        return 0
    phase = state.get("phase", "")
    if phase in ("done", "open", "interview", "setup") or state.get("waiting_on_user"):
        return 0
    auto = state.setdefault("autopilot", {})
    if auto.get("paused"):
        return 0
    used = int(auto.get("continues", 0))
    cap = int(auto.get("max_continues", 40))
    if used >= cap:
        return 0
    auto["continues"] = used + 1
    save_state(project, state)
    step = state.get("next") or NEXT_BY_PHASE.get(phase, "continue the current phase")
    reason = (
        f"Tempovision full autonomy (continuation {used + 1}/{cap}): the production is in phase '{phase}' and nobody "
        f"is waiting on the artist. Next: {step}. If you truly need the artist, ask them and run "
        f"`tempovision project wait \"<question>\"`; if the work is delivered, run `tempovision project phase done`; "
        f"to stop autopilot, run `tempovision project autopilot pause`."
    )
    print(json.dumps({"decision": "block", "reason": reason}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
