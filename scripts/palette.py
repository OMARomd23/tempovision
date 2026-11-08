#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["numpy>=1.24", "pillow>=10"]
# ///
"""Palette from an image (cover art, a reference still), with contrast pairs for type.

  tempovision palette IMAGE [-k 8]           dominant colours (k-means in Lab), their share, saturation and lightness
  tempovision palette IMAGE --swatch         also writes IMAGE-palette.png
  tempovision palette --check "#F2EDE4" "#151313"   WCAG contrast ratio of two colours

Use the result as a starting point for SPEC.md: one ground, one ink, one accent, and at most two supports.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _common import Fail, table  # noqa: E402


def srgb_to_linear(c):
    c = c / 255.0
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def luminance(rgb):
    r, g, b = srgb_to_linear(np.asarray(rgb, dtype=float))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    la, lb = luminance(a), luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


def rgb_to_lab(rgb):
    lin = srgb_to_linear(rgb.astype(float))
    M = np.array([[0.4124, 0.3576, 0.1805], [0.2126, 0.7152, 0.0722], [0.0193, 0.1192, 0.9505]])
    xyz = lin @ M.T / np.array([0.95047, 1.0, 1.08883])
    f = np.where(xyz > 0.008856, np.cbrt(xyz), 7.787 * xyz + 16 / 116)
    L = 116 * f[:, 1] - 16
    a = 500 * (f[:, 0] - f[:, 1])
    b = 200 * (f[:, 1] - f[:, 2])
    return np.stack([L, a, b], axis=1)


def hsl(rgb):
    r, g, b = (np.asarray(rgb, dtype=float) / 255.0)
    mx, mn = max(r, g, b), min(r, g, b)
    l = (mx + mn) / 2
    if mx == mn:
        return 0.0, 0.0, l
    d = mx - mn
    s = d / (2 - mx - mn) if l > 0.5 else d / (mx + mn)
    if mx == r:
        h = (g - b) / d + (6 if g < b else 0)
    elif mx == g:
        h = (b - r) / d + 2
    else:
        h = (r - g) / d + 4
    return h * 60, s, l


def kmeans(X, k, iters=30, seed=0):
    rng = np.random.default_rng(seed)
    C = X[rng.choice(len(X), size=1)]
    for _ in range(1, k):  # k-means++
        d = np.min(((X[:, None, :] - C[None]) ** 2).sum(-1), axis=1)
        C = np.vstack([C, X[rng.choice(len(X), p=d / d.sum())]])
    for _ in range(iters):
        lab = np.argmin(((X[:, None, :] - C[None]) ** 2).sum(-1), axis=1)
        newC = np.array([X[lab == j].mean(axis=0) if np.any(lab == j) else C[j] for j in range(k)])
        if np.allclose(newC, C):
            break
        C = newC
    return C, lab


def hexc(rgb):
    return "#{:02X}{:02X}{:02X}".format(*[int(round(v)) for v in rgb])


def parse_hex(s):
    s = s.strip().lstrip("#")
    if len(s) == 3:
        s = "".join(c * 2 for c in s)
    return np.array([int(s[i:i + 2], 16) for i in (0, 2, 4)], dtype=float)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="tempovision palette", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("image", nargs="?")
    ap.add_argument("-k", type=int, default=8)
    ap.add_argument("--swatch", action="store_true")
    ap.add_argument("--check", nargs=2, metavar=("A", "B"))
    a = ap.parse_args(argv)
    if a.check:
        c = contrast(parse_hex(a.check[0]), parse_hex(a.check[1]))
        verdict = "body text OK (≥4.5)" if c >= 4.5 else ("large/hero text only (≥3)" if c >= 3 else "too low for text")
        print(f"{a.check[0]} on {a.check[1]}: {c:.2f}:1 · {verdict}")
        return
    if not a.image:
        raise Fail("give an image or --check A B")
    from PIL import Image

    im = Image.open(a.image).convert("RGB")
    im.thumbnail((200, 200))
    px = np.asarray(im, dtype=float).reshape(-1, 3)
    lab = rgb_to_lab(px)
    C, labels = kmeans(lab, min(a.k, len(px)))
    cols = []
    for j in range(len(C)):
        m = labels == j
        if not m.any():
            continue
        rgb = px[m].mean(axis=0)
        h, s, l = hsl(rgb)
        cols.append({"hex": hexc(rgb), "rgb": rgb, "share": m.mean(), "sat": s, "light": l, "hue": h})
    cols.sort(key=lambda c: -c["share"])
    rows = [[c["hex"], f"{c['share']:.0%}", f"{c['sat']:.0%}", f"{c['light']:.0%}", f"{c['hue']:.0f}°"] for c in cols]
    print(table(rows, ["Colour", "Share", "Saturation", "Lightness", "Hue"]))
    by_light = sorted(cols, key=lambda c: c["light"])
    dark, light = by_light[0], by_light[-1]
    print("\nSuggested roles (a start, not a decision):")
    ground = max(cols, key=lambda c: c["share"])
    ink = dark if abs(ground["light"] - dark["light"]) > abs(ground["light"] - light["light"]) else light
    rest = [c for c in cols if c["hex"] not in (ground["hex"], ink["hex"])] or cols
    accent = max(rest, key=lambda c: c["sat"] * (1 - abs(c["light"] - 0.5)) * min(1.0, contrast(ground["rgb"], c["rgb"]) / 3))
    print(f"  ground {ground['hex']} · ink {ink['hex']} ({contrast(ground['rgb'], ink['rgb']):.1f}:1) · accent {accent['hex']} "
          f"({contrast(ground['rgb'], accent['rgb']):.1f}:1 on ground)")
    pairs = []
    for i, x in enumerate(cols):
        for y in cols[i + 1:]:
            cr = contrast(x["rgb"], y["rgb"])
            if cr >= 3:
                pairs.append([x["hex"], y["hex"], f"{cr:.1f}:1", "body OK" if cr >= 4.5 else "hero only"])
    if pairs:
        print("\nPairs usable for type:")
        print(table(sorted(pairs, key=lambda r: -float(r[2].split(":")[0]))[:10], ["A", "B", "Contrast", "Use"]))
    hi_sat = sum(1 for c in cols if c["sat"] > 0.8)
    if hi_sat > 2:
        print(f"\nNote: {hi_sat} colours above 80% saturation; most palettes that look designed keep one saturated colour.")
    if a.swatch:
        sw = Image.new("RGB", (100 * len(cols), 120), "white")
        from PIL import ImageDraw

        d = ImageDraw.Draw(sw)
        for i, c in enumerate(cols):
            d.rectangle([i * 100, 0, i * 100 + 99, 99], fill=tuple(int(v) for v in c["rgb"]))
            d.text((i * 100 + 6, 104), c["hex"], fill="black")
        out = Path(a.image).with_name(Path(a.image).stem + "-palette.png")
        sw.save(out)
        print(f"\n{out}")


if __name__ == "__main__":
    main()
