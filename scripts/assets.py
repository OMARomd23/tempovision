#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""The asset ledger: every file in assets/ with its source and licence; plus search and download helpers.

  tempovision assets add PATH --license "CC0" --source "Poly Haven" --url URL [--author NAME] [--kind texture]
  tempovision assets add PATH --generated --model "fal-ai/flux-pro" --prompt-file prompts/c1-03.txt --seed 42 --cost 0.05
  tempovision assets add PATH --own --author "the artist"
  tempovision assets fetch URL --license "Pexels License" --source "Pexels" --page PAGE_URL [--author NAME] [--kind footage]
  tempovision assets search "slow push through tall grass golden light" --source openverse|pexels|pixabay|nasa|met|aic|commons [--type image|video]
  tempovision assets list
  tempovision assets check            fails on unrecorded files, non-commercial licences in a commercial project, missing attribution
  tempovision assets credits          paste-ready credits for the video description

Search uses each source's public API from this machine. Pexels needs PEXELS_API_KEY and Pixabay needs
PIXABAY_API_KEY in the environment; the session-start hook sets both from the plugin settings (the Pexels MCP
server is the other Pexels route). Pixabay results are cached for 24 hours, as its API terms require.
Always open the item's page and read its licence before using it.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import mimetypes
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import Fail, find_project, info, load_json, now_iso, plugin_data_dir, save_json, table  # noqa: E402

UA = "tempovision-music-video/0.1 (+https://github.com; asset search for a music video)"
KIND_DIRS = {"font": "fonts", "image": "images", "footage": "footage", "texture": "textures", "sfx": "sfx",
             "generated": "generated", "ref": "refs", "model3d": "images", "lut": "textures", "other": "images"}


def classify(license_str: str) -> tuple[bool | None, bool]:
    """(commercial_ok, attribution_required) from a licence name. None = unknown: read it."""
    s = (license_str or "").lower().replace("_", "-")
    if not s:
        return None, False
    if re.search(r"\bnc\b|non-?commercial|personal use|editorial", s):
        return False, True
    if re.search(r"cc0|public domain|pdm|no known copyright|unlicense", s):
        return True, False
    if re.search(r"pexels|pixabay|unsplash|mixkit", s):
        return True, False
    if re.search(r"\bofl\b|open font|sil", s):
        return True, False
    if re.search(r"by-sa|by sa|sharealike|share-alike", s):
        return True, True
    if re.search(r"cc[- ]?by|attribution", s):
        return True, True
    if re.search(r"\bown\b|artist|commissioned|licensed|purchased|royalty-free|generated|model terms", s):
        return True, False
    if re.search(r"shadertoy", s):
        return False, True
    return None, False


def ledger_path(project: Path) -> Path:
    return project / "assets" / "LEDGER.json"


def load_ledger(project: Path) -> dict:
    return load_json(ledger_path(project), default={"schema": 1, "assets": []})


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def guess_kind(p: Path) -> str:
    ext = p.suffix.lower()
    if ext in (".ttf", ".otf", ".woff", ".woff2"):
        return "font"
    if ext in (".mp4", ".mov", ".webm", ".mkv", ".m4v"):
        return "footage"
    if ext in (".wav", ".mp3", ".flac", ".ogg", ".aiff"):
        return "sfx"
    if ext in (".cube", ".3dl"):
        return "lut"
    if ext in (".glb", ".gltf", ".obj", ".fbx", ".usdz"):
        return "model3d"
    return "image"


def record(project: Path, path: Path, **fields) -> dict:
    led = load_ledger(project)
    rel = str(path.resolve().relative_to(project.resolve()))
    commercial_ok, attr = classify(fields.get("license") or "")
    entry = {
        "path": rel, "kind": fields.get("kind") or guess_kind(path), "source": fields.get("source"),
        "source_url": fields.get("url"), "author": fields.get("author"), "license": fields.get("license"),
        "license_url": fields.get("license_url"), "commercial_ok": commercial_ok if fields.get("commercial_ok") is None else fields["commercial_ok"],
        "attribution_required": attr, "attribution_text": fields.get("attribution"),
        "generated": fields.get("generated"), "notes": fields.get("notes"), "sha256": sha256(path), "added": now_iso(),
    }
    if attr and not entry["attribution_text"]:
        bits = [fields.get("title") or path.stem, f"by {entry['author']}" if entry["author"] else None,
                entry["license"], entry["source_url"]]
        entry["attribution_text"] = " · ".join(b for b in bits if b)
    led["assets"] = [a for a in led["assets"] if a["path"] != rel] + [entry]
    save_json(ledger_path(project), led)
    return entry


