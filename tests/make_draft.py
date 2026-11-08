#!/usr/bin/env python3
"""Render a stand-in 'draft' for a test project: a colour field that cuts on section starts and chorus downbeats,
lyrics burned in from lyrics/lyrics.ass, and the song as audio. Used to test tempovision qa / sheet / deliver.

  python3 tests/make_draft.py PROJECT_DIR OUT.mp4 [--offset-audio 0.0] [--size 640x360]
"""
import argparse
import json
import subprocess
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("project")
ap.add_argument("out")
ap.add_argument("--offset-audio", type=float, default=0.0, help="delay the audio by this many seconds (to test av_offset)")
ap.add_argument("--size", default="640x360")
ap.add_argument("--black-at", type=float, default=None, help="insert 1 s of black at this time (to test black detection)")
a = ap.parse_args()
p = Path(a.project)
sm = json.loads((p / "analysis/songmap.json").read_text())
fps = 30
snapf = lambda t: round(t * fps) / fps  # noqa: E731
cuts = sorted({0.0} | {snapf(s["start"]) for s in sm["sections"]} | {snapf(h["t"]) for h in sm["hits"] if h["kind"] == "chorus-downbeat"})
dur = sm["duration"]
palette = ["0x2E2A26", "0xC94F3D", "0xE8DCC4", "0x3D5A6C", "0xD9A441", "0x6B8F71"]
w, h = a.size.split("x")
parts, labels = [], []
for i, t in enumerate(cuts):
    end = cuts[i + 1] if i + 1 < len(cuts) else dur
    c = "black" if a.black_at is not None and t <= a.black_at < end and False else palette[i % len(palette)]
    nfr = round(snapf(end) * fps) - round(t * fps)
    parts.append(f"color=c={c}:s={w}x{h}:r={fps},trim=end_frame={nfr}[v{i}]")
    labels.append(f"[v{i}]")
fc = ";".join(parts) + ";" + "".join(labels) + f"concat=n={len(cuts)}:v=1:a=0[base]"
vf_chain = "[base]"
if a.black_at is not None:
    fc += f";[base]drawbox=x=0:y=0:w=iw:h=ih:color=black:t=fill:enable='between(t,{a.black_at},{a.black_at + 1})'[b2]"
    vf_chain = "[b2]"
fc += f";{vf_chain}ass=lyrics.ass[v]"
audio_in = ["-itsoffset", str(a.offset_audio), "-i", str((p / "input").glob("song.*").__next__().resolve())]
cmd = ["ffmpeg", "-v", "error", "-y", "-filter_complex", fc] + audio_in + ["-map", "[v]", "-map", "0:a", "-c:v", "libx264",
       "-preset", "veryfast", "-crf", "26", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-t", f"{dur:.3f}", str(Path(a.out).resolve())]
subprocess.run(cmd, check=True, cwd=p / "lyrics")
print(a.out)
