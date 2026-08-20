# Setup prompt

Paste everything below into a fresh Claude Code session. It is written to be
self-contained: Claude clones the repo, installs the Fish Audio skill, asks you
for one API key, and hands you a running JARVIS.

---

I want you to set up my own JARVIS assistant. Clone and run this repo:

https://github.com/Itsme23476/jarvis-claude-code

## What this is

A local voice-and-graph HUD driven by Claude Code. A small Python server (standard
library only, no pip installs) shells out to the `claude` CLI in headless mode and
streams the result to a browser front end. There are three parts:

- **Brain** — `runtime.py` runs `claude -p --output-format stream-json --include-partial-messages --verbose`
  and maps the event stream to HUD events. Because it invokes the CLI directly, it
  authenticates with my **Claude subscription** — no API key, no per-token billing.
- **Memory** — `memory.py` reads `vault/*.md` (Obsidian-style markdown with YAML
  frontmatter and `[[wikilinks]]`) and turns it into a force-directed knowledge
  graph. On every question it injects the most relevant notes into Claude's system
  prompt and focuses the graph on the note it used.
- **Voice** — `voice.py` speaks through Fish Audio. The key stays server-side; the
  browser only ever receives mp3 bytes from `/api/speak`.

## Steps

1. Clone the repo and `cd` into it.
2. Run `python3 seed_vault.py` if `vault/` is empty (writes 133 sample notes).
3. Install the Fish Audio agent skill so you have the exact API contract:
   `npx skills add https://docs.fish.audio`
   (It is also vendored in the repo at `.agents/skills/fish-audio-api/SKILL.md`.)
4. Copy `.env.example` to `.env` and ask me for my Fish Audio API key. Put it in
   `FISH_AUDIO_API_KEY`. **Never print the key back to me and never commit it** —
   `.env` is already gitignored.
5. Pick a voice: `GET https://api.fish.audio/model?title=jarvis` (or any search
   term), show me a few options with their ids, and put my choice in
   `FISH_AUDIO_VOICE_ID`.
6. Start it with `./start.sh` and open http://localhost:8720.
7. Verify before telling me it works: check `/api/status` reports
   `server_voice: true`, POST a line to `/api/speak` and confirm you get real mp3
   bytes back, then send a question through `/api/run` and confirm Claude answers
   from the vault.

## Hard rules

- **Never add `--bare` to the claude invocation.** It forces `ANTHROPIC_API_KEY`
  auth and silently bypasses my subscription, so I would start paying per token.
- Do not set `ANTHROPIC_API_KEY` in the environment for the same reason.
- The server must stay bound to `127.0.0.1`. It mints a random per-launch API
  token and checks Host/Origin on every request — keep all of that.
- Do not commit `.env` or `state.json`.

## Fish Audio — the part that makes this sound like JARVIS instead of a train announcement

This is the most important thing to get right, because it decides what text you
generate. Read it carefully.

### Delivery tags

Fish Audio reads **square brackets as stage directions, not as words**. They are
performed and never spoken aloud. So this input:

```
[sighing] [dry] I've moved your three o'clock. Again.
```

...produces an actual sigh and a dry delivery, and the words "sighing" and "dry"
are never read out. This is verified behaviour, not a guess: an open-domain tag of
twelve words produces *shorter* audio than the same line untagged, which is only
possible if the tag is consumed rather than spoken.

Syntax depends on the model family:

| Model | Syntax | Vocabulary |
|---|---|---|
| `s2.1-pro`, `s2.1-pro-free`, `s2-pro` | `[brackets]` | **free-form natural language** |
| `s1` (legacy) | `(parentheses)` | fixed list, must match exactly |

This project uses `s2.1-pro-free`, so **use square brackets and write whatever you
want inside them**. There is no separate API parameter — tags go inline in `text`.

Documented categories: 24 basic emotions (`[happy]` `[sad]` `[angry]` `[excited]`
`[calm]` `[nervous]` `[sarcastic]`), 25 advanced (`[anxious]` `[nostalgic]`
`[determined]` `[resigned]`), 6 tone markers (`[whispering]` `[shouting]`
`[soft tone]` `[emphasis]`), 11 audio effects (`[laughing]` `[sighing]` `[gasping]`
`[yawning]`), and 5 special effects (`[break]` `[long-break]`
`[audience laughing]`). Full list:
https://docs.fish.audio/api-reference/emotion-reference.md

Two things the fixed list undersells:

- **Intensity modifiers work**: `[very excited]`, `[slightly sad]`.
- **Open-domain descriptions work**, and this is the real party trick:
  `[the calm, measured tone of someone who has done this a thousand times]`
  is a valid tag. You are not limited to a vocabulary.

### How this shapes the text you write

Every reply JARVIS gives is read aloud. So when you write replies — in demo
fixtures, in the system prompt, anywhere — write them **to be spoken**:

- Put one or two delivery tags per reply, placed where the register actually
  changes. More than that reads as noise.
- No markdown, no bullet points, no headings, no emoji. None of it survives TTS.
- Numbers as words when they will be spoken: "six thousand euros", not "€6000".
- Dry understatement over enthusiasm. JARVIS is deadpan; that is the whole
  character. A JARVIS that sounds cheerful undercuts the entire thing.

The repo already does this in two places — `VOICE_DIRECTION` in `commands.py` (the
system prompt appended to every real Claude turn) and the hardcoded demo replies.
Match that style if you add more.

### Other Fish Audio facts worth knowing

- **TTS**: `POST https://api.fish.audio/v1/tts`, JSON body, model as an HTTP
  header (`model: s2.1-pro-free`), `reference_id` selects the voice, `format: mp3`.
  Response is raw audio bytes with no JSON wrapper.
- **ASR**: `POST /v1/asr`, `multipart/form-data`, field name `audio`. **Billed from
  a separate "API credit" balance**, not the subscription/platform balance that TTS
  uses — so TTS can work while ASR returns `402 Insufficient API credit`. If that
  happens, say so plainly rather than reporting the mic as broken.
- **83 languages in one model**, with automatic detection and the same voice
  identity across all of them. You do not declare the language in the request.
- **Voice cloning**: `POST /model` (multipart) with 10–30 seconds of clean audio,
  returns a voice id to use as `reference_id`. Not available through the Fish MCP
  server — use the REST endpoint.
- **Latency**: roughly 90ms time-to-first-audio on the model side. What you measure
  end to end will be much higher, because it includes the LLM turn and network.
  Do not conflate the two.

## Speech-to-text caveat

The browser's Web Speech API relies on Google's speech service. Chromium builds
shipped without a Google API key — Brave most notably — fail instantly with error
`network`. The front end tries Fish Audio ASR first and falls back to the browser,
so if I am in Brave and have no Fish ASR credit, listening will not work. Tell me
that directly rather than debugging my microphone.

## When you are done

Tell me: the URL, which voice you set, whether server-side voice and listening are
each working, and how many notes are in the vault. Then suggest three questions I
can ask it.
