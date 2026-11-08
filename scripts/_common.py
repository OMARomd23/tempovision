"""Shared helpers for Tempovision tools: project discovery, JSON I/O, ffprobe/ffmpeg, timing utilities.

Standard library only, so every script can import it whatever its own dependencies are.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PLUGIN_ROOT / "data"
TEMPLATES = PLUGIN_ROOT / "templates"

PHASES = ["open", "interview", "setup", "songmap", "treatment", "assets", "build", "review", "deliver", "done"]
GATES = {
    "G1": "brief approved",
    "G2": "setup ready",
    "G3": "lyric sync preview OK",
    "G4": "style frames approved",
    "G5": "rough cut approved",
}
AUTONOMY = ["guided", "checkpoints", "full"]


# ---------------------------------------------------------------- output


class Fail(SystemExit):
    """Exit with a readable message (no traceback)."""

    def __init__(self, msg: str, code: int = 1):
        print(f"tempovision: {msg}", file=sys.stderr)
        super().__init__(code)


def info(msg: str) -> None:
    print(msg, file=sys.stderr)


def now_iso() -> str:
    return _dt.datetime.now().astimezone().isoformat(timespec="seconds")


def plugin_data_dir() -> Path:
    """Persistent per-user data (model caches, venvs). CLAUDE_PLUGIN_DATA when set by Claude Code."""
    d = os.environ.get("CLAUDE_PLUGIN_DATA") or os.environ.get("TEMPOVISION_DATA")
    p = Path(d) if d else Path.home() / ".cache" / "tempovision"
    p.mkdir(parents=True, exist_ok=True)
    return p


# ---------------------------------------------------------------- project


def find_project(start: Path | None = None, required: bool = True) -> Path | None:
    p = (start or Path.cwd()).resolve()
    for _ in range(8):
        if (p / "tempovision.json").is_file():
            return p
        if p.parent == p:
            break
        p = p.parent
    if required:
        raise Fail("no tempovision.json here or above. Run `tempovision project init \"<title>\" --song <file>` first, "
                   "or cd into the project folder.")
    return None


def load_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        if default is not None:
            return default
        raise Fail(f"missing {path}")
    except json.JSONDecodeError as e:
        raise Fail(f"{path} is not valid JSON: {e}")


def save_json(path: Path, data: Any) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def load_state(project: Path) -> dict:
    return load_json(project / "tempovision.json")


def save_state(project: Path, state: dict) -> None:
    state["updated"] = now_iso()
    save_json(project / "tempovision.json", state)


def song_path(project: Path, state: dict | None = None) -> Path:
    state = state or load_state(project)
    rel = state.get("inputs", {}).get("song")
    if not rel:
        raise Fail("no song in this project. Add it: `tempovision project import <file> --as song`.")
    p = project / rel
    if not p.exists():
        raise Fail(f"song file missing: {p}")
    return p


def lyrics_path(project: Path, state: dict | None = None) -> Path | None:
    state = state or load_state(project)
    rel = state.get("inputs", {}).get("lyrics")
    return (project / rel) if rel else None


def project_fps(project: Path, state: dict | None = None) -> float:
    state = state or load_state(project)
    return float(state.get("fps") or 30)


# ---------------------------------------------------------------- media


def which(name: str) -> str | None:
    return shutil.which(name)


def run(cmd: list[str], check: bool = True, capture: bool = True, timeout: float | None = None) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(cmd, check=check, capture_output=capture, text=True, timeout=timeout)
    except FileNotFoundError:
        raise Fail(f"`{cmd[0]}` not found. Run `tempovision doctor`.")
    except subprocess.CalledProcessError as e:
        tail = (e.stderr or "").strip().splitlines()[-6:]
        raise Fail(f"`{' '.join(cmd[:3])} …` failed:\n  " + "\n  ".join(tail))


def ffprobe(path: Path) -> dict:
    if not which("ffprobe"):
        raise Fail("ffprobe not found. Install FFmpeg (`tempovision doctor`).")
    out = run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)])
    return json.loads(out.stdout)


def media_summary(path: Path) -> dict:
    meta = ffprobe(path)
    fmt = meta.get("format", {})
    v = next((s for s in meta.get("streams", []) if s.get("codec_type") == "video"), None)
    a = next((s for s in meta.get("streams", []) if s.get("codec_type") == "audio"), None)
    res: dict[str, Any] = {"duration": float(fmt.get("duration", 0) or 0), "format": fmt.get("format_name")}
    if v:
        num, _, den = (v.get("avg_frame_rate") or v.get("r_frame_rate") or "0/1").partition("/")
        fps = float(num) / float(den or 1) if float(den or 1) else 0.0
        res["video"] = {
            "codec": v.get("codec_name"), "width": v.get("width"), "height": v.get("height"),
            "fps": round(fps, 3), "pix_fmt": v.get("pix_fmt"),
            "frames": int(v["nb_frames"]) if str(v.get("nb_frames", "")).isdigit() else None,
            "duration": float(v.get("duration", 0) or 0) or res["duration"],
        }
    if a:
        res["audio"] = {
            "codec": a.get("codec_name"), "sample_rate": int(a.get("sample_rate", 0) or 0),
            "channels": a.get("channels"), "duration": float(a.get("duration", 0) or 0) or res["duration"],
        }
    return res


def decode_audio(path: Path, sr: int = 22050, mono: bool = True, start: float | None = None,
                 duration: float | None = None):
    """Decode any audio/video file to float32 numpy via ffmpeg (no codec surprises)."""
    import numpy as np  # local import: _common stays stdlib-only at import time

    if not which("ffmpeg"):
        raise Fail("ffmpeg not found. Install FFmpeg (`tempovision doctor`).")
    cmd = ["ffmpeg", "-v", "error", "-nostdin"]
    if start:
        cmd += ["-ss", f"{start:.6f}"]
    if duration:
        cmd += ["-t", f"{duration:.6f}"]
    cmd += ["-i", str(path), "-vn", "-f", "f32le", "-acodec", "pcm_f32le", "-ar", str(sr), "-ac", "1" if mono else "2", "-"]
    proc = subprocess.run(cmd, capture_output=True)
    if proc.returncode != 0:
        raise Fail(f"could not decode audio from {path}: {proc.stderr.decode(errors='ignore')[-400:]}")
    y = np.frombuffer(proc.stdout, dtype=np.float32).copy()
    if not mono:
        y = y.reshape(-1, 2).T
    return y


# ---------------------------------------------------------------- timing


def snap(t: float, fps: float) -> float:
    return round(round(t * fps) / fps, 6)


def to_frame(t: float, fps: float) -> int:
    return int(round(t * fps))


def fmt_time(t: float) -> str:
    sign = "-" if t < 0 else ""
    t = abs(t)
    m, s = divmod(t, 60)
    return f"{sign}{int(m)}:{s:05.2f}"


def parse_time(s: str) -> float:
    """'1:12.5' or '72.5' or '1:02:03' -> seconds."""
    s = s.strip()
    if not s:
        raise ValueError("empty time")
    parts = s.split(":")
    total = 0.0
    for p in parts:
        total = total * 60 + float(p)
    return total


def parse_range(s: str) -> tuple[float, float]:
    """'1:12-1:30', '72-90' or '72.0,74.5' -> (start, end) seconds."""
    sep = "," if "," in s else "-"
    a, _, b = s.partition(sep)
    if not b:
        raise ValueError(f"not a range: {s!r} (use START-END or START,END)")
    start, end = parse_time(a), parse_time(b)
    if end <= start:
        raise ValueError(f"range ends before it starts: {s!r}")
    return start, end


def nearest(values: Iterable[float], t: float) -> tuple[float | None, float]:
    best, dist = None, float("inf")
    for v in values:
        d = abs(v - t)
        if d < dist:
            best, dist = v, d
    return best, dist


def slug(s: str, maxlen: int = 48) -> str:
    s = re.sub(r"[^\w\s-]", "", s.lower(), flags=re.UNICODE).strip()
    s = re.sub(r"[\s_-]+", "-", s)
    return s[:maxlen].strip("-") or "untitled"


def table(rows: list[list[Any]], header: list[str]) -> str:
    """Markdown table."""
    out = ["| " + " | ".join(header) + " |", "|" + "|".join("---" for _ in header) + "|"]
    for r in rows:
        out.append("| " + " | ".join("" if c is None else str(c).replace("|", "\\|") for c in r) + " |")
    return "\n".join(out)


def detect_cuts(video: Path, threshold: float = 12.0) -> list[dict]:
    """Scene cuts via ffmpeg's scdet filter: [{t, score}]. Threshold is scdet's 0-100 scene score."""
    proc = subprocess.run(["ffmpeg", "-hide_banner", "-nostdin", "-i", str(video), "-an", "-vf",
                           f"scdet=threshold={threshold}:sc_pass=0,metadata=print:file=-", "-f", "null", "-"],
                          capture_output=True, text=True)
    cuts, cur_t = [], None
    for line in (proc.stdout or "").splitlines():
        line = line.strip()
        m = re.search(r"pts_time:([\d.]+)", line)
        if m:
            cur_t = float(m.group(1))
            continue
        m = re.search(r"lavfi\.scd\.score=([\d.]+)", line)
        if m and cur_t is not None:
            score = float(m.group(1))
            if score >= threshold:
                cuts.append({"t": round(cur_t, 3), "score": round(score, 1)})
    return cuts


def extract_frame(video: Path, t: float, out: Path, width: int | None = None) -> bool:
    vf = f"scale={width}:-2" if width else "null"
    proc = subprocess.run(["ffmpeg", "-v", "error", "-y", "-nostdin", "-ss", f"{max(0.0, t):.4f}", "-i", str(video),
                           "-frames:v", "1", "-vf", vf, str(out)], capture_output=True, text=True)
    return proc.returncode == 0 and out.exists()


def set_marker(name: str) -> None:
    """Record that an optional component is installed (read by `tempovision doctor`)."""
    d = plugin_data_dir() / "markers"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{name}.ok").write_text(now_iso() + "\n", encoding="utf-8")
