# Painted story

A narrative told in painted frames: a character and their world, generated as stills from a locked reference
sheet, then brought to life in the engine with parallax, camera moves, and a few generated motion shots.

## Medium

- A painting tradition named precisely in `prompts/STYLE.txt` (for example "gouache on cold-press paper, visible
  brush strokes, limited palette of 6 colours, flat graphic shadows, no outlines"), with the palette's hex values
  repeated in words. Avoid naming living artists.
- Every still is generated at the same aspect and resolution from the same model and settings.
- Paper texture and a light grain (3–4%) over everything in finishing, so generated and drawn parts share one
  surface.

## Consistency procedure

1. Character sheet: front, three-quarter, profile, two expressions, full-body, palette strip. Approve.
2. Location sheets for each recurring place. Approve.
3. Each shot: generate from the sheet(s) with a reference-capable model; 2–4 candidates; pick; record seed and
   prompt.
4. Split approved stills into depth layers (foreground / subject / background) with a segmentation or
   background-removal model, inpaint the background behind the subject, and animate the parallax in the engine.
5. Generate motion (image-to-video) only for shots that need performance (a turn of the head, walking, hair in
   wind), from the approved still, 3–5 s, and conform to the film's fps.

## Type

A book-like serif for line sets, placed in painted negative space (generate the frame with space for it: say
where in the prompt). Hero lines painted into the world (on a sign, in the sky) only if the model handles text
reliably; otherwise set it as real type on a surface tracked in the engine.

## Motion personality

Slow parallax pushes (1.00→1.08 over a phrase), occasional generated motion shots on hero lines, cuts on phrases;
the chorus returns to one home painting that changes each time (season, light, what the character holds).

## Budget

Estimate before starting: (shots × candidates × image price) + (motion shots × clip price) + upscales. Quote it
and log every spend. Typical: 30–40 stills and 6–10 motion clips for a 3-minute song.

## How it goes wrong

The character drifts off-model between shots, the generator's default sheen (plastic, over-detailed), different
light direction from shot to shot, text rendered by the model with errors, every shot a slow zoom.
