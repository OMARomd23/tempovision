# The look: a design system with numbers

Adjectives are where generic output comes from. "Dreamy, cinematic, modern" leaves every choice open, and an
open choice gets the same default every time: a dark void, a glow, small centred text, everything fading in.
`SPEC.md` closes those choices with numbers before any scene is built. If a value you need is not in the spec,
add it to the spec first.

## SPEC.md, section by section

Use `templates/docs/SPEC.md`. What each part needs:

### Frame and time

`W×H`, fps (24 for filmic, 30 for type-heavy and social, never mixed), duration in seconds and frames, BPM,
frames per beat (`fps × 60 / BPM`), frames per bar. Safe areas: action 90%, title 80%; for 9:16, keep text out
of the bottom 20% and top 12% (platform UI).

### Palette

- 1 ground, 1 ink, 1 accent, at most 2 supporting colours. Hex values. Write where the accent may appear (for
  example "only on hero words and the chorus light").
- Contrast: body type against ground ≥ 4.5:1; hero type ≥ 3:1 and usually much more.
- **Palette from cover art**: `tempovision palette assets/cover.jpg` extracts dominant colours and reports contrast
  pairs. Start there when there is cover art; the video should feel like the record.
- Saturation is a decision: a palette whose colours are all above 80% saturation looks generated. Most
  palettes that look expensive have one saturated colour and everything else muted.
- One palette shift per film at most, on a section boundary, as a story beat (the bridge going cold, the last
  chorus gaining the accent).

### Type

See `typography.md`. In the spec: display face, weight, size in px (and as % of frame height), tracking,
leading; body or secondary face the same; the maximum words on screen; the lyric treatments by section.

### Medium and texture

Name the physical medium and give it numbers. Examples:

- Paper: base colour, fibre texture opacity 6–12%, a shadow of 2–6 px at 15–25% for cut layers, edge
  roughness.
- Print (riso, screen print): ink colours, misregistration 1–4 px per layer, halftone cell size, ink
  coverage noise.
- Film: grain 3–8% (luminance only), gate weave ≤ 1 px, halation on highlights, vignette 4–10%, black level
  lifted to 4–8%.
- Ink: bleed radius, wet-edge darkening, paper absorption.
- Glass/chrome: roughness, environment, highlight colour.

Texture is applied once, globally, at the end of the stack (`finishing.md`), not per element, so the frame
reads as one material.

### Light and depth

Key direction, shadow offset/blur/opacity, depth layers and their parallax ratios (for example background
0.3×, midground 0.6×, foreground 1×), depth of field if any.

### Motion

- Eases by role, as named curves: `enter`, `move`, `exit`, `camera`, `hit`. For example enter
  `cubic-bezier(0.16, 1, 0.3, 1)` (expo out), exit `cubic-bezier(0.7, 0, 0.84, 0)` (expo in), camera
  `cubic-bezier(0.45, 0, 0.55, 1)` (sine in-out), hit: none (instant).
- Springs as damping ratio and stiffness, used only on position and scale, never on opacity or colour.
- Durations in frames: enter 8–14, exit 6–10, camera 2–8 bars; staggers 2–4 frames per word.
- One hero move per shot; secondary moves 50–70% of its travel, starting 3–6 frames after; everything else
  still.
- The camera has a personality: locked off, handheld (noise of 2–6 px at 0.5–1 Hz), or slow dolly. Pick one per
  chapter.

### Composition

- The subject of a shot fills ≥ 40% of the frame's height or width. A small thing in the middle of an empty
  frame is not a shot.
- A grid (for example 12 columns, 96 px margins at 1080p) for type-led layouts; asymmetry is the default,
  centred is a choice that needs a reason.
- One focal point per frame; value contrast puts the eye there.

### Banned

Copy `banned.md`'s list and add anything this film must not become.

### QA frames

The frames that must be checked and what each must show: the first frame (it is the thumbnail on social
players), each section's first frame, each hero line, the chorus peak, the last frame.

## Turning words into numbers

| The word | Becomes |
|---|---|
| dreamy | palette under 40% saturation; soft edges (blur 2–6 px at the frame edge); slow pushes 1.00→1.06 over 4 bars; dissolves of 12–24 frames only at section changes |
| raw | hard cuts; grain 6–8%; misregistration 2–4 px; type set tight (−2% tracking) and large; no eases on cuts |
| cinematic | 2.39:1 or 1.85:1 letterbox inside 16:9 only if the whole film is framed for it; a key light direction; vignette 6%; 24 fps |
| energetic | layout change every bar in the chorus; hit list honoured; scale moves 8–20%; contrast high |
| intimate | close framing (subject ≥ 60% of the frame); one light; long holds (2–4 bars); type small and close to the subject |
| retro | a period medium with its real artefacts (VHS: chroma bleed 2–3 px, head-switch noise in the bottom 2%; 16 mm: gate weave, grain 8%, rounded corners) not just a filter |

## Colour and grade

Grade the whole film at the end, once, through one look (a LUT or a set of curves) so every source sits in the
same world. Footage and generated images from different sources need matching first: white balance, black
level, then the look. `finishing.md` has the order.
