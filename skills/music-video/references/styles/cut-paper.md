# Cut paper

A diorama of cut and layered paper, lit from one side, built in depth. Warm, tactile, storybook.

## Medium

- 4–7 depth layers, each a flat paper colour with fibre texture (6–10%) and a torn or knife-cut edge.
- Shadow per layer: offset 3–8 px away from the key light, blur 6–14 px, opacity 18–30%; deeper layers cast
  larger, softer shadows.
- Palette: 5 paper colours sampled from a real paper swatch book feel: one dark (`#2E2A26`-ish), one light, three
  mid tones; low saturation (20–45%), one stronger accent paper.
- Slight paper curl: layers are not perfectly flat; a 1–2% gradient across each.
- Animation on twos for characters and props (stop-motion), smooth for the camera.

## Type

Cut-out letters (each glyph its own paper piece with shadow) for hero lines; a warm serif or a soft grotesk for
line sets. Letters arrive by sliding in from behind a layer or folding up from flat (rotateX 90°→0° with a 2-frame
settle).

## Motion personality

A slow camera truck across the diorama (parallax 0.3×/0.6×/1×), pop-up-book reveals on downbeats (pieces fold up
on their hinge), props on sticks (a slight 1–2° wobble while they move).

## Sections

- Verse: one set per line, the camera trucks to the next set on the phrase.
- Chorus: a pop-up spread that opens; each return adds layers.
- Bridge: lights off; a single torch-lit layer.
- Outro: the book closes on the opening set.

## Build notes

Each layer an SVG with an organic edge path (generate rough edges procedurally with noise on the path), the
fibre texture as a shared image with `multiply`, shadows as `filter: drop-shadow` sized from a light vector in
the spec. Characters as SVG rigs (limbs as separate pieces with pivots).

## How it goes wrong

Too many layers moving at once, perfect vector edges, drop shadows all the same, saturated colours (looks like
an app illustration rather than paper).
