# Setup: from brief to a working machine

The person asked for one thing explicitly: before the work starts, tell them everything they need to set up.
So setup is a deliverable, not a side effect. It happens after the brief, because the brief decides what is
needed: a pure type-and-vector film needs no API keys; a story with generated characters needs fal and a
budget.

## The procedure

1. `tempovision doctor --brief BRIEF.md --write SETUP.md`. It reads the brief's capability lines, checks the machine,
   and writes a checklist. `tempovision doctor --json` gives the raw results.
2. Show the person the checklist in three groups. For each item: what it unlocks in *this* video, the exact
   command or link, the cost (time, disk, money).
   - **Required**: the video cannot be made as briefed without it.
   - **Recommended**: the video gets clearly better or the work much faster.
   - **Optional**: nice to have.
3. Offer to run every install yourself. Run them one at a time, re-check with `tempovision doctor`, and report.
4. Things only the person can do (create an account, paste an API key, approve a spend) get exact steps: the
   URL, which button, where to paste. API keys go through the plugin settings (`/plugin` → Tempovision →
   configure, or `/config`), never into a file in the project, and never into chat.
5. When every Required item is green: pass G2 (`tempovision project gate G2 pass`). A declined Recommended item gets
   a line in `BRIEF.md` "Fallbacks": what the video loses.

## Capabilities and what satisfies them

| Capability | Needed when | Satisfied by | Fallback |
|---|---|---|---|
| `core` | always | Python ≥3.10, `uv`, `ffmpeg` + `ffprobe` ≥6, `git`, ~5 GB free | none |
| `engine:hyperframes` | engine is HyperFrames | Node ≥22, `npx hyperframes doctor` passes, HyperFrames skills installed | Remotion |
| `engine:remotion` | engine is Remotion | Node ≥18, a Remotion project, Remotion skills installed | HyperFrames |
| `stems` | always recommended | Demucs (`tempovision stems` installs on first run, ~2 GB with PyTorch) | analysis on the full mix; alignment less accurate |
| `align` | lyrics on screen | WhisperX + alignment model for the language (downloads on first run) | stable-ts; then person-tapped timing; then heuristic |
| `gpu` | long songs, generation locally | NVIDIA GPU with CUDA | CPU: stems ~1–3× song length, alignment ~1× |
| `fonts` | always | font files in `assets/fonts/` with licences recorded | engine's bundled fonts |
| `stock` | real footage or photos | Pexels key (free) for the Pexels MCP; Openverse needs no key | `tempovision assets search` against Openverse and the archives in `data/sources.json` |
| `genai` | generated images or clips | fal key with credit, fal MCP connected; a budget in the brief | draw it in code; real material |
| `upscale` | generated or archival footage below delivery size | fal (upscaler models) | deliver at the source's resolution |
| `autonomy` | `full` autonomy | Claude Code auto mode (`claude --enable-auto-mode`, then Shift+Tab), run in a dedicated folder | the person approves prompts |

## Install recipes (what to run, verbatim)

```bash
# uv (Python runner every tempovision tool uses)
curl -LsSf https://astral.sh/uv/install.sh | sh            # macOS/Linux
# ffmpeg
brew install ffmpeg            # macOS
sudo apt install ffmpeg        # Debian/Ubuntu
winget install Gyan.FFmpeg     # Windows
# Node 22+ (HyperFrames needs >=22)
# https://nodejs.org or: brew install node / nvm install 22

# Engine skills, installed into the project so they load with it
npx skills add heygen-com/hyperframes           # HyperFrames skills
npx skills add remotion-dev/skills              # Remotion skills
npx hyperframes doctor                          # checks Chrome, FFmpeg and the rest

# Heavy Python tools: installed into the plugin's own data folder on first use
tempovision stems --install        # Demucs + PyTorch
tempovision align --install        # WhisperX (+ stable-ts fallback)
```

Keys are entered in the plugin's settings, which feed the bundled MCP servers:

- fal: https://fal.ai/dashboard/keys → create key → `/plugin` → Tempovision → configure → *fal API key*.
  Check pricing before generating: the fal MCP has a pricing tool; quote the per-run cost to the person.
- Pexels: https://www.pexels.com/api/ → request key (free, instant) → same place, *Pexels API key*.

After keys change, the MCP servers reconnect on the next session start (`/mcp` shows their state).

## Writing SETUP.md

`tempovision doctor --write` produces it from `templates/docs/SETUP.md`. Edit the "Why" column so it speaks about
this video ("Demucs separates your vocal so the chorus type can follow the voice, not the drums"), then show it.
Keep it short enough to act on in five minutes.

## When the network is restricted

- HyperFrames downloads a headless Chrome on first render. If that host is blocked but Chrome is installed,
  point it there: `export HYPERFRAMES_BROWSER_PATH="/path/to/chrome"` (`npx hyperframes doctor` shows which it
  found).
- The HyperFrames scaffold loads GSAP from a CDN. If renders report a failed script load, vendor it:
  `npm pack gsap@<version>`, copy `package/dist/gsap.min.js` to `video/assets/vendor/`, and point the
  `<script src>` at `assets/vendor/gsap.min.js`. Do the same for any other CDN script. Renders then work
  offline and stay reproducible.
- `tempovision doctor --network` lists which of the hosts Tempovision needs are reachable.

## Rules

- Never install system-wide without saying so first (brew, apt, winget). Python and Node packages go into the
  plugin's data folder or the project, not the system.
- Never put a key in a file inside the project or in a command line that is logged. Read keys only through the
  plugin settings or environment variables the person set.
- If a download is blocked (corporate proxy, offline), say which host and ask the person to allow it or to
  provide the file; do not try other routes around it.
