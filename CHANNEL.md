# सन्नाटपुर की रातें | Sannatpur Ki Raatein: editorial rules

Channel `UCX-96TVtOBCEkDMloHuYAHw` (handle still @KahaaniChaos until the owner claims a new one in Studio). Tagline:
"1996 का एक काल्पनिक गाँव, और उसकी अजीब रातें". Original Hindi Shorts about the strange nights of an invented
village, for a general Hindi audience aged 13+. Not made for kids. These rules bind every story. The code enforces
what it can (`kahaani/gate.py`, `kahaani/variation.py`, `kahaani/vision.py`, `kahaani/voice.py`,
`kahaani/compose.py`, `kahaani/youtube.py`), and a second model reads the rest as an editor (`kahaani/writer.py`).
The full design is PLAN.md in `kahaani-recreate-2026-10-22/design/`. The world itself lives in `bible/`.

## World

- **Sannatpur, 1996**, a fictional north-Indian village (`bible/world.yaml`), always labelled काल्पनिक. It is never
  attached to a real district, state, river or city. A story says "शहर" or "ज़िले का दफ़्तर", never a name.
- **The frame:** in 2026, प्रभात at 47 remembers the nights when he was 17. Every Short is a memory and is told in his
  adult voice.
- **The cast** (`bible/cast.yaml`; every name passed `bible/name_checks.md`):
  - झब्बू पहरेदार (60), the night watchman who writes the village's rules in his red-spined register;
  - प्रभात (17);
  - नुज़हत (17);
  - शैलेश (18).

  Each has fixed props and colours. The plan names अंशु, शबनम, मोंटी and ज़रीना failed the name check, so they are
  retired and the gate refuses them.
- **The rules:** the village's rules for strange nights are the niyam in `bible/canon.json`. A story may only cite a
  niyam that exists there.
- **90s textures:** power cuts and lanterns, PCO/STD meters, transistors and cassettes, inland letters, ration
  queues, dynamo cycle lights. Strangeness lives in these everyday objects.
- New PCO writer drafts make bare counter scenes explicitly enclosed before editorial and picture checks.
  Deliberate exterior establishing views stay outside. This prevents the generic outdoor house style from
  displacing the counter room; existing replay stories and exact cached prompts remain unchanged.

## Red lines

Never, in narration, title, description, premise or picture:

- gods, saints, scriptures, temples, prayers, rituals, exorcism or religious miracles;
- the banned beings: no चुड़ैल, डायन, प्रेत, जिन्न and the like. The strange is an object or a night, never a
  demon;
- real people, real places, real brands or broadcasters, news, or any "true story" claim;
- gore, wounds or killing; sexual content; harm to a child; self-harm;
- caste, religion or regional stereotypes.

An exclamation such as "हे भगवान" is refused, and the fix "हाय, बाप रे or अरे" is offered. Hindi is checked through
`kahaani/hindi.py`, which normalises nukta and chandrabindu and tokenises Devanagari. A `\w+` or `[a-z0-9]+`
tokenizer is never used on Hindi, because it sees nothing in "साइकिल की लाइट".

## F1: सन्नाटपुर की छोटी एंट्री (micro-entry Shorts)

Every entry comes from the hand-written bank of 40 in `bible/micro_bank.json`. Each entry fixes the following:

- the object, the anomaly and the place;
- the niyam;
- the hook line;
- the heart beat;
- the resolution type and the ending type;
- the title and its skeleton.

The writer expands one entry. Nothing is invented outside the bank.

- **Length:** 35-55 s spoken. The hard gate is 30-58 s on the measured narration, with the turn landing by 75% of
  the runtime. The script is 85-130 spoken Hindi words in 5-7 beats, in Devanagari only, with numbers as words
  (the year is "उन्नीस सौ छियानवे").
- **Beats:** cold open on the impossible moment, then "1996, उस रात…", then the first sign, the escalation, the turn
  (the trio realises the rule), the heart beat (a kindness, a confessed lie or a goodbye) and the ending.
