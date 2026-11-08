# Light type

The words are made of light: projected, refracted through glass, reflected on wet streets, smeared by long
exposure. Dreamy, nocturnal, sensual, for R&B, ambient, synth and night-drive songs.

## Medium

- A real dark scene, never a void: a wall, a curtain, water, glass, fog with structure. The ground has texture
  and a light gradient (key light falling off over the frame).
- Light behaves physically: additive blending, falloff, soft bloom limited to real highlights (threshold above
  the 90th percentile of luminance), colour fringing through glass.
- Palette: 2 light colours at most (for example sodium `#FFB35C` and a cyan `#5CE1FF`) over a ground with
  10–20% value so blacks are not crushed.

## Type

A clean grotesk or a high-contrast serif, set as light: emitted from a source (a projector beam, a neon tube
seen out of focus, a reflection on a surface). Hero lines exposed like long-exposure light painting (a path
traced over the line's duration).

## Motion personality

Slow camera drifts; focus pulls between the type and the world (blur 0→8 px in 12–24 frames) on phrase
boundaries; the light breathes with the vocal energy (intensity ±10–20%, smoothed ≥ 200 ms).

## Sections

- Verse: the type is a reflection or projection on a surface in the scene.
- Chorus: the light source enters frame, the whole scene brightens, the type becomes the light itself.
- Bridge: darkness with one moving source.

## Build notes

WebGL/Three.js or canvas with a render pass for light (additive, blur pyramid for bloom); seeded,
timeline-driven. Surfaces from real photos (wet asphalt, frosted glass) or procedural. Keep bloom out of the type
edges so the words stay sharp.

## How it goes wrong

Neon glow on everything (the banned glow), pure black ground, bloom on all values, colours outside the two
lights.
