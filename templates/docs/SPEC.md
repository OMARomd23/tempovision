# Spec: {{title}}

Every adjective as a number. Build from this; check against this; change this first when the film changes.

```text
GOAL:     what the viewer feels at the end, one sentence
OUTPUT:   engine, W x H, fps
TIME:     duration s = frames; BPM; frames per beat; frames per bar
SAFE:     action 90%, title 80%; 9:16 text keep-out: top 12%, bottom 20%
```

## Palette

| Role | Hex | Where it may appear |
|---|---|---|
| ground | | |
| ink | | |
| accent | | only on … |
| support 1 | | |

Contrast: ink/ground = …:1, accent/ground = …:1. Palette shift (if any): at … because …

## Type

| Role | Face | Weight | Size px (% H) | Tracking | Leading | Licence |
|---|---|---|---|---|---|---|
| display / hero | | | | | | |
| line set | | | | | | |
| secondary | | | | | | |

- Max words on screen:
- Treatment by section: intro … / verse … / pre … / chorus … / bridge … / outro …
- Ad-libs:
- Read floor: 0.5 s + 0.3 s/word, never under one beat

## Medium and texture

- Medium:
- Texture layers with numbers (grain %, paper %, misregistration px, halftone cell px):
- Applied once at the end of the stack.

## Light and depth

- Key light direction; shadow offset / blur / opacity:
- Depth layers and parallax ratios:

## Motion

| Role | Curve | Duration (frames) |
|---|---|---|
| enter | | |
| move | | |
| exit | | |
| camera | | |
| hit | instant | 0 |

- Springs (position/scale only): damping …, stiffness …
- Staggers: on sung word times (default) / fixed … frames
- Secondary moves: 50–70% of hero travel, start 3–6 frames after
- Camera personality per chapter:

## Composition

- Grid:
- Subject ≥ 40% of the frame; one focal point
- Centred only when:

## Hits

- Which hits get a visual event (from SONGMAP hit list), and what kind:

## Banned

(copy from `references/banned.md`, plus this film's own)

## QA frames

| Frame | Time | Must show |
|---|---|---|
| first frame | 0.0 | a finished image (the thumbnail) |
| | | |
