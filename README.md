# सन्नाटपुर की रातें | Sannatpur Ki Raatein

This is an unattended pipeline for channel `UCX-96TVtOBCEkDMloHuYAHw` (ex-Kahaani Chaos). It writes, paints, voices,
renders and publishes the F1 micro-entry Shorts "सन्नाटपुर की छोटी एंट्री". Everything runs on free GitHub Actions
CPU runners and the free Gemini tier. The binding editorial rules are in [CHANNEL.md](CHANNEL.md), and the world
(cast, places, niyam, the 40-entry bank) is in [bible/](bible/README.md).

Until the repository variable `KC_CHANNEL_ID` is set, nothing can publish.

## How a Short is made

| Step | Module | What it does |
|---|---|---|
| Bible | `kahaani/bible.py`, `bible/` | Loads the world, cast, niyam and `micro_bank.json` for the writer, the gates and the image prompts. |
| Entry | `kahaani/premises.py` | Picks the next unused bank entry. It never repeats a skeleton from the last 2 Shorts, never repeats the last Short's ending or resolution, and never reuses an object, anomaly or place from the last 10. A look-ahead keeps the rest of the bank completable. Learned skeleton lift decides among the entries that fit. The next-raat-tease ending is swapped out until F3 exists. A health note is raised when fewer than 10 entries are unused. |
| Story | `kahaani/writer.py`, `kahaani/gemini.py`, `kahaani/llm.py` | Gemini writes the entry as JSON: 5-7 beats, the hook strip, the cast, the turn and heart beats, the title and the description. Local Gemma 4 is the fallback, but a story written locally is held, never published. |
| Gates | `kahaani/gate.py`, `kahaani/variation.py`, `kahaani/hindi.py` | Checks the following: <br>• bands of 85-130 words, 5-7 beats and a hook of at most 10 words naming the object, plus a 3-5 word strip; <br>• the turn and heart beats, and the entry's ending, resolution and niyam; <br>• title rules (40-75 characters, one emoji, the object in the first 5 words, the skeleton); <br>• red lines in Hindi and English, the real world, retired names, banned asks, made-for-kids wording; <br>• variation against the ledger (3-gram Jaccard ≤0.25, title Jaccard ≤0.5). <br>A second model then edits for logic, natural Hindi and spoilers, and flags kids-directed writing. Up to two repairs are made, then the run holds. |
| Paint | `kahaani/look.py`, `kahaani/imagegen.py` | The house style plus each character's fixed props and colours go to Z-Image-Turbo (stable-diffusion.cpp, 576×1024, 4 steps). Each matrix job paints one beat. Cast shots get up to 2 alternates (`--alternates 2 --budget 62`). |
| Screen | `kahaani/vision.py`, `kahaani/aiart.py` | Gemini checks each painting for fit, text, gore and bodies, and checks prop identity on cast shots. A failed cast shot tries its alternates. The run holds when fewer than 70% of beats pass, the hook fails, or fewer than 85% of cast shots show their props. |
| Voice | `kahaani/voice.py`, `kahaani/align.py`, `tts/` | Gemini TTS Charon reads as adult प्रभात. Whisper large-v3-turbo measures: <br>• onset ≤0.3 s; <br>• hook 170-185 wpm (hard band 150-205) and body 155-175 wpm (hard band 140-190); <br>• coverage ≥0.95, CER ≤0.12 and maximum gap 1.2 s. <br>The fallback is a Chatterbox clone of `tts/voices/narrator_ref.wav`; failing that, the run holds. |
| Render | `kahaani/compose.py`, `kahaani/depth.py`, `kahaani/music.py` | Renders 1080×1920 at 30 fps with depth parallax, Mukta captions, the hook strip on frame 0, the always-on AI label, an end card and the code-written bed. The picture and sound gates check: <br>• frame-0 luma 90-170 and contrast 0.18-0.45; <br>• strip height and safe zones; <br>• no blink outside a cut; <br>• frame count ±1 (ffprobe); <br>• runtime 30-58 s with the turn by 75%; <br>• ebur128 at -15 to -13 LUFS with true peak ≤-1 dBFS. <br>Results go to `picture-checks.json`. |
| Buffer | `kahaani/store.py`, `kahaani/slots.py` | Each finished Short waits as a draft release `ready-<id>`, up to two at a time. The slot is daily at 19:00 IST (13:30 UTC). A slot missed by under 2 h is filled at once. |
| Publish | `kahaani/youtube.py` | Publishing is identity-pinned to `KC_CHANNEL_ID`. Each upload is: <br>• private, with `publishAt` at the slot; <br>• flagged as synthetic content and not made for kids; <br>• category 24, Hindi, with `notifySubscribers=False`. <br>Uploads retry dropped connections and 5xx errors. Then: <br>• **read-back:** the video is read again, and any drift in kids, privacy, `publishAt`, the synthetic flag, upload status or channel holds the run; <br>• filed in the `KC_PLAYLIST_MICRO` playlist; <br>• one first comment (the open question, otherwise the default ask); <br>• the release is deleted. |
| Learn | `kahaani/learn.py` | At 48 h each Short scores 0.5 × viewed% + 0.3 × log views + 0.2 × subs per 1K (as z-scores), with a views-only fallback when Analytics is not granted. Once there are 4 or more samples, each feature gets a lift clamped to 0.75-1.35. Results go to `state/LEARNINGS.md`. |
| Memory | `kahaani/ledger.py` | `ready.json`, `published.json`, `tries.json`, `performance.json` and `health.json` are kept on the `state` branch. |

