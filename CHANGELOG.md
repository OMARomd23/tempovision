# Changelog

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