- **Hook:** the first spoken line is at most 10 words and names the entry's 90s object together with its anomaly.
  The hook strip on frame 0 is 3-5 words.
- **Endings** rotate, and never repeat the previous Short's:
  - loop-back (the last line rhymes with frame 0);
  - register-line (Jhabbu adds one line to the register);
  - open-question (one question to the comments).

  The next-raat-tease ending is held back until the weekly long-form (F3) exists. Until then a tease entry takes
  another ending.
- **Resolution types** (leave-it-be, kindness, bargain, outsmart) also differ from the previous Short.
- **Variation.** The following are refused:
  - an object, anomaly, place or opening from the last 10 F1 Shorts;
  - a script whose Hindi 3-gram Jaccard with any earlier Short is above 0.25;
  - a title whose word Jaccard is above 0.5.

  An empty token set is a problem, never a pass.
- **Never** a greeting or host opener, the channel's name, "क्या आप जानते", or a like/subscribe/share/follow ask,
  including on the end card.

## Title

- 40-75 characters, one or two emoji (PLAN.md §7.2's `📻😨`), with the entry's object in the first five words, in
  spoken Hindi. Roman-Hinglish twin titles (PLAN.md §7.2) are deferred: F1 publishes the Devanagari title only.
- The title never gives away the turn.
- Three skeletons rotate, and a skeleton is used at most once in any three Shorts:
  - **S1:** `<90s act>… <impossible result> + emoji`;
  - **S2:** `<object> ने <strange action> 😨 | सन्नाटपुर`;
  - **S3:** `"<who/why…?>" + emoji`.
- The description carries `#सन्नाटपुर` and the disclosure line. No made-for-kids wording ("बच्चों के लिए", "सोने से
  पहले की कहानी", "नैतिक कहानी", "kids") appears anywhere.

## Look

- One AI painting per beat in the bible's house style: a bright moonlit 1996 village, one warm practical light,
  lifted shadows, painterly-cinematic and realistic adult proportions (`kahaani/look.py`).
- Never chibi, anime, 3D, kids-book style, gore, or any written text.
- Faces stay small, backlit or turned away. Who someone is comes from their props and colours, which never change.
- A beat with nobody in it says "no people", and its close-up never asks for a face.
- The vision check refuses gore, nudity, malformed bodies, text and pictures that do not fit the line.
- **Prop identity:** 85% of a video's cast shots must show each painted character's signature prop or colour. A cast
  shot may be repainted from two spare seeds before it is dropped.
  An early check can stop spare generation once a painting passes these same picture rules. Its verdict is bound
  to the exact image and story prompt; a missing key, unavailable editor or timeout keeps ordinary spare generation.
  This saves painting time only. Render independently checks the selected pictures and full audiovisual approval
  remains mandatory before batch release.
- A refused beat repeats the nearest earlier passing painting. The Short is held when fewer than 70% of its beats
  pass, or when the hook painting fails.
- **Frame 0 is the peak image:**
  - mean luma 90-170 and RMS contrast 0.18-0.45;
  - the hook strip in the top third, 10-28% of the frame height;
  - all text inside the safe zone.
- No luma blink of more than 35% outside a cut is allowed, and the frame count must match the narration to within
  one frame.
- An opening below the brightness band receives one bounded gamma lift, calibrated after the camera crop,
  grade and overlays. The same plate is used throughout its shot and loop; the finished picture gates still apply.
- A painting reused from an earlier beat must pass the current beat's own scene and prop checks. Object-only
  scenes use the same plan in the painter and picture editor; an unsuitable replacement holds the Short.
- Reviewed replays can keep original paintings in the replay's adjacent `art/` directory. Story, exact painter
  prompt and image SHA-256 must match; only the remaining beats request paint jobs. All inputs are screened again.

## Voice and sound

- One narrator: adult प्रभात, read by Gemini TTS Charon. He sounds like he is remembering: low, warm and
  unhurried. The fallback is a Chatterbox clone of the same voice. A Short read by a local fallback writer is never
  published.
- Onset within 0.3 s.
- Pace:
  - the hook aims at 170-185 wpm, with a hard band of 150-205;
  - the body aims at 155-175 wpm, with a hard band of 140-190.
- Whisper checks every line: coverage ≥0.95, Devanagari character error rate ≤0.12, and no gap over 1.2 s.
- The music is a dark-ambient bed written in code, with a bell at the turn.
- The final mix is measured with ebur128: -15 to -13 LUFS integrated, and a true peak at or below -1 dBFS.

## Disclosure

- The YouTube altered-or-synthetic flag is set on every upload.
- The on-screen label "AI चित्र और आवाज़ · काल्पनिक कहानी" stays up for the whole Short.
- The description includes a line saying the story is fiction with AI pictures and an AI voice.
- An end card repeats it.
- Every upload is category Entertainment (24), language Hindi, not made for kids.

## Publishing, cadence and learning

**Reviewed batch releases (25 October 2026).** `ops/cloud_batch.py` and `kahaani/batch_release.py` add a
resumable release path for exact successful preview artifacts. The AI editor receives the complete rendered video
and mixed soundtrack; timestamped visual/audio observations and an approval bound to the original MP4 and brief
are mandatory. This is AI review, never a claim of human listening. Missing quota, a negative or incomplete verdict,
local writer output, an uncalibrated picture editor, stale rotation, duplicate premise or occupied release slot
holds the entry. A private draft release preserves media and review receipts. State checkpoints precede dispatch
and upload. Upload recovery requires both the existing story marker and the reviewed MP4 SHA-256 binding; an older
unbound upload is held for reconciliation. Private processing and audience readback must pass before making a new
upload public. Reviewer/network outages retry with backoff; negative verdicts persist for unchanged media. Two approved episodes are required before
the first recovery release. The ordinary producer/publisher respects the batch's durable calendar reservation.
`batch-release.yml` serializes these checks with the existing publisher, runs on completed builds and every
fifteen minutes when `BATCH_RELEASE_ENABLED=true`, and defaults manual runs to review only. Automatic mode
uses the channel's existing environment credentials. The complete media-bound verdict is checkpointed before
archiving, so an archive outage cannot replace a refusal with a new review on the next runner.
Code alone is not proof of a release. No existing upload
ids, disclosure settings, voices or cadence are changed.
A known editorial hold allows only bounded dry production ahead (four unconsumed previews maximum);
review and release retain their predecessor checks. Every pending dispatch is reconciled before another is sent.

Object-only still-life scenes also receive at most two spare seeds. The early exact-image editor skips
unused spares after a passing base; a failed empty-object shot retains the same bounded repaint path as cast
shots. Final picture and AV checks remain mandatory.

**Explicit production holds (25 October 2026).** A bank entry with `production_hold` stays in the bible but
is excluded from ordinary selection and refused by explicit replays, including preview replays without rotation.
While a hold unbalances the three title-skeleton counts, selection checks a feasible ten-entry lookahead; an
unheld bank retains the existing full-bank lookahead. Every actual pick still passes all rotation rules.
The unbooked carrom e08 slot is replanned to existing e32 at the same time after repeated materially wrong
board/action images. `strategy/carrom-e08-quarantine.json` records exact refusals. Old runs, media and unresolved
holds remain quarantined; the replacement requires the normal complete production and release checks.

**Batch previews (25 October 2026).** `strategy/batch-2026-10-25.json` lists twenty distinct future entries plus
the first corrected preview. `.github/replay/batch-2026-10-25/*.json` are bank-entry briefs, not finished stories.
The existing dry-run dispatch accepts these through `replay`, checks the planned predecessor rotation and calls
the normal writer/editor, painter, picture checks, voice and render gates. A brief is refused in publish mode.
No preview consumes the live ledger, creates an upload, or books a release. Complete audiovisual review and a
fresh duplicate/rotation check are required before promoting a finished story. Existing release slots stay fixed.

Replay repairs reuse only matching story, beat, exact painter prompt and SHA-256 image bytes. Original alternate
paintings retain their variant metadata and go back through the current picture editor with the base image.
Changing a scene invalidates that beat's cached inputs.
English painter directions are bounded at 12–120 words so a repair can specify distinct actors and physical prop
support; the normal writer still targets 20–60. Spoken Hindi, runtime, picture, voice and AV gates retain their
existing limits. Local repair staging checks the full story before dispatch. The e02 recovery reuses beats 0–5 and repaints ending 6;
the superseded run's duplicated ending is excluded and its id is retained in the adoption record.

- **Cadence:** the current `config.FORMATS` has F1 slots daily at 13:00 and 19:00 IST (07:30 and 13:30 UTC), with
  capacity for three ready Shorts. Recovery first requires two passing buffered episodes and two verified public
  slots; an empty buffer does not justify bypassing a gate. The F2 and F3 slots register when those formats are built.
- **Uploads:**
  - private with `publishAt` at the slot, with subscribers not notified for the first 30 days after the relaunch;
  - filed in the F1 playlist when `KC_PLAYLIST_MICRO` is set;
  - the channel posts one first comment: the Short's own question for an open-question ending, otherwise "आपके
    गाँव में भी कोई ऐसी चीज़ थी, जिसका कोई नियम था? नीचे लिखिए 👇".
- **Read-back:** every upload is read back. Any drift in made-for-kids, privacy, `publishAt`, the synthetic flag,
  upload status or the channel holds the run, and nothing is commented or filed.
- **Learning:**
  - Each Short is scored at 48 h as 0.5 × viewed% + 0.3 × log views + 0.2 × subscribers per 1K views (as z-scores).
    The score falls back to views alone when the Analytics scope is missing, and the gap is reported.
  - Once there are at least 4 samples, the score becomes a lift per feature value (skeleton, ending, resolution,
    heart type), clamped to 0.75-1.35. The skeleton lift reorders the bank, and the rest are reported in
    `state/LEARNINGS.md`.
  - Health alerts open when fewer than 10 bank entries are unused.
- No views are promised.

### Narration failure evidence (25 October 2026)

The production artifact retains `narration.wav` even when the voice gate holds. The quiet-pause editor records candidate intervals and the exact word/sample protection that refused each cut in `pause-diagnostics.json`. `diagnose-voice.yml` reproduces an existing replay with the established narrator clone only; it has read-only repository access, no secrets, no painting, no state writes and no publishing. A diagnosis never approves a release.

Producer metadata is refreshed independently of ordered review, including behind an editorial hold. A completed later preview still occupies the bounded buffer but never an active producer slot. This cannot clear a hold or approve media.

A final Gemini narration that fails after pacing is rejected before returning from synthesis. Its exact WAV and checks are retained as `gemini-rejected.*`; the existing narrator clone gets one ordinary bounded attempt and must pass every final voice gate itself. The same failing audio is never approved or retried for a different verdict.

The batch preview image limits are shared across both channels: two Pangaea producers with four image jobs each plus two Kahaani producers with three painting jobs each use at most fourteen of twenty account runners. Six remain for news, release coordinators, narration, CI and monitoring. Earlier per-channel reservations did not account for the other channel and allowed the actual release coordinators to queue behind painting jobs. Existing producer, buffer and release-order limits stay in force.

Actual e07 diagnostic40158648541 identified an accumulated join gap: recorded quiet clip edges plus the inserted twist pause produced1.22 seconds, and a full-take Whisper word interval protected the zero centre. Clone assembly now budgets only newly inserted inter-beat zeros against existing quiet edges, allowing the slowest permitted tempo and two RMS frames of margin. Every source clip remains unchanged. The protected-word editor and1.2-second final ceiling remain in force. Regression uses a hashed excerpt of the actual failure and checks exact speech preservation and the slowest tempo; a successful test is not audiovisual or release approval.

New writer drafts describe the opening object before a softly blurred setting and explicitly target the existing 30%-90% opening-subject gate. Paper-ticket, slip, receipt, letter and postcard scenes use their blank reverse or hide the marked surface while narration supplies written details. Exact replays, speech and all picture/audiovisual gates remain unchanged. This addresses the directly inspected e12 tiny printed-ticket hook; prompt instructions alone do not approve an image.
