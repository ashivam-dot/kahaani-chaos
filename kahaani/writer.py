"""One original Hindi twist story from one premise: Gemini writes it (local Gemma when Gemini can't), the code gates
check it, a second call edits it as a story editor would, and up to REPAIRS rewrites fix what either found. A story
that still fails is held, never published.
"""
from __future__ import annotations

import json

from . import gate, gemini, llm

REPAIRS = 2


class WriterHold(RuntimeError):
    """No draft passed the gates and the editor."""


SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "hook": {"type": "string"},
        "beats": {"type": "array", "items": {"type": "object", "properties": {
            "text": {"type": "string"},
            "scene": {"type": "string"},
            "people": {"type": "array", "items": {"type": "object", "properties": {
                "name": {"type": "string"}, "expression": {"type": "string"}}, "required": ["name", "expression"]}},
        }, "required": ["text", "scene", "people"]}},
        "cast": {"type": "array", "items": {"type": "object", "properties": {
            "name": {"type": "string"}, "look": {"type": "string"}}, "required": ["name", "look"]}},
        "subgenre": {"type": "string", "enum": list(gate.SUBGENRES)},
        "ending": {"type": "string", "enum": list(gate.ENDINGS)},
        "twist_beat": {"type": "integer"},
        "description": {"type": "string"},
        "hashtags": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["title", "hook", "beats", "cast", "subgenre", "ending", "twist_beat", "description", "hashtags"],
}
EDIT_SCHEMA = {
    "type": "object",
    "properties": {
        "logic_ok": {"type": "boolean"},
        "twist_clear": {"type": "boolean"},
        "payoff_answers_hook": {"type": "boolean"},
        "natural_hindi": {"type": "boolean"},
        "title_spoils_twist": {"type": "boolean"},
        "red_line": {"type": "boolean"},
        "problems": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["logic_ok", "twist_clear", "payoff_answers_hook", "natural_hindi", "title_spoils_twist", "red_line",
                 "problems"],
}
ENDING_RULE = {
    "twist-reveal": "The twist beat reveals the truth that changes everything; the payoff shows its result and the "
                    "sting line leaves a small chill or smile.",
    "dilemma": "After the payoff, the last beat turns to the viewer with one short sincere question about the choice "
               "in the story, such as 'आप होते तो क्या करते?', ending with '?'.",
    "loop-back": "The last line echoes the hook in fresh words so the story seems to begin again, and the video "
                 "replays naturally into beat 1.",
}
SYSTEM = """You are the head writer of a Hindi YouTube Shorts channel of ORIGINAL magical and mysterious folk-fantasy
stories with a twist ("जादुई और रहस्यमयी कहानियाँ"), for a general Hindi audience aged 13+, not for kids. You write
the way a gripping storyteller talks to one listener at night: everyday spoken Hindi, short sentences, concrete
images, no textbook words (तत्पश्चात, उपरोक्त, अत्यंत). Every story is fiction and never claims to be true."""
BRIEF = """PREMISE ({subgenre}): {hi}
(English gloss: {en})

Write one Short of {words_lo}-{words_hi} spoken Hindi words across {beats_lo}-{beats_hi} beats (60-90 seconds).
ARC: beat 1 is the hook, at most {hook} words, stating the impossible image or the stakes; then a concrete character
with a want; the strange encounter; a rule or warning; a choice; the twist; the payoff that answers the hook; and a
sting line. ENDING ({ending}): {ending_rule}

RULES (all mandatory):
- text: one or two short spoken sentences per beat, Devanagari only, no English words, no digits (numbers as Hindi
  words). Never greet, never say the channel's name, never ask to like, share, follow or subscribe, never 'क्या आप
  जानते'. Do not open beat 1 with: {openings}.
- Never: gods, avatars, saints or holy men, scriptures, temples, prayers or religious miracles; real people, real
  events or news; gore or wounds; sexual content; harm to a child; self-harm; caste, religion or regional
  stereotypes. Ghosts may be eerie or gentle, never gory.
- cast: every character (1-4) with a fixed English look of 10-40 words: age, build, face, hair, clothes, one
  distinctive detail. An animal is described as a REAL animal ("a real thin grey village cat, not a person, no
  clothes"). The same look is used in every picture.
- scene: for each beat, 20-60 English words describing ONE painting: who is in it (cast names exactly), what they
  do at this moment, the setting, the light (lantern, moonlight, mist, dusk), and the camera (close-up, medium,
  wide, low angle). Beat 1 is a close-up of the impossible image. Vary the framing. No text in the picture. For
  danger show the moment before, or a symbol, never an injury.
- people: for each beat, every cast member visible in its painting with their expression at this moment
  (frightened, greedy grin, wide-eyed wonder...). An empty list when no one is visible.
- twist_beat: the number of the beat where the twist lands.
- title: spoken Hindi in Devanagari, the impossible turn first, at most {title} characters, exactly one emoji, ending
  with '!' or '?' (the emoji may follow it), e.g. "गरीब ने एक रोटी दी… सुबह घर सोने से भर गया! 😱". Never
  reveal the twist.
- description: 1-2 Hindi sentences that tease the story without the twist.
- hashtags: 3-5, e.g. #कहानी #रहस्य #hindistory.
Return only the JSON."""
EDITOR = """You are the story editor of a Hindi Shorts channel of original magical and mysterious twist stories for
a 13+ audience. Read this draft as a viewer would and answer honestly:
- logic_ok: every event follows from what came before; the rule set up earlier is what the twist turns on; nothing
  happens without a cause.
- twist_clear: a viewer hearing it once understands the twist.
- payoff_answers_hook: the payoff answers the question or image the hook raised.
- natural_hindi: the narration sounds like natural everyday spoken Hindi, not a translation.
- title_spoils_twist: true if the title or description gives the twist away.
- red_line: true if it touches gods, saints, scriptures, temples or religious miracles, real people or events,
  gore, sexual content, harm to a child, self-harm, or caste, religion or regional stereotypes.
- problems: each concrete fix needed, in a short English sentence naming the beat; empty when it is ready.

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
    openings = sorted({r["opening"] for r in history[-gate.RECENT_OPENINGS:] if r.get("opening")})
    ending = gate.required_ending(history)
    brief = BRIEF.format(subgenre=premise["subgenre"], hi=premise["hi"], en=premise["en"], words_lo=gate.WORDS[0],
                         words_hi=gate.WORDS[1], beats_lo=gate.BEATS[0], beats_hi=gate.BEATS[1], hook=gate.HOOK_WORDS,
                         ending=ending, ending_rule=ENDING_RULE[ending], title=gate.TITLE_CHARS,
                         openings=", ".join(f"'{o}'" for o in openings) or "(none yet)")
    out = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": brief}]
    if problems and previous:
        out += [{"role": "assistant", "content": json.dumps(previous, ensure_ascii=False)},
                {"role": "user", "content": "Your draft failed these checks. Fix every one and return the full "
                                            "corrected JSON:\n" + "\n".join(f"- {p}" for p in problems)}]
    return out


def _squash(value) -> str:
    return " ".join(str(value or "").split())


def tidy(draft: dict) -> dict:
    """Normalise whitespace and small shape slips; the hook is beat 1's spoken line."""
    draft = dict(draft)
    beats = []
    for b in draft.get("beats") or []:
        people = [{"name": _squash(p.get("name")), "expression": _squash(p.get("expression"))}
                  for p in b.get("people") or [] if isinstance(p, dict)]
        beats.append({"text": _squash(b.get("text")), "scene": _squash(b.get("scene")), "people": people})
    draft["beats"] = beats
    draft["cast"] = [{"name": _squash(c.get("name")), "look": _squash(c.get("look"))}
                     for c in draft.get("cast") or [] if isinstance(c, dict)]
    draft["title"] = _squash(draft.get("title"))
    draft["hook"] = beats[0]["text"] if beats else ""
    draft["description"] = _squash(draft.get("description"))
    try:
        draft["twist_beat"] = int(draft.get("twist_beat"))
    except (TypeError, ValueError):
        draft["twist_beat"] = None
    draft["hashtags"] = [t.strip() for t in draft.get("hashtags") or []
                         if isinstance(t, str) and t.strip().startswith("#") and " " not in t.strip()][:5]
    return draft


def edit(draft: dict, ask) -> list[str]:
    """The editor's problems with a draft that passed the code gates; empty when it is ready."""
    shown = {k: draft[k] for k in ("title", "beats", "twist_beat", "ending", "description")}
    verdict = ask([{"role": "user", "content": EDITOR.format(draft=json.dumps(shown, ensure_ascii=False, indent=1))}],
                  EDIT_SCHEMA)
    found = [p for p in verdict.get("problems") or [] if isinstance(p, str) and p.strip()]
    flags = {"logic_ok": "the story's logic has a gap", "twist_clear": "the twist is unclear",
             "payoff_answers_hook": "the payoff does not answer the hook",
             "natural_hindi": "the Hindi sounds unnatural"}
    found += [why for key, why in flags.items() if verdict.get(key) is False]
    if verdict.get("title_spoils_twist"):
        found.append("the title or description gives the twist away")
    if verdict.get("red_line"):
        found.append("the editor found a red-line topic")
    return list(dict.fromkeys(found))


def write(premise: dict, history: list[dict], ask) -> tuple[dict, list[dict]]:
    """(draft, log) for a premise; raises WriterHold after REPAIRS failed rewrites. ask(messages, schema) -> dict."""
    log: list[dict] = []
    draft = tidy(ask(messages(premise, history), SCHEMA))
    for attempt in range(REPAIRS + 1):
        found = gate.check(draft, premise, history)
        stage = "gates"
        if not found:
            found, stage = edit(draft, ask), "editor"
        log.append({"attempt": attempt, "stage": stage, "problems": found})
        if not found:
            return draft, log
        if attempt == REPAIRS:
            break
        draft = tidy(ask(messages(premise, history, found, draft), SCHEMA))
    raise WriterHold(f"hold: no draft of {premise['id']} passed after {REPAIRS} repairs: " + "; ".join(found)[:300])
