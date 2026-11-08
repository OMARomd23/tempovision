#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy>=1.24", "soundfile>=0.12", "whisperx>=3.4"]
# ///
"""Model backend for `tempovision align` (run in its own environment because PyTorch is large).

Reads a job JSON, writes a result JSON. Methods:
  forced     CTC forced alignment of the given tokens over the whole vocal (wav2vec2 via WhisperX's model table)
  windows    the same, but each line aligned inside its own time window (used by anchored and --range)
  transcribe Whisper transcription with segment times (anchors for the anchored method)
  check      load the alignment model for the language (downloads it) and report

  uv run --script _align_ml.py JOB.json OUT.json
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _ctc  # noqa: E402

SR = 16000


def device_and_type():
    import torch

    if torch.cuda.is_available():
        return "cuda", "float16"
    return "cpu", "int8"


def load_audio(path: str) -> np.ndarray:
    import soundfile as sf

    y, sr = sf.read(path, dtype="float32", always_2d=False)
    if y.ndim > 1:
        y = y.mean(axis=1)
    if sr != SR:
        raise SystemExit(f"expected {SR} Hz audio, got {sr}")
    return y


def load_aligner(language: str, device: str, model_name: str | None):
    import whisperx

    model, meta = whisperx.load_align_model(language_code=language, device=device, model_name=model_name)
    dictionary = {k.lower(): v for k, v in meta["dictionary"].items()}
    blank = None
    for cand in ("[pad]", "<pad>", "-", "<blank>", "<s>"):
        if cand in dictionary:
            blank = dictionary[cand]
            break
    if blank is None:
        blank = 0
    return model, meta["type"], dictionary, blank


def emissions(model, kind: str, audio: np.ndarray, device: str, chunk_s: float = 20.0, ctx_s: float = 2.0):
    """Log-probs (T, C) over the whole audio, computed in overlapping chunks so long songs fit in memory."""
    import torch

    n = len(audio)
    chunk, ctx = int(chunk_s * SR), int(ctx_s * SR)
    parts = []
    frame_rate = None
    pos = 0
    while pos < n:
        a = max(0, pos - ctx)
        b = min(n, pos + chunk + ctx)
        x = torch.from_numpy(audio[a:b]).float()[None].to(device)
        with torch.inference_mode():
            if kind == "torchaudio":
                em, _ = model(x)
            else:
                em = model(x).logits
            em = torch.log_softmax(em, dim=-1)[0].float().cpu().numpy()
        fr = em.shape[0] / ((b - a) / SR)
        frame_rate = frame_rate or fr
        keep_a = int(round((pos - a) / SR * fr))
        keep_b = keep_a + int(round((min(pos + chunk, n) - pos) / SR * fr))
        parts.append(em[keep_a:keep_b])
        pos += chunk
    em = np.concatenate(parts, axis=0)
    return em, (em.shape[0] / (n / SR))


def tokenise(words: list[str], dictionary: dict, spaced: bool):
    """Map each word's characters to model ids. Returns tokens and, per token, (word_index or -1 for separator)."""
    sep = dictionary.get("|")
    toks, owner = [], []
    for wi, w in enumerate(words):
        if spaced and sep is not None and toks:
            toks.append(sep)
            owner.append(-1)
        for ch in w.lower():
            if ch in dictionary:
                toks.append(dictionary[ch])
                owner.append(wi)
    return toks, owner


def align_words(em: np.ndarray, fr: float, words: list[str], dictionary: dict, blank: int, offset_s: float = 0.0,
                spaced: bool = True):
    toks, owner = tokenise(words, dictionary, spaced)
    out = [None] * len(words)
    if not toks:
        return out
    spans = _ctc.align(em, toks, blank)
    for sp in spans:
        wi = owner[sp.token_index]
        if wi < 0:
            continue
        rec = out[wi]
        s, ee, e = sp.start / fr + offset_s, sp.emit_end / fr + offset_s, sp.end / fr + offset_s
        if rec is None:
            out[wi] = {"start": s, "emit_end": ee, "hold_end": e, "scores": [sp.score]}
        else:
            rec["emit_end"] = ee
            rec["hold_end"] = e
            rec["scores"].append(sp.score)
    for rec in out:
        if rec:
            rec["score"] = round(float(np.mean(rec.pop("scores"))), 3)
            for k in ("start", "emit_end", "hold_end"):
                rec[k] = round(rec[k], 3)
    return out


def run(job: dict) -> dict:
    method = job["method"]
    device, ctype = device_and_type()
    lang = job.get("language", "en")
    spaced = lang not in ("ja", "zh", "yue", "th", "lo", "km", "my")

    if method == "transcribe":
        import whisperx

        audio = load_audio(job["audio"])
        model = whisperx.load_model(job.get("whisper_model", "small"), device, compute_type=ctype, language=lang)
        res = model.transcribe(audio, batch_size=8, language=lang)
        return {"segments": [{"start": s["start"], "end": s["end"], "text": s["text"]} for s in res["segments"]]}

    model, kind, dictionary, blank = load_aligner(lang, device, job.get("align_model"))
    if method == "check":
        return {"ok": True, "language": lang, "model_type": kind, "vocab": len(dictionary), "device": device}

    audio = load_audio(job["audio"])
    em, fr = emissions(model, kind, audio, device)
    result = {"frame_rate": fr, "lines": []}
    if method == "forced":
        words = [w for line in job["lines"] for w in line["words"]]
        aligned = align_words(em, fr, words, dictionary, blank, 0.0, spaced)
        k = 0
        for line in job["lines"]:
            n = len(line["words"])
            result["lines"].append(aligned[k:k + n])
            k += n
    elif method == "windows":
        for line in job["lines"]:
            a, b = line["window"]
            fa, fb = max(0, int(a * fr)), min(em.shape[0], int(b * fr))
            try:
                result["lines"].append(align_words(em[fa:fb], fr, line["words"], dictionary, blank, fa / fr, spaced))
            except ValueError:
                result["lines"].append([None] * len(line["words"]))
    else:
        raise SystemExit(f"unknown method {method}")
    return result


def main():
    job = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    out = run(job)
    Path(sys.argv[2]).write_text(json.dumps(out), encoding="utf-8")


if __name__ == "__main__":
    main()