def cmd_add(a):
    project = find_project()
    p = Path(a.path).expanduser()
    if not p.exists():
        raise Fail(f"no such file: {p}")
    try:
        p.resolve().relative_to((project / "assets").resolve())
    except ValueError:
        raise Fail("assets must live inside assets/ (move or copy the file there first)")
    gen = None
    lic = a.license
    if a.generated:
        prompt = Path(a.prompt_file).read_text(encoding="utf-8") if a.prompt_file else a.prompt
        gen = {"model": a.model, "prompt": prompt, "seed": a.seed, "refs": a.refs, "cost_usd": a.cost}
        lic = lic or f"generated ({a.model}; provider terms)"
    if a.own:
        lic = lic or "own (the artist's material)"
    if not lic:
        raise Fail("give --license (or --generated / --own)")
    e = record(project, p, license=lic, source=a.source, url=a.url, author=a.author, kind=a.kind, license_url=a.license_url,
               attribution=a.attribution, generated=gen, notes=a.notes, title=a.title,
               commercial_ok=False if a.non_commercial else (True if a.commercial_ok else None))
    flag = {True: "commercial OK", False: "NOT for commercial use", None: "licence unknown: read it"}[e["commercial_ok"]]
    print(f"recorded {e['path']} · {e['license']} · {flag}" + (" · attribution required" if e["attribution_required"] else ""))


def download(url: str, dest_dir: Path) -> Path:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=120) as r:
        name = Path(urllib.parse.urlparse(r.geturl()).path).name or "download"
        ctype = r.headers.get("Content-Type", "").split(";")[0]
        if "." not in name and ctype:
            name += mimetypes.guess_extension(ctype) or ""
        dest = dest_dir / re.sub(r"[^\w.\-]", "_", name)
        k = 1
        while dest.exists():
            dest = dest.with_name(f"{dest.stem}-{k}{dest.suffix}")
            k += 1
        dest_dir.mkdir(parents=True, exist_ok=True)
        with open(dest, "wb") as f:
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                f.write(chunk)
    return dest


def cmd_fetch(a):
    project = find_project()
    kind = a.kind or "image"
    dest = download(a.url, project / "assets" / KIND_DIRS.get(kind, "images"))
    e = record(project, dest, license=a.license, source=a.source, url=a.page or a.url, author=a.author, kind=kind,
               license_url=a.license_url, attribution=a.attribution, notes=a.notes, title=a.title)
    print(f"{e['path']} · {e['license']} · commercial_ok={e['commercial_ok']}")


def get_json(url: str, headers: dict | None = None):
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def pixabay_get(path: str, params: dict) -> dict:
    """Pixabay API call with the 24-hour result cache its terms require. The key never reaches the cache key."""
    key = os.environ.get("PIXABAY_API_KEY")
    if not key:
        raise Fail("set PIXABAY_API_KEY: free key at https://pixabay.com/api/docs/ → /plugin → Tempovision → configure "
                   "→ Pixabay API key, then start a new session")
    query = urllib.parse.urlencode(sorted(params.items()))
    cache = plugin_data_dir() / "cache" / "pixabay" / (hashlib.sha256(f"{path}?{query}".encode()).hexdigest()[:32] + ".json")
    if cache.is_file() and time.time() - cache.stat().st_mtime < 24 * 3600:
        return json.loads(cache.read_text(encoding="utf-8"))
    try:
        d = get_json(f"https://pixabay.com/api/{path}?key={urllib.parse.quote(key)}&{query}")
    except urllib.error.HTTPError as e:
        if e.code == 400:
            raise Fail("Pixabay rejected the request (invalid API key, or a bad parameter); check the key in /plugin")
        if e.code == 429:
            raise Fail(f"Pixabay rate limit reached (100 requests a minute); retry in {e.headers.get('X-RateLimit-Reset', '60')} s")
        raise
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(d), encoding="utf-8")
    return d


