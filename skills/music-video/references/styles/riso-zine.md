# Riso zine

Two or three inks printed on off-white paper, slightly out of register, with halftone and ink-starved edges.
Loud, handmade, honest.

## Medium

- Paper `#F2EDE4` (warm) or `#EDEDE8` (cool), fibre noise 8% at 2 px scale, static.
- Inks: pick 2 from the real riso set and treat them as the whole palette: fluorescent pink `#FF48B0`, blue
  `#0078BF`, yellow `#FFE800`, green `#00A95C`, black `#3D3B3C` (riso black is never pure). Overprint by
  `multiply`, so pink over blue gives a real third colour.
- Misregistration: each ink layer offset 1–4 px in a random but per-scene fixed direction; re-seeded on each
  cut (a new print), not every frame.
- Halftone: photos and gradients as dot screens, cell 6–10 px at 1080p, angle 15° for one ink and 75° for the
  other.
- Ink coverage: large flats get 3–6% speckle and slightly lighter edges (starved ink).
- Animate on twos (12 fps feel) for drawn elements; type can move at full rate.

## Type

Heavy grotesk or a condensed slab, set very large (20–40% of frame height), tight tracking (−2 to −4%), in one
ink; hero words knocked out of a flat. Hand-lettered words for hero lines (an SVG path traced from the person's
handwriting is ideal).

## Motion personality

Hard cuts, stop-motion stepping, paste-up moves (elements slide in and stop dead, a 2-frame overshoot at most).
Camera locked; the page itself shifts on downbeats (translate 8–20 px, rotate 0.5–2°).

## Sections

- Verse: one page per line, line set big, one halftone image fragment.
- Chorus: pages flip on the bar, inks swap order (pink on top ↔ blue on top) on each chorus return, scale
  doubles on the last chorus.
- Bridge: one ink only, lots of paper, slow.

## Build notes

Layers as separate DOM/SVG groups with `mix-blend-mode: multiply`; halftone via an SVG pattern or a
fragment shader; misregistration as a per-layer translate set at the cut. Paper texture is a single full-frame
layer on top with `multiply`.

## How it goes wrong

Too clean (no misregistration, perfect flats), too many inks (looks like a flat vector), halftone on everything,
moving the misregistration every frame (reads as jitter, not print).
