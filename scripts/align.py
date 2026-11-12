#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy>=1.24", "soundfile>=0.12", "scipy>=1.10", "matplotlib>=3.7"]
# ///
"""Word-level lyric timing: align the artist's own lyric text to the vocal.

  tempovision align                         auto: forced -> mms -> anchored -> stable-ts -> heuristic (first that passes QA)
  tempovision align --method forced|mms|anchored|stable-ts|heuristic
                                            mms: Meta's multilingual aligner (1,100+ languages, romanised text):
                                            for languages without a wav2vec2 model, Arabizi, code-switched lyrics
  tempovision align --import FILE           use the artist's timing (.lrc, .srt, or a tap file from lyrics/tap.html)
  tempovision align --taps                  write lyrics/tap.html: the artist taps each line start in a browser
  tempovision align --preview               render lyrics/preview.mp4: karaoke over the song, to check by ear
  tempovision align --inspect N             plot line N (vocal energy + word marks) -> lyrics/inspect-N.png
  tempovision align --range 1:12-1:30       re-align only the lines starting in this range
  tempovision align --nudge 14:+0.08        shift line 14 by +80 ms (repeatable); --nudge all:-0.03 shifts everything
  tempovision align --export srt,lrc,ass,hyperframes,remotion   (default: all)
  tempovision align --install               set up the model backend and download the alignment model now

Options: --language en (ISO 639-1), --align-model NAME (any wav2vec2 CTC model on Hugging Face),
--whisper small|medium|large-v3 (for anchored), --audio vocals|mix.
Lyrics: one sung line per line, every repeat written out; [Section] tags; (ad-libs) in parentheses.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (PLUGIN_ROOT, Fail, decode_audio, find_project, fmt_time, info, load_json, load_state,  # noqa: E402
                     lyrics_path, now_iso, parse_range, save_json, save_state, set_marker, song_path)

SR = 16000
SCRIPTS = Path(__file__).resolve().parent

# ---------------------------------------------------------------- lyrics parsing

ONES = "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen " \
       "seventeen eighteen nineteen".split()
TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()


def num_to_words(n: int) -> str:
    """English number words, enough for lyrics ("99 problems", "1999", "24/7" -> parts)."""
    if n < 20:
        return ONES[n]
    if n < 100:
        return TENS[n // 10] + ("" if n % 10 == 0 else " " + ONES[n % 10])
    if 1100 <= n < 2000 or 2010 <= n < 2100:  # years read in pairs: nineteen ninety nine
        hi, lo = divmod(n, 100)
        return num_to_words(hi) + " " + ("hundred" if lo == 0 else ("oh " + ONES[lo] if lo < 10 else num_to_words(lo)))
    if n < 1000:
        return ONES[n // 100] + " hundred" + ("" if n % 100 == 0 else " " + num_to_words(n % 100))
    if n < 1_000_000:
        return num_to_words(n // 1000) + " thousand" + ("" if n % 1000 == 0 else " " + num_to_words(n % 1000))
    return str(n)


def normalise_word(w: str, language: str) -> str:
    w = unicodedata.normalize("NFC", w)
    w = w.replace("’", "'").replace("‘", "'").replace("`", "'")
    if language == "en" and re.fullmatch(r"\d+", w):
        return num_to_words(int(w))
    w = re.sub(r"[^\w'\s]", " ", w, flags=re.UNICODE).replace("_", " ")
    return re.sub(r"\s+", " ", w).strip().lower()


def syllables(word: str) -> int:
    w = re.sub(r"[^a-zà-ÿ]", "", word.lower())
    if not w:
        return max(1, len(word) // 3)
    groups = re.findall(r"[aeiouyà-ÿ]+", w)
    n = len(groups)
    if w.endswith("e") and n > 1 and not w.endswith(("le", "ee")):
        n -= 1
    return max(1, n)


def parse_lyrics(text: str, language: str = "en") -> list[dict]:
    lines, section, sec_count, pending_break = [], None, {}, False
    for raw in text.splitlines():
        s = raw.strip()
        if not s:
            if lines:
                lines[-1]["phrase_break_after"] = True
            continue
        m = re.fullmatch(r"\[(.+?)\]", s)
        if m:
            name = m.group(1).strip()
            sec_count[name] = sec_count.get(name, 0) + 1
            section = name
            continue
        adlib_line = bool(re.fullmatch(r"\(.*\)", s))
        words = []
        in_paren = False
        for tok in s.split():
            opens, closes = tok.startswith("("), tok.endswith(")")
            if opens:
                in_paren = True
            display = tok
            norm = normalise_word(tok, language)
            for part in (norm.split() if norm else []):
                words.append({"text": display, "norm": part, "adlib": in_paren or adlib_line, "syl": syllables(part)})
                display = ""  # a number expanded to several words shows once
            if closes:
                in_paren = False
        if not words:
            continue
        # merge display: words created from one token keep the display on the first part only
        lines.append({"id": len(lines) + 1, "section": section, "text": s, "words": words, "adlib": adlib_line,
                      "phrase_break_after": False})
    return lines


# ---------------------------------------------------------------- audio helpers


def vocal_source(project: Path, state: dict, which: str) -> Path:
    v = project / "analysis" / "stems" / "vocals.wav"
    if which == "vocals" or (which == "auto" and v.exists()):
        if not v.exists():
            raise Fail("no vocal stem yet; run `tempovision stems` (or use --audio mix)")
        return v
    return song_path(project, state)


def activity(y: np.ndarray, sr: int = SR, rate: int = 100):
    hop = sr // rate
    n = len(y) // hop
    frames = y[: n * hop].reshape(n, hop)
    rms = np.sqrt((frames ** 2).mean(axis=1) + 1e-12)
    e = 20 * np.log10(rms + 1e-10)
    k = 5
    e = np.convolve(e, np.ones(k) / k, mode="same")
    loud = np.percentile(e, 95)
    thr = max(loud - 24, np.percentile(e, 20) + 6)
    return e, e > thr, rate


# ---------------------------------------------------------------- backends


def uv_run(script: str, *args: str, timeout: float | None = None) -> subprocess.CompletedProcess:
    override = os.environ.get("TEMPOVISION_ML_BACKEND") if script in ("_align_ml.py", "_align_mms.py") else None
    if override:  # tests: a stand-in backend with the same job/result contract
        return subprocess.run([sys.executable, override, *args], capture_output=True, text=True, timeout=timeout)
    uv = shutil.which("uv")
    if not uv:
        raise Fail("uv not found; run `tempovision doctor`")
    cmd = [uv, "run", "--quiet", "--script", str(SCRIPTS / script), *args]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def ml_job(job: dict, script: str = "_align_ml.py") -> dict:
    with tempfile.TemporaryDirectory() as td:
        jp, op = Path(td) / "job.json", Path(td) / "out.json"
        jp.write_text(json.dumps(job), encoding="utf-8")
        name = "mms" if script == "_align_mms.py" else "wav2vec2"
        info(f"model backend: {name} {job['method']} (first run installs PyTorch and downloads the model) …")
        proc = uv_run(script, str(jp), str(op))
        if proc.returncode != 0 or not op.exists():
            tail = "\n  ".join((proc.stderr or "").strip().splitlines()[-8:])
            raise RuntimeError(f"alignment backend failed:\n  {tail}")
        res = json.loads(op.read_text(encoding="utf-8"))
        if res.get("device"):
            info(f"model backend ran on {res['device']}{' (' + res['gpu'] + ')' if res.get('gpu') else ''}")
        return res


def write_16k(src: Path, dest: Path) -> np.ndarray:
    import soundfile as sf

    y = decode_audio(src, sr=SR)
    sf.write(dest, y, SR, subtype="FLOAT")
    return y


def apply_word_times(lines, per_line, act_e, act_on, rate, method):
    """Fill word start/end from backend results; refine ends with vocal activity; interpolate gaps."""
    for line, res in zip(lines, per_line):
        for w, r in zip(line["words"], res or [None] * len(line["words"])):
            if r:
                w["start"] = r["start"]
                # a word lasts while the voice holds it: from its last emission, extend through active frames,
                # never past the next token
                end = r["emit_end"]
                i = int(end * rate)
                limit = int(r["hold_end"] * rate)
                while i < min(limit, len(act_on)) and act_on[i]:
                    i += 1
                w["end"] = max(r["emit_end"], i / rate)
                w["score"] = r.get("score")
            else:
                w.pop("start", None)
                w.pop("end", None)
                w["score"] = None
        line["method"] = method
    interpolate_missing(lines)


def interpolate_missing(lines):
    flat = [w for line in lines for w in line["words"]]
    known = [i for i, w in enumerate(flat) if w.get("start") is not None]
    if not known:
        return
    for i, w in enumerate(flat):
        if w.get("start") is not None:
            continue
        prev = max((k for k in known if k < i), default=None)
        nxt = min((k for k in known if k > i), default=None)
        if prev is not None and nxt is not None:
            a, b = flat[prev]["end"], flat[nxt]["start"]
            span = nxt - prev
            frac = (i - prev) / span
            w["start"] = a + (b - a) * frac
            w["end"] = a + (b - a) * min(1.0, frac + 1 / span)
        elif prev is not None:
            w["start"] = flat[prev]["end"] + 0.05 * (i - prev)
            w["end"] = w["start"] + 0.25
        else:
            w["end"] = flat[nxt]["start"] - 0.05 * (nxt - i - 1)
            w["start"] = w["end"] - 0.25
        w["interpolated"] = True


def method_forced(lines, audio16, language, align_model):
    job = {"method": "forced", "audio": str(audio16), "language": language, "align_model": align_model,
           "lines": [{"words": [w["norm"] for w in line["words"]]} for line in lines]}
    return ml_job(job)["lines"]


def method_mms(lines, audio16):
    job = {"method": "forced", "audio": str(audio16), "lines": [{"words": [w["norm"] for w in line["words"]]} for line in lines]}
    return ml_job(job, "_align_mms.py")["lines"]


def method_anchored(lines, audio16, language, align_model, whisper, duration):
    tr = ml_job({"method": "transcribe", "audio": str(audio16), "language": language, "whisper_model": whisper})
    tw = []  # transcript words with approximate times
    for seg in tr["segments"]:
        ws = [normalise_word(x, language) for x in seg["text"].split()]
        ws = [x for x in ws if x]
        for k, x in enumerate(ws):
            t = seg["start"] + (seg["end"] - seg["start"]) * (k + 0.5) / max(1, len(ws))
            tw.append((x, t))
    lyr = [(li, w["norm"]) for li, line in enumerate(lines) for w in line["words"]]
    sm = SequenceMatcher(a=[x for _, x in lyr], b=[x for x, _ in tw], autojunk=False)
    times: dict[int, list[float]] = {}
    for blk in sm.get_matching_blocks():
        for k in range(blk.size):
            li = lyr[blk.a + k][0]
            times.setdefault(li, []).append(tw[blk.b + k][1])
    windows = []
    for li in range(len(lines)):
        if li in times:
            windows.append([min(times[li]) - 1.5, max(times[li]) + 1.5])
        else:
            windows.append(None)
    # unmatched lines: between neighbours
    for li, wnd in enumerate(windows):
        if wnd is None:
            prev = next((windows[k] for k in range(li - 1, -1, -1) if windows[k]), None)
            nxt = next((windows[k] for k in range(li + 1, len(windows)) if windows[k]), None)
            windows[li] = [prev[1] - 1.0 if prev else 0.0, nxt[0] + 1.0 if nxt else duration]
    job = {"method": "windows", "audio": str(audio16), "language": language, "align_model": align_model,
           "lines": [{"words": [w["norm"] for w in line["words"]], "window": [max(0.0, a), min(duration, b)]}
                     for line, (a, b) in zip(lines, windows)]}
    return ml_job(job)["lines"], len(times) / max(1, len(lines))


def method_stable_ts(lines, audio16, language, whisper):
    with tempfile.TemporaryDirectory() as td:
        jp, op = Path(td) / "job.json", Path(td) / "out.json"
        text = "\n".join(" ".join(w["norm"] for w in line["words"]) for line in lines)
        jp.write_text(json.dumps({"audio": str(audio16), "text": text, "language": language, "model": whisper}), encoding="utf-8")
        info("stable-ts backend (first run installs it) …")
        proc = uv_run("_align_stable.py", str(jp), str(op))
        if proc.returncode != 0 or not op.exists():
            raise RuntimeError("stable-ts failed: " + " ".join((proc.stderr or "").strip().splitlines()[-4:]))
        words = json.loads(op.read_text(encoding="utf-8"))["words"]
    lyr = [w["norm"] for line in lines for w in line["words"]]
    got = [normalise_word(w["word"], language) for w in words]
    sm = SequenceMatcher(a=lyr, b=got, autojunk=False)
    mapping = {}
    for blk in sm.get_matching_blocks():
        for k in range(blk.size):
            mapping[blk.a + k] = words[blk.b + k]
    out, k = [], 0
    for line in lines:
        res = []
        for _ in line["words"]:
            w = mapping.get(k)
            res.append({"start": w["start"], "emit_end": w["end"], "hold_end": w["end"], "score": w.get("probability")} if w else None)
            k += 1
        out.append(res)
    return out


def active_regions(act_on, rate, min_gap=0.35, min_len=0.12):
    regions, i, n = [], 0, len(act_on)
    while i < n:
        if act_on[i]:
            j = i
            while j < n and act_on[j]:
                j += 1
            regions.append([i / rate, j / rate])
            i = j
        else:
            i += 1
    merged = []
    for r in regions:
        if merged and r[0] - merged[-1][1] < min_gap:
            merged[-1][1] = r[1]
        else:
            merged.append(r)
    return [r for r in merged if r[1] - r[0] >= min_len]


def spread_words(line, t0, t1):
    s = sum(w["syl"] for w in line["words"])
    acc = 0.0
    for w in line["words"]:
        w["start"] = t0 + (t1 - t0) * acc / s
        acc += w["syl"]
        w["end"] = t0 + (t1 - t0) * acc / s
        w["score"] = None


def method_heuristic(lines, act_on, rate, duration):
    """Line-level timing from vocal activity alone. Lines are separated by the largest pauses in the vocal;
    words are spread by syllables inside each line. Low confidence: never animate word by word on it."""
    regions = active_regions(act_on, rate)
    L = len(lines)
    syl = [sum(w["syl"] for w in line["words"]) for line in lines]
    if len(regions) >= L and L > 0:
        gaps = sorted(range(len(regions) - 1), key=lambda k: regions[k + 1][0] - regions[k][1], reverse=True)[: L - 1]
        cuts = sorted(gaps)
        groups, start = [], 0
        for c in cuts:
            groups.append(regions[start:c + 1])
            start = c + 1
        groups.append(regions[start:])
        for line, grp in zip(lines, groups):
            spread_words(line, grp[0][0], grp[-1][1])
            line["method"] = "heuristic"
        return
    # fewer pauses than lines: share the active time in proportion to syllables
    on = act_on.astype(float)
    if on.sum() < rate:
        on = np.ones_like(on)
    cum = np.cumsum(on) / on.sum()
    total, pos = sum(syl), 0.0
    for line, sy in zip(lines, syl):
        a_, b_ = pos, pos + sy / total
        ia = int(np.searchsorted(cum, a_ + 1e-9))
        ib = int(np.searchsorted(cum, b_ - 1e-9))
        spread_words(line, ia / rate, max(ia + 1, ib) / rate)
        line["method"] = "heuristic"
        pos = b_


# ---------------------------------------------------------------- import


def parse_ts(s: str) -> float:
    s = s.strip().replace(",", ".")
    parts = s.split(":")
    t = 0.0
    for p in parts:
        t = t * 60 + float(p)
    return t


def import_timing(lines, path: Path):
    text = path.read_text(encoding="utf-8", errors="ignore")
    starts: list[float] = []
    word_times: list[list[float]] = []
    if path.suffix.lower() == ".lrc":
        for raw in text.splitlines():
            m = re.match(r"\[(\d+:\d+(?:\.\d+)?)\](.*)", raw.strip())
            if not m or re.match(r"\[(ar|ti|al|by|offset|length|re|ve):", raw):
                continue
            starts.append(parse_ts(m.group(1)))
            word_times.append([parse_ts(x) for x in re.findall(r"<(\d+:\d+(?:\.\d+)?)>", m.group(2))])
    elif path.suffix.lower() in (".srt", ".vtt"):
        for m in re.finditer(r"(\d+:\d+:\d+[.,]\d+)\s*-->\s*(\d+:\d+:\d+[.,]\d+)", text):
            starts.append(parse_ts(m.group(1)))
            word_times.append([])
    else:  # tap file: one time per line, optional "# comments"
        for raw in text.splitlines():
            raw = raw.split("#")[0].strip()
            if raw:
                starts.append(parse_ts(raw.split()[0]))
                word_times.append([])
    if len(starts) < len(lines):
        info(f"warning: {len(starts)} timed lines for {len(lines)} lyric lines; the rest are interpolated")
    for i, line in enumerate(lines):
        if i >= len(starts):
            break
        t0 = starts[i]
        t1 = starts[i + 1] - 0.05 if i + 1 < len(starts) else t0 + 3.0
        wt = word_times[i]
        n = len(line["words"])
        syl = [w["syl"] for w in line["words"]]
        acc = 0
        for k, w in enumerate(line["words"]):
            if len(wt) == n:
                w["start"] = wt[k]
                w["end"] = wt[k + 1] if k + 1 < n else min(t1, wt[k] + 0.6)
            else:
                w["start"] = t0 + (t1 - t0) * acc / sum(syl)
                acc += syl[k]
                w["end"] = t0 + (t1 - t0) * acc / sum(syl)
            w["score"] = None
        line["method"] = "imported" if len(wt) == n else "imported-line"
    interpolate_missing(lines)


# ---------------------------------------------------------------- QA


def qa(lines, act_on, rate) -> dict:
    flags = []
    prev_end = 0.0
    for line in lines:
        ws = line["words"]
        t0, t1 = ws[0]["start"], ws[-1]["end"]
        line["start"], line["end"] = round(t0, 3), round(t1, 3)
        dur = max(t1 - t0, 1e-3)
        syl = sum(w["syl"] for w in ws)
        rate_syl = syl / dur
        problems = []
        if rate_syl > 8:
            problems.append(f"fast: {rate_syl:.1f} syllables/s")
        if dur > 2.5 and rate_syl < 0.4:
            problems.append(f"slow: {rate_syl:.2f} syllables/s over {dur:.1f} s")
        if t0 < prev_end - 0.05:
            problems.append(f"overlaps the previous line by {prev_end - t0:.2f} s")
        scores = [w["score"] for w in ws if w.get("score") is not None]
        if scores and min(scores) < 0.05:
            problems.append(f"low alignment score ({min(scores):.2f})")
        i = int(t0 * rate)
        if 0 <= i < len(act_on) and not act_on[max(0, i - 5): i + 15].any():
            problems.append("starts where the vocal is silent")
        if any(w.get("interpolated") for w in ws):
            problems.append("some words interpolated")
        if problems:
            flags.append({"line": line["id"], "time": fmt_time(t0), "text": line["text"], "problems": problems})
        prev_end = t1
    return {"flagged": len(flags), "lines": len(lines), "flags": flags}


# ---------------------------------------------------------------- exports


def ass_time(t: float) -> str:
    t = max(0.0, t)
    h = int(t // 3600)
    m = int(t % 3600 // 60)
    s = t % 60
    return f"{h}:{m:02d}:{s:05.2f}"


def srt_time(t: float) -> str:
    t = max(0.0, t)
    ms = int(round(t * 1000))
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def lrc_time(t: float) -> str:
    t = max(0.0, t)
    m = int(t // 60)
    return f"{m:02d}:{t - 60 * m:05.2f}"


def display_words(line):
    """Words as displayed (numbers that expanded to several aligned words show once, on the first)."""
    out = []
    for w in line["words"]:
        if w["text"]:
            out.append(w)
        elif out:
            out[-1] = {**out[-1], "end": w["end"]}
    return out


def export_all(project: Path, data: dict, which: set[str]):
    ld = project / "lyrics"
    lines = data["lines"]
    written = []
    if "hyperframes" in which:
        words = []
        for line in lines:
            for w in display_words(line):
                words.append({"id": f"w{len(words)}", "text": w["text"], "start": round(w["start"], 3),
                              "end": round(w["end"], 3), "line": line["id"]})
        save_json(ld / "words.hyperframes.json", words)
        written.append("words.hyperframes.json")
    if "remotion" in which:
        caps = []
        for line in lines:
            for k, w in enumerate(display_words(line)):
                caps.append({"text": (" " if k else "") + w["text"], "startMs": int(round(w["start"] * 1000)),
                             "endMs": int(round(w["end"] * 1000)), "timestampMs": int(round((w["start"] + w["end"]) / 2 * 1000)),
                             "confidence": w.get("score")})
        save_json(ld / "captions.remotion.json", caps)
        written.append("captions.remotion.json")
    if "srt" in which:
        out = []
        for i, line in enumerate(lines, 1):
            out += [str(i), f"{srt_time(line['start'])} --> {srt_time(line['end'] + 0.3)}", line["text"], ""]
        (ld / "lyrics.srt").write_text("\n".join(out), encoding="utf-8")
        written.append("lyrics.srt")
    if "lrc" in which:
        out = [f"[ti:{data.get('title', '')}]", "[by:tempovision]"]
        for line in lines:
            parts = " ".join(f"<{lrc_time(w['start'])}>{w['text']}" for w in display_words(line))
            out.append(f"[{lrc_time(line['start'])}]{parts} <{lrc_time(line['end'])}>")
        (ld / "lyrics.lrc").write_text("\n".join(out) + "\n", encoding="utf-8")
        written.append("lyrics.lrc")
    if "ass" in which:
        (ld / "lyrics.ass").write_text(ass_document(lines, 1280, 720), encoding="utf-8")
        written.append("lyrics.ass")
    return written


def ass_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace("{", "(").replace("}", ")")


def ass_document(lines, w, h, title="") -> str:
    fs = int(h * 0.075)
    head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {w}
PlayResY: {h}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Kara,DejaVu Sans,{fs},&H0000D7FF,&H00FFFFFF,&H00000000,&H64000000,-1,0,0,0,100,100,0,0,1,3,0,5,60,60,40,1
Style: Next,DejaVu Sans,{int(fs * 0.6)},&H00808080,&H00808080,&H00000000,&H64000000,0,0,0,0,100,100,0,0,1,2,0,8,60,60,{int(h * 0.62)},1
Style: Info,DejaVu Sans Mono,{int(h * 0.03)},&H00A0A0A0,&H00A0A0A0,&H00000000,&H64000000,0,0,0,0,100,100,0,0,1,1,0,7,30,30,24,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    ev = []
    for i, line in enumerate(lines):
        start = line["start"] - 0.25
        end = lines[i + 1]["start"] - 0.25 if i + 1 < len(lines) else line["end"] + 1.0
        end = max(end, line["end"] + 0.1)
        parts = []
        cursor = start
        for wd in display_words(line):
            lead = max(0, int(round((wd["start"] - cursor) * 100)))
            if lead:
                parts.append(f"{{\\k{lead}}}")
            dur = max(1, int(round((wd["end"] - wd["start"]) * 100)))
            parts.append(f"{{\\kf{dur}}}{ass_escape(wd['text'])} ")
            cursor = wd["end"]
        ev.append(f"Dialogue: 0,{ass_time(start)},{ass_time(end)},Kara,,0,0,0,,{''.join(parts).strip()}")
        if i + 1 < len(lines):
            ev.append(f"Dialogue: 0,{ass_time(start)},{ass_time(end)},Next,,0,0,0,,{ass_escape(lines[i + 1]['text'])}")
        tag = f"line {line['id']} · {line.get('section') or ''} · {line.get('method', '')}"
        ev.append(f"Dialogue: 0,{ass_time(start)},{ass_time(end)},Info,,0,0,0,,{ass_escape(tag)}")
    return head + "\n".join(ev) + "\n"


def render_preview(project: Path, data: dict, song: Path, fps: int = 30):
    ld = project / "lyrics"
    ass = ld / "_preview.ass"
    ass.write_text(ass_document(data["lines"], 1280, 720), encoding="utf-8")
    out = ld / "preview.mp4"
    dur = data["duration"]
    vf = (f"ass={ass.name},"
          f"drawbox=x=0:y=ih-8:w=iw*t/{dur:.3f}:h=8:color=0xFFD700@0.9:t=fill,"
          f"drawtext=text='%{{pts\\:hms}}':x=w-tw-24:y=24:fontsize=22:fontcolor=0xA0A0A0")
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", f"color=c=0x101010:s=1280x720:r={fps}:d={dur:.3f}",
           "-i", str(song), "-vf", vf, "-map", "0:v", "-map", "1:a", "-c:v", "libx264", "-preset", "veryfast",
           "-crf", "23", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart",
           out.name]
    proc = subprocess.run(cmd, cwd=ld, capture_output=True, text=True)
    if proc.returncode != 0:
        # drawtext needs a font; retry without it
        vf2 = vf.rsplit(",drawtext", 1)[0]
        cmd[cmd.index(vf)] = vf2
        proc = subprocess.run(cmd, cwd=ld, capture_output=True, text=True)
        if proc.returncode != 0:
            raise Fail("preview render failed: " + proc.stderr.strip()[-400:])
    ass.unlink(missing_ok=True)
    return out


def inspect_line(project: Path, data: dict, n: int, audio: Path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    line = next((l for l in data["lines"] if l["id"] == n), None)
    if not line:
        raise Fail(f"no line {n}")
    a, b = max(0.0, line["start"] - 1.5), line["end"] + 1.5
    y = decode_audio(audio, sr=SR, start=a, duration=b - a)
    e, on, rate = activity(y)
    t = a + np.arange(len(e)) / rate
    fig, ax = plt.subplots(figsize=(16, 3.5))
    ax.plot(a + np.arange(len(y)) / SR, y / (np.abs(y).max() + 1e-9) * 20 - 40, color="#bbbbbb", linewidth=0.3)
    ax.plot(t, e, color="#C2185B", linewidth=1)
    ax.fill_between(t, -80, e, where=on, color="#C2185B", alpha=0.15)
    for w in line["words"]:
        ax.axvspan(w["start"], w["end"], color="#1565C0", alpha=0.15)
        ax.axvline(w["start"], color="#1565C0", linewidth=1)
        ax.text(w["start"], 2, w["text"] or w["norm"], fontsize=10, color="#0D47A1", va="bottom")
    ax.set_xlim(a, b)
    ax.set_ylim(-80, 10)
    ax.set_title(f"line {n} · {line['text']} · method {line.get('method')}")
    ax.set_xlabel("seconds")
    out = project / "lyrics" / f"inspect-{n}.png"
    fig.tight_layout()
    fig.savefig(out, dpi=90)
    plt.close(fig)
    return out


TAP_HTML = (PLUGIN_ROOT / "templates" / "tap.html")


# ---------------------------------------------------------------- main


def finish(project, state, lines, act_on, rate, duration, method, language, offset=0.0):
    for line in lines:
        for w in line["words"]:
            w["start"] = round(max(0.0, w["start"] + offset), 3)
            w["end"] = round(max(w["start"] + 0.02, w["end"] + offset), 3)
    report = qa(lines, act_on, rate)
    data = {
        "schema": 1, "title": state.get("title"), "created": now_iso(), "method": method, "language": language,
        "duration": round(duration, 3), "fps": state.get("fps", 30),
        "word_level": method not in ("heuristic", "imported-line"),
        "lines": lines, "qa": report,
    }
    save_json(project / "lyrics" / "timing.json", data)
    return data


def main(argv=None):
    p = argparse.ArgumentParser(prog="tempovision align", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--method", default="auto", choices=["auto", "forced", "mms", "anchored", "stable-ts", "heuristic"])
    p.add_argument("--import", dest="import_file")
    p.add_argument("--taps", action="store_true")
    p.add_argument("--preview", action="store_true")
    p.add_argument("--inspect", type=int)
    p.add_argument("--range")
    p.add_argument("--nudge", action="append", default=[])
    p.add_argument("--export", default=None, help="formats to write (default: all)")
    p.add_argument("--install", action="store_true")
    p.add_argument("--language")
    p.add_argument("--align-model")
    p.add_argument("--whisper", default="small")
    p.add_argument("--audio", default="auto", choices=["auto", "vocals", "mix"])
    p.add_argument("--offset", type=float, default=0.0, help="shift every time by this many seconds")
    a = p.parse_args(argv)
    export_only = a.export is not None and a.method == "auto" and not any([a.import_file, a.range, a.taps])
    a.export = a.export or "srt,lrc,ass,hyperframes,remotion"

    project = find_project()
    state = load_state(project)
    language = a.language or state.get("language") or "en"
    timing_path = project / "lyrics" / "timing.json"

    if a.install:
        with tempfile.TemporaryDirectory():
            try:
                if a.method == "mms":
                    res = ml_job({"method": "check"}, "_align_mms.py")
                else:
                    res = ml_job({"method": "check", "language": language, "align_model": a.align_model})
            except RuntimeError as e:
                raise Fail(str(e))
        set_marker("align-mms" if a.method == "mms" else f"align-{language}")
        print(f"alignment backend ready: {res}")
        return

    if a.preview or a.inspect or a.nudge or export_only:
        if not timing_path.exists():
            raise Fail("no lyrics/timing.json yet; run `tempovision align` first")
        data = load_json(timing_path)
        if a.nudge:
            for spec in a.nudge:
                target, _, delta = spec.partition(":")
                d = float(delta)
                for line in data["lines"]:
                    if target == "all" or str(line["id"]) == target:
                        for w in line["words"]:
                            w["start"] = round(w["start"] + d, 3)
                            w["end"] = round(w["end"] + d, 3)
                        line["nudged"] = round(line.get("nudged", 0) + d, 3)
            e, on, rate = activity(decode_audio(vocal_source(project, state, a.audio), sr=SR))
            data["qa"] = qa(data["lines"], on, rate)
            save_json(timing_path, data)
            info(f"nudged; {data['qa']['flagged']} lines flagged")
        written = export_all(project, data, set(x.strip() for x in a.export.split(",") if x.strip()))
        if a.inspect:
            print(inspect_line(project, data, a.inspect, vocal_source(project, state, a.audio)))
        if a.preview:
            print(render_preview(project, data, song_path(project, state), int(state.get("fps", 30))))
        if not a.preview and not a.inspect:
            print("exported: " + ", ".join(written))
        return

    lp = lyrics_path(project, state)
    if not lp or not lp.exists():
        raise Fail("no lyrics in this project: `tempovision project import <lyrics.txt> --as lyrics`")
    lines = parse_lyrics(lp.read_text(encoding="utf-8"), language)
    if not lines:
        raise Fail("the lyrics file has no lines")

    if a.taps:
        html = TAP_HTML.read_text(encoding="utf-8").replace("__LINES__", json.dumps([l["text"] for l in lines]))
        out = project / "lyrics" / "tap.html"
        out.write_text(html, encoding="utf-8")
        print(out)
        info("Send this file to the artist: open it in a browser, load the song, press space at the start of each "
             "line. It downloads taps.txt; then `tempovision project import taps.txt --as refs` and "
             "`tempovision align --import input/refs/taps.txt`.")
        return

    src = vocal_source(project, state, a.audio)
    with tempfile.TemporaryDirectory() as td:
        audio16 = Path(td) / "vocal16k.wav"
        y = write_16k(src, audio16)
        duration = len(y) / SR
        act_e, act_on, rate = activity(y)

        if a.range:
            if not timing_path.exists():
                raise Fail("--range needs an existing alignment")
            r0, r1 = parse_range(a.range)
            data = load_json(timing_path)
            old = data["lines"]
            idx = [i for i, l in enumerate(old) if r0 <= l["start"] <= r1]
            if not idx:
                raise Fail("no lines start in that range")
            subset = [old[i] for i in idx]
            job = {"method": "windows", "audio": str(audio16), "language": language, "align_model": a.align_model,
                   "lines": [{"words": [w["norm"] for w in l["words"]],
                              "window": [max(0.0, (old[i - 1]["end"] if i > 0 else 0.0) - 0.3),
                                         min(duration, (old[i + 1]["start"] if i + 1 < len(old) else duration) + 0.3)]}
                             for i, l in zip(idx, subset)]}
            mms = str(data.get("method", "")).startswith("mms")
            if mms:
                for ln in job["lines"]:
                    ln.pop("language", None)
            try:
                res = ml_job(job, "_align_mms.py" if mms else "_align_ml.py")["lines"]
            except RuntimeError as e:
                raise Fail(str(e))
            apply_word_times(subset, res, act_e, act_on, rate, "mms-range" if mms else "forced-range")
            data = finish(project, state, old, act_on, rate, duration, data["method"], language)
            print(f"re-aligned {len(idx)} lines; {data['qa']['flagged']} flagged")
            export_all(project, data, set(x.strip() for x in a.export.split(",") if x.strip()))
            return

        if a.import_file:
            import_timing(lines, Path(a.import_file))
            method = lines[0].get("method", "imported")
        else:
            order = ["forced", "mms", "anchored", "stable-ts", "heuristic"] if a.method == "auto" else [a.method]
            method, errors = None, []
            for m in order:
                try:
                    if m == "forced":
                        apply_word_times(lines, method_forced(lines, audio16, language, a.align_model), act_e, act_on, rate, m)
                    elif m == "mms":
                        apply_word_times(lines, method_mms(lines, audio16), act_e, act_on, rate, m)
                    elif m == "anchored":
                        res, coverage = method_anchored(lines, audio16, language, a.align_model, a.whisper, duration)
                        if coverage < 0.5:
                            raise RuntimeError(f"transcript matched only {coverage:.0%} of the lines")
                        apply_word_times(lines, res, act_e, act_on, rate, m)
                    elif m == "stable-ts":
                        apply_word_times(lines, method_stable_ts(lines, audio16, language, a.whisper), act_e, act_on, rate, m)
                    else:
                        method_heuristic(lines, act_on, rate, duration)
                    report = qa(lines, act_on, rate)
                    if a.method == "auto" and m != "heuristic" and report["flagged"] > max(2, 0.25 * len(lines)):
                        errors.append(f"{m}: {report['flagged']}/{len(lines)} lines flagged")
                        info(f"{m}: too many flagged lines ({report['flagged']}/{len(lines)}); trying the next method")
                        continue
                    method = m
                    if m in ("forced", "anchored"):
                        set_marker(f"align-{language}")
                    elif m == "mms":
                        set_marker("align-mms")
                    break
                except (RuntimeError, ValueError) as e:
                    errors.append(f"{m}: {e}")
                    info(f"{m} unavailable: {str(e).splitlines()[0]}")
            if method is None:
                raise Fail("no method succeeded:\n  " + "\n  ".join(errors))
            if errors:
                info("earlier methods: " + "; ".join(errors))
        data = finish(project, state, lines, act_on, rate, duration, method, language, a.offset)

    state = load_state(project)
    state["language"] = language
    save_state(project, state)
    written = export_all(project, data, set(x.strip() for x in a.export.split(",") if x.strip()))
    q = data["qa"]
    print(f"method: {method} · {len(lines)} lines · {sum(len(l['words']) for l in lines)} words · "
          f"{q['flagged']} lines flagged · exports: {', '.join(written)}")
    for f in q["flags"][:12]:
        print(f"  line {f['line']} at {f['time']}: {'; '.join(f['problems'])} — {f['text'][:60]}")
    if method in ("heuristic", "imported-line"):
        print("  note: timing is line-level only; do not animate word by word on it.")


if __name__ == "__main__":
    main()
