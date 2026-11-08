# Review: measure, look, then fresh eyes

You built the film, so you know what it is meant to be; the viewer sees it once, at full speed, often on a phone.
Review is how you see it as they will. Run it on every full draft and after any change that moves timing or
layout.

## 1. Measure

```bash
tempovision qa renders/drafts/draft.mp4
```

Checks, each PASS / WARN / FAIL with numbers, written to `qa/<render>.json` and `.md`:

| Check | What it measures | Fails when |
|---|---|---|
| `format` | resolution, fps, duration vs the spec and the song | wrong size or fps; duration off by > 1 frame |
| `audio_present` | an audio stream with signal | missing or silent |
| `av_offset` | cross-correlation of the render's audio with the master | offset > 1 frame |
| `loudness` | integrated LUFS and true peak of the render's audio | differs from the master by > 0.5 LU (the master was altered) |
| `black` | frames that are ≥ 99.8% black (a lyric on a dark ground is not black) | black ≥ 3 s or on the first frame; shorter black stretches are WARN |
| `freeze` | stretches where nothing on screen changes | WARN at ≥ 3 s (a dead stretch) unless it is a deliberate hold |
| `cuts_vs_beats` | scene cuts detected in the picture vs beats/downbeats/sections | report only: % of cuts within ±1 frame of a hit, and cuts landing mid-word |
| `lyric_cues` | the engine's cue manifest vs `lyrics/timing.json`, and whether the picture changes where each line starts being sung | the export is stale (re-aligned since `tempovision timing`), or a cue is early by > 2 frames or late by > 1 frame; WARN when nothing changes on screen within −4/+3 frames of a line's first word |
| `first_frame` | luminance and detail of frame 0 (the social thumbnail) | empty or black |

The cue manifest is written by the timing export (`video/assets/tempovision/cues.json` or `src/tempovision/cues.json`).
It catches the commonest sync bug, a build still using times from before a re-alignment or a nudge. The visual
part catches a line that is sung while nothing on screen responds. If you changed a cue inside the engine on
purpose, add `{"id": "l12", "why": "..."}` to the manifest's `overrides`.

Numbers win over your eye when they disagree: a cue 3 frames late looks fine on a sheet.

## 2. Look

```bash
tempovision sheet renders/drafts/draft.mp4 --mode review
```

Writes three sheets in `frames/sheets/`: **beats** (each section start, each hero line, each chorus downbeat),
**cuts** (a strip −0.2 s to +0.2 s around every detected cut), and **phone** (the beat frames at 360 px wide).
Open all three. Then for the hero move of each section, `tempovision sheet <video> --range 72.0,74.0 --frames 8`.

For each beat frame, first describe it in one sentence as a stranger would, naming everything you see. Anything
you would have to explain is a problem. Then go through the sheets once per question:

| Question | What it catches |
|---|---|
| Does it read? | text too small or too short, low contrast, type over busy areas, words cut by the frame |
| Is there one focal point? | two things competing, the eye with nowhere to go, subject too small |
| Does it match the spec? | palette, faces, sizes, medium, eases that drifted |
| Is it the song? | a picture that could belong to any song; a hero line set like any other line |
| Does it escalate? | the third chorus no bigger than the first |
| Tells | anything in `banned.md` |
| Phone | every line meant to be read is readable at 360 px |

## 3. Fresh eyes

Dispatch the `tempovision:critic` agent with only `SPEC.md`, `SHOTLIST.md`, `BRIEF.md` (summary) and the sheet
paths. It has not seen your code or your reasoning, so it judges what is on screen. Keep fixing to yourself.

## 4. Notes and fixes

Write every problem as one line: `t=52.4s · c1-03 · problem → exact change · what stays`. Rank them:

- **P0** breaks the read or the brief: unreadable, wrong words, out of sync, a banned tell in a hero shot,
  a licence problem.
- **P1** weakens the film: a dead stretch, a soft chorus arrival, a cut that jumps, a hero line without its idea.
- **P2** polish.

Fix all P0 and the P1s worth their time: words and sync first, then timing, then layout, then detail. Re-measure
and re-sheet only what changed. A second full pass only when a P0 was open. Never score the film out of 10.

When a fix does not hold, sheet the frames either side of the problem, list every difference, and change the
one cause. When the film feels busy, remove a third of the motion and keep the moves that lead the eye.

## 5. The rough cut (G5)

Send the draft with: what changed since the style frames, the three things you are least sure of, and one
question. In `full` autonomy, skip sending and go straight to finishing, recording the open doubts for
`REVIEW.md`.
