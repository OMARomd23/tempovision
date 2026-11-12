# Mapping the song

Everything you will cut, move and set later is timed from here. You cannot hear the song, so this map is your
ears: make it accurate and read it often.

## Order and outputs

```bash
tempovision stems            # analysis/stems/{vocals,drums,bass,other}.wav   (Demucs htdemucs)
tempovision analyze          # analysis/audio.json + analysis/plots/overview.png
tempovision align            # lyrics/timing.json (+ hyperframes, remotion, srt, ass, lrc exports)
tempovision songmap          # SONGMAP.md + analysis/songmap.json
tempovision align --preview  # lyrics/preview.mp4 for the person to check by ear
```

Always open `analysis/plots/overview.png` after `analyze`: it shows the waveform, the energy curve per stem,
the beat grid and the section boundaries on one time axis. It is the single best picture of the song you get.

## What `audio.json` holds

- `tempo.bpm`, `tempo.confidence`, `tempo.stable` (whether the tempo holds through the song).
- `beats[]` (seconds), `downbeats[]` (bar starts), `bars[]`, `beats_per_bar`.
- `onsets.{full,vocals,drums,bass,other}[]` with strengths: the attacks the ear hears.
- `energy.{full,…}` as RMS in dB, sampled at 10 Hz, plus `energy.smooth` (1 s window).
- `sections[]`: `start`, `end`, `label` (A, B, C… by similarity: repeated material gets the same letter),
  `energy_db`, `density` (onsets per second), `vocal_presence` (share of time with vocals).
- `moments[]`: drops, breaks, the loudest bar, the quietest bar, sudden silences.
- `key` (estimate), `duration`, `sample_rate`, `loudness.integrated_lufs`, `loudness.true_peak_db`.

## Trust and doubt

- **Beats** are reliable on rhythmic music with drums. On rubato, ambient or acoustic stretches the tracker
  invents a metronome, often at double or half tempo: `tempo.confidence` below 0.5 or `tempo.stable: false`
  means cut on phrases and onsets there, not on the grid. Compare the beat grid to `onsets.drums` in the plot.
- **Related tempi.** The tracker can lock onto a relative of the real tempo: ×2, ×½, and on half-time rap
  beats ×4/3 (a 75 BPM song read as 99 BPM). `analyze` scores each relative by how much onset strength lands
  on its beats versus between them, on the drum stem when it exists (run `tempovision stems` first). A clearly
  better relative replaces the detection (`tempo.corrected_from`); a close one sets `tempo.ambiguous` with the
  candidates. When ambiguous, look at the drum onsets on the overview plot, ask the person to tap a bar, and
  force it with `tempovision analyze --bpm 75`. Count the bars too: sections come in 4s and 8s.
- **Downbeats** are estimated from where accents fall. Check them against the first chorus and a section
  change: a bar boundary should land on each. If they are a beat off, `tempovision analyze --downbeat-offset 1`.
- **Section labels** group by sound, not by meaning. Rename them with the lyrics in hand (`songmap` does a first
  pass: the section whose lyric repeats most is the chorus). Check boundaries against the vocal energy.
- **Energy** is what the edit follows: cut density, scale of movement, how much of the frame is lit.

## The hit list: which beats get a visual hit

Not every beat. In order of priority:

1. Section boundaries (always a change: a cut, a new layout, a held breath).
2. Downbeats of the chorus (a layout change every bar or every two bars).
3. Strong drum onsets in high-energy sections (top 15% by strength), at most one hit per beat.
4. The first word of each hero line.
5. Silences and drops: a hold or a hard cut to black counts as a hit.

Timing of a hit: a move that must land starts 40–190 ms before the hit and arrives on it; the hit itself is
instantaneous (no ease into the impact frame). A reaction (shake, flash, particles) starts 0–45 ms after. At
30 fps a frame is 33 ms; at 24 fps 42 ms. Round hit times to the nearest frame once, in the timing export.

## Lyric alignment

