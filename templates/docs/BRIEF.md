# Brief: {{title}}

<!-- The block below is read by `tempovision doctor --brief`. Keep its keys; change the values. -->
```yaml
tempovision:
  title: "{{title}}"
  artist: ""
  engine: hyperframes            # hyperframes | remotion
  aspect: "16:9"                 # master aspect
  fps: 30                        # 24 filmic, 30 type-heavy/social
  duration: full                 # full | <start>-<end> in seconds, e.g. 48.2-80.5
  deliverables: [master, youtube, vertical, thumbnail]
  kind: hybrid                   # lyric | story | abstract | hybrid
  sources: {code: 80, real: 20, generated: 0}   # % of the picture
  lyrics_on_screen: all          # all | hero | chorus | none
  language: en
  commercial: true               # monetised release? (licence checks depend on it)
  budget_usd: 0                  # hard cap for paid generation
  deadline: ""
  gpu: unknown                   # yes | no | unknown
  autonomy: checkpoints          # guided | checkpoints | full
  capabilities: [core, engine:hyperframes, stems, align, fonts]
```

## The song

- **What it is about, in the artist's words**:
- **Who speaks, to whom, when**:
- **Measured**: BPM, key, duration, sections (from `tempovision analyze --quick`):
- **Hero lines** (2–5):

## The film

- **In one sentence**:
- **Kind**: lyric / story / abstract / hybrid, and why
- **Look and medium**:
- **Palette source** (cover art, references, or chosen):
- **References** (links, files in `input/refs/`), and what to take from each:
- **Never** (things the artist does not want):

## Lyrics on screen

- **Presence**:
- **Treatment by section**:
- **Language, script, spelling notes, censored words**:

## Deliverables

| File | Aspect | Size | Length | Notes |
|---|---|---|---|---|
| master | 16:9 | 1920×1080 | full | ProRes 422 HQ |

## Practical

- **Assets the artist provides**:
- **Budget for generation**: (hard cap)
- **Deadline / drafts wanted**:
- **Hardware**:
- **Credits**:

## How we work

- **Autonomy**: and what that means for the gates
- **Fallbacks** (setup items declined and what the video loses):

## Approved

- G1 brief approved on: (date), by: (artist)
