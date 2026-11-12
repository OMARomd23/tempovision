#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10,<3.13"
# dependencies = ["numpy>=1.24", "soundfile>=0.12", "torch==2.5.1", "torchaudio==2.5.1"]
#
# [[tool.uv.index]]
# name = "pytorch-cu124"
# url = "https://download.pytorch.org/whl/cu124"
# explicit = true
#
# [tool.uv.sources]
# torch = [{ index = "pytorch-cu124", marker = "sys_platform == 'win32' or (sys_platform == 'linux' and platform_machine == 'x86_64')" }]
# torchaudio = [{ index = "pytorch-cu124", marker = "sys_platform == 'win32' or (sys_platform == 'linux' and platform_machine == 'x86_64')" }]
# ///
"""Multilingual model backend for `tempovision align --method mms`: Meta's MMS forced aligner (torchaudio MMS_FA).

MMS_FA was trained on 1,100+ languages and aligns romanised text (a-z and '), so it suits languages without a
dedicated wav2vec2 model and lyrics written in Latin script: Darija or other Arabic written in Arabizi, code-switched
lyrics (Darija + French), Wolof, Tagalog... A wildcard <star> token sits before every line, so sung material that
isn't in the lyrics (ad-libs, an unwritten repeat) is absorbed there instead of stretching the neighbouring words.

On Windows and x86-64 Linux the CUDA build of PyTorch is installed (it also runs on CPU); the GPU is used when there
is one. Same job/result contract as _align_ml.py (methods: forced, windows, check).

  uv run --script _align_mms.py JOB.json OUT.json
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
from pathlib import Path

import numpy as np

SR = 16000
# Arabizi: digits standing for Arabic letters inside a word (3 = ع, 7 = ح, 9 = ق ...), mapped to their nearest
# Latin sound. A word made only of digits ("10", "666") is sung as a number: it becomes a wildcard.
ARABIZI = {"2": "a", "3": "a", "5": "kh", "6": "t", "7": "h", "8": "gh", "9": "q"}


def romanise(word: str) -> str:
    w = word.lower()
    if re.fullmatch(r"[\d.,]+", w):
        return ""
    if re.search(r"[a-z]", w):
        w = "".join(ARABIZI.get(c, c) for c in w)
    w = unicodedata.normalize("NFKD", w)
    w = "".join(c for c in w if not unicodedata.combining(c))
    return re.sub(r"[^a-z']", "", w)


def load_audio(path: str):
    import soundfile as sf

    y, sr = sf.read(path, dtype="float32", always_2d=True)
    y = y.mean(axis=1)
    if sr != SR:
        raise SystemExit(f"expected {SR} Hz audio, got {sr}")
    return y


def emissions(model, audio: np.ndarray, device, chunk_s: float = 20.0, ctx_s: float = 2.0):
    """Frame log-probs for long audio in overlapping windows, keeping only each window's centre."""
    import torch

    n, chunk, ctx = len(audio), int(chunk_s * SR), int(ctx_s * SR)
    parts, pos = [], 0
    with torch.inference_mode():
        while pos < n:
            a, b = max(0, pos - ctx), min(n, pos + chunk + ctx)
            em, _ = model(torch.from_numpy(audio[a:b])[None].to(device))
            em = em[0].float().cpu()
            fr = em.shape[0] / ((b - a) / SR)
            keep_a = int(round((pos - a) / SR * fr))
            keep_b = keep_a + int(round((min(pos + chunk, n) - pos) / SR * fr))
            parts.append(em[keep_a:keep_b])
            pos += chunk
    em = torch.cat(parts)
    return em, em.shape[0] / (n / SR)


def align_lines(em, fr: float, lines: list[list[str]], dictionary: dict, star: int, offset_s: float = 0.0):
    """Per line, per word: {start, emit_end, hold_end, score} (the _align_ml.py contract), or None."""
    import torch
    import torchaudio.functional as F

    tokens, owner = [], []  # owner: (line, word) or None for a separator star
    for li, words in enumerate(lines):
        tokens.append(star)
        owner.append(None)
        for wi, w in enumerate(words):
            r = romanise(w)
            for c in (r if r else "*"):
                tokens.append(dictionary[c] if c != "*" else star)
                owner.append((li, wi))
    tokens.append(star)
    owner.append(None)
    if em.shape[0] < len(tokens):
        raise ValueError("audio too short for the lyrics")
    ali, scores = F.forced_align(em[None], torch.tensor([tokens], dtype=torch.int32), blank=0)
    spans = F.merge_tokens(ali[0], scores[0].exp())
    words: dict = {}
    order = []
    for k, (sp, own) in enumerate(zip(spans, owner)):
        if own is None:
            continue
        rec = words.get(own)
        if rec is None:
            rec = words[own] = {"start": sp.start, "end": sp.end, "scores": [], "next": None}
            order.append(own)
        rec["end"] = sp.end
        rec["scores"].append(float(sp.score))
        # the voice may hold a word until the next token is emitted
        rec["next"] = spans[k + 1].start if k + 1 < len(spans) else sp.end
    out = [[None] * len(words_) for words_ in lines]
    for (li, wi) in order:
        r = words[(li, wi)]
        out[li][wi] = {"start": round(r["start"] / fr + offset_s, 3), "emit_end": round(r["end"] / fr + offset_s, 3),
                       "hold_end": round(max(r["end"], r["next"]) / fr + offset_s, 3),
                       "score": round(float(np.mean(r["scores"])), 3)}
    return out


def run(job: dict) -> dict:
    import torch
    import torchaudio

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    bundle = torchaudio.pipelines.MMS_FA
    model = bundle.get_model(with_star=True).to(device).eval()
    dictionary = bundle.get_dict(star="*")
    star = dictionary["*"]
    gpu = torch.cuda.get_device_name(0) if device.type == "cuda" else None
    if job["method"] == "check":
        return {"ok": True, "model_type": "mms_fa", "vocab": len(dictionary), "device": device.type, "gpu": gpu}
    audio = load_audio(job["audio"])
    em, fr = emissions(model, audio, device)
    result = {"frame_rate": fr, "device": device.type, "gpu": gpu, "lines": []}
    if job["method"] == "forced":
        result["lines"] = align_lines(em, fr, [line["words"] for line in job["lines"]], dictionary, star)
    elif job["method"] == "windows":
        for line in job["lines"]:
            a, b = line["window"]
            fa, fb = max(0, int(a * fr)), min(em.shape[0], int(b * fr))
            try:
                result["lines"].append(align_lines(em[fa:fb], fr, [line["words"]], dictionary, star, fa / fr)[0])
            except (ValueError, RuntimeError):
                result["lines"].append([None] * len(line["words"]))
    else:
        raise SystemExit(f"unknown method {job['method']}")
    return result


def main():
    job = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    Path(sys.argv[2]).write_text(json.dumps(run(job)), encoding="utf-8")


if __name__ == "__main__":
    main()