def search(source: str, q: str, kind: str, n: int) -> list[dict]:
    qq = urllib.parse.quote(q)
    out = []
    if source == "openverse":
        path = "audio" if kind == "audio" else "images"
        d = get_json(f"https://api.openverse.org/v1/{path}/?q={qq}&page_size={n}&license_type=commercial")
        for r in d.get("results", []):
            out.append({"title": r.get("title"), "url": r.get("url"), "page": r.get("foreign_landing_url"),
                        "author": r.get("creator"), "license": f"CC {r.get('license', '').upper()} {r.get('license_version', '')}".strip(),
                        "license_url": r.get("license_url"), "size": f"{r.get('width')}x{r.get('height')}" if r.get("width") else ""})
    elif source == "pexels":
        key = os.environ.get("PEXELS_API_KEY")
        if not key:
            raise Fail("set PEXELS_API_KEY in the environment, or use the Pexels MCP tools")
        if kind == "video":
            d = get_json(f"https://api.pexels.com/videos/search?query={qq}&per_page={n}", {"Authorization": key})
            for v in d.get("videos", []):
                files = sorted(v.get("video_files", []), key=lambda f: (f.get("width") or 0), reverse=True)
                best = files[0] if files else {}
                out.append({"title": v.get("url", "").rstrip("/").split("/")[-1], "url": best.get("link"), "page": v.get("url"),
                            "author": (v.get("user") or {}).get("name"), "license": "Pexels License",
                            "license_url": "https://www.pexels.com/license/", "size": f"{best.get('width')}x{best.get('height')} · {v.get('duration')} s"})
        else:
            d = get_json(f"https://api.pexels.com/v1/search?query={qq}&per_page={n}", {"Authorization": key})
            for ph in d.get("photos", []):
                out.append({"title": ph.get("alt"), "url": (ph.get("src") or {}).get("original"), "page": ph.get("url"),
                            "author": ph.get("photographer"), "license": "Pexels License",
                            "license_url": "https://www.pexels.com/license/", "size": f"{ph.get('width')}x{ph.get('height')}"})
    elif source == "pixabay":
        if kind == "audio":
            raise Fail("the Pixabay API has no audio search; use --type image or video")
        params = {"q": q[:100], "per_page": max(3, min(200, n)), "safesearch": "true"}
        lic = {"license": "Pixabay Content License", "license_url": "https://pixabay.com/service/license-summary/"}
        if kind == "video":
            d = pixabay_get("videos/", params)
            for v in d.get("hits", [])[:n]:
                # large (4K) is empty on many clips; medium, small and tiny always exist
                rend = [r for r in (v.get("videos") or {}).values() if r.get("url") and r.get("size")]
                best = max(rend, key=lambda r: r.get("width") or 0, default={})
                out.append({"title": v.get("tags"), "url": best.get("url"), "page": v.get("pageURL"), "author": v.get("user"),
                            **lic, "size": f"{best.get('width')}x{best.get('height')} · {v.get('duration')} s"})
        else:
            d = pixabay_get("", params)
            for ph in d.get("hits", [])[:n]:
                # largeImageURL is capped at 1280 px; the original needs Pixabay's full API access
                out.append({"title": ph.get("tags"), "url": ph.get("imageURL") or ph.get("largeImageURL"), "page": ph.get("pageURL"),
                            "author": ph.get("user"), **lic,
                            "size": f"{ph.get('imageWidth')}x{ph.get('imageHeight')}" + ("" if ph.get("imageURL") else " (url ≤1280 px)")})
    elif source == "nasa":
        mt = "video" if kind == "video" else "image"
        d = get_json(f"https://images-api.nasa.gov/search?q={qq}&media_type={mt}")
        for it in d.get("collection", {}).get("items", [])[:n]:
            meta = (it.get("data") or [{}])[0]
            nid = meta.get("nasa_id")
            out.append({"title": meta.get("title"), "url": (it.get("links") or [{}])[0].get("href"),
                        "page": f"https://images.nasa.gov/details/{nid}", "author": meta.get("center"),
                        "license": "NASA media (generally not copyrighted; check the item)", "license_url": "https://www.nasa.gov/nasa-brand-center/images-and-media/",
                        "size": ""})
    elif source == "met":
        d = get_json(f"https://collectionapi.metmuseum.org/public/collection/v1/search?hasImages=true&q={qq}")
        for oid in (d.get("objectIDs") or [])[: n * 2]:
            o = get_json(f"https://collectionapi.metmuseum.org/public/collection/v1/objects/{oid}")
            if not o.get("isPublicDomain") or not o.get("primaryImage"):
                continue
            out.append({"title": o.get("title"), "url": o.get("primaryImage"), "page": o.get("objectURL"),
                        "author": o.get("artistDisplayName"), "license": "CC0 (The Met Open Access)",
                        "license_url": "https://www.metmuseum.org/policies/image-resources", "size": ""})
            if len(out) >= n:
                break
    elif source == "aic":
        d = get_json(f"https://api.artic.edu/api/v1/artworks/search?q={qq}&limit={n}"
                     f"&query[term][is_public_domain]=true&fields=id,title,image_id,artist_display,is_public_domain")
        for r in d.get("data", []):
            if r.get("image_id"):
                out.append({"title": r.get("title"), "url": f"https://www.artic.edu/iiif/2/{r['image_id']}/full/1686,/0/default.jpg",
                            "page": f"https://www.artic.edu/artworks/{r['id']}", "author": r.get("artist_display"),
                            "license": "CC0 (Art Institute of Chicago public domain)", "license_url": "https://www.artic.edu/open-access", "size": ""})
    elif source == "commons":
        d = get_json("https://commons.wikimedia.org/w/api.php?action=query&format=json&generator=search&gsrnamespace=6"
                     f"&gsrlimit={n}&gsrsearch={qq}&prop=imageinfo&iiprop=url|extmetadata|size")
        for pg in (d.get("query", {}).get("pages", {}) or {}).values():
            ii = (pg.get("imageinfo") or [{}])[0]
            em = ii.get("extmetadata", {})
            out.append({"title": pg.get("title"), "url": ii.get("url"), "page": ii.get("descriptionurl"),
                        "author": re.sub(r"<[^>]+>", "", (em.get("Artist") or {}).get("value", "")).strip(),
                        "license": (em.get("LicenseShortName") or {}).get("value"), "license_url": (em.get("LicenseUrl") or {}).get("value"),
                        "size": f"{ii.get('width')}x{ii.get('height')}"})
    else:
        raise Fail(f"unknown source {source}")
    for r in out:
        r["commercial_ok"], r["attribution_required"] = classify(r.get("license") or "")
    return out


