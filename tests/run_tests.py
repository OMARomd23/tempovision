#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""End-to-end test of the Tempovision tools on a synthesised song with known structure (no model downloads).

  uv run tests/run_tests.py [--keep]

Synthesises a song (tests/make_song.py) with known tempo, sections, stems and word times; then runs
project → analyze → align (stand-in backend + heuristic) → songmap → timing (both engines) → a stand-in draft
render → sheet → qa (passing and failing drafts) → assets → deliver → hooks, checking results against the truth.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TEMPOVISION = str(ROOT / "bin" / "tempovision")
PASSED, FAILED = [], []


def run(cmd, cwd=None, env=None, ok=(0,)):
    if os.name == "nt" and cmd and str(cmd[0]) == TEMPOVISION and len(cmd) > 1:
        # bin/tempovision is a bash script that Windows can't exec (and `bash` may be WSL): dispatch the way it does
        cmd = ["uv", "run", "--quiet", "--script", str(ROOT / "scripts" / f"{cmd[1]}.py"), *cmd[2:]]
    p = subprocess.run(cmd, cwd=cwd, env={**os.environ, **(env or {})}, capture_output=True, text=True)
    if p.returncode not in ok:
        raise AssertionError(f"{' '.join(map(str, cmd[:4]))} exited {p.returncode}:\n{p.stdout[-1500:]}\n{p.stderr[-1500:]}")
    return p


def test(name):
    def deco(fn):
        def wrapper(*a, **k):
            try:
                fn(*a, **k)
                PASSED.append(name)
                print(f"  ✅ {name}")
            except Exception as e:  # noqa: BLE001
                FAILED.append((name, e))
                print(f"  ❌ {name}: {e}")
        return wrapper
    return deco


