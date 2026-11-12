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
  tempovision deliver RENDER --targets vertical --vertical V.mp4 --vertical-range 70.8
                                                               the 9:16 cut plays the song from 70.8 s
  tempovision deliver RENDER --master audio/new_mix.aligned.wav  a new mix (check it first: `tempovision master`)

Where each render sits in the song: --range / --vertical-range / --square-range when given; otherwise found by
matching the render's own audio track against the master. A render without audio and without a range is refused:
its place in the song can't be guessed (an excerpt silently given the song's opening is the worst failure).

Each file is probed after writing: duration within one frame of the picture, and the delivered audio measured
against the render's own audio track (the picture's timeline) to within half a frame. A render without audio
can't be measured that way; the file says so instead of claiming sync. Writes renders/final/DELIVERY.json.
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import (DATA_DIR, Fail, find_project, fmt_time, info, load_json, load_state, media_summary,  # noqa: E402
                     now_iso, parse_range, parse_time, save_json, slug, song_path)

# bytes per pixel per frame, generous, for the free-space check before writing
BYTES_PER_PX_FRAME = {"prores_ks": 0.45, "libx264": 0.04}


def range_start(s: str | None) -> float | None:
    """'70.8' or '70.8-101.8' -> 70.8 (the song time where the render's first frame plays)."""
    if not s:
        return None
    return parse_range(s)[0] if ("-" in s.strip("-") or "," in s) else parse_time(s)


def place_in_song(kind: str, src: Path, master: Path, explicit: float | None, fps: float) -> tuple[float, str]:
    """Song time of the render's first frame, and how it was found. Raises when it can't be known."""
    from master import Z_MATCH, locate

    has_audio = bool(media_summary(src).get("audio"))
    found = None
    if has_audio:
        t, z = locate(src, master)
        if z >= Z_MATCH:
            found = 0.0 if abs(t) < 0.5 / fps else round(t, 3)
    if explicit is not None:
        if found is not None and abs(found - explicit) > 1.0 / fps:
            raise Fail(f"the {kind} render's own audio sits at {found:.3f} s of the master, but the range given says "
                       f"{explicit:.3f} s: fix the range (or the render)")
        return explicit, "given"
    if found is not None:
        return found, "matched"
    if kind == "main":
        if has_audio:
            info("⚠️ main render: its audio doesn't clearly match the master; assuming it starts at 0.0 s")
        return 0.0, "assumed"
    raise Fail(f"the {kind} render has no audio track, so its place in the song can't be measured: pass "
               f"--{kind}-range START (the song time of its first frame, e.g. --{kind}-range 70.8)")