def cmd_search(a):
    try:
        res = search(a.source, a.query, a.type, a.n)
    except (OSError, ValueError) as e:
        raise Fail(f"{a.source} search failed: {e}")
    if a.json:
        print(json.dumps(res, indent=2, ensure_ascii=False))
        return
    rows = [[i + 1, (r["title"] or "")[:50], r["license"], {True: "yes", False: "NO", None: "?"}[r["commercial_ok"]],
             r.get("size", ""), r.get("page")] for i, r in enumerate(res)]
    print(table(rows, ["#", "Title", "Licence", "Commercial", "Size", "Page"]))
    if a.source == "pixabay":
        print("\nImages and videos from Pixabay (https://pixabay.com)")
    print("\nDownload one with: tempovision assets fetch <url> --license \"<licence>\" --source "
          f"\"{a.source}\" --page <page> --author \"<author>\"")


def cmd_list(a):
    project = find_project()
    led = load_ledger(project)
    rows = [[e["path"], e["license"], {True: "yes", False: "NO", None: "?"}[e["commercial_ok"]],
             "yes" if e["attribution_required"] else "", (e.get("generated") or {}).get("model", "")] for e in led["assets"]]
    print(table(rows, ["Path", "Licence", "Commercial", "Attribution", "Generated by"]) if rows else "ledger is empty")


def brief_commercial(project: Path) -> bool:
    b = project / "BRIEF.md"
    if b.exists():
        m = re.search(r"commercial:\s*(true|false)", b.read_text(encoding="utf-8"))
        if m:
            return m.group(1) == "true"
    return True