def main():
    keep = "--keep" in sys.argv
    work = Path(tempfile.mkdtemp(prefix="tempovision-test-"))
    os.environ["TEMPOVISION_DATA"] = str(work / "data")
    song_dir = work / "song"
    print(f"workspace: {work}")
    run(["uv", "run", "-q", str(ROOT / "tests" / "make_song.py"), str(song_dir)])
    truth = json.loads((song_dir / "truth.json").read_text())
    p = run([TEMPOVISION, "project", "init", "Paper Walls", "--song", str(song_dir / "song.wav"), "--lyrics",
             str(song_dir / "lyrics.txt"), "--dir", str(work)])
    proj = Path(p.stdout.strip().splitlines()[-1])
    for f in (song_dir / "stems").glob("*.wav"):
        shutil.copy2(f, proj / "analysis" / "stems" / f.name)

    @test("project init creates the tree, read-only originals, git repo")
    def _():
        assert (proj / "tempovision.json").exists() and (proj / "BRIEF.md").exists()
        root = hasattr(os, "geteuid") and os.geteuid() == 0  # root ignores read-only bits; Windows has no geteuid
        assert (proj / "input" / "song.wav").exists() and not os.access(proj / "input" / "song.wav", os.W_OK) or root
        assert (proj / ".git").exists()
    _()

    @test("analyze: tempo within 1 BPM, downbeats on bar lines, 6 sections A B C B C A")
    def _():
        run([TEMPOVISION, "analyze"], cwd=proj)
        a = json.loads((proj / "analysis" / "audio.json").read_text())
        assert abs(a["tempo"]["bpm"] - truth["bpm"]) < 1.0, a["tempo"]
        bar = truth["bar_seconds"]
        downs = [d for d in a["downbeats"] if 8 <= d <= 70]
        off = max(min(abs(d - round(d / bar) * bar), bar) for d in downs)
        assert off < 0.08, f"downbeat off by {off:.3f} s"
        labels = "".join(s["label"] for s in a["sections"])
        assert labels == "ABCBCA", labels
        for s, t in zip(a["sections"], truth["sections"]):
            assert abs(s["start"] - t["start"]) < 0.1, (s["start"], t["start"])
        assert (proj / "analysis" / "plots" / "overview.png").exists()
    _()

    @test("align (heuristic): line starts within 50 ms")
    def _():
        run([TEMPOVISION, "align", "--method", "heuristic"], cwd=proj)
        d = json.loads((proj / "lyrics" / "timing.json").read_text())
        errs = [abs(a["start"] - b["start"]) for a, b in zip(truth["lines"], d["lines"])]
        assert max(errs) < 0.05, max(errs)
        assert d["word_level"] is False
    _()

    @test("align (forced, stand-in backend): word starts and ends within 40 ms, exports written")
    def _():
        env = {"TEMPOVISION_ML_BACKEND": str(ROOT / "tests" / "mock_align_backend.py"), "TEMPOVISION_TRUTH": str(song_dir / "truth.json")}
        run([TEMPOVISION, "align"], cwd=proj, env=env)
        d = json.loads((proj / "lyrics" / "timing.json").read_text())
        assert d["method"] == "forced"
        tw = [w for l in truth["lines"] for w in l["words"]]
        dw = [w for l in d["lines"] for w in l["words"]]
        assert len(tw) == len(dw)
        assert max(abs(a["start"] - b["start"]) for a, b in zip(tw, dw)) < 0.04
        assert max(abs(a["end"] - b["end"]) for a, b in zip(tw, dw)) < 0.04
        for f in ("words.hyperframes.json", "captions.remotion.json", "lyrics.srt", "lyrics.lrc", "lyrics.ass"):
            assert (proj / "lyrics" / f).exists(), f
    _()

    @test("align --nudge shifts one line; --preview renders the karaoke check")
    def _():
        before = json.loads((proj / "lyrics" / "timing.json").read_text())["lines"][2]["start"]
        run([TEMPOVISION, "align", "--nudge", "3:+0.1"], cwd=proj)
        after = json.loads((proj / "lyrics" / "timing.json").read_text())["lines"][2]["start"]
        assert abs(after - before - 0.1) < 1e-6
        run([TEMPOVISION, "align", "--nudge", "3:-0.1"], cwd=proj)
        run([TEMPOVISION, "align", "--preview"], cwd=proj)
        assert (proj / "lyrics" / "preview.mp4").stat().st_size > 10000
    _()

    @test("songmap names sections from lyric tags and finds the hook")
    def _():
        run([TEMPOVISION, "songmap"], cwd=proj)
        sm = json.loads((proj / "analysis" / "songmap.json").read_text())
        names = [s["display"] for s in sm["sections"]]
        assert names == ["Intro", "Verse 1", "Chorus 1", "Verse 2", "Chorus 2", "Outro"], names
        assert sm["hooks"][0]["text"] == "light it up and let it go" and sm["hooks"][0]["count"] == 6
        assert any(h["kind"] == "chorus-downbeat" for h in sm["hits"])
    _()

    @test("timing export: HyperFrames composition + Remotion timing.ts, frame-snapped, cue manifest")
    def _():
        run([TEMPOVISION, "timing", "--engine", "hyperframes"], cwd=proj)
        html = (proj / "video" / "compositions" / "lyrics.html").read_text()
        assert 'data-composition-id="lyrics"' in html and 'class="clip line"' in html and "data-end=" not in html
        run([TEMPOVISION, "timing", "--engine", "remotion", "--range", "24-40"], cwd=proj)
        ts = (proj / "video" / "src" / "tempovision" / "timing.ts").read_text()
        assert "export const LYRICS" in ts and "DURATION_FRAMES = 480" in ts
        cues = json.loads((proj / "video" / "assets" / "tempovision" / "cues.json").read_text())
        for c in cues["cues"]:
            assert abs(c["t"] * 30 - round(c["t"] * 30)) < 1e-3
    _()

    draft, bad = proj / "renders" / "drafts" / "draft.mp4", proj / "renders" / "drafts" / "bad.mp4"
    run([sys.executable, str(ROOT / "tests" / "make_draft.py"), str(proj), str(draft)])
    run([sys.executable, str(ROOT / "tests" / "make_draft.py"), str(proj), str(bad), "--offset-audio", "0.12", "--black-at", "30",
         "--size", "640x360"])
    # the bad draft's black box is covered by lyrics at 30 s; make a truly black stretch too
    black = proj / "renders" / "drafts" / "black.mp4"
    run(["ffmpeg", "-v", "error", "-y", "-i", str(draft), "-vf", "drawbox=x=0:y=0:w=iw:h=ih:color=black:t=fill:enable='between(t,30,34)'",
         "-c:a", "copy", str(black)])

    @test("qa passes a good draft: sync, loudness, cuts on beats, cues")
    def _():
        run([TEMPOVISION, "qa", str(draft)], cwd=proj)
        r = json.loads((proj / "qa" / "draft.json").read_text())
        st = {c["check"]: c for c in r["checks"]}
        assert st["av_offset"]["status"] == "PASS" and abs(st["av_offset"]["seconds"]) < 0.01
        assert st["loudness"]["status"] == "PASS"
        cv = st["cuts_vs_beats"]
        assert cv["on_beat"] == len(cv["cuts"]) and not cv["mid_word"], cv
        assert st["lyric_cues"]["status"] in ("PASS", "WARN") and not st["lyric_cues"]["stale"]
    _()

    @test("qa fails a draft with audio 120 ms late and a 4 s black stretch")
    def _():
        run([TEMPOVISION, "qa", str(bad)], cwd=proj, ok=(1,))
        r = json.loads((proj / "qa" / "bad.json").read_text())
        st = {c["check"]: c for c in r["checks"]}
        assert st["av_offset"]["status"] == "FAIL" and abs(st["av_offset"]["seconds"] - 0.12) < 0.01
        run([TEMPOVISION, "qa", str(black)], cwd=proj, ok=(1,))
        r = json.loads((proj / "qa" / "black.json").read_text())
        assert {c["check"]: c for c in r["checks"]}["black"]["status"] == "FAIL"
    _()

    @test("qa catches a stale timing export after re-alignment")
    def _():
        run([TEMPOVISION, "align", "--nudge", "all:+0.2"], cwd=proj)
        run([TEMPOVISION, "qa", str(draft)], cwd=proj, ok=(1,))
        r = json.loads((proj / "qa" / "draft.json").read_text())
        assert {c["check"]: c for c in r["checks"]}["lyric_cues"]["stale"] is True
        run([TEMPOVISION, "align", "--nudge", "all:-0.2"], cwd=proj)
        run([TEMPOVISION, "timing", "--engine", "hyperframes", "--no-composition"], cwd=proj)
    _()

    @test("sheet: review set writes beats, cuts and phone sheets")
    def _():
        out = run([TEMPOVISION, "sheet", str(draft), "--mode", "review"], cwd=proj).stdout
        for k in ("beats", "cuts", "phone"):
            assert (proj / "frames" / "sheets" / f"draft-{k}.png").exists(), k
        run([TEMPOVISION, "sheet", str(draft), "--section", "chorus-1", "--offset", "0"], cwd=proj)
        assert (proj / "frames" / "sheets" / "draft-chorus-1-sheet.png").exists()
    _()

    @test("assets: unrecorded and non-commercial files fail the check; credits list attribution")
    def _():
        tex = proj / "assets" / "textures" / "grain.png"
        run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=gray:s=64x64", "-frames:v", "1", str(tex)])
        run([TEMPOVISION, "assets", "check"], cwd=proj, ok=(1,))
        run([TEMPOVISION, "assets", "add", str(tex), "--own"], cwd=proj)
        run([TEMPOVISION, "assets", "check"], cwd=proj)
        nc = proj / "assets" / "images" / "nc.png"
        shutil.copy2(tex, nc)
        run([TEMPOVISION, "assets", "add", str(nc), "--license", "CC BY-NC 4.0", "--source", "x", "--author", "Someone"], cwd=proj)
        run([TEMPOVISION, "assets", "check"], cwd=proj, ok=(1,))
        assert "Someone" in run([TEMPOVISION, "assets", "credits"], cwd=proj).stdout
        nc.unlink()
    _()

    @test("deliver: master + youtube with the master audio in sync; vertical needs its own render")
    def _():
        out = run([TEMPOVISION, "deliver", str(draft), "--targets", "master,youtube,vertical,thumbnail,poster"], cwd=proj)
        man = json.loads((proj / "renders" / "final" / "DELIVERY.json").read_text())
        got = {f["target"]: f for f in man["files"]}
        assert set(got) == {"master", "youtube", "thumbnail", "poster"}, got.keys()
        assert got["master"]["sync_ok"] and got["youtube"]["sync_ok"]
        assert got["master"]["video"]["codec"] == "prores"
    _()

    @test("doctor turns the brief into grouped requirements")
    def _():
        p = run([TEMPOVISION, "doctor", "--brief", "BRIEF.md", "--write", "SETUP.md", "--no-mcp", "--json"], cwd=proj, ok=(0, 1))
        d = json.loads(p.stdout)
        req = {i["key"] for i in d["groups"]["Required"]}
        assert {"uv", "ffmpeg", "node", "align"} <= req, req
        assert (proj / "SETUP.md").exists()
    _()

    @test("hooks: resume context, protect input/, autopilot only in full autonomy")
    def _():
        H = ROOT / "hooks"
        def hook(name, payload):
            return subprocess.run([sys.executable, str(H / name)], input=json.dumps(payload), capture_output=True, text=True).stdout
        assert "Tempovision project open" in hook("session_start.py", {"cwd": str(proj)})
        assert "deny" in hook("protect_input.py", {"cwd": str(proj), "tool_name": "Bash", "tool_input": {"command": "rm input/song.wav"}})
        assert hook("protect_input.py", {"cwd": str(proj), "tool_name": "Bash", "tool_input": {"command": "ffprobe input/song.wav"}}) == ""
        assert hook("autopilot.py", {"cwd": str(proj)}) == ""
        run([TEMPOVISION, "project", "set", "autonomy", "full"], cwd=proj)
        run([TEMPOVISION, "project", "gate", "G1", "pass"], cwd=proj)
        run([TEMPOVISION, "project", "gate", "G2", "pass"], cwd=proj)
        run([TEMPOVISION, "project", "phase", "build"], cwd=proj)
        assert '"block"' in hook("autopilot.py", {"cwd": str(proj)})
        run([TEMPOVISION, "project", "wait", "Which treatment?"], cwd=proj)
        assert hook("autopilot.py", {"cwd": str(proj)}) == ""
    _()

    @test("budget: spending over the cap is refused")
    def _():
        run([TEMPOVISION, "project", "set", "budget", "1.00"], cwd=proj)
        run([TEMPOVISION, "project", "spend", "0.60", "stills"], cwd=proj)
        run([TEMPOVISION, "project", "spend", "0.60", "more stills"], cwd=proj, ok=(1,))
    _()

    print(f"\n{len(PASSED)} passed, {len(FAILED)} failed")
    if not keep and not FAILED:
        shutil.rmtree(work, ignore_errors=True)
    else:
        print(f"kept: {work}")
    sys.exit(1 if FAILED else 0)


if __name__ == "__main__":
    main()
