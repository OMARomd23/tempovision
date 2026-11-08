#!/usr/bin/env python3
"""PreToolUse: never modify the artist's originals in <project>/input/.

Blocks Write/Edit into input/, and Bash commands that delete, move, truncate or overwrite files there
(rm, mv, redirection, ffmpeg -y output, sed -i, truncate, cp onto). Reading from input/ is always allowed.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _state import find_project, read_hook_input  # noqa: E402

DESTRUCTIVE = [
    r"\brm\b[^|;&]*\binput/",
    r"\bmv\b[^|;&]*\binput/",
    r"\btruncate\b[^|;&]*\binput/",
    r"\bsed\b[^|;&]*\s-i\b[^|;&]*\binput/",
    r">\s*['\"]?[^\s'\"|;&]*\binput/",
    r"\bcp\b[^|;&]*\s['\"]?[^\s'\"|;&]*\binput/[^\s'\"|;&]*['\"]?\s*$",
    r"\bffmpeg\b[^|;&]*\s['\"]?[^\s'\"|;&]*\binput/[^\s'\"|;&]+['\"]?\s*(?:$|[|;&])",
]


def deny(reason: str) -> None:
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))


def main() -> int:
    data = read_hook_input()
    project = find_project(data.get("cwd"))
    if not project:
        return 0
    tool = data.get("tool_name", "")
    tin = data.get("tool_input", {}) or {}
    input_dir = (project / "input").resolve()

    if tool in ("Write", "Edit"):
        path = tin.get("file_path")
        if path:
            p = Path(path)
            if not p.is_absolute():
                p = Path(data.get("cwd") or project) / p
            try:
                p.resolve().relative_to(input_dir)
            except ValueError:
                return 0
            deny("Tempovision keeps the artist's originals in input/ untouched. Write a copy elsewhere (for example "
                 "assets/ or analysis/) instead.")
        return 0

    if tool == "Bash":
        cmd = tin.get("command", "")
        if "input/" not in cmd:
            return 0
        for pattern in DESTRUCTIVE:
            if re.search(pattern, cmd):
                deny("This command would change a file in input/, where Tempovision keeps the artist's originals "
                     "untouched. Read from input/ and write the result to another folder. If the artist asked "
                     "for this, ask them to confirm and do it by hand.")
                return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
