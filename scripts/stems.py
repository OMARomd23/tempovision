#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10,<3.14"
# dependencies = ["numpy>=1.24", "soundfile>=0.12", "torch>=2.1,<2.9", "torchaudio>=2.1,<2.9", "demucs>=4.0.1"]
#
# On Windows and x86-64 Linux, PyPI's torch is the CPU build: take the CUDA build instead (it runs on CPU too), so an
# NVIDIA GPU is actually used.
# [[tool.uv.index]]
# name = "pytorch-cu124"
# url = "https://download.pytorch.org/whl/cu124"
# explicit = true
#
# [tool.uv.sources]
# torch = [{ index = "pytorch-cu124", marker = "sys_platform == 'win32' or (sys_platform == 'linux' and platform_machine == 'x86_64')" }]
# torchaudio = [{ index = "pytorch-cu124", marker = "sys_platform == 'win32' or (sys_platform == 'linux' and platform_machine == 'x86_64')" }]
# ///
"""Separate the song into stems with Demucs (htdemucs): vocals, drums, bass, other.

  tempovision stems                       all four stems -> analysis/stems/*.wav
  tempovision stems --only vocals         vocals (and the instrumental as other.wav sum) only
  tempovision stems --model htdemucs_ft   the fine-tuned model: better, ~4x slower
  tempovision stems --file SONG --out DIR outside a project
  tempovision stems --install             install and download the model now (first run does it anyway)

CPU works (about 1-3x the song's length); an NVIDIA GPU (CUDA) or Apple Silicon (MPS) is much faster.
Models download once (~80 MB per model) into the Torch hub cache.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import Fail, decode_audio, find_project, info, load_state, set_marker, song_path  # noqa: E402


def pick_device(pref: str | None) -> str:
    import torch

    if pref:
        return pref
    if torch.cuda.is_available():
        return "cuda"
    if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def load_model(name: str):
    from demucs.pretrained import get_model

    try:
        model = get_model(name)
    except Exception as e:  # network, unknown name
        raise Fail(f"could not load Demucs model {name!r}: {e}. The first run downloads it from "
                   "dl.fbaipublicfiles.com; check the connection or proxy.")
    model.eval()
    return model


def separate(model, mix: np.ndarray, sr: int, device: str, shifts: int = 1, overlap: float = 0.25) -> dict[str, np.ndarray]:
    """mix: (channels, samples) float32 at the model's sample rate. Returns {stem: (channels, samples)}."""
    import torch
    from demucs.apply import apply_model

    wav = torch.from_numpy(mix).float()
    ref = wav.mean(0)
    mean, std = ref.mean(), ref.std() + 1e-8
    wav = (wav - mean) / std
    with torch.no_grad():
        out = apply_model(model, wav[None], device=device, shifts=shifts, split=True, overlap=overlap,
                          progress=sys.stderr.isatty())[0]
    out = out * std + mean
    return {name: out[i].cpu().numpy() for i, name in enumerate(model.sources)}


def main(argv=None):
    p = argparse.ArgumentParser(prog="tempovision stems", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--file")
    p.add_argument("--out")
    p.add_argument("--only", choices=["vocals"], help="write only vocals.wav and other.wav (= everything else)")
    p.add_argument("--model", default="htdemucs")
    p.add_argument("--device", choices=["cpu", "cuda", "mps"])
    p.add_argument("--shifts", type=int, default=1, help="random shifts averaged (quality vs time)")
    p.add_argument("--install", action="store_true", help="only download the model and exit")
    a = p.parse_args(argv)

    import soundfile as sf

    model = load_model(a.model)
    set_marker("stems")
    if a.install:
        print(f"Demucs {a.model} ready (sources: {', '.join(model.sources)}; sample rate {model.samplerate})")
        return

    project = None if a.file else find_project()
    src = Path(a.file).expanduser() if a.file else song_path(project, load_state(project))
    out_dir = Path(a.out) if a.out else (project / "analysis" / "stems")
    out_dir.mkdir(parents=True, exist_ok=True)

    sr = int(model.samplerate)
    mix = decode_audio(src, sr=sr, mono=False).astype(np.float32)
    device = pick_device(a.device)
    info(f"separating {src.name} ({mix.shape[1] / sr:.0f} s) with {a.model} on {device} …")
    t0 = time.time()
    stems = separate(model, mix, sr, device, shifts=a.shifts)
    info(f"done in {time.time() - t0:.0f} s")
    if a.only == "vocals":
        rest = sum(v for k, v in stems.items() if k != "vocals")
        stems = {"vocals": stems["vocals"], "other": rest}
    for name, data in stems.items():
        sf.write(out_dir / f"{name}.wav", data.T, sr, subtype="FLOAT")
        print(out_dir / f"{name}.wav")


if __name__ == "__main__":
    main()