`tempovision align` aligns the person's own lyric text to the vocal stem; it does not transcribe. Methods, in the
order it tries them, recorded as `method` in `timing.json`:

1. `forced`: WhisperX's wav2vec2 forced alignment of the full lyric text against the vocals. Word times
   within ~50–100 ms on clean vocals.
2. `mms`: Meta's multilingual MMS aligner (1,100+ languages, romanised text), with a wildcard before every
   line that absorbs vocals missing from the lyrics (ad-libs, an unwritten repeat) instead of stretching the
   neighbouring words. The choice for languages without a wav2vec2 model, lyrics in Latin script for a language
   usually written in another (Darija or Arabic in Arabizi: digits inside words are read as letters, a word made
   of digits is a wildcard), and code-switched lyrics. It installs CUDA PyTorch on Windows and Linux and uses an
   NVIDIA GPU when there is one. On Deux Faces (Darija + French in Arabizi) the French wav2vec2 model flagged
   42 of 69 lines and put the first line at 0:00; MMS flagged 21, all low scores on one-letter words.
3. `anchored`: Whisper transcribes, lines are matched to the transcript, and each line is force-aligned in its
   window. Used when (1) drifts (long instrumental gaps, ad-libs not in the lyrics). Whisper transcribes poorly
   in languages it barely knows (Darija): prefer `mms` there.
4. `stable-ts`: the stable-ts aligner, when WhisperX is unavailable.
5. `imported`: the person's own timing from an `.lrc`, `.srt` or a tap file (`tempovision align --taps`).
6. `heuristic`: lines spread over vocal activity by syllable count. Marked low confidence; never ship
   word-level animation on it, only line-level.

### Lyrics file format

Plain text, one sung line per line, every repeat written out. Optional section tags on their own line:
`[Intro]`, `[Verse 1]`, `[Pre-Chorus]`, `[Chorus]`, `[Bridge]`, `[Outro]`. Ad-libs in parentheses
`(yeah)` are aligned but flagged `adlib: true`. A blank line is a phrase break. `tempovision align` normalises
punctuation and numbers for alignment and keeps the person's original spelling for display.

### Checking alignment

`timing.json` has a `qa` block: lines whose words are implausibly fast (> 8 syllables/s) or slow, lines that
overlap, words with low alignment scores, and lines that start in silence on the vocal stem. Every flagged line
gets a look: plot it (`tempovision align --inspect <line#>`), then fix by re-aligning the range
(`tempovision align --range 1:12-1:30`), nudging (`--nudge <line#>:+0.08`), or asking the person.

Then the preview: `tempovision align --preview` burns plain, centred karaoke (current word highlighted) over the
song. Send it and ask "do the words land on time? note any line that is early or late." This is the one check
only a human can do.

Look for vocals that aren't in the lyrics: a stretch of vocal activity with no line over it (after a chorus, in
an outro) is an unwritten repeat, a second voice or ad-libs. Ask the person whether it should be on screen; if
it should, they add it to the lyrics and the alignment runs again.

When the person edits the lyrics after alignment (a word added, a line break moved because two lines are sung in
one breath), import the new file (`tempovision project import FILE --as lyrics`) and re-align; the display text
always comes from their file.

### When alignment fails

Dense mixes, heavy vocal effects, harmonies, rap at 6+ syllables per second, or a language without an
alignment model. In order: re-run on the vocal stem; a language without a model, romanised lyrics or several
languages in one song: `--method mms`; switch to `anchored`; align only
the chorus and the hero lines and keep the rest at line level; import the person's timing (most DAWs export
markers; LRC files from their distributor often exist); last, have them tap: `tempovision align --taps` prints a
tap-sheet procedure they can do in two minutes in any browser.

## The song map

`tempovision songmap` joins the analysis and the lyrics into `SONGMAP.md`: one table row per section with its time
range, bars, energy, density, vocal presence and its lyric lines, then the hook lines (most repeated), the
hit list, and the gaps (instrumental stretches longer than two bars, where the picture has to carry alone).
Edit the section names and add the person's notes; this is the document the shot list is built on.
