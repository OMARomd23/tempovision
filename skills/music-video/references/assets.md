# Assets: make, find, generate, and record

## The order of preference

1. **Make it in code.** Type, vector shapes, SVG illustration and rigs, shaders, procedural paper, grain,
   halftone, light leaks, particles. Free, consistent, editable, and exactly on brand. Most of a lyric video
   should come from here.
2. **Use the person's own material.** Their footage, photos, cover art, handwriting, sketches. Ask for it in
   the interview. It is the most personal and the least generic.
3. **Find real material.** Stock footage and photos, public-domain archives, CC0 textures and 3D. See
   `data/sources.json`.
4. **Generate** only what none of the above can show: a specific scene, a character in many poses, a place
   that does not exist. Inside the budget, from references.

## Finding

- `tempovision:asset-scout` searches categories in parallel and returns a shortlist with licence notes; give it
  the shot list rows and the spec's palette and medium.
- Pexels MCP (`pexels_search_videos`, photos) when the key is set; otherwise `tempovision assets search "<query>"
  --source openverse|pexels|pixabay|nasa|met|aic|commons`. For stock footage and photos, use whichever of Pexels
  and Pixabay has a key (`tempovision doctor` shows which); search both when both do, since their libraries differ.
  Pixabay image URLs from the API stop at 1280 px: for a full-frame hero image, have the person download the
  original from the item's page.
- Search for what the shot needs (light, texture, motion direction, framing), not for the lyric's literal
  words. "Slow handheld push through tall grass, golden backlight" finds usable footage; "freedom" does not.
- Prefer clips longer than the shot, at or above the delivery resolution, with no burned-in text, logos or
  recognisable people (people need a model release for commercial use; stock sites say which clips have one).
- Download with `tempovision assets fetch <url> --license "<licence>" --source "<page url>" --author "<name>"`, which
  stores the file and its record together.

## Generating

Through the fal MCP: `search_models` / `recommend_model` to find a model, `get_pricing` to quote the cost,
`run_model` (images) or `submit_job` + `check_job` (video), `upload_file` for references. Another generation
service the person has (Higgsfield, for example) works the same way: quote, ledger every job, stay inside its
credits. Trial accounts may only work through one route (Higgsfield's trial: the MCP, not the CLI).

- **Quote first.** Before any batch, tell the person the per-item price and the total, unless the brief's budget
  covers it; log each spend: `tempovision project spend 0.40 "6 chorus stills, model X"`. Stop at the cap.
- **Style lock.** Put the spec's medium, palette and light into every prompt verbatim (keep a `prompts/STYLE.txt`
  and prepend it). Use the same model and settings for the whole film.
- **Consistency for characters and places.** First make a reference sheet (front, three-quarter, profile,
  expressions, palette) and approve it. Then generate every shot from it with a reference-capable image model
  (image-to-image or reference conditioning), and animate with image-to-video from approved stills, never
  text-to-video for recurring characters.
- **Generate stills, then motion.** Approve a still before paying for its motion. Animate only shots that need
  motion the engine cannot add (camera moves and parallax on a still are usually better done in the engine).
- **The person's characters are theirs.** Figures from their cover or artwork are never regenerated, even
  "in the same style": a model redraws faces, eyes and hands its own way, and the person sees it at once. Clean
  the original (remove the title and logo), upscale it for close-ups, and animate it (image-to-video from that
  file, or its layers moved in the engine). Read every clip frame by frame: a clip that grows ears, irises, a
  torso or skin texture on their figure is rejected, however good it looks. Generate new scenes only where a
  figure is small, seen from behind, or partial (a hand, a silhouette at a distance).
- **Hold the style at both ends.** Image-to-video drifts toward photographic: a painted hand becomes a real hand
  by the second second, and the morph target (a sword, a wave) arrives rendered. Generate the first AND the last
  frame as stills in the film's medium, approve both, then use a first-and-last-frame video model; every frame
  in between stays painted. Name what must stay naive in the prompt ("crude, flat, no knuckles, no skin
  texture"), not only what it is.
- **Resolution for the delivery, not more.** For a 1080p film, generate at 1080p (FHD); 2K and 4K cost more and
  add nothing, unless a shot crops deep into the image (then upscale that one still).
- **Reject fast.** Hands, text in images, faces drifting off-model, physics that melt: reject and change the
  approach after two failures (crop, reframe, draw it instead).
- **Upscale and match** before compositing: same resolution, same frame rate (convert with `ffmpeg -r` only
  with frame blending off), graded to the film's look in finishing.
- Record model, prompt, seed, reference images and cost in the ledger for every generated file, rejected
  ones included (with why). Paid generations are never "regenerable": no cleanup deletes them.

## Fonts

Download into `assets/fonts/` as `.woff2` or `.ttf`, record the licence (`OFL`, the foundry's free licence, or
the person's own licence). Engines need the file, not a system font name.

## The ledger

`assets/LEDGER.json` has one entry per file: `path`, `kind`, `source`, `source_url`, `author`, `license`,
`license_url`, `commercial_ok`, `attribution_required`, `attribution_text`, `generated` (`model`, `prompt`,
`seed`, `refs`, `cost`), `notes`, `added`. `tempovision assets add` writes entries; `tempovision assets check` fails
when a file in `assets/` has no entry, when a licence is non-commercial while the brief is commercial, or when
attribution is required and not in the credits.

## Licences, briefly (verify at the source every time)

- **CC0 / public domain**: free for any use. Archives mark this per item; trust the item, not the site.
- **Pexels, Pixabay, Unsplash licences**: free for commercial use, no attribution required; not for resale of
  the asset itself or implying endorsement; identifiable people and brands still need care.
- **CC BY**: commercial use allowed with attribution in the credits.
- **CC BY-SA**: attribution, and the derived work may need the same licence: avoid for a release.
- **CC BY-NC**, **Shadertoy's default (CC BY-NC-SA 3.0)**: non-commercial only. Not for a monetised release.
- **Fonts**: OFL allows embedding in video. Other "free" fonts may be personal-use only: read the licence.
- **Generated**: governed by the model provider's terms; record them. Do not prompt for living artists' styles
  by name, real people, or trademarks.
