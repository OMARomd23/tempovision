---
name: setup
description: Check and prepare this computer for making a music video with Tempovision. Lists what is installed and what is missing (Python/uv, FFmpeg, Node, HyperFrames or Remotion and their skills, Demucs stems, WhisperX lyric alignment, GPU, fal and Pexels keys, auto mode), explains what each unlocks, and installs what the person approves. Use it when the person asks to set up, check or repair Tempovision, before a first project, or when a tempovision tool reports something missing.
argument-hint: "[path to BRIEF.md]"
---

# Tempovision setup

Read `${CLAUDE_PLUGIN_ROOT}/skills/music-video/references/setup.md` first; it is the full procedure and the
install recipes.

1. Run the doctor. With a brief (inside a project, or the path in `$ARGUMENTS`):

   ```bash
   tempovision doctor --brief BRIEF.md --write SETUP.md
   ```

   Without one, check everything Tempovision can use:

   ```bash
   tempovision doctor --all
   ```

2. Show the result as three groups (Required, Recommended, Optional). For each missing item: what it unlocks for
   the person's video, the exact command or link, and the cost in time, disk and money.
3. Ask which installs to run (`AskUserQuestion`, multi-select, recommended items pre-listed first). Run the
   approved ones one by one and re-run `tempovision doctor` after each.
4. For API keys, give the exact steps (sign-up URL, where the key is, `/plugin` → Tempovision → configure) and never
   ask the person to paste a key into the chat.
5. Finish with the doctor's final table and, inside a project, `tempovision project gate G2 pass` once every
   Required item passes.

If `tempovision` is not on PATH, call `"${CLAUDE_PLUGIN_ROOT}/bin/tempovision"`.
