#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["pillow>=10"]
# ///
"""Contact sheets from a render: how you see motion as stills.

  tempovision sheet VIDEO                         a frame every 2 s
  tempovision sheet VIDEO --every 0.5
  tempovision sheet VIDEO --times 12.0,12.5,13.0
  tempovision sheet VIDEO --range 72.0,74.0 --frames 8      the hero move, frame by frame
  tempovision sheet VIDEO --section chorus-1 --offset 24.0  a section draft: its first frame, line arrivals, hits, last frame
  tempovision sheet VIDEO --mode review           three sheets: beats, cuts (-0.2/0/+0.2 s around each cut), phone (360 px)

Sheets go to frames/sheets/ in a project (or next to the video). Each tile is labelled with its time, frame
number and what is meant to happen there.
"""
from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (Fail, detect_cuts, extract_frame, find_project, fmt_time, info, load_json, media_summary,  # noqa: E402
                     parse_range, to_frame)

FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/Arial.ttf", "/Library/Fonts/Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/dejavu/DejaVuSans.ttf",
    "C:/Windows/Fonts/arial.ttf",
]


def font(size):
    from PIL import ImageFont

    for f in FONT_CANDIDATES:
        if Path(f).exists():
            return ImageFont.truetype(f, size)
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def build_sheet(video: Path, items: list[dict], out: Path, tile_w: int = 480, cols: int = 4, title: str = "", fps: float = 30.0):
    """items: [{t, label}] -> one PNG grid."""
    from PIL import Image, ImageDraw

    if not items:
        raise Fail("no frames to put on the sheet")
    with tempfile.TemporaryDirectory() as td:
        tiles = []
        for i, it in enumerate(items):
            p = Path(td) / f"{i:04d}.png"
            ok = extract_frame(video, it["t"], p, tile_w)
            tiles.append((it, Image.open(p).convert("RGB") if ok else None))
        h0 = next((im.height for _, im in tiles if im), int(tile_w * 9 / 16))
        label_h = 44
        cols = min(cols, len(tiles))
        rows = (len(tiles) + cols - 1) // cols
        pad = 8
        head = 40 if title else 0
        W = cols * tile_w + (cols + 1) * pad
        H = head + rows * (h0 + label_h) + (rows + 1) * pad
        sheet = Image.new("RGB", (W, H), (24, 24, 24))
        d = ImageDraw.Draw(sheet)
        f_small, f_title = font(15), font(20)
        if title:
            d.text((pad, 10), title, fill=(230, 230, 230), font=f_title)
        for k, (it, im) in enumerate(tiles):
            r, c = divmod(k, cols)
            x = pad + c * (tile_w + pad)
            y = head + pad + r * (h0 + label_h + pad)
            if im:
                sheet.paste(im, (x, y))
            else:
                d.rectangle([x, y, x + tile_w, y + h0], outline=(200, 60, 60))
                d.text((x + 10, y + 10), "no frame", fill=(200, 60, 60), font=f_small)
            line1 = f"{fmt_time(it['t'])}  f{to_frame(it['t'], fps)}"
            d.text((x, y + h0 + 4), line1, fill=(200, 200, 200), font=f_small)
            if it.get("label"):
                d.text((x, y + h0 + 22), str(it["label"])[:60], fill=(150, 150, 150), font=f_small)
        out.parent.mkdir(parents=True, exist_ok=True)
        sheet.save(out)
    return out


def project_context():
    project = find_project(required=False)
    songmap = timing = None
    if project:
        sp = project / "analysis" / "songmap.json"
        tp = project / "lyrics" / "timing.json"
        songmap = load_json(sp) if sp.exists() else None
        timing = load_json(tp) if tp.exists() else None
    return project, songmap, timing


def beat_items(songmap, timing, offset, duration):
    items = []
    if songmap:
        for s in songmap["sections"]:
            items.append({"t": s["start"], "label": f"{s.get('display', s['label'])} starts"})
        hook_norm = {h["norm"] for h in songmap.get("hooks", [])}
        for h in songmap.get("hits", []):
            if h["kind"] in ("chorus-downbeat",) and h.get("label", "").endswith("1"):
                items.append({"t": h["t"], "label": f"downbeat · {h.get('label', '')}"})
    if timing:
        import re
        seen = set()
        for l in timing["lines"]:
            k = re.sub(r"[^\w\s]", "", l["text"].lower())
            if k not in seen:
                seen.add(k)
                items.append({"t": l["start"] + 0.15, "label": f"line {l['id']}: {l['text'][:40]}"})
    items = [{**it, "t": it["t"] - offset} for it in items if 0 <= it["t"] - offset < duration]
    items.sort(key=lambda x: x["t"])
    return merge_close(items)


