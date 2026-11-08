---
name: lyric-sync
description: Get word-level timing for a song's lyrics: align the person's lyric text to their recording and export SRT, LRC, ASS karaoke, HyperFrames caption JSON or Remotion captions, with a karaoke preview video to check by ear. Use it whenever someone wants synced lyrics, karaoke timing, an LRC file, lyric timestamps, captions for a song, or word timings for an animation, even outside a full music video project.
argument-hint: "[song file] [lyrics file]"
---

# Lyric sync

Read `${CLAUDE_PLUGIN_ROOT}/skills/music-video/references/audio.md` ("Lyric alignment" and "When alignment
fails").

1. Get the song (the master, not a phone recording) and the lyrics as sung with every repeat written out. If the
   lyrics have no repeats written out but the song clearly repeats a chorus, ask.
2. Inside a Tempovision project, use it. Outside one, make a light workspace:

   ```bash
   tempovision project init "<title>" --song "<song>" --lyrics "<lyrics>" --light
   ```

3. Separate the vocal (much better alignment), then align and preview:

   ```bash
   tempovision stems --only vocals
   tempovision align
   tempovision align --preview
   ```

4. Read the `qa` block in `lyrics/timing.json`. Inspect and fix flagged lines (`--inspect`, `--range`,
   `--nudge`) before sending anything.
5. Send `lyrics/preview.mp4` and ask the person to note any early or late lines; you cannot hear it.
6. Export what they need: `tempovision align --export srt,lrc,ass,hyperframes,remotion` (all are written by
   default into `lyrics/`). Send the files with one line each.

State the method used (`forced`, `anchored`, `stable-ts`, `imported`, `heuristic`) and its confidence; never
present heuristic timing as word-accurate.
