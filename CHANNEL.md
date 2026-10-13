# Kahaani Chaos — editorial rules

@KahaaniChaos (`UCX-96TVtOBCEkDMloHuYAHw`). "जादुई और रहस्यमयी कहानियाँ": original Hindi folk-fantasy and mystery
Shorts with a twist, for a general Hindi audience aged 13+. Not made for kids. These rules bind every story; the
code enforces what it can (`kahaani/gate.py`) and a second model reads the rest as an editor (`kahaani/writer.py`).

## Lane

- Five sub-genres: **jadui-inaam** (a kindness or a greed meets magic), **shraapit-cheez** (a cursed or strange
  object), **bhoot-rahasya** (a gentle or eerie ghost, a village mystery), **samay-chakra** (a time slip or loop),
  **chatur-chaal** (a clever trick).
- Ordinary Indian villages, towns and cities. Every story is fiction and says so.

## Red lines

Never, in narration, title, description, premise or picture:

- gods, avatars, saints or holy men, scriptures, temples, prayers or religious miracles (Mool Katha's lane);
- real people, real places as real events, news, or any "true story" claim;
- gore, wounds or killing shown; sexual content; harm to a child; self-harm;
- caste, religion or regional stereotypes.

Ghosts may be eerie or gentle, never gory. For danger, paint the moment before, or a symbol.

## Story

- 60-90 s: 140-200 spoken Hindi words in 9-12 beats, everyday spoken Hindi, Devanagari only, numbers as words.
- Arc: a hook of at most 10 words stating the impossible image or the stakes; a concrete character with a want; the
  strange encounter; a rule or warning; a choice; the twist (after the middle, before the last beat); the payoff that
  answers the hook; a sting line.
- Endings rotate, never two the same in a row: twist-reveal, then dilemma (the last beat asks the viewer one
  question, "आप होते तो क्या करते?"), then loop-back (the last line echoes the hook so the Short replays).
- No greetings or host openers in the hook, no channel name, no "क्या आप जानते", no like/subscribe/share/follow asks
  anywhere, including the end card.
- One premise is used once. No motif from the last 10 Shorts, no sub-genre from the last 2, no opening words from
  the last 10.

## Title

Spoken Hindi in Devanagari, the impossible turn first, at most 70 characters, exactly one emoji, ending in "!" or
"?" (the emoji may follow), never giving the twist away. Example: "एक सिक्का डालो, दो पाओ… पर कुएँ ने बदले में
क्या लिया? 😨".

## Look

One AI painting per beat in one house style: cinematic Indian folk-fantasy painting, lantern and moonlight, mist,
teal and amber, painterly, not photoreal, not cartoon (`kahaani/look.py`). Each story has a cast sheet; every prompt
repeats each character's fixed look and states their expression in that beat. Animals are real animals, never
animal-headed people. A vision check refuses gore, nudity, malformed bodies, text and pictures that don't fit the
line; a refused beat repeats the nearest earlier passing painting, and a story with under 70% passing, or a failed
hook painting, is held. A beat with nobody in it says "no people" in its prompt, and its hook close-up never asks
for a face: without that the model invented a stranger pouring the tea and the first dry run was held.

## Voice and sound

One storyteller narrator (Gemini TTS, `voice.VOICE`, chosen by a listening test), low and intimate, about 150 wpm,
a held pause before the twist. Fallback: a Chatterbox clone of the same narrator from `tts/voices/narrator_ref.wav`.
Whisper checks every line. Music is a dark-ambient bed written in code, with a bell struck at the twist; mixed to
-14 LUFS.

## Disclosure

The YouTube altered-or-synthetic flag on every upload; the on-screen label "AI चित्र और आवाज़ · काल्पनिक कहानी" for
the whole Short; a description line saying the story is fiction with AI pictures and an AI voice; an end card that
repeats it. Category Entertainment (24), language Hindi, not made for kids.

## Cadence and learning

Two Shorts a day at 12:30 and 20:30 IST, from a buffer of up to two finished Shorts. Views at 48 h per sub-genre
give a lift (shrunk n/(n+4), clamped 0.75-1.35) that reorders the next premises; a sub-genre's rest since it last
ran keeps all five rotating. After 20 Shorts the target is a median of 300+ views at 48 h; under 50, drop the two
weakest sub-genres and test 100-120 s stories. No views are promised.
