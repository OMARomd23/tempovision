#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy>=1.24", "scipy>=1.10"]
# ///
"""Write the deliverables: picture from the final render, sound from the artist's untouched master.

  tempovision deliver RENDER                                   targets from BRIEF.md (default: master,youtube,thumbnail,poster)
  tempovision deliver RENDER --targets master,youtube,vertical --vertical RENDER_9x16
  tempovision deliver RENDER --targets canvas --vertical RENDER_9x16 --canvas 52.0-59.5
  tempovision deliver RENDER --thumb-at 61.2                   the thumbnail frame (default: the first frame)
  tempovision deliver RENDER --range 48.2-80.5                 the render is an excerpt starting at 48.2 s of the song

Each file is probed after writing: duration within one frame of the picture, audio offset against the master
within one frame. Writes renders/final/DELIVERY.json.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (DATA_DIR, Fail, find_project, fmt_time, info, load_json, load_state, media_summary,  # noqa: E402
                     now_iso, parse_range, save_json, slug, song_path)


def brief_targets(project: Path) -> list[str] | None:
    b = project / "BRIEF.md"
    if not b.exists():
        return None
    m = re.search(r"deliverables:\s*\[([^\]]*)\]", b.read_text(encoding="utf-8"))
    return [x.strip().strip("'\"") for x in m.group(1).split(",") if x.strip()] if m else None


def vcodec_args(v: dict) -> list[str]:
    args = ["-c:v", v["codec"]]
    if v["codec"] == "prores_ks":
        args += ["-profile:v", str(v.get("profile", 3)), "-vendor", "apl0"]
    if v.get("profile") and v["codec"] == "libx264":
        args += ["-profile:v", v["profile"]]
    if v.get("crf") is not None:
        args += ["-crf", str(v["crf"])]
    if v.get("preset"):
        args += ["-preset", v["preset"]]
    if v.get("pix_fmt"):
        args += ["-pix_fmt", v["pix_fmt"]]
    args += ["-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709"]
    return args


def acodec_args(au: dict | None) -> list[str]:
    if not au:
        return ["-an"]
    args = ["-c:a", au["codec"], "-ar", str(au.get("sample_rate", 48000))]
    if au.get("bitrate"):
        args += ["-b:a", au["bitrate"]]
    return args


def run_ffmpeg(cmd: list[str]):
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise Fail("ffmpeg failed: " + proc.stderr.strip()[-600:])


def main(argv=None):
    ap = argparse.ArgumentParser(prog="tempovision deliver", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("render")
    ap.add_argument("--targets")
    ap.add_argument("--vertical", help="the 9:16 render")
    ap.add_argument("--square", help="the 1:1 render")
    ap.add_argument("--canvas", help="START-END of the Canvas loop, in the vertical render's time")
    ap.add_argument("--thumb-at", type=float, default=None)
    ap.add_argument("--range")
    ap.add_argument("--fade-out", type=float, default=0.0, help="audio fade at the end (excerpts only), seconds")
    ap.add_argument("--out")
    ap.add_argument("--master")
    a = ap.parse_args(argv)

    project = find_project(required=False)
    state = load_state(project) if project else {}
    master = Path(a.master) if a.master else (song_path(project, state) if project else None)
    if not master:
        raise Fail("outside a project, pass --master SONG")
    render = Path(a.render).expanduser()
    if not render.exists():
        raise Fail(f"no such render: {render}")
    presets = load_json(DATA_DIR / "platforms.json")["targets"]
    targets = [t.strip() for t in a.targets.split(",")] if a.targets else (brief_targets(project) if project else None) \
        or ["master", "youtube", "thumbnail", "poster"]
    unknown = [t for t in targets if t not in presets]
    if unknown:
        raise Fail(f"unknown targets: {', '.join(unknown)}; known: {', '.join(presets)}")
    out_dir = Path(a.out) if a.out else ((project / "renders" / "final") if project else render.parent)
    out_dir.mkdir(parents=True, exist_ok=True)
    name = slug(state.get("title") or render.stem)
    start, end = parse_range(a.range) if a.range else (0.0, None)
    sources = {"main": render, "vertical": Path(a.vertical) if a.vertical else None, "square": Path(a.square) if a.square else None}

    from qa import av_offset  # same cross-correlation as tempovision qa

    manifest = {"schema": 1, "at": now_iso(), "master_audio": str(master), "render": str(render), "files": []}
    for t in targets:
        p = presets[t]
        src = sources.get(p.get("source", "main"))
        if src is None:
            info(f"skip {t}: needs --{p['source']} (a render designed for {p['label']}; Tempovision never centre-crops by default)")
            continue
        meta = media_summary(src)
        vdur = meta["video"]["duration"]
        fps = meta["video"]["fps"] or 30
        if t in ("thumbnail", "poster"):
            at = 0.0 if t == "poster" else (a.thumb_at if a.thumb_at is not None else 0.0)
            ext = p["format"]
            dest = out_dir / f"{name}-{t}.{ext}"
            vf = f"scale={p['size'][0]}:{p['size'][1]}:force_original_aspect_ratio=decrease,pad={p['size'][0]}:{p['size'][1]}:(ow-iw)/2:(oh-ih)/2" if p.get("size") else "null"
            q = ["-q:v", "2"] if ext == "jpg" else []
            run_ffmpeg(["ffmpeg", "-v", "error", "-y", "-ss", f"{at:.3f}", "-i", str(src), "-frames:v", "1", "-vf", vf, *q, str(dest)])
            size = dest.stat().st_size
            ok = size <= p.get("max_bytes", 10 ** 12)
            manifest["files"].append({"target": t, "path": str(dest), "bytes": size, "at": at, "ok": ok})
            print(f"{'✅' if ok else '⚠️'} {t}: {dest.name} ({size // 1024} KB)")
            continue
        dest = out_dir / f"{name}-{t}.{p['container']}"
        cmd = ["ffmpeg", "-v", "error", "-y"]
        seg = None
        if t == "canvas":
            if not a.canvas:
                info("skip canvas: pass --canvas START-END (3-8 s)")
                continue
            c0, c1 = parse_range(a.canvas)
            if not (p["min_seconds"] <= c1 - c0 <= p["max_seconds"]):
                raise Fail(f"Canvas must be {p['min_seconds']}-{p['max_seconds']} s; got {c1 - c0:.2f} s")
            seg = (c0, c1)
            cmd += ["-ss", f"{c0:.4f}", "-t", f"{c1 - c0:.4f}"]
        cmd += ["-i", str(src)]
        if p.get("audio"):
            cmd += ["-ss", f"{start:.4f}"] if start else []
            cmd += ["-i", str(master), "-map", "0:v:0", "-map", "1:a:0", "-t", f"{vdur:.4f}"]
        else:
            cmd += ["-map", "0:v:0"]
        vf = []
        if p.get("size"):
            w, h = p["size"]
            vf.append(f"scale={w}:{h}:force_original_aspect_ratio=decrease:flags=lanczos,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2")
        if vf:
            cmd += ["-vf", ",".join(vf)]
        cmd += vcodec_args(p["video"]) + acodec_args(p.get("audio"))
        if p.get("audio") and a.fade_out > 0:
            cmd += ["-af", f"afade=t=out:st={max(0.0, vdur - a.fade_out):.3f}:d={a.fade_out:.3f}"]
        if p.get("faststart"):
            cmd += ["-movflags", "+faststart"]
        cmd += [str(dest)]
        info(f"writing {t} …")
        run_ffmpeg(cmd)
        dm = media_summary(dest)
        expect = (seg[1] - seg[0]) if seg else vdur
        dur_ok = abs(dm["video"]["duration"] - expect) <= 1.01 / fps
        entry = {"target": t, "path": str(dest), "bytes": dest.stat().st_size, "video": dm.get("video"), "audio": dm.get("audio"),
                 "duration_ok": dur_ok}
        sync = ""
        if p.get("audio"):
            lag, corr = av_offset(dest, master, start, min(vdur, 60.0))
            entry["av_offset_s"] = round(lag, 4)
            entry["sync_ok"] = abs(lag) <= 1.0 / fps and corr > 0.3
            sync = f" · audio offset {lag * 1000:+.0f} ms"
        ok = dur_ok and entry.get("sync_ok", True)
        manifest["files"].append({**entry, "ok": ok})
        print(f"{'✅' if ok else '❌'} {t}: {dest.name} · {dm['video']['width']}x{dm['video']['height']} · "
              f"{fmt_time(dm['video']['duration'])}{sync} · {dest.stat().st_size / 1e6:.1f} MB")
    save_json(out_dir / "DELIVERY.json", manifest)
    print(out_dir / "DELIVERY.json")
    if any(not f.get("ok", True) for f in manifest["files"]):
        sys.exit(1)


if __name__ == "__main__":
    main()
