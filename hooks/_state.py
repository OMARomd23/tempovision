"""Shared helpers for Tempovision hooks: find the active project's tempovision.json from the hook's working directory."""
from __future__ import annotations

import json
import os
from pathlib import Path


def read_hook_input() -> dict:
    import sys

    try:
        raw = sys.stdin.read()
        return json.loads(raw) if raw.strip() else {}
    except (json.JSONDecodeError, OSError):
        return {}


def find_project(start: str | os.PathLike | None) -> Path | None:
    """Walk up from start (at most 6 levels) to the folder holding tempovision.json."""
    candidates = []
    if start:
        candidates.append(Path(start))
    env_dir = os.environ.get("CLAUDE_PROJECT_DIR")
    if env_dir:
        candidates.append(Path(env_dir))
    for base in candidates:
        p = base.resolve()
        for _ in range(7):
            if (p / "tempovision.json").is_file():
                return p
            if p.parent == p:
                break
            p = p.parent
    return None


def load_state(project: Path) -> dict | None:
    try:
        return json.loads((project / "tempovision.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def save_state(project: Path, state: dict) -> None:
    tmp = project / "tempovision.json.tmp"
    tmp.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(project / "tempovision.json")
