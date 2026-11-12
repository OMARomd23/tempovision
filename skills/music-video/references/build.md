# Building the film

## Project layout

`tempovision project init` creates:

```text
<project>/
  tempovision.json            state: phase, gates, autonomy, engine, budget, decisions, sections
  BRIEF.md SETUP.md SONGMAP.md TREATMENT.md SPEC.md SHOTLIST.md REVIEW.md
  input/                  untouched originals: song, lyrics, the person's references (never modified)
  analysis/               audio.json, songmap.json, stems/, plots/
  lyrics/                 timing.json and its exports, preview.mp4
  assets/                 fonts/ images/ footage/ textures/ sfx/ generated/ refs/  + LEDGER.json
  prompts/                STYLE.txt and per-shot prompts for generation
  frames/                 styleframes/ sheets/
  video/                  the engine project (HyperFrames or Remotion)
  renders/                drafts/ final/
  qa/                     QA reports
```

The whole folder is a git repository from `init`; `input/`, `renders/` and `analysis/stems/` are git-ignored
(large files).

## Choosing the engine

| | HyperFrames | Remotion |
|---|---|---|
| Authoring | HTML + CSS + GSAP, one file per scene | React components |
| Strengths | fast iteration, free-form art direction, shaders/canvas/Three.js, built-in `check`, `snapshot`, audio tools, Studio editing for the person | huge ecosystem, `@remotion/captions`, Lottie, 3D, typed data, precise frame maths |
| Needs | Node ≥22, Chrome (bundled), FFmpeg | Node ≥18; a company licence for teams of 4+ |
| Pick when | the default; type-led and illustrative films | the person or their team already uses React/Remotion, or the film needs a library only Remotion has |

Record the choice in `tempovision.json` (`tempovision project set engine hyperframes`). Then load the engine's skill
and follow its contract to the letter: `/hyperframes` (and `/hyperframes-cli`, `/hyperframes-registry`,
`/media-use` as it directs) or `/remotion-best-practices`. Where Tempovision and the engine skill disagree on an
engine mechanic, the engine skill wins. Where they disagree on music-video craft, Tempovision wins.

### Scaffolding

```bash
# HyperFrames
npx hyperframes init video --skip-skills --skill=hyperframes
# Remotion
npx create-video@latest video --blank
```

Vendor every script the scaffold loads from a CDN (HyperFrames loads GSAP from jsDelivr) into
`video/assets/vendor/` and reference it locally: renders must not depend on a network at render time
(`setup.md` "When the network is restricted").

Copy the song into the engine's assets (`video/assets/song.wav` or `video/public/song.wav`) as the one
`<audio>` / `<Audio>` source. Never place sound effects over the master unless the brief says so.

## Timing into the engine

Never type a lyric time or a beat time by hand. Export them:

```bash
tempovision timing --engine hyperframes   # video/assets/tempovision/{lyrics,beats,sections}.json + lyrics.html snippet
tempovision timing --engine remotion      # video/src/tempovision/{timing.ts,tempovision.ts}
```

- **HyperFrames**: `lyrics.html` contains one timed element per line (and per word inside it) with ids,
  `class="clip"`, `data-start` and `data-duration` from the alignment, ready to paste into the captions
  sub-composition and style. Beats and sections are JSON the scene scripts can read at build time, or values to
  copy into `data-start`. Times are snapped to the frame grid at the project fps.
- **Remotion**: `timing.ts` exports typed `LYRICS`, `BEATS`, `DOWNBEATS`, `SECTIONS`, `FPS`; `tempovision.ts` has
  helpers: `sec(frame)`, `frameAt(seconds)`, `activeLine(frame)`, `wordProgress(word, frame)`,
  `beatPulse(frame, {decay})`, `barIndex(frame)`, `sectionAt(frame)`.

Re-run the export after any alignment fix; the build reads the new times on the next render.

## The section loop

Build in song order, one section at a time. For each section:

1. Re-read its rows in `SHOTLIST.md` and the spec values it uses.
2. Build the shots. One scene (sub-composition or component) per shot or per tightly linked shot group, named
   after the shot list (`c1-03-home-stage`).
3. Lint: `npx hyperframes check --json` (fix every error, weigh every warning) or `npx tsc --noEmit` and a
   Remotion still render.
4. Look: render a draft of the section (`renders/drafts/<section>.mp4`), then
   `tempovision sheet renders/drafts/<section>.mp4 --section <name> --offset <section start s>` stills its key
   frames (first frame, each lyric line's arrival, each hit, last frame) into `frames/sheets/<section>.png`.
   In HyperFrames, `npx hyperframes snapshot` is the engine-native equivalent and needs no render; use either.
5. Compare against `SPEC.md` and the shot list: every value that differs is a note. Fix.
6. Lock: `git commit -am "<section>: locked"` and `tempovision project section <section> locked`.

A section's first build should be complete but plain: layout, type, timing, the hero move. Texture, grain and
grade come once, at the end, over the whole film.

The first chorus is built with the most care: every later chorus starts as a copy of it and escalates.

## Style frames (phase 4)

Style frames are real compositions in the engine, not mockups: build each as its own short composition (2–4 s)
at the exact frame of the song it represents, with final type, palette and medium. Still them
(`npx hyperframes snapshot --at <s>` or `npx remotion still`), save to `frames/styleframes/`, run the critic,
then show the person. Approved style frames become the first scenes of the build.

## Rendering

- Drafts: half resolution or the engine's draft quality, to `renders/drafts/`. Use them for QA timing and
  sheets.
- Final: full resolution, high quality, to `renders/final/master_video.mov` (or `.mp4`), without trusting the
  engine's audio encode: `tempovision deliver` muxes the master audio afresh.
- Long renders run in the background; keep working on the next section meanwhile, or on the delivery notes.
- One render at a time, with few workers on a 16 GB machine (`--workers 2` for HyperFrames): two renders side by
  side, or a preview open during a render, can exhaust memory and get a render killed mid-way. Check free disk
  before a ProRes render.
- Before a final render, `git status`: the preview's editor writes what you drag into the composition files.
- Transitions between segments: during a wipe or a dissolve the outgoing side must keep showing the previous
  shot. When shots are chained on one board, the next shot's elements may start drawing before its start time
  and flash under the transition; read the frames either side of every transition on a sheet.

## When the engine is not enough

- Heavy generative visuals (fluid, particles in the hundreds of thousands): render them as a separate pass
  (Three.js/WebGL inside HyperFrames, or a dedicated tool) to an intra-frame video, then composite.
- 3D scenes: Three.js in either engine; Blender only if the person has it and the brief needs it.
- Footage editing: trims, speed ramps and reframes belong to the engine; heavy treatment (denoise, upscaling,
  stabilisation) is done to the clip before it enters the edit.
