#!/usr/bin/env python3
"""Stand-in for scripts/_align_ml.py in tests: answers alignment jobs from a truth.json (TEMPOVISION_TRUTH),
with small jitter, so `tempovision align` can be tested end to end without downloading models."""
import json
import os
import random
import sys
from pathlib import Path

job = json.loads(Path(sys.argv[1]).read_text())
truth = json.loads(Path(os.environ["TEMPOVISION_TRUTH"]).read_text())
rnd = random.Random(1)
words = [w for line in truth["lines"] for w in line["words"]]
if job["method"] == "check":
    out = {"ok": True}
elif job["method"] == "transcribe":
    out = {"segments": [{"start": l["start"], "end": l["end"], "text": l["text"]} for l in truth["lines"]]}
else:
    k = 0
    lines = []
    for line in job["lines"]:
        res = []
        for _ in line["words"]:
            w = words[k] if k < len(words) else None
            k += 1
            if w is None:
                res.append(None)
                continue
            j = rnd.uniform(-0.02, 0.02)
            res.append({"start": w["start"] + j, "emit_end": w["start"] + j + 0.06, "hold_end": w["end"] + 0.4, "score": 0.8})
        lines.append(res)
    out = {"frame_rate": 50.0, "lines": lines}
Path(sys.argv[2]).write_text(json.dumps(out))