## Running it

```
uv sync --frozen --extra dev
uv sync --project tts                                      # Chatterbox, for the fallback voice
uv run python -m kahaani.cli next                          # the bank entry that would be written next
uv run python -m kahaani.cli plan --out work/plan --dry    # write and gate one story, and its image prompts
uv run python -m kahaani.cli plan --out work/plan --dry --replay .github/replay/dynamo-wali-cycle.json
python3 -m kahaani.imagegen beats --prompts work/plan/art-plan.json --out work/art --root ~/.cache/kc-art --alternates 2
uv run python -m kahaani.cli render --plan work/plan --art work/art --out work --dry
uv run pytest -q
```

## GitHub Actions

- **`run.yml`:**
  - Production runs at 01:30 and 07:30 UTC (07:00 and 13:00 IST): plan, then the paint matrix, then render, then
    publish. Production is skipped while the buffer is full.
  - Publish-only runs at 12:00 and 13:15 UTC fill the 13:30 UTC slot from the buffer.
  - `workflow_dispatch` takes two inputs:
    - `mode`: `dry-run` (the default) or `publish`;
    - `replay`: a reviewed story JSON in `.github/replay/`. In publish mode it is published once, and never if its
      story or bank entry was already made.
  - Dry runs keep the MP4 and records as the `short-<run id>` artifact, and touch neither the ledger, the releases
    nor YouTube.
- **`health.yml`:** runs every six hours. It opens or updates an `alert` issue titled "Sannatpur Ki Raatein needs
  attention" when any of the following happens:
  - nothing ran for 30 h;
  - the last production or publish run failed or is holding;
  - the bank has fewer than 10 unused entries;
  - a read-back mismatched;
  - the Analytics scope is missing.
- **`tests.yml`:** runs the test suite on every push. `tests/test_hindi_gates.py` proves that every text gate sees
  Devanagari tokens.

What the coordinator supplies (environment `youtube` unless noted):

| Name | Kind | What it is |
|---|---|---|
| `GEMINI_API_KEY` | environment secret | Google AI Studio key for the writer, editor, picture check and voice |
| `YOUTUBE_OAUTH_JSON` | environment secret | Authorized-user JSON for the channel. Scopes: `youtube.upload`, `youtube`, `youtube.force-ssl` (first comment) and `yt-analytics.readonly` (learning; without it, learning is views-only and health alerts). |
| `KC_CHANNEL_ID` | variable | `UCX-96TVtOBCEkDMloHuYAHw`; the uploader refuses any other channel |
| `KC_PLAYLIST_MICRO` | variable | Playlist id for "सन्नाटपुर की छोटी एंट्री (Shorts)". Optional: when it is empty, nothing is filed. |
| `PAUSED` | repository variable | `true` stops the schedule, publishing and health alerts. Dry runs still work. Set it on any read-back alert. |

The `state` branch is created by the first non-dry run.

## Credits

| Role | Credit |
|---|---|
| Pictures | Z-Image-Turbo (Apache-2.0) via stable-diffusion.cpp (MIT) |
| Depth | Depth Anything V2 Small (Apache-2.0) |
| Speech recognition | Whisper large-v3-turbo (MIT) via faster-whisper |
| Fallback voice | Chatterbox Multilingual (MIT) |
| Fallback writer | Gemma 4 (Apache-2.0) via llama.cpp (MIT) |
| Narration, writing and picture checks | Google Gemini |
| Font | Mukta (SIL Open Font License, `kahaani/fonts`) |
| Music | Generated in code |
