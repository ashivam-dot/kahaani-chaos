# Kahaani Chaos

An unattended pipeline that writes, paints, voices, renders and publishes original Hindi magical and mysterious
twist-story Shorts for [@KahaaniChaos](https://www.youtube.com/@KahaaniChaos), entirely on free GitHub Actions CPU
runners and the free Gemini tier. The binding editorial rules are in [CHANNEL.md](CHANNEL.md).

Until the repository variable `KC_CHANNEL_ID` is set, nothing can publish.

## How a Short is made

| Step | Module | What it does |
|---|---|---|
| Premise | `kahaani/premises.py`, `kahaani/premises.json` | 60 hand-written premises (12 per sub-genre) plus Gemini refills when fewer than 15 are unused, red-line checked and deduplicated. Refuses a motif from the last 10 Shorts and a sub-genre from the last 2; then learned lift × rest decides. |
| Story | `kahaani/writer.py`, `kahaani/gemini.py`, `kahaani/llm.py` | Gemini (ListModels discovery, the next model on a 429), then local Gemma 4, writes the story as JSON: beats with an English scene and everyone's expression, a cast sheet, twist beat, ending, title. |
| Gates | `kahaani/gate.py`, `kahaani/hindi.py` | Word, beat and hook counts, arc, ending rotation, title rules, banned asks and openers, red lines in Hindi and English. Then a second model call edits for logic, twist clarity, natural Hindi and spoilers. Up to two repairs, then hold. |
| Paint | `kahaani/look.py`, `kahaani/imagegen.py` | The house style plus each character's fixed look; Z-Image-Turbo (stable-diffusion.cpp, 576×1024, 4 steps) paints one beat per matrix job. |
| Screen | `kahaani/vision.py`, `kahaani/aiart.py` | Gemini looks at the paintings; refused beats repeat the nearest earlier passing one; under 70% passing or a failed hook holds. |
| Voice | `kahaani/voice.py`, `kahaani/align.py`, `tts/` | Gemini TTS storyteller (`VOICE` = Charon, picked by `tools/audition.py`), pause before the twist; Whisper large-v3-turbo checks every line and the 140-160 wpm pace. Fallback: Chatterbox cloning `tts/voices/narrator_ref.wav`; otherwise hold. |
| Render | `kahaani/compose.py`, `kahaani/depth.py`, `kahaani/music.py` | 1080×1920, 30 fps: depth parallax, teal-amber grade, RAQM-shaped Mukta captions, the always-on "AI चित्र और आवाज़ · काल्पनिक कहानी" label, an end card without asks, a dark-ambient bed with a bell at the twist, −14 LUFS. |
| Buffer | `kahaani/store.py`, `kahaani/slots.py` | Each finished Short waits as a draft release `ready-<id>`; up to two wait. Slots 12:30 and 20:30 IST; a slot missed by under 2 h is filled at once. |
| Publish | `kahaani/youtube.py` | Identity-pinned to `KC_CHANNEL_ID`; private upload with `publishAt` at the slot (public at once if it passed), synthetic-content flag, not made for kids, category 24, Hindi; the release is deleted once published. |
| Learn | `kahaani/learn.py` | Views at 48 h per sub-genre become a lift (n/(n+4), 0.75-1.35); `state/LEARNINGS.md`. |
| Memory | `kahaani/ledger.py` | `ready.json`, `published.json`, `tries.json`, `premises.json`, `performance.json`, `health.json` on the `state` branch. |

## Running it

```
uv sync --extra dev
uv sync --project tts                                      # Chatterbox, for the fallback voice
uv run python -m kahaani.cli next                          # the premise that would be written next
uv run python -m kahaani.cli plan --out work/plan --dry    # write and gate one story, and its image prompts
uv run python -m kahaani.cli plan --out work/plan --dry --replay .github/replay/sikko-wala-kuan.json
python3 -m kahaani.imagegen beats --prompts work/plan/art-plan.json --out work/art --root ~/.cache/kc-art
uv run python -m kahaani.cli render --plan work/plan --art work/art --out work --dry
uv run pytest
```

## GitHub Actions

- `run.yml`: production at 06:00 and 14:15 UTC (plan → paint matrix → render → publish); publish only at 05:30 and
  13:45 UTC. Production is skipped while the buffer is full. `workflow_dispatch` with `mode` (`dry-run` by default,
  or `publish`) and `replay` (a reviewed story JSON in `.github/replay/`; in publish mode it is published once, never if its story or
  premise was already made). Dry runs keep the MP4 and records as the
  `short-<run id>` artifact and touch neither the ledger, the releases nor YouTube.
- `health.yml`: every six hours; opens or updates an `alert` issue when nothing ran for 30 h, or the last
  production or publish run failed or is holding.
- `tests.yml`: the test suite on every push.

What the coordinator supplies (environment `youtube` unless noted):

| Name | Kind | What it is |
|---|---|---|
| `GEMINI_API_KEY` | environment secret | Google AI Studio key: writer, editor, picture check and voice |
| `YOUTUBE_OAUTH_JSON` | environment secret | authorized-user JSON for the channel (scopes `youtube.upload` and `youtube`) |
| `KC_CHANNEL_ID` | variable | `UCX-96TVtOBCEkDMloHuYAHw`; the uploader refuses any other channel |
| `PAUSED` | repository variable | `true` stops the schedule, publishing and health alerts; dry runs still work |

The `state` branch is created by the first non-dry run.

## Credits

Pictures: Z-Image-Turbo (Apache-2.0) via stable-diffusion.cpp (MIT). Depth: Depth Anything V2 Small (Apache-2.0).
Speech recognition: Whisper large-v3-turbo (MIT) via faster-whisper. Fallback voice: Chatterbox Multilingual (MIT).
Fallback writer: Gemma 4 (Apache-2.0) via llama.cpp (MIT). Narration, writing and picture checks: Google Gemini.
Font: Mukta (SIL Open Font License, `kahaani/fonts`). Music: generated in code.
