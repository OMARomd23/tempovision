# Tempovision

**A music video studio for Claude Code.** Give it your song and your lyrics. It interviews you like a director,
tells you exactly what to set up, maps the song (stems, beats, bars, sections, word-level lyric timing), writes
treatments and a design spec with numbers instead of adjectives, sources or generates assets with their licences
recorded, builds the film section by section in HyperFrames or Remotion, checks its own work with measured QA
and a fresh-eyes critic, and delivers masters for each platform.

Tempovision is built around one honest constraint: **Claude can't hear your song and can't watch video in real
time.** So everything that matters is measured (where every word is sung, where every bar starts, whether the
render's audio is the master and in sync, whether a lyric appears when it is sung), and the few things only a
human can judge (does the karaoke preview land? do the style frames feel like the song?) are put in front of you
at the moments where a wrong guess would cost hours.

```text
 1 Interview ─▶ 2 Setup checklist ─▶ 3 Song map ─▶ 4 Treatment · spec · style frames ─▶ 5 Assets ─▶ 6 Build ─▶ 7 Review ─▶ 8 Deliver
   BRIEF.md      SETUP.md             SONGMAP.md     TREATMENT.md SPEC.md SHOTLIST.md     LEDGER.json  video/     qa/ notes   masters + REVIEW.md
   (G1, always)  (G2, always)         (G3 preview)   (G4 style frames)                                            (G5 rough cut)
```

## Install

```bash
# In Claude Code
/plugin marketplace add OMARomd23/tempovision
/plugin install tempovision@tempovision
```

Or from a local clone: `claude --plugin-dir /path/to/tempovision`.

Then, in any folder: *"Make a music video for my song"*, or `/tempovision:music-video ~/Music/song.wav ~/Music/lyrics.txt`.

Requirements, which the setup step checks and helps install: [uv](https://docs.astral.sh/uv/), FFmpeg ≥ 6 (with
libass and libx264), git, Node ≥ 22 for HyperFrames (≥ 18 for Remotion). Stems and lyric alignment download
PyTorch and models on first use (~3 GB); an NVIDIA GPU or Apple Silicon makes them faster, the CPU works.

Optional keys, entered in the plugin settings (`/plugin` → Tempovision → configure), never in chat:

- **fal** for generated images and footage, image-to-video and upscaling (pay per use, capped by the budget in
  your brief).
- **Pixabay** or **Pexels** (both free; either is enough) for stock footage and photo search. Get a Pixabay key
  by logging in at [pixabay.com/api/docs](https://pixabay.com/api/docs/). Openverse, NASA, The Met, the Art Institute of Chicago and
  Wikimedia Commons work without keys.

## What's inside

| Part | What it does |
|---|---|
| `skills/music-video` | The director: eight phases with gates, the rules that keep it professional, and 12 craft references (interview, setup, audio, story, look, typography, assets, build, review, finishing, banned defaults) plus 7 worked style recipes |
| `skills/setup` | `/tempovision:setup`: checks the machine, turns the brief into a Required / Recommended / Optional checklist, installs what you approve |
| `skills/lyric-sync` | `/tempovision:lyric-sync`: word-level lyric timing on its own, exported as SRT, LRC, ASS karaoke, HyperFrames or Remotion captions |
| `skills/review` | `/tempovision:review`: measured QA, review sheets, fresh-eyes critic, ranked notes |
| `agents/critic` | Reviews frames against the spec without seeing the code or the builder's reasoning |
| `agents/asset-scout` | Searches several asset categories in parallel and returns licence-checked shortlists |
| `hooks/` | Resumes the project at session start; blocks any change to your original files in `input/`; in full autonomy, keeps the production going until it is delivered or truly needs you |
| `.mcp.json` | fal (generation) and Pexels (stock) MCP servers, fed by the plugin settings |
| `bin/tempovision` | One command for every tool (on PATH while the plugin is enabled) |
| `data/` | Asset sources with licences and APIs; delivery presets per platform |
| `templates/` | Brief, spec, treatment, shot list, setup and delivery-note templates; Remotion timing helpers; a browser tap tool for when alignment needs a human |

### The tools

```text
tempovision project   init · status · import · phase · gate · set · decide · wait · resume · spend · section · autopilot
tempovision doctor    machine check; BRIEF.md → SETUP.md checklist; --network probes
tempovision analyze   tempo, beat grid through beat-less intros, downbeats, bars, sections (A/B/C by similarity),
                  energy and onsets per stem, key, LUFS/true peak, overview plot; --quick for the interview
tempovision stems     Demucs vocals / drums / bass / other
tempovision align     the artist's lyrics → word timing: CTC forced alignment (wav2vec2) → transcript-anchored →
                  stable-ts → imported (LRC/SRT/taps) → heuristic; QA flags; preview, inspect, range, nudge, exports
tempovision songmap   SONGMAP.md: sections named from lyric tags, bars, frames, energy, hooks, hit list, gaps
tempovision timing    lyrics, beats, sections, hits → HyperFrames (data + a lint-clean lyrics composition) or
                  Remotion (typed timing.ts + helpers), frame-snapped, with a cue manifest for QA
tempovision palette   colours from cover art, roles, contrast pairs; --check two colours
tempovision sheet     contact sheets: grid, frame-by-frame range, a section's key frames, review set (beats, cuts, phone)
tempovision qa        format, audio present, A/V offset vs master, loudness vs master, black, freeze, first frame,
                  cuts vs beats and sung words, lyric cues (stale exports, nothing appearing when a line is sung)
tempovision assets    licence ledger: add, fetch, search (Openverse, Pexels, Pixabay, NASA, Met, AIC, Commons), check, credits
tempovision deliver   ProRes master, YouTube, vertical, square, Spotify Canvas, thumbnail, poster from the final
                  render + the untouched master audio; each file re-checked for duration and sync
```

## Autonomy

In the interview you choose how often Tempovision stops:

- **Checkpoints** (default): the brief, the setup, the treatment pick, the style frames, the rough cut.
- **Guided**: after every phase.
- **Full**: after the brief and setup it runs to the finished video. A stop hook keeps the session working until
  delivery (with a continuation budget), every call made without you is logged, and the delivery note lists them.
  Pair it with Claude Code's auto mode (`claude --enable-auto-mode`) in a dedicated folder.

Whatever you choose, it always stops before spending beyond your budget, touching your original files, or
publishing anything.

## Tests

```bash
uv run tests/run_tests.py          # synthesises a song with known beats, sections and word times, then runs
                                   # project → analyze → align → songmap → timing → sheet → qa → assets → deliver → hooks
uv run tests/test_ctc.py           # forced alignment recovers known word starts from a synthetic emission
```

Plugin structure: `claude plugin validate .`. Behaviour evals (does the interview happen before any build, does
setup list what the brief needs, does lyric sync trigger) live in `evals/` and run with `claude plugin eval .`.

## Privacy

Tempovision runs on your machine. It sends nothing anywhere by itself. Your song and lyrics are processed locally
(stems, alignment, analysis, renders). Network calls happen only when you use a service: the fal MCP server when
you approve generation (prompts and reference images go to fal, under [fal's terms and privacy
policy](https://fal.ai/privacy)), Pexels, Pixabay and the open archives when searching for assets, and the package and model
hosts during setup.

## Licence

MIT. Tempovision orchestrates other tools under their own licences: Demucs (MIT), WhisperX (BSD-2), wav2vec2 models
(per model), stable-ts (MIT), HyperFrames (Apache-2.0), Remotion (Remotion licence: free for individuals and
companies up to 3 people), the fal, Pexels and Pixabay services (their terms). Assets you use are governed by their own
licences, recorded per file in your project's ledger.
