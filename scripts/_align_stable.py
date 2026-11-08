#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["stable-ts>=2.17"]
# ///
"""stable-ts backend for `tempovision align --method stable-ts`: align known text with Whisper's attention.

  uv run --script _align_stable.py JOB.json OUT.json     JOB: {"audio", "text", "language", "model"}
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def main():
    job = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    import stable_whisper

    model = stable_whisper.load_model(job.get("model", "small"))
    result = model.align(job["audio"], job["text"], language=job.get("language", "en"))
    words = []
    for seg in result.segments:
        for w in seg.words:
            words.append({"word": w.word.strip(), "start": float(w.start), "end": float(w.end),
                          "probability": float(getattr(w, "probability", 0.0) or 0.0)})
    Path(sys.argv[2]).write_text(json.dumps({"words": words}), encoding="utf-8")


if __name__ == "__main__":
    main()
