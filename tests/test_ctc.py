#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy>=1.24", "soundfile>=0.12"]
# ///
"""CTC forced alignment on a synthetic emission matrix with known token times (no model download needed).

Builds a 50 fps emission where each character of each word "fires" at a known frame and blank dominates
elsewhere (plus noise), runs the same word-alignment code `tempovision align` uses, and checks the word starts.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import _align_ml  # noqa: E402
from _ctc import log_softmax  # noqa: E402

LABELS = ["-", "|"] + list("etaonihsrdlumwcfgypbvk'xjqz")
DICT = {c: i for i, c in enumerate(LABELS)}
FR = 50.0


def synth(words, starts, char_frames=3, gap_noise=0.15, seed=0, T=None):
    rng = np.random.default_rng(seed)
    T = T or int((starts[-1] + 2.0) * FR)
    logits = rng.normal(0, gap_noise, size=(T, len(LABELS)))
    logits[:, DICT["-"]] += 4.0
    for w, t0 in zip(words, starts):
        f = int(round(t0 * FR))
        for k, ch in enumerate(w):
            fi = f + k * char_frames
            if fi < T:
                logits[fi, DICT[ch]] += 9.0
    return log_softmax(logits, axis=1)


def main():
    words = "light it up and let it go every night i let you know".split()
    starts = [1.0 + 0.4 * i + (1.5 if i >= 7 else 0) for i in range(len(words))]
    em = synth(words, starts)
    out = _align_ml.align_words(em, FR, words, DICT, DICT["-"], 0.0, True)
    errs = [abs(o["start"] - s) for o, s in zip(out, starts)]
    print(f"word start error: max {max(errs) * 1000:.0f} ms, mean {np.mean(errs) * 1000:.0f} ms")
    assert max(errs) <= 0.021, errs
    # windows: the same words inside a sub-window with an offset
    fa, fb = int(4.5 * FR), em.shape[0]
    sub = _align_ml.align_words(em[fa:fb], FR, words[7:], DICT, DICT["-"], fa / FR, True)
    errs2 = [abs(o["start"] - s) for o, s in zip(sub, starts[7:])]
    assert max(errs2) <= 0.021, errs2
    # unknown characters (digits) are skipped, not fatal
    out3 = _align_ml.align_words(em, FR, ["light", "it", "up", "and", "let", "it", "go", "3very"], DICT, DICT["-"], 0.0, True)
    assert out3[0] is not None
    print("ok: CTC alignment recovers known word starts")


if __name__ == "__main__":
    main()