def check_free_space(out_dir: Path, plan: list):
    """Refuse before writing when the planned files can't fit (a full disk mid-ProRes leaves a broken master)."""
    need = 0.0
    for _, p, meta in plan:
        v = meta.get("video") or {}
        rate = BYTES_PER_PX_FRAME.get((p.get("video") or {}).get("codec"), 0.05)
        w, h = p.get("size") or (v.get("width") or 1920, v.get("height") or 1080)
        need += rate * w * h * (v.get("fps") or 30) * (v.get("duration") or meta.get("duration") or 0)
    free = shutil.disk_usage(out_dir).free
    if need > free * 0.95:
        names = ", ".join(t for t, _, _ in plan)
        raise Fail(f"not enough disk space for {names}: about {need / 1e9:.1f} GB needed, {free / 1e9:.1f} GB free on "
                   f"{out_dir}. Free space, write elsewhere with --out, or drop the ProRes master from --targets.")


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
    ap.add_argument("--vertical-range", help="song time where the 9:16 render starts: START or START-END")
    ap.add_argument("--square", help="the 1:1 render")
    ap.add_argument("--square-range", help="song time where the 1:1 render starts: START or START-END")
    ap.add_argument("--canvas", help="START-END of the Canvas loop, in the vertical render's time")
    ap.add_argument("--thumb-at", type=float, default=None)
    ap.add_argument("--range")
    ap.add_argument("--fade-out", type=float, default=0.0, help="audio fade at the end (excerpts only), seconds")
    ap.add_argument("--out")
    ap.add_argument("--master")
    ap.add_argument("--allow-master-offset", action="store_true",
                    help="deliver with a --master that measures off the project's song (not recommended)")
    a = ap.parse_args(argv)

    project = find_project(required=False)
    state = load_state(project) if project else {}
    master = Path(a.master) if a.master else (song_path(project, state) if project else None)
    if not master:
        raise Fail("outside a project, pass --master SONG")
    render = Path(a.render).expanduser()
    if not render.exists():
        raise Fail(f"no such render: {render}")
    if a.master and project and not a.allow_master_offset:
        # a new mix or master: the film was timed to the project's song, so it must line up with it
        from master import offset_between, verdict

        song = song_path(project, state)
        if song.resolve() != master.resolve():
            r = offset_between(master, song)
            if not r["same_song"] or r["drift"] or abs(r["offset_ms"]) > 2.0:
                raise Fail(f"--master {master.name}: {verdict(r)}. Deliver with the aligned file "
                           f"(`tempovision master align {master}`), or pass --allow-master-offset.")
            info(f"--master {master.name}: lines up with the project's song ({r['offset_ms']:+.1f} ms)")
    presets = load_json(DATA_DIR / "platforms.json")["targets"]
    targets = [t.strip() for t in a.targets.split(",")] if a.targets else (brief_targets(project) if project else None) \
        or ["master", "youtube", "thumbnail", "poster"]
    unknown = [t for t in targets if t not in presets]
    if unknown:
        raise Fail(f"unknown targets: {', '.join(unknown)}; known: {', '.join(presets)}")
    out_dir = Path(a.out) if a.out else ((project / "renders" / "final") if project else render.parent)
    out_dir.mkdir(parents=True, exist_ok=True)
    name = slug(state.get("title") or render.stem)
    sources = {"main": render, "vertical": Path(a.vertical) if a.vertical else None, "square": Path(a.square) if a.square else None}
    explicit = {"main": range_start(a.range), "vertical": range_start(a.vertical_range), "square": range_start(a.square_range)}
    for k, src in sources.items():
        if src is not None and not src.exists():
            raise Fail(f"no such {k} render: {src}")

    from master import offset_between

    plan = []
    for t in targets:
        p = presets[t]
        src = sources.get(p.get("source", "main"))
        if src is None:
            info(f"skip {t}: needs --{p['source']} (a render designed for {p['label']}; Tempovision never centre-crops by default)")
            continue
        plan.append((t, p, media_summary(src)))
    check_free_space(out_dir, [x for x in plan if x[0] not in ("thumbnail", "poster")])
    starts: dict = {}
    for t, p, meta in plan:
        kind = p.get("source", "main")
        if p.get("audio") and kind not in starts:
            starts[kind] = place_in_song(kind, sources[kind], master, explicit[kind], (meta.get("video") or {}).get("fps") or 30)
            info(f"{kind} render plays the song from {starts[kind][0]:.3f} s ({starts[kind][1]})")

    manifest = {"schema": 2, "at": now_iso(), "master_audio": str(master), "render": str(render), "files": []}
    for t, p, meta in plan:
        src = sources.get(p.get("source", "main"))
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
        start, how = starts.get(p.get("source", "main"), (0.0, "none"))
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
        af = []
        if p.get("audio") and start > 0:
            af.append("afade=t=in:d=0.015")  # an excerpt starts mid-waveform: no click
        if p.get("audio") and a.fade_out > 0:
            af.append(f"afade=t=out:st={max(0.0, vdur - a.fade_out):.3f}:d={a.fade_out:.3f}")
        if af:
            cmd += ["-af", ",".join(af)]
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
            entry["song_start"] = start
            entry["song_start_from"] = how
            if meta.get("audio"):
                # the delivered sound against the render's own track: the picture's timeline, whatever the master
                r = offset_between(dest, src, windows=2, win_s=min(20.0, vdur / 2.5))
                lag = r["offset_ms"] / 1000.0
                entry["av_offset_s"] = round(lag, 4)
                entry["sync_ok"] = bool(r["same_song"]) and abs(lag) <= 0.5 / fps
                entry["sync_checked_against"] = "render audio"
                sync = f" · audio offset {lag * 1000:+.0f} ms" + ("" if r["same_song"] else " (no clear match!)")
            else:
                entry["sync_ok"] = None
                entry["sync_checked_against"] = None
                sync = f" · song {start:.3f} s on ({how}); the render has no audio, so sync is unmeasured"
        ok = dur_ok and entry.get("sync_ok") is not False
        manifest["files"].append({**entry, "ok": ok})
        print(f"{'✅' if ok else '❌'} {t}: {dest.name} · {dm['video']['width']}x{dm['video']['height']} · "
              f"{fmt_time(dm['video']['duration'])}{sync} · {dest.stat().st_size / 1e6:.1f} MB")
    save_json(out_dir / "DELIVERY.json", manifest)
    print(out_dir / "DELIVERY.json")
    if any(not f.get("ok", True) for f in manifest["files"]):
        sys.exit(1)


if __name__ == "__main__":
    main()
