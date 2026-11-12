# Finishing and delivery

## The finishing stack, in order

Applied once, over the whole film, in the engine's final composition (or as a pass over the render):

1. **Match** sources: footage and generated material balanced to the same white point and black level before
   the look.
2. **Look**: one grade for the film (a LUT or curves). In HyperFrames use `npx hyperframes media-treatment` for
   footage (its skill says how); in Remotion, CSS/WebGL filters on the root or a LUT pass with FFmpeg's
   `lut3d`.
3. **Texture**: grain (luminance, 3–8%, animated every frame, scaled to the delivery resolution), paper or print
   texture if the medium has one. Grain goes on top of everything, type included, so the type sits in the
   world.
4. **Optics**, only if the medium has them: halation, vignette (4–10%), gate weave, chromatic aberration
   (≤ 1 px at the edges, never on type centre).
5. **Motion blur** on fast moves (engine motion blur or shutter-angle sampling at 180°). Type moving faster than
   about 1/10 of the frame per frame without blur strobes.

Check a still before and after each layer at 100% and at phone size; each layer should be felt, not seen.

## Audio

The person's master is the soundtrack, untouched. No normalising, compression, EQ or fades unless the brief
asks for them (a fade on a cut-down edit is fine, ≥ 0.5 s, recorded). `tempovision deliver` takes the picture from
the render and the audio from `input/`, and encodes it once per deliverable.

Loudness: streaming platforms normalise playback (YouTube, Spotify and others reference around −14 LUFS
integrated). Do not chase a number; report the master's measured LUFS and true peak in `REVIEW.md`, and warn
the person if true peak is above −1 dBTP, which can distort after the platform's lossy encode.

## Deliverables

`tempovision deliver --targets master,youtube,vertical` writes each file listed in `data/platforms.json` that the
brief asks for, then probes it and checks duration and sync again:

- `master`: ProRes 422 HQ (`.mov`) at full resolution with 24-bit PCM audio, the archive and the source for any
  platform later.
- `youtube`: H.264 High profile, CRF 16–18 (or 4K at the master's size), `yuv420p`, AAC-LC 320 kbps 48 kHz,
  `+faststart`.
- `vertical`: 1080×1920 from the 9:16 composition, never a centre crop of the 16:9 unless the spec designed
  the framing for it; same codec settings. The 9:16 cut is usually an excerpt: deliver places it in the song from
  `--vertical-range START` (the song time of its first frame) or by matching the render's own audio. A silent
  render without a range is refused rather than given the song's opening. Check `song_start` in
  `DELIVERY.json`.
- `canvas`: Spotify Canvas, 9:16, 3–8 s, no audio, a seamless loop cut from the film or designed for it.
- `thumbnail`: a designed still (the hero frame, the title set in the film's type), 1280×720 JPEG under 2 MB,
  plus `poster` (the first frame) and a 1080×1920 vertical cover.

Platform specifics change: re-check the platform's current upload spec when the person names a platform and
update `data/platforms.json` if it moved.

Sync is measured against the render's own audio track (the picture's timeline), to half a frame. A render without
audio can't be measured that way: `DELIVERY.json` says `sync_ok: null` and the note says "placed, not measured".

**A new mix or master.** When the person sends a new mix after the film is built, it must sit exactly where the
old one did: `tempovision master compare NEW` measures it against the song the film was timed to (an MP3 source
usually carries 20–60 ms of encoder delay that a WAV doesn't), `tempovision master align NEW` writes the
corrected file, and `tempovision deliver ... --master audio/NEW.aligned.wav` refuses a master that measures off.
The person's file itself stays untouched.

**Disk space.** ProRes 422 HQ at 1080p is ~27 MB/s (4 GB for a 2:30 song), and an intermediate render the same
again. `deliver` checks free space before it writes. On a nearly full disk, render H.264 at CRF 12 and skip the
ProRes master, and say so in the note.

## The delivery note: REVIEW.md

From `templates/docs/REVIEW.md`:

- What was made: the files, their specs, where they are.
- The creative calls: the treatment chosen and the two not built; every decision made without the person
  (from `tempovision.json` decisions).
- What was measured and what was only looked at; what nobody checked (it was measured, not heard).
- The weakest shot, and what you would change with more time.
- QA warnings kept on purpose, and why.
- Credits and licences: every asset from the ledger that needs attribution, ready to paste into the video
  description; every generated asset's model; total generation spend.

Then send the masters, one line each, and offer the one next step that matters (a 9:16 cut, a Canvas loop, a
teaser).

Tell the person how to watch the film before it renders: the engine's live preview (`npm run dev` in `video/`
for HyperFrames, `npx remotion studio` for Remotion), with one warning: dragging anything in the preview's editor
writes into the composition (a stray `translate` on the canvas moves the whole film). `git status` before every
render shows such edits.

## Cleaning up

When the person asks to free space, delete only what can be made again for free, largest first: drafts,
intermediate renders once the finals are written, frame caches and contact-sheet scratch, the engine's preview
caches, then stems (slow to remake; ask). Never delete `input/`, the finals, the ledger, or anything that cost
money: generated stills and clips, upscales. List what will go and its size before deleting.
