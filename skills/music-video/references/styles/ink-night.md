# Ink at night

Black ink blooming into wet paper, white space, one red accent. Quiet, close, devastating when it works.

## Medium

- Paper `#F4F1EA`, a soft paper grain 5%; ink `#151313` with wet-edge darkening (the edge of each bloom 10–20%
  darker than its centre).
- Blooms: ink spreads from a point along a noise field over 12–48 frames, slowing as it spreads (ease out),
  edges feathered 2–6 px with tendrils.
- One accent: a single red `#B3261E` (or the song's own colour), used for at most one element per section.
- Negative space ≥ 60% of the frame in verses.

## Type

A light or regular serif with real italics, set modestly (4–7% of frame height), placed asymmetrically near the
ink, never centred in the void. Words written by the ink: the bloom reveals the word as a mask. Hero lines can
be handwritten as a stroke animation (path draw-on at the word's sung duration).

## Motion personality

Almost still. The camera drifts (1–3% over a phrase). Everything else is ink spreading on the voice: the vocal
stem's onsets start blooms; the vocal energy sets their speed.

## Sections

- Verse: one bloom per line, slow.
- Chorus: blooms overlap, ink fills more of the page, the accent appears.
- Bridge: the page goes almost fully black; type in paper-white knocked out.
- Outro: the ink dries and lightens; the last word stays.

## Build notes

Canvas or WebGL: a reaction-diffusion or noise-driven mask that grows from seeds, rendered deterministically
from timeline time (seeded noise, no `Math.random`). Type revealed by the same mask. Paper grain on top.

## How it goes wrong

Smoke-like blur instead of ink edges, too many blooms (busy), centred text in white space, a looped bloom
animation reused visibly.
