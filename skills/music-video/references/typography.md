# Lyric typography

In a lyric video the type is the cinematography. Set it like a designer setting a poster that moves, not like
subtitles.

## Choosing faces

- One display face with character, chosen for the song's voice; at most one secondary face. Pairing rule: contrast in
  structure (a grotesk with a serif), not similarity.
- The face must have the weights and glyphs the lyrics need (accents, non-Latin scripts, apostrophes, numerals).
  Check the actual lyric text in it before committing.
- Sources with licences that allow video use: `data/sources.json` → `fonts`. Record the licence in the ledger.
- Variable fonts let weight or width animate with the music (weight on the vocal energy, width on the bass).
  Use one axis, deliberately.

## Size, measure, hold

- Readable text is at least 2.6% of the frame's short side (28 px at 1080p); hero type is usually 9–25% of the
  frame height.
- A line holds at least 0.5 s plus 0.3 s per word, and never less than one beat. If it cannot (rap, fast
  lines), show fewer words: the hook words, set big.
- 3–7 words on screen at once for kinetic type; one line at a time unless the layout is a poster that builds.
- Too many words for the space: cut words or change the layout. Never shrink the type below the floor.

## Timing type to the voice

Use `lyrics/timing.json` (word `start`/`end`) through the engine export, never typed times.

- A word appears at or slightly before (0–2 frames) its sung start; on a hit, its arrival frame is the hit.
- A line's exit begins after its last word ends and finishes before the next line's first word, or the two
  overlap on purpose (a crossfade of 4–8 frames on calm sections).
- Long sung words (melisma) can be drawn out: stretch letter-spacing, extend a stroke, fill a word left to right
  over the word's duration.
- Staggers follow the syllables, not a fixed interval: per-word reveal at the word's own time is always more
  alive than a uniform stagger.
- Ad-libs (`adlib: true`) are smaller, offset, a secondary colour, or left out; decide in the spec.

## Treatments, from quiet to loud

| Treatment | Where it fits | How |
|---|---|---|
| Line set | calm verses | one line, set well, enters on its first word; slight drift (1–2% over the line) |
| Build | storytelling verses | words appear on their sung time and stay until the line ends |
| Highlight | singalong, choruses | full line visible, sung word gains weight/colour/underline on its time |
| Word stack | dense choruses, rap | one or two words at a time, very large, each on its own time; layout changes on the bar |
| Type in the world | story/hybrid | the words are objects: written in light, carved, printed on things, seen through glass; tracked to the scene |
| Hero moment | hero lines | a one-off idea for that line alone: the meaning made visible |

Mix by section: the contrast between treatments is what makes the chorus feel like a chorus.

## Kinetic moves worth knowing

- Mask reveals (text rising out of a baseline mask) for clean arrivals.
- Scale punches on hits: 100% → 108–115% → 100% over 3–6 frames, landing on the hit.
- Tracking breath: tracking from −4% to 0% across a held word.
- Weight on energy (variable font): map vocal stem energy to weight with smoothing (≥ 150 ms), never raw.
- Kinetic layout: the words re-arrange on each bar into a new composition (a different grid cell, a rotation of
  90°, a scale jump).
- Split and slide: lines cut horizontally and the halves slide apart on a beat.
- Text along a path or around an object in the scene.

Each needs a reason in the shot list. A move used everywhere becomes a tic; give each one a home section.

## Knock-outs: letters cut out of a band

A knock-out (letters cut out of a band of paint, chalk or colour) is reversed type on a label, and it needs more
room than the same words set plainly:

- **Band height ≈ 1.7–1.8× the letters' body**: about 0.4 of the body clear above and below. Letters that touch
  the band's edges read cramped and smaller than they are.
- **Centre the ink, not the em box.** Display faces sit high or low in their box (Rock Salt's ink runs ~1.1 em
  above the baseline to ~0.35 below). Measure the ink and centre it in the band.
- **Run the band a full em past the text** at both ends, plus its own taper.
- **Open the tracking** by 2–4% and widen word spaces; cut-out letters close up visually.
- **Separate stacked bands** with a clear gap (≥ 0.3 em) so each line reads as its own stroke, not one slab.
- Check the knock-outs in the layout pass: they are the widest blocks in the film, and the first to break
  title-safe when anything grows.

## Edges of the frame

A word that runs out of the frame reads as a mistake unless it is visibly moving out (still in motion, or leaving
on a cut). A held frame with a clipped word looks clipped, whatever the intention. Keep every word whole inside
title-safe while it is read; let it leave only as an exit.

## End credits

Ask the person at the interview who to credit (mix and recording, animation and video, director, label) and
exactly how each name or handle is written. Set them on the last hold, quiet, in the film's own type, inside
title-safe, after the title has landed; they stay until the end.

## Legibility over footage or busy backgrounds

Choose by the brightness behind the text: dark ground → light type; mid → add a local scrim (30–40% sized to the
text), or a blend mode; light → dark ink. Never a full-width subtitle bar. Check on the phone-width sheet.

## Language and script

Right-to-left scripts need direction set and font support; check joining. Unspaced scripts (Chinese, Japanese)
time by phrase or character groups, not words. Preserve the person's spelling, capitalisation and stylisation
exactly; alignment normalises a copy, never the display text.