def merge_close(items, gap=0.25):
    out = []
    for it in sorted(items, key=lambda x: x["t"]):
        if out and abs(it["t"] - out[-1]["t"]) < gap:
            if it.get("label") and it["label"] not in out[-1].get("label", ""):
                out[-1]["label"] = " · ".join(x for x in (out[-1].get("label"), it["label"]) if x)
            continue
        out.append(dict(it))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(prog="tempovision sheet", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("video")
    ap.add_argument("--every", type=float)
    ap.add_argument("--times")
    ap.add_argument("--range")
    ap.add_argument("--frames", type=int, default=8)
    ap.add_argument("--section")
    ap.add_argument("--offset", type=float, default=0.0, help="song time at the video's first frame")
    ap.add_argument("--mode", choices=["grid", "review"], default="grid")
    ap.add_argument("--cols", type=int, default=4)
    ap.add_argument("--width", type=int, default=480)
    ap.add_argument("--out")
    a = ap.parse_args(argv)

    video = Path(a.video).expanduser()
    if not video.exists():
        raise Fail(f"no such video: {video}")
    meta = media_summary(video)
    if "video" not in meta:
        raise Fail("the file has no video stream")
    dur = meta["video"]["duration"]
    fps = meta["video"]["fps"] or 30.0
    project, songmap, timing = project_context()
    out_dir = Path(a.out).parent if a.out else ((project / "frames" / "sheets") if project else video.parent)
    stem = video.stem
    written = []

    if a.mode == "review":
        beats = beat_items(songmap, timing, a.offset, dur)
        if not beats:
            beats = [{"t": t, "label": ""} for t in [i * 2.0 for i in range(int(dur // 2) + 1)] if t < dur]
        beats.insert(0, {"t": 0.0, "label": "first frame (thumbnail)"})
        beats.append({"t": max(0.0, dur - 3 / fps), "label": "last frame"})
        beats = merge_close(beats)
        written.append(build_sheet(video, beats, out_dir / f"{stem}-beats.png", a.width, a.cols,
                                   f"{video.name} · beat frames", fps))
        cuts = detect_cuts(video)
        strip = []
        for c in cuts[:40]:
            for dt, lab in ((-0.2, "−0.2"), (0.0, f"cut {c['score']}"), (0.2, "+0.2")):
                if 0 <= c["t"] + dt < dur:
                    strip.append({"t": c["t"] + dt, "label": lab})
        if strip:
            written.append(build_sheet(video, strip, out_dir / f"{stem}-cuts.png", 360, 6, f"{video.name} · {len(cuts)} cuts", fps))
        else:
            info("no cuts detected")
        written.append(build_sheet(video, beats, out_dir / f"{stem}-phone.png", 360 if meta["video"]["width"] >= meta["video"]["height"] else 202,
                                   6, f"{video.name} · phone width", fps))
    else:
        if a.times:
            items = [{"t": float(x), "label": ""} for x in a.times.split(",")]
        elif a.range:
            r0, r1 = parse_range(a.range)
            n = max(2, a.frames)
            items = [{"t": r0 + (r1 - r0) * i / (n - 1), "label": ""} for i in range(n)]
        elif a.section:
            if not songmap:
                raise Fail("--section needs a project with analysis/songmap.json")
            sec = next((s for s in songmap["sections"] if s.get("id") == a.section or s.get("display", "").lower() == a.section.lower()), None)
            if not sec:
                raise Fail(f"no section {a.section!r}; ids: {', '.join(s.get('id', '') for s in songmap['sections'])}")
            items = [{"t": sec["start"], "label": "section start"}]
            for l in sec.get("lines", []):
                items.append({"t": l["t"] + 0.15, "label": f"line {l['id']}: {l['text'][:36]}"})
            for h in songmap.get("hits", []):
                if sec["start"] < h["t"] < sec["end"] and h["kind"] != "drum-hit":
                    items.append({"t": h["t"], "label": h["kind"]})
            items.append({"t": sec["end"] - 3 / fps, "label": "section end"})
            items = sorted(({**i, "t": i["t"] - a.offset} for i in items if 0 <= i["t"] - a.offset < dur), key=lambda x: x["t"])
            stem = f"{stem}-{a.section}"
        else:
            step = a.every or 2.0
            items = [{"t": i * step, "label": ""} for i in range(int(dur / step) + 1) if i * step < dur]
        out = Path(a.out) if a.out else out_dir / f"{stem}-sheet.png"
        written.append(build_sheet(video, items, out, a.width, a.cols, video.name, fps))
    for w in written:
        print(w)


if __name__ == "__main__":
    main()