def cmd_check(a):
    project = find_project()
    led = load_ledger(project)
    known = {e["path"]: e for e in led["assets"]}
    commercial = brief_commercial(project)
    problems = []
    for p in sorted((project / "assets").rglob("*")):
        if p.is_dir() or p.name in ("LEDGER.json", ".DS_Store") or p.name.startswith("."):
            continue
        rel = str(p.relative_to(project))
        if rel.startswith("assets/refs/"):
            continue  # reference material, never in the film
        e = known.get(rel)
        if not e:
            problems.append(["FAIL", rel, "not in the ledger: `tempovision assets add` it with its licence"])
            continue
        if e.get("sha256") and e["sha256"] != sha256(p):
            problems.append(["WARN", rel, "file changed since it was recorded (edit? re-record if it is a derivative)"])
        if commercial and e["commercial_ok"] is False:
            problems.append(["FAIL", rel, f"{e['license']} does not allow commercial use, and the brief is commercial"])
        if e["commercial_ok"] is None:
            problems.append(["WARN", rel, f"licence '{e['license']}' not recognised: read it, then re-add with --commercial-ok or --non-commercial"])
    for rel in known:
        if not (project / rel).exists():
            problems.append(["WARN", rel, "in the ledger but the file is gone"])
    gen_cost = sum(((e.get("generated") or {}).get("cost_usd") or 0) for e in led["assets"])
    if problems:
        print(table(problems, ["Status", "Asset", "Problem"]))
    print(f"\n{len(known)} recorded · {sum(1 for x in problems if x[0] == 'FAIL')} failing · "
          f"{sum(1 for e in led['assets'] if e['attribution_required'])} need attribution · generation cost ${gen_cost:.2f}")
    if any(x[0] == "FAIL" for x in problems):
        sys.exit(1)


def cmd_credits(a):
    project = find_project()
    led = load_ledger(project)
    lines = []
    for e in led["assets"]:
        if e["attribution_required"]:
            lines.append(e.get("attribution_text") or f"{e['path']} · {e['license']}")
    models = sorted({(e.get("generated") or {}).get("model") for e in led["assets"] if e.get("generated")} - {None})
    fonts = [e for e in led["assets"] if e["kind"] == "font"]
    print("Credits")
    for f in fonts:
        print(f"Type: {Path(f['path']).stem} ({f['license']}{', ' + f['author'] if f.get('author') else ''})")
    for l in lines:
        print(l)
    if models:
        print("Generated imagery: " + ", ".join(models))


def main(argv=None):
    p = argparse.ArgumentParser(prog="tempovision assets", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    x = sub.add_parser("add")
    x.add_argument("path")
    x.add_argument("--license")
    x.add_argument("--license-url")
    x.add_argument("--source")
    x.add_argument("--url")
    x.add_argument("--author")
    x.add_argument("--title")
    x.add_argument("--kind", choices=sorted(KIND_DIRS))
    x.add_argument("--attribution")
    x.add_argument("--notes")
    x.add_argument("--non-commercial", action="store_true")
    x.add_argument("--commercial-ok", action="store_true", help="you read the licence and it allows commercial use")
    x.add_argument("--own", action="store_true")
    x.add_argument("--generated", action="store_true")
    x.add_argument("--model")
    x.add_argument("--prompt")
    x.add_argument("--prompt-file")
    x.add_argument("--seed")
    x.add_argument("--refs", nargs="*")
    x.add_argument("--cost", type=float)
    x.set_defaults(fn=cmd_add)
    x = sub.add_parser("fetch")
    x.add_argument("url")
    x.add_argument("--license", required=True)
    x.add_argument("--license-url")
    x.add_argument("--source", required=True)
    x.add_argument("--page")
    x.add_argument("--author")
    x.add_argument("--title")
    x.add_argument("--kind", choices=sorted(KIND_DIRS))
    x.add_argument("--attribution")
    x.add_argument("--notes")
    x.set_defaults(fn=cmd_fetch)
    x = sub.add_parser("search")
    x.add_argument("query")
    x.add_argument("--source", default="openverse", choices=["openverse", "pexels", "pixabay", "nasa", "met", "aic", "commons"])
    x.add_argument("--type", default="image", choices=["image", "video", "audio"])
    x.add_argument("-n", type=int, default=10)
    x.add_argument("--json", action="store_true")
    x.set_defaults(fn=cmd_search)
    sub.add_parser("list").set_defaults(fn=cmd_list)
    sub.add_parser("check").set_defaults(fn=cmd_check)
    sub.add_parser("credits").set_defaults(fn=cmd_credits)
    a = p.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
