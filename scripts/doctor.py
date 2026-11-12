#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml>=6"]
# ///
"""Check this machine for what a Tempovision music video needs, and turn a brief into a setup checklist.

  tempovision doctor                         what is installed (all capabilities, nothing marked required)
  tempovision doctor --brief BRIEF.md        Required / Recommended / Optional for this video
  tempovision doctor --brief BRIEF.md --write SETUP.md
  tempovision doctor --network               also probe the hosts the installs and APIs need
  tempovision doctor --json

Exit code 1 when a Required item fails.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import TEMPLATES, find_project, now_iso, plugin_data_dir  # noqa: E402

OK, MISSING, WARN, UNKNOWN = "ok", "missing", "warn", "unknown"
ICON = {OK: "✅", MISSING: "❌", WARN: "⚠️", UNKNOWN: "❔"}

HOSTS = {
    "pypi.org": "Python packages (uv)",
    "files.pythonhosted.org": "Python package files",
    "registry.npmjs.org": "Node packages (HyperFrames, Remotion, MCP servers)",
    "download.pytorch.org": "the English alignment model (torchaudio)",
    "huggingface.co": "alignment models for other languages, Whisper",
    "dl.fbaipublicfiles.com": "Demucs stem models",
    "mcp.fal.ai": "fal MCP server (generation)",
    "api.pexels.com": "Pexels search",
    "pixabay.com": "Pixabay search",
    "api.openverse.org": "Openverse search (CC media)",
    "fonts.googleapis.com": "Google Fonts",
}


def sh(cmd: list[str], timeout: float = 20) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout + p.stderr).strip()
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError) as e:
        return 127, str(e)


def version_tuple(s: str) -> tuple[int, ...]:
    m = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", s or "")
    return tuple(int(x) for x in m.groups(default="0")) if m else (0,)


def item(key, label, status, detail, unlocks, how, cost=""):
    return {"key": key, "label": label, "status": status, "detail": detail, "unlocks": unlocks, "how": how, "cost": cost}


def os_install(pkg_mac: str, pkg_apt: str, pkg_win: str) -> str:
    sysname = platform.system()
    if sysname == "Darwin":
        return f"brew install {pkg_mac}"
    if sysname == "Windows":
        return f"winget install {pkg_win}"
    return f"sudo apt install {pkg_apt}"


def check_core() -> list[dict]:
    out = []
    py = sys.version_info
    out.append(item("python", "Python ≥3.10", OK if py >= (3, 10) else MISSING, platform.python_version(),
                    "every tempovision tool", "https://www.python.org/downloads/ (uv can also install Python)"))
    uv = shutil.which("uv")
    out.append(item("uv", "uv (runs the tools with their own dependencies)", OK if uv else MISSING,
                    sh(["uv", "--version"])[1] if uv else "not found", "every tempovision tool",
                    "curl -LsSf https://astral.sh/uv/install.sh | sh   (Windows: powershell -c \"irm https://astral.sh/uv/install.ps1 | iex\")"))
    ff = shutil.which("ffmpeg")
    if ff:
        _, v = sh(["ffmpeg", "-version"])
        ver = version_tuple(v.splitlines()[0] if v else "")
        _, filters = sh(["ffmpeg", "-hide_banner", "-filters"])
        _, enc = sh(["ffmpeg", "-hide_banner", "-encoders"])
        missing = [n for n, src in (("libass (ass filter)", " ass "), ("drawtext", "drawtext"), ("scdet", "scdet"),
                                    ("ebur128", "ebur128")) if src not in filters]
        missing += [n for n in ("libx264", "prores_ks") if n not in enc]
        st = OK if ver >= (6,) and not missing else WARN
        detail = f"{'.'.join(map(str, ver))}" + (f"; missing: {', '.join(missing)}" if missing else "")
    else:
        st, detail = MISSING, "not found"
    out.append(item("ffmpeg", "FFmpeg ≥6 with libass, libx264, ProRes", st, detail, "analysis, previews, QA, sheets, delivery",
                    os_install("ffmpeg", "ffmpeg", "Gyan.FFmpeg")))
    out.append(item("git", "git", OK if shutil.which("git") else MISSING, "", "locking sections, undoing a bad fix",
                    os_install("git", "git", "Git.Git")))
    free = shutil.disk_usage(Path.cwd()).free / 1e9
    out.append(item("disk", "≥ 10 GB free", OK if free >= 10 else (WARN if free >= 5 else MISSING), f"{free:.0f} GB free",
                    "models (~3 GB), renders, ProRes masters", "free some space"))
    return out


def node_version() -> tuple[int, ...]:
    if not shutil.which("node"):
        return (0,)
    return version_tuple(sh(["node", "--version"])[1])


def skills_present(names: list[str], project: Path | None) -> list[str]:
    roots = [Path.home() / ".claude" / "skills", Path.home() / ".agents" / "skills"]
    if project:
        roots += [project / ".claude" / "skills", project / ".agents" / "skills", project / "video" / ".claude" / "skills",
                  project / "video" / ".agents" / "skills"]
    found = []
    for n in names:
        if any((r / n / "SKILL.md").exists() for r in roots):
            found.append(n)
    return found


def check_engine(engine: str, project: Path | None) -> list[dict]:
    out = []
    nv = node_version()
    need = (22,) if engine == "hyperframes" else (18,)
    out.append(item("node", f"Node.js ≥{need[0]}", OK if nv >= need else MISSING, ".".join(map(str, nv)) if nv != (0,) else "not found",
                    f"{engine} renders", "https://nodejs.org (LTS)  or  " + os_install("node", "nodejs npm", "OpenJS.NodeJS.LTS")))
    if engine == "hyperframes":
        sk = skills_present(["hyperframes", "hyperframes-cli"], project)
        out.append(item("hyperframes-skills", "HyperFrames skills", OK if "hyperframes" in sk else MISSING,
                        ", ".join(sk) or "not installed", "the engine's render contract, checks and snapshots",
                        "npx skills add heygen-com/hyperframes   (in the project folder)"))
        out.append(item("hyperframes-doctor", "HyperFrames runtime (Chrome, FFmpeg)", UNKNOWN, "run it once",
                        "rendering", "npx hyperframes doctor", "~300 MB on first run (headless Chrome)"))
    else:
        has_proj = bool(project and (project / "video" / "package.json").exists() and "remotion" in
                        (project / "video" / "package.json").read_text(encoding="utf-8", errors="ignore"))
        out.append(item("remotion-project", "Remotion project in video/", OK if has_proj else WARN,
                        "found" if has_proj else "not created yet", "rendering", "npx create-video@latest video --blank"))
        sk = skills_present(["remotion-best-practices", "remotion-create"], project)
        out.append(item("remotion-skills", "Remotion skills", OK if sk else MISSING, ", ".join(sk) or "not installed",
                        "Remotion rules the build follows", "npx skills add remotion-dev/skills"))
    return out


def marker(name: str) -> Path:
    return plugin_data_dir() / "markers" / f"{name}.ok"


def check_ml(language: str) -> list[dict]:
    out = []
    m = marker("stems")
    out.append(item("stems", "Demucs stem separation", OK if m.exists() else MISSING,
                    "installed" if m.exists() else "not installed yet",
                    "vocal stem for accurate lyric timing; per-stem energy (drums, bass, vocals) to drive layers",
                    "tempovision stems --install", "~2.5 GB (PyTorch) + 80 MB model; 3-10 min"))
    m2, m3 = marker(f"align-{language}"), marker("align-mms")
    have = [n for n, m in ((language, m2), ("multilingual MMS", m3)) if m.exists()]
    out.append(item("align", f"Lyric alignment model ({language})", OK if have else MISSING,
                    "installed: " + ", ".join(have) if have else "not installed yet",
                    "word-level lyric timing from the artist's own lyrics (MMS covers 1,100+ languages, romanised "
                    "lyrics such as Arabizi, and code-switching)",
                    f"tempovision align --install --language {language}   (or --method mms --install)",
                    "~2.5 GB shared with stems + ~360 MB model"))
    return out


def check_gpu() -> dict:
    if shutil.which("nvidia-smi"):
        rc, o = sh(["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"])
        if rc == 0 and o:
            return item("gpu", "GPU acceleration", OK, o.splitlines()[0],
                        "stems and alignment 5-20x faster (stems and the MMS aligner install CUDA PyTorch)", "")
    if platform.system() == "Darwin" and platform.machine() == "arm64":
        return item("gpu", "GPU acceleration", OK, "Apple Silicon (MPS)", "stems faster", "")
    return item("gpu", "GPU acceleration", WARN, "CPU only", "stems ~1-3x the song length on CPU; fine, just slower",
                "an NVIDIA GPU with CUDA drivers (optional)")


def check_mcp() -> dict:
    """Best effort: ask the Claude Code CLI which MCP servers are connected."""
    res = {}
    if shutil.which("claude"):
        rc, o = sh(["claude", "mcp", "list"], timeout=40)
        for line in o.splitlines():
            low = line.lower()
            for name in ("fal", "pexels"):
                if re.search(rf"\b{name}\b", low):
                    res[name] = OK if ("✓" in line or "connected" in low and "not connected" not in low and "failed" not in low) else WARN
    return res


def check_stock(mcp: dict) -> dict:
    found = [name for name, ok in (("Pexels MCP", mcp.get("pexels") == OK), ("Pexels key", os.environ.get("PEXELS_API_KEY")),
                                   ("Pixabay key", os.environ.get("PIXABAY_API_KEY"))) if ok]
    st = OK if found else (mcp.get("pexels") or UNKNOWN)
    return item("stock", "Stock footage search (Pexels or Pixabay)", st,
                ", ".join(found) if found else {WARN: "Pexels configured but not connected", UNKNOWN: "no key found"}[st],
                "real footage and photos for the shot list (Openverse and archives work without a key)",
                "free key from either: https://pixabay.com/api/docs/ (log in, copy the key) or https://www.pexels.com/api/"
                "  → /plugin → Tempovision → configure → Pixabay / Pexels API key; then start a new session")


def check_genai(mcp: dict) -> dict:
    st = mcp.get("fal", UNKNOWN)
    return item("genai", "Generation (fal MCP: images, video, upscaling)", st,
                {OK: "connected", WARN: "configured but not connected (key? credit?)", UNKNOWN: "check /mcp"}[st],
                "generated scenes and characters; image-to-video; upscaling",
                "key: https://fal.ai/dashboard/keys → /plugin → Tempovision → configure → fal API key; add credit",
                "pay per generation; the budget in BRIEF.md caps it")


def check_fonts(project: Path | None) -> dict:
    d = project / "assets" / "fonts" if project else None
    files = [p for p in d.iterdir() if p.suffix.lower() in (".ttf", ".otf", ".woff", ".woff2")] if d and d.exists() else []
    return item("fonts", "Display fonts in assets/fonts/", OK if files else WARN, f"{len(files)} font files",
                "type with character (engines only ship a few defaults)",
                "chosen in phase 4; sources in data/sources.json → fonts (tempovision assets fetch …)")


def check_autonomy() -> dict:
    return item("autonomy", "Claude Code auto mode", UNKNOWN, "set in Claude Code",
                "full-autonomy runs without approving every command",
                "claude --enable-auto-mode, then Shift+Tab to auto mode; run in a dedicated folder")


def probe_hosts() -> list[dict]:
    out = []
    for host, why in HOSTS.items():
        try:
            req = urllib.request.Request(f"https://{host}/", method="HEAD", headers={"User-Agent": "tempovision-doctor"})
            urllib.request.urlopen(req, timeout=8)
            st = OK
            det = "reachable"
        except urllib.error.HTTPError as e:
            st, det = OK, f"reachable (HTTP {e.code})"
        except Exception as e:  # noqa: BLE001
            st, det = MISSING, f"unreachable: {str(e)[:60]}"
        out.append(item(f"net:{host}", host, st, det, why, "allow this host in your proxy/firewall"))
    return out


def read_brief(path: Path) -> dict:
    import yaml

    text = path.read_text(encoding="utf-8")
    m = re.search(r"```yaml\s*\n(.*?)```", text, flags=re.S)
    if not m:
        return {}
    data = yaml.safe_load(m.group(1)) or {}
    return data.get("tempovision", data)


def classify(brief: dict, items: list[dict]) -> dict[str, list[dict]]:
    groups = {"Required": [], "Recommended": [], "Optional": []}
    caps = set(brief.get("capabilities") or [])
    src = brief.get("sources") or {}
    lyrics = str(brief.get("lyrics_on_screen", "all")).lower()
    gen = float(src.get("generated", 0) or 0)
    real = float(src.get("real", 0) or 0)
    autonomy = brief.get("autonomy", "checkpoints")
    for it in items:
        k = it["key"]
        if k in ("python", "uv", "ffmpeg", "git", "disk", "node") or k.startswith(("hyperframes", "remotion")):
            g = "Required"
        elif k == "align":
            g = "Required" if lyrics != "none" or "align" in caps else "Optional"
        elif k == "stems":
            g = "Recommended"
        elif k == "genai":
            g = "Required" if gen > 0 or "genai" in caps else "Optional"
        elif k == "stock":
            g = "Recommended" if real > 0 or "stock" in caps else "Optional"
        elif k == "fonts":
            g = "Recommended"
        elif k == "autonomy":
            g = "Recommended" if autonomy == "full" else "Optional"
        elif k == "gpu":
            g = "Optional"
        elif k.startswith("net:"):
            g = "Optional"
        else:
            g = "Optional"
        it["group"] = g
        groups[g].append(it)
    return groups


def render_md(groups: dict[str, list[dict]]) -> str:
    out = []
    for g, items in groups.items():
        if not items:
            continue
        out.append(f"## {g}\n")
        out.append("| | Item | Status | Why (for this video) | How | Cost |")
        out.append("|---|---|---|---|---|---|")
        for it in items:
            how = it["how"].replace("|", "\\|") if it["status"] != OK else ""
            out.append(f"| {ICON[it['status']]} | {it['label']} | {it['detail']} | {it['unlocks']} | `{how}` | {it['cost']} |"
                       if how else f"| {ICON[it['status']]} | {it['label']} | {it['detail']} | {it['unlocks']} | | {it['cost']} |")
        out.append("")
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="tempovision doctor", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--brief")
    ap.add_argument("--write")
    ap.add_argument("--network", action="store_true")
    ap.add_argument("--all", action="store_true", help="check every capability (default without --brief)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--no-mcp", action="store_true", help="skip asking Claude Code about MCP servers")
    a = ap.parse_args(argv)

    project = find_project(required=False)
    brief = {}
    if a.brief:
        bp = Path(a.brief)
        if not bp.is_absolute() and project and not bp.exists():
            bp = project / a.brief
        brief = read_brief(bp) if bp.exists() else {}
    state = {}
    if project:
        try:
            state = json.loads((project / "tempovision.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            state = {}
    engine = brief.get("engine") or state.get("engine") or os.environ.get("CLAUDE_PLUGIN_OPTION_DEFAULT_ENGINE") or "hyperframes"
    language = brief.get("language") or state.get("language") or "en"

    items = check_core() + check_engine(engine, project) + check_ml(language) + [check_gpu()]
    mcp = {} if a.no_mcp else check_mcp()
    items += [check_stock(mcp), check_genai(mcp), check_fonts(project), check_autonomy()]
    if a.network:
        items += probe_hosts()

    groups = classify(brief, items) if brief else {"Required": [i for i in items if i["key"] in ("python", "uv", "ffmpeg", "git", "disk", "node")],
                                                    "Recommended": [], "Optional": []}
    if not brief:
        rest = [i for i in items if i not in groups["Required"]]
        groups["Recommended"] = [i for i in rest if i["key"] in ("stems", "align") or i["key"].startswith(("hyperframes", "remotion"))]
        groups["Optional"] = [i for i in rest if i not in groups["Recommended"]]
    failed = [i for i in groups["Required"] if i["status"] == MISSING]

    if a.json:
        print(json.dumps({"engine": engine, "language": language, "groups": groups, "required_failing": len(failed)}, indent=2, ensure_ascii=False))
    else:
        title = f"Tempovision setup check · engine {engine} · lyrics language {language} · {platform.system()} {platform.machine()}"
        print(title + "\n")
        print(render_md(groups))
        print(f"{'All required items are ready.' if not failed else f'{len(failed)} required item(s) missing: ' + ', '.join(i['label'] for i in failed)}")
    if a.write:
        tpl = (TEMPLATES / "docs" / "SETUP.md").read_text(encoding="utf-8")
        doc = (tpl.replace("{{title}}", brief.get("title") or state.get("title") or "this video")
               .replace("{{date}}", now_iso()).replace("{{checklist}}", render_md(groups)))
        dest = Path(a.write)
        if not dest.is_absolute() and project:
            dest = project / dest
        dest.write_text(doc, encoding="utf-8")
        print(f"\nwrote {dest}", file=sys.stderr if a.json else sys.stdout)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
