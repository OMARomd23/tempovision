# Changelog

## 0.3.0 (2026-11-12)

Lessons from producing *Deux Faces* (Darija rap, 2:33, a canvas-chalk film with painted clips, delivered in 16:9
and 9:16).

- **deliver (bug fix):** the vertical and square files took their audio from the main render's `--range`
  (default 0 s), so a 9:16 cut of 70.8–101.8 s was delivered with the song's first 31 s, and the sync check,
  comparing that file with the master at the same wrong offset, reported +0 ms. Now each render is placed in the
  song from `--vertical-range` / `--square-range` or by matching its own audio against the master; a silent render
  without a range is refused; sync is measured against the render's own audio track to half a frame, and a render
  without audio is reported as unmeasured. Also: a `--master` that measures off the project's song is refused, a
  free-space check runs before writing, and excerpts get a 15 ms fade-in.
- **master (new):** `tempovision master compare | align | locate`. Measures a new mix against the song the film was
  timed to with 1 ms onset envelopes (they match across different mixes; confidence is the peak's prominence),
  writes an aligned 24-bit WAV, and finds where an excerpt sits in the song. The new mix of Deux Faces sat 27 ms
  early (the old MP3's encoder delay).
- **analyze:** the detected tempo is checked against its relatives (×2, ×½, ×¾, ×4/3, ×3/2, ×2/3) by how much
  onset strength lands on their beats versus between them, on the drum stem when present. Deux Faces was read as
  99.4 BPM; it is a steady 75 (now detected as 74.95 BPM, 48 bars, matching the hand-fitted grid).
  `tempo.candidates`, `tempo.corrected_from`, `tempo.ambiguous`; `--bpm` forces a tempo.
- **align:** a new `mms` method (Meta's MMS forced aligner, 1,100+ languages, romanised text, a wildcard before
  each line for unwritten vocals; Arabizi digits read as letters), tried after `forced` in auto mode. It and
  `stems` install CUDA PyTorch on Windows and x86-64 Linux, so an NVIDIA GPU is used (PyPI's torch there is
  CPU-only). `doctor` counts an MMS install as an alignment model.
- **tests:** the suite runs on Windows; new tests for excerpt delivery, new-mix alignment, the tempo check and the
  MMS route (16 → 20 tests).
- **skill:** the person's own artwork is canon (animate it, never redraw it; reject clips that change it);
  first-and-last-frame generation to stop image-to-video drifting photographic; generate at the delivery
  resolution; knock-out type spacing; no clipped words on held frames; end credits asked at the interview;
  measured on-screen word checks for code-drawn lyrics; new mixes, disk space, one render at a time, the preview
  editor writing into the composition, safe cleanup that never deletes paid generations.

## 0.2.0 (2026-11-08)

- Renamed from Cadence to Tempovision.
- Pixabay as a second stock footage and photo source: a *Pixabay API key* plugin setting,
  `tempovision assets search --source pixabay [--type video]` with the 24-hour result cache Pixabay's API terms
  require, and Pixabay in `doctor`, the source catalogue and the asset-scout agent. Pexels stays as it was.
- The session-start hook now passes the Pexels and Pixabay keys from the plugin settings to `tempovision`
  commands; before, `--source pexels` only worked with `PEXELS_API_KEY` set in the shell.

## 0.1.0 (2026-11-07)

First release.

- Director skill with eight phases and five gates (brief and setup always gated), autonomy levels, and 12 craft
  references plus 7 style recipes.
- Tools: project state, doctor (brief → setup checklist), analyze (beat grid, downbeats, sections, stems energy,
  key, loudness), stems (Demucs), align (CTC forced alignment of the artist's lyrics with fallbacks, QA, preview,
  inspect, range re-align, nudge, LRC/SRT/ASS/HyperFrames/Remotion exports, tap tool), songmap, timing export,
  palette, contact sheets, measured QA, asset ledger and search, delivery.
- Agents: critic (fresh eyes), asset-scout (parallel licensed sourcing).
- Hooks: session resume, protection of input/ originals, full-autonomy stop guard.
- MCP: fal and Pexels, configured from plugin settings.
