# Swiss kinetic

International-style typography in motion: a strict grid, big grotesk type, flat colour fields, and layout
changes on the bar. Confident, rhythmic, made for dense lyrics.

## Medium

- A 12-column grid with 96 px margins at 1080p (64 px at 9:16 width), baseline grid 12 px.
- Flat fields: 2–3 colours plus black and white; the field colour changes only on section boundaries or on
  chorus downbeats.
- No texture, or a 2% paper grain if the brief wants warmth.

## Type

A neo-grotesk (one family, 2–3 weights), set flush-left, ragged right, sizes on a modular scale (for example
×1.333: 28, 37, 50, 66, 88, 117, 156, 208, 277 px). Hero words at 156–277 px. Numbers and section labels as
small secondary type in the margins (bar count, timestamp) for structure.

## Motion personality

Precise: everything moves on the grid, snaps to grid positions, uses one ease (`expo out` in 8–12 frames).
Layout changes on the bar in choruses (the text block jumps to a new grid area, rotates 90°, or scales up a step).
Word-by-word reveals exactly on sung times. Hard cuts between layouts; no dissolves.

## Sections

- Verse: lines flush-left in the left 7 columns, the right side holds a colour field or a single image.
- Chorus: word stack, one or two words per beat, each a step larger; the whole frame flips colour on the
  downbeat of each bar.
- Bridge: one word, tiny, alone in a corner.

## Build notes

Define the grid and the modular scale as CSS variables or TS constants from the spec; place by column index
only. Use the downbeats export to drive layout state changes.

## How it goes wrong

Breaking the grid without reason, more than one ease, colour changes on every beat (strobe), centred type.
