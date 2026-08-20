# JARVIS · Claude Code Memory HUD

A local voice-and-graph front end for **Claude Code**. The brain is your own
`claude` CLI, so it runs on your Claude subscription — no API key, no per-token
billing. The memory is a folder of markdown you can open in Obsidian.

Nothing is hosted. The server binds to `127.0.0.1` only.

## Quick start with Claude Code

Paste this into a fresh Claude Code session:

> Clone https://github.com/Itsme23476/jarvis-claude-code and set it up for me.
> Read SETUP-PROMPT.md in the repo first and follow it — it has the rules that
> matter. Short version: it runs on my Claude subscription so never use `--bare`
> and never set ANTHROPIC_API_KEY; ask me for my Fish Audio key and put it in
> `.env` without printing it back; help me pick a voice; then start it and verify
> it actually speaks before telling me it works.
>
> One thing to get right: Fish Audio performs `[square brackets]` as delivery
> directions and never speaks them, so write JARVIS's lines to be spoken —
> `[dry]`, `[warm]`, `[lightly amused]`, or free-form like `[the calm tone of
> someone who has done this a thousand times]`. No markdown, no emoji, numbers as
> words, deadpan throughout.

## What it is

Two things fused together:

- **The HUD** — command matrix, live telemetry, action log, reactor core.
- **The memory graph** — every note in your vault as a node, every `[[wikilink]]`
  as an edge. Click a node and only it and its neighbours light up. Shift-click a
  second node to trace the shortest path between them.

The graph is not decoration. When you ask JARVIS something, the server finds the
vault notes that answer it, injects them into Claude's system prompt, **and
focuses the graph on the note it used** — so you watch the answer come out of a
specific file.

## Run it

```bash
cd jarvis-claude
python3 seed_vault.py     # writes a sample agency vault (skip if you have one)
./start.sh
```

Then open <http://localhost:8720>.

Requirements: Python 3.9+ and Claude Code on your PATH. No pip installs — the
whole server is standard library.

## The vault

`vault/*.md`. Frontmatter sets the type, wiki links make the edges:

```markdown
---
type: client
updated: 2026-08-18
---

# Copper & Rye

Independent distillery. Won through [[Outbound campaign]] and
qualified with [[Lead qualification]].
```

Types drive the colours in the filter legend: `client`, `project`, `call`,
`note`, `concept`, `person`, `invoice`, `proposal`, `sop`, `brief`, `campaign`.

Point it at a real Obsidian vault with `JARVIS_VAULT=~/Documents/MyVault`. The
graph reloads from disk automatically when files change, or on `/graph`.

## Commands

| command | does |
|---|---|
| `/recall <query>` | search the vault |
| `/graph` | reload memory from disk |
| `/goal`, `/profile`, `/personality` | standing context injected into every turn |
| `/mission [task]` | mission queue |
| `/status` | runtime, model, vault size |
| `/new` | fresh Claude session |

Anything else goes to Claude Code with the relevant vault notes attached.
`Esc` cancels a running turn. `/` focuses the input.

## Voice

Ships mute — the browser's own `speechSynthesis` voice, which is the robotic
default. Add a Fish Audio key to `.env` and it speaks through that instead:

```
FISH_AUDIO_API_KEY=...
FISH_AUDIO_MODEL=s2.1-pro-free
FISH_AUDIO_VOICE_ID=612b878b113047d9a770c069c8b4fdfe   # Jarvis (MCU)
```

Find voice ids with `GET https://api.fish.audio/model?title=<search>`. Check
remaining quota with `GET /wallet/self/package`.

The key stays server-side. The browser only ever receives mp3 bytes from
`/api/speak`, so it never appears in devtools, page source, or a screen capture.

Verified against the live API: `POST https://api.fish.audio/v1/tts` with the
model as a header, `reference_id` selecting the voice. Speech-to-text uses
`POST /v1/asr` (multipart field `audio`). The bundled skills under
`.agents/skills/` carry the full contract, including the WebSocket streaming
endpoint if you later want token-by-token speech.

Swapping voices means editing `.env` and restarting — the value is read at
startup.

## Demo fixtures

`JARVIS_DEMO=1` (the default) intercepts a handful of scripted questions so a
recording is deterministic: the greeting, the agency numbers, competitor
research, and the campaign-replies chain. Matching is tolerant of speech-to-text
drift. Set `JARVIS_DEMO=0` to send everything to the real Claude.

## Configuration

All optional, all in `.env` — see `.env.example`.

| var | default | notes |
|---|---|---|
| `JARVIS_PORT` | 8720 | |
| `JARVIS_VAULT` | `./vault` | point at any Obsidian vault |
| `JARVIS_MODEL` | Claude default | `opus`, `sonnet`, … |
| `JARVIS_PERMISSION` | `acceptEdits` | Claude Code permission mode |
| `JARVIS_WORKDIR` | `~` | what Claude can see |
| `CLAUDE_CMD` | auto-detected | absolute path if `claude` isn't on PATH |

## Security notes

- Localhost bind, per-launch random API token, same-origin checks, bounded
  request sizes.
- `.env` and `state.json` are gitignored. Never commit them.
- **Never add `--bare` to the Claude invocation.** It forces `ANTHROPIC_API_KEY`
  auth and would bypass your subscription entirely.
- Your subscription is for you. Running this on a VPS for your own phone access
  is still one user; exposing it so other people can talk to it is account
  sharing. If you productise this, ship the code and have each person
  authenticate their own Claude Code.

## Layout

```
server.py      HTTP + NDJSON streaming, token auth
runtime.py     drives `claude -p --output-format stream-json`
memory.py      vault -> graph, recall, per-turn context
commands.py    slash commands + demo fixtures
voice.py       Fish Audio TTS/STT (optional)
seed_vault.py  writes the sample vault
ui/            index.html · styles.css · app.js · graph.js
vault/         your markdown memory
```
