"""One F1 micro-entry ("सन्नाटपुर की छोटी एंट्री") from one bank entry: Gemini writes it (local Gemma when Gemini
can't) with the bible injected, the code gates check it, a second call edits it as a story editor would (including
the made-for-kids self-check), and up to REPAIRS rewrites fix what either found. A story that still fails is held,
never published.
"""
from __future__ import annotations

import json
import re

from . import bible, gate, gemini, hindi, llm, variation

REPAIRS = 2


class WriterHold(RuntimeError):
    """No draft passed the gates and the editor."""

    def __init__(self, message, *, draft=None, log=None):
        super().__init__(message)
        self.draft, self.log = draft, log


CAST_IDS = [c for c in bible.ON_SCREEN]
SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "hook_strip": {"type": "string"},
        "object_token": {"type": "string"},
        "anomaly": {"type": "string"},
        "niyam_id": {"type": "string"},
        "resolution_type": {"type": "string", "enum": list(gate.RESOLUTIONS)},
        "ending_type": {"type": "string", "enum": list(gate.ENDINGS)},
        "turn_beat": {"type": "integer"},
        "heart_beat": {"type": "integer"},
        "cast": {"type": "array", "items": {"type": "string", "enum": CAST_IDS}},
        "beats": {"type": "array", "items": {"type": "object", "properties": {
            "text": {"type": "string"},
            "scene": {"type": "string"},
            "people": {"type": "array", "items": {"type": "object", "properties": {
                "name": {"type": "string", "enum": CAST_IDS}, "expression": {"type": "string"}},
                "required": ["name", "expression"]}},
        }, "required": ["text", "scene", "people"]}},
        "description": {"type": "string"},
        "hashtags": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["title", "hook_strip", "object_token", "anomaly", "niyam_id", "resolution_type", "ending_type",
                 "turn_beat", "heart_beat", "cast", "beats", "description", "hashtags"],
}
EDIT_SCHEMA = {
    "type": "object",
    "properties": {
        "logic_ok": {"type": "boolean"},
        "rule_clear": {"type": "boolean"},
        "hook_has_anomaly": {"type": "boolean"},
        "heart_lands": {"type": "boolean"},
        "natural_hindi": {"type": "boolean"},
        "canon_ok": {"type": "boolean"},
        "kids_directed": {"type": "boolean"},
        "title_spoils_turn": {"type": "boolean"},
        "red_line": {"type": "boolean"},
        "problems": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["logic_ok", "rule_clear", "hook_has_anomaly", "heart_lands", "natural_hindi", "canon_ok",
                 "kids_directed", "title_spoils_turn", "red_line", "problems"],
}
ENDING_RULE = {
    "loop-back": "The last beat echoes frame 0 in fresh words, naming the same object again, so the Short seems to "
                 "begin again and replays naturally into beat 1.",
    "register-line": "The last beat is Jhabbu writing one line in his रजिस्टर about this night (say रजिस्टर).",
    "open-question": "The last beat leaves one honest open question about the night for the comments, ending with "
                     "'?'. Never ask for likes or comments; just ask the question.",
    "next-raat-tease": "The last beat says the whole night comes on शनिवार (say शनिवार), without giving it away.",
}
RESOLUTION_RULE = {
    "leave-it-be": "they solve it by following the rule and leaving the thing alone",
    "kindness": "they solve it with a kindness, not force",
    "bargain": "they solve it with a fair small bargain the rule allows",
    "outsmart": "they solve it by using the rule cleverly",
}
SYSTEM = """You are the head writer of "सन्नाटपुर की रातें", a Hindi YouTube channel of ORIGINAL 90s-nostalgia
mystery stories for ADULTS (18-44) who grew up in the 90s. Not for kids, never a kids' cartoon, no rhymes. One
narrator only: प्रभात, now forty-seven, remembering in 2026 a night from 1996 when he was seventeen. He tells it the
way a man talks to an old friend at night: warm, everyday spoken Hindi with idiom, short sentences, concrete 90s
textures, no textbook words (तत्पश्चात, उपरोक्त, अत्यंत). Narration only: nobody else speaks a line out loud; what
others said is told in his words. Every story is fiction in an invented village and never claims to be true."""
BRIEF = """THE BIBLE (fixed; never contradict it):
{bible}

TODAY'S MICRO-ENTRY ({id}): object {object!r} (token {object_token!r}); anomaly: {anomaly}
place: {location}; rule {niyam_id}; heart ({heart_type}): {heart_beat}
resolution ({resolution_type}): {resolution_rule}
logline: {logline}
hook line to build on: {hook_line}
title seed (skeleton {skeleton}): {title}

Write one Short of {words_lo}-{words_hi} spoken Hindi words across {beats_lo}-{beats_hi} beats (35-55 seconds).
BEATS, in order:
1. COLD OPEN, the peak image: the impossible moment itself, at most {hook} words, naming the {object_token!r} and
   its anomaly in the first {hook} words. No "1996", no set-up, no greeting.
2. "उन्नीस सौ छियानवे, उस रात…": the ordinary 90s night it happened in (say छियानवे in words).
3. The first sign. 4. Escalation. (May merge into one beat when you use five beats.)
5. The turn: the trio realise which rule of the night this is ({niyam_id}). turn_beat = this beat's number.
6. The heart beat ({heart_type}): {heart_beat} heart_beat = this beat's number (at or after the turn).
7. ENDING ({ending}): {ending_rule}

RULES (all mandatory):
- text: one or two short spoken sentences per beat, Devanagari only, no English words, no digits (numbers as Hindi
  words). Never greet, never say a channel name, never ask to like, share, follow or subscribe, never 'क्या आप
  जानते'. Do not open beat 1 with: {openings}.
- Only these people: झब्बू, प्रभात, नुज़हत, शैलेश, and minor people called by their job only. No other names.
- Never: gods, saints, holy men, temples, mosques, shrines, graveyards, puja, aarti, havan, namaz, tantrik,
  jhaad-phoonk, amulets, mantras, any spirit or being (brahmarakshas, pishach, betaal, chudail, daayan, jinn,
  preta); nobody is possessed, cursed or killed. No real places, people, films, songs or brands (say "रेडियो",
  "बिस्कुट", "पुरानी सफ़ेद कार"). No gore, sexual content, self-harm, caste or community markers. Exclamations
  too: say हाय, बाप रे, अरे or उफ़, never हे भगवान or या खुदा.
- cast: the ids of everyone painted in any beat, from {cast_ids}. At most four ids across the whole Short,
  including prabhat_adult if his present-day hands appear. Choose the few people this entry needs; never add
  all the available cast. A memory narrated by adult Prabhat need not paint his present-day hands.
- scene: for each beat, 20-60 English words describing ONE painting: who is in it (cast ids exactly), what they do,
  the place, one warm practical light (lantern, electric battery flashlight or bulb) against moonlit blue (a next-morning beat says dawn
  instead), and the camera. Beat 1 is the
  peak image, an extreme close view of the {object_token!r} doing the impossible. Its subject must occupy
  30%-90% of the frame: describe the large foreground object before the softly blurred setting, rather than
  a wide room with a tiny object. For a paper ticket, slip, receipt, letter or postcard, show its blank unprinted
  reverse or turn the marked surface away; the Hindi narration supplies any written date, name or message.
  Faces small, backlit or three-quarters away; the object and props carry the picture.
  Never append "People: empty" or serialized character JSON to scene; put structured cast data only in people.
  Nuzhat's light is her metal battery flashlight with a cracked lens and a split electric beam. Call it
  "electric metal flashlight" in English scenes; the English word "torch" can produce a burning stick instead.
  When it is the scene's sole practical light, include "The electric flashlight is the only practical light."
  If she needs both hands, explicitly say "Her metal battery flashlight rests beside her"; retain its cracked
  lens and split electric beam, rather than giving her a third hand or replacing it with an oil lantern.
  The present-day prabhat_adult is always the bible's close-up of one pair of middle-aged hands with the faded
  blue notebook and steel-rimmed glasses beside a desk lamp. Frame at the wrists: never a portrait, chin-on-hand
  pose, visible face, full body or a second younger Prabhat in the same painting.
  Include the exact framing sentence "Only hands and wrists are within the frame."
  For an outdoor object close-up, include "The scene is outdoors." so an object's interior or a look inside a
  bucket does not turn the canal or well into an enclosed room. Reserve room/interior directions for actual rooms.
  No text, signs, logos or labels in any picture. Call the cast
  young men and young women, never kids, children, boys or girls; when the object moves by itself, that beat shows
  the object alone (nobody in the painting, people empty) and the cast react in the beats around it.
  When a discovered object explains the turn, show that object and its exact location clearly in a close shot;
  put reactions in the adjacent beat. Do not crowd the reveal with the whole cast or put the same prop on a
  character and on the ground at once. Choose the smallest visible cast the narrated moment needs, usually
  one or two people. An introspective question ending can show the narrator alone; do not add a four-person
  group merely to include everyone, because their distinct clothing and carried props must stay clear.
  If the narration says nobody is at the object or station, paint that station unoccupied and leave people
  empty. A lantern can rest unattended on a shelf; its owner's name does not put that person in the shot.
  Repeat the actual location in EVERY beat's scene. An indoor story stays inside enclosing walls with a solid
  ceiling; moonlight enters through windows. Ceiling-mounted objects remain attached to that ceiling.
  Make the named acting character perform the narrated action, identified by their fixed clothing. When one
  character handles the key object, prefer a clear shot of that character alone; put other reactions in adjacent
  beats. A character setting down a prop must not simultaneously be described carrying the same prop.
  No painting may contain readable or invented letters, names or numbers. If the plot turns on a written name,
  register entry or message, let the Hindi narration tell it while the painting shows the character reacting,
  with the marked surface turned away or out of view. Do not ask the painter to scratch, print or display a name.
- people: for each beat, every cast id visible in its painting with their expression at this moment; empty when
  no one is visible.
- hook_strip: 3-5 Hindi words painted over frame 0 (a teaser, not the title), no emoji.
- object_token: exactly {object_token!r}. anomaly: one short Hindi phrase. niyam_id: exactly {niyam_id!r}.
  resolution_type: exactly {resolution_type!r}. ending_type: exactly {ending!r}.
- title: skeleton {skeleton} ({skeleton_help}); {title_lo}-{title_hi} characters; one or two emoji; the
  {object_token!r} within the first five words; never बच्चों, kids, cartoon, चौकीदार. You may keep or improve
  the seed title. Never reveal the turn.
- description: 1-2 Hindi sentences that tease the night without the turn.
- hashtags: 3-5, always #सन्नाटपुर, e.g. #सन्नाटपुर #90sकीयादें #रहस्य.
Return only the JSON."""
EDITOR = """You are the story editor of "सन्नाटपुर की रातें", Hindi 90s-nostalgia mystery Shorts for adults. Read
this draft as a viewer would and answer honestly:
- logic_ok: every event follows from what came before; nothing happens without a cause.
- rule_clear: the rule of the night (below) is what solves it, and a viewer hearing it once understands how.
- hook_has_anomaly: beat 1 names the selected bank object below AND the impossible thing it does.
  Judge its concrete role in this 1996 village. The bank includes fixtures and structures as well as
  portable objects; do not require technology exclusive to the 1990s or substitute a different object.
  Still refuse an absent object, a missing impossible action, or a scene that fails to show that action.
- heart_lands: the heart beat (a kindness, a confessed lie or a goodbye) is felt, not just stated.
- natural_hindi: the narration sounds like natural everyday spoken Hindi, not a translation.
- canon_ok: the people, their ages, props and the rule match the bible below; nobody else has a proper name.
- kids_directed: true if the script, title or description reads as made for children (nursery tone, a moral
  lesson told to kids, cartoon framing, simplistic baby talk). It is meant for adults.
- title_spoils_turn: true if the title or description gives the turn away.
- red_line: true if it touches any religion, deity, saint, ritual, shrine or spirit-being; real people, places,
  brands or events; gore, sexual content, harm to a child, self-harm; caste or community coding of anyone.
- problems: each concrete fix needed, in a short English sentence naming the beat; empty when it is ready.

RULE OF THE NIGHT {niyam_id}: {niyam}
SELECTED BANK PREMISE:
{premise}
BIBLE:
{bible}

DRAFT:
{draft}"""


class Pen:
    """Gemini first, then the local Gemma model (started only if needed). Records which model answered each call."""

    def __init__(self, local: str | None = None):
        self.local_name = local or llm.DEFAULT
        self.local = None
        self.used: list[str] = []

    def chat(self, messages: list[dict], schema: dict | None = None, temperature: float = 0.8,
             max_tokens: int = 4096) -> dict | str:
        if gemini.available():
            try:
                answer, model = gemini.chat(messages, schema, temperature, max_tokens)
                self.used.append(model)
                return answer
            except gemini.Unavailable:
                pass
        if self.local is None:
            self.local = llm.Model(self.local_name).__enter__()
        self.used.append(self.local_name)
        return self.local.chat(messages, schema, temperature=temperature, max_tokens=max_tokens)

    def close(self) -> None:
        if self.local is not None:
            self.local.__exit__(None, None, None)
            self.local = None

    def __enter__(self) -> "Pen":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def messages(premise: dict, history: list[dict], problems: list[str] | None = None,
             previous: dict | None = None) -> list[dict]:
    from .premises import f1

    openings = sorted({r["opening"] for r in f1(history)[-variation.RECENT:] if r.get("opening")})
    ending = premise["ending_type"]
    skeleton = premise.get("title_skeleton") or "S1"
    brief = BRIEF.format(bible=bible.writer_context(premise), id=premise["id"], object=premise["object"],
                         object_token=premise["object_token"], anomaly=premise["anomaly"],
                         location=premise["location"], niyam_id=premise["niyam_id"],
                         heart_type=premise["heart_type"], heart_beat=premise["heart_beat"],
                         resolution_type=premise["resolution_type"],
                         resolution_rule=RESOLUTION_RULE.get(premise["resolution_type"], ""),
                         logline=premise["logline"], hook_line=premise["hook_line"], title=premise["title"],
                         skeleton=skeleton, skeleton_help=gate.SKELETON_HELP[skeleton], words_lo=gate.WORDS[0],
                         words_hi=gate.WORDS[1], beats_lo=gate.BEATS[0], beats_hi=gate.BEATS[1], hook=gate.HOOK_WORDS,
                         ending=ending, ending_rule=ENDING_RULE[ending], title_lo=gate.TITLE_CHARS[0],
                         title_hi=gate.TITLE_CHARS[1], cast_ids=", ".join(CAST_IDS),
                         openings=", ".join(f"'{o}'" for o in openings) or "(none yet)")
    out = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": brief}]
    if problems and previous:
        hook_help = ""
        hook = (previous.get("beats") or [{}])[0].get("text", "")
        if len(hindi.words(hook)) > gate.HOOK_WORDS:
            counted = " | ".join(f"{i}: {word}" for i, word in enumerate(hindi.words(hook), 1))
            hook_help = f"\nThe actual Hindi hook tokens are: {counted}."
            bank_hook = premise.get("hook_line", "")
            if bank_hook and len(hindi.words(bank_hook)) <= gate.HOOK_WORDS:
                hook_help += (f"\nUse this bank opening verbatim as beat 1's spoken text: {bank_hook}"
                              f"\nIt has {len(hindi.words(bank_hook))} Hindi words. Do not add a name or setup "
                              "to that line. Preserve the other valid story beats while fixing the listed checks.")
        counts = [len(hindi.words(b.get("text", ""))) for b in previous.get("beats", [])]
        if sum(counts) > gate.WORDS[1] and len(counts) > 1:
            target = sum(gate.WORDS) // 2
            per_beat = (target - gate.HOOK_WORDS) // (len(counts) - 1)
            hook_help += (f"\nCurrent spoken words by beat: {counts}, total {sum(counts)}. "
                          f"Use at most {gate.HOOK_WORDS} words in beat 1 and about {per_beat} words in each "
                          f"remaining beat, roughly {target} words overall. Cut clauses; do not add setup.")
        out += [{"role": "assistant", "content": json.dumps(untidy(previous), ensure_ascii=False)},
                {"role": "user", "content": "Your draft failed these checks. Fix every one and return the full "
                                            "corrected JSON, every beat's text, scene and people written out in "
                                            "full even where nothing changed:\n"
                                            + "\n".join(f"- {p}" for p in problems) + hook_help}]
    return out


def _squash(value) -> str:
    return " ".join(str(value or "").split())


def _int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def tidy(draft: dict) -> dict:
    """Normalise whitespace and small shape slips into the Story's field names; the hook is beat 1's spoken line and
    the cast sheet is the bible's (ids the writer named, looks from cast.yaml)."""
    raw = dict(draft)
    beats = []
    for b in raw.get("beats") or []:
        people = [{"name": _squash(p.get("name")), "expression": _squash(p.get("expression"))}
                  for p in b.get("people") or [] if isinstance(p, dict)]
        beats.append({"text": _squash(b.get("text")), "scene": _squash(b.get("scene")), "people": people})
    known = bible.cast()
    ids = [i for i in dict.fromkeys(_squash(c.get("id") if isinstance(c, dict) else c) for c in raw.get("cast") or [])]
    for b in beats:  # someone painted in a beat is in the cast even if the writer forgot to list them
        ids += [p["name"] for p in b["people"] if p["name"] not in ids]
    cast = [{"id": i, "name": known[i]["name"]["hi"], "look": known[i]["image"]} if i in known else {"id": i}
            for i in ids]
    return {"title": _squash(raw.get("title")), "hook": beats[0]["text"] if beats else "",
            "hook_strip": _squash(raw.get("hook_strip")), "object_token": _squash(raw.get("object_token")),
            "anomaly": _squash(raw.get("anomaly")), "niyam_id": _squash(raw.get("niyam_id")),
            "resolution": _squash(raw.get("resolution_type", raw.get("resolution"))),
            "ending": _squash(raw.get("ending_type", raw.get("ending"))),
            "twist_beat": _int(raw.get("turn_beat", raw.get("twist_beat"))), "heart_beat": _int(raw.get("heart_beat")),
            "cast": cast, "beats": beats, "description": _squash(raw.get("description")),
            "hashtags": [t.strip() for t in raw.get("hashtags") or []
                         if isinstance(t, str) and t.strip().startswith("#") and " " not in t.strip()][:5]}


def untidy(draft: dict) -> dict:
    """A tidied draft in the writer's own schema, for a repair turn."""
    return {"title": draft["title"], "hook_strip": draft["hook_strip"], "object_token": draft["object_token"],
            "anomaly": draft["anomaly"], "niyam_id": draft["niyam_id"], "resolution_type": draft["resolution"],
            "ending_type": draft["ending"], "turn_beat": draft["twist_beat"], "heart_beat": draft["heart_beat"],
            "cast": [c["id"] for c in draft["cast"]], "beats": draft["beats"], "description": draft["description"],
            "hashtags": draft["hashtags"]}


def carry(previous: dict, draft: dict) -> dict:
    """A rewrite asked to fix the narration can come back with the untouched scenes cut short ("same as before"): with
    the beat count unchanged, an unusable scene keeps the previous draft's scene and people for that beat."""
    old, new = previous.get("beats") or [], draft.get("beats") or []
    if len(old) != len(new):
        return draft
    for before, now in zip(old, new):
        if not gate.scene_ok(now["scene"]) and gate.scene_ok(before["scene"]):
            now["scene"], now["people"] = before["scene"], before["people"]
    return draft


def anchor_place(draft: dict, premise: dict) -> dict:
    """Make new PCO counter scenes explicitly indoor before the story editor and painter see them.

    Bare 'PCO counter' inherited the outdoor village house style in e17. This only normalises new
    writer drafts; replay stories and their exact cached painting prompts remain untouched.
    """
    if premise.get("place_id") != "pco":
        return draft
    for beat in draft.get("beats", []):
        scene = beat["scene"]
        if not re.search(r"\bPCO\b", scene, re.I):
            continue
        if re.search(r"\b(interior|indoors|inside|enclosed)\b", scene, re.I):
            continue
        # An establishing view outside the building is deliberate; blue night outside a window is not.
        if re.search(r"\b(?:outside|exterior of|in front of)\s+(?:the\s+)?(?:village\s+)?PCO\b", scene, re.I):
            continue
        beat["scene"] = ("Inside an enclosed PCO counter room with solid plaster walls and a solid ceiling. "
                         + scene)
    return draft


def edit(draft: dict, ask, premise: dict | None = None) -> list[str]:
    """The editor's problems with a draft that passed the code gates; empty when it is ready."""
    premise = premise or {}
    shown = {k: draft[k] for k in ("title", "hook_strip", "beats", "twist_beat", "heart_beat", "ending",
                                    "description")}
    rule = bible.niyam().get(draft.get("niyam_id"), {})
    verdict = ask([{"role": "user", "content": EDITOR.format(
        niyam_id=draft.get("niyam_id"), niyam=rule.get("hi", ""), bible=bible.writer_context(premise),
        premise=json.dumps({k: premise[k] for k in ("object", "object_token", "anomaly", "logline")
                            if k in premise}, ensure_ascii=False),
        draft=json.dumps(shown, ensure_ascii=False, indent=1))}], EDIT_SCHEMA)
    found = [p for p in verdict.get("problems") or [] if isinstance(p, str) and p.strip()]
    flags = {"logic_ok": "the story's logic has a gap", "rule_clear": "the rule of the night does not clearly solve it",
             "hook_has_anomaly": "beat 1 must show the object and its impossible behaviour",
             "heart_lands": "the heart beat is stated, not felt", "natural_hindi": "the Hindi sounds unnatural",
             "canon_ok": "the draft contradicts the bible (people, props or the rule)"}
    found += [why for key, why in flags.items() if verdict.get(key) is False]
    if verdict.get("kids_directed"):
        found.append("the editor reads it as made for kids; write it for adults who grew up in the 90s")
    if verdict.get("title_spoils_turn"):
        found.append("the title or description gives the turn away")
    if verdict.get("red_line"):
        found.append("the editor found a red-line topic")
    return list(dict.fromkeys(found))


def scene_metadata_problems(draft: dict) -> list[str]:
    """Reject leaked schema before new drafts spend a painter job; exact saved replays keep their prompts."""
    leaked = re.compile(r'\b(?:people|cast)\s*:\s*(?:empty\b|none\b|\[|\{)|'
                        r'["\'](?:name|expression|people|cast)["\']\s*:', re.I)
    return [f"beat {i} painter scene contains character metadata or JSON; write English visual prose only. "
            "Keep character ids and expressions in the separate people array, and preserve spoken text."
            for i, beat in enumerate(draft.get("beats") or [], 1) if leaked.search(beat.get("scene", ""))]


def write(premise: dict, history: list[dict], ask) -> tuple[dict, list[dict]]:
    """(draft, log) for a bank entry (premises.premise_for); raises WriterHold after REPAIRS failed rewrites.
    ask(messages, schema) -> dict."""
    log: list[dict] = []
    draft = anchor_place(tidy(ask(messages(premise, history), SCHEMA)), premise)
    for attempt in range(REPAIRS + 1):
        found = gate.check(draft, premise, history) + scene_metadata_problems(draft)
        stage = "gates"
        if not found:
            found, stage = edit(draft, ask, premise), "editor"
        log.append({"attempt": attempt, "stage": stage, "problems": found})
        if not found:
            return draft, log
        if attempt == REPAIRS:
            break
        draft = anchor_place(carry(draft, tidy(ask(messages(premise, history, found, draft), SCHEMA))), premise)
        # The bank fixes the opening already. A rewrite that keeps adding words
        # can use that exact canonical line before all code and editor checks.
        # This neither truncates Hindi nor invents a replacement; record the edit.
        bank_hook = premise.get("hook_line", "")
        if (draft.get("beats") and len(hindi.words(draft["beats"][0]["text"])) > gate.HOOK_WORDS
                and bank_hook and len(hindi.words(bank_hook)) <= gate.HOOK_WORDS):
            log[-1]["canonical_hook_repair"] = {"original": draft["beats"][0]["text"], "replacement": bank_hook}
            draft["beats"][0]["text"] = draft["hook"] = bank_hook
    raise WriterHold(f"hold: no draft of {premise['id']} passed after {REPAIRS} repairs: " + "; ".join(found)[:300],
                     draft=draft, log=log)
