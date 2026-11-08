---
name: review
description: Review a rendered music video or lyric video draft like a director before anyone else sees it. Runs measured QA (sync against the master audio, loudness, black and frozen frames, cut timing against beats, lyric cue timing), builds review contact sheets, dispatches the fresh-eyes critic, and writes ranked P0/P1/P2 notes. Use it when the person asks to review, check, QA or critique a render, or after any full draft in a Tempovision project.
argument-hint: "[render path]"
---

# Review a draft

Read `${CLAUDE_PLUGIN_ROOT}/skills/music-video/references/review.md` and
`${CLAUDE_PLUGIN_ROOT}/skills/music-video/references/banned.md`, then:

1. Pick the render: `$ARGUMENTS`, or the newest file in `renders/drafts/`.
2. Measure: `tempovision qa <render>`. Read `qa/<render>.md`. Every FAIL is a P0.
3. Look: `tempovision sheet <render> --mode review`. Open the beats, cuts and phone sheets. Describe each beat frame
   in one sentence as a stranger would.
4. Fresh eyes: dispatch the `tempovision:critic` agent with the paths of `SPEC.md`, `SHOTLIST.md`, a three-line
   brief summary you write, and the three sheets. Do not send code or your own notes.
5. Merge your notes and the critic's into one ranked list in the format
   `P0 · t=… · shot · problem → exact change · what stays`, de-duplicated, and write it to
   `qa/NOTES-<render>.md`.
6. Outside a project (a video without Tempovision data), run only `tempovision qa <render> --master <audio>` if the
   person gives the song, the sheets, and the critic with whatever spec they describe.

Report the P0 count, the P1 count, the three most important notes, and what you will fix first. Do not claim
anything was checked that a command did not check.
