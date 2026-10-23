"""Looks at every painting before it can reach a Short: refuses nudity, sexual content, gore, malformed bodies, text
or logos in the picture, religious imagery, a made-for-kids look (chibi, big eyes, a kids' book), a cast shot that
does not show its characters' signature props or colours (prop identity, PLAN.md §7.4 gate l), and a picture that
doesn't show its line. The hook's painting is frame 0, so its main subject must fill HOOK_SUBJECT of the frame (PLAN.md
§7.4 g: at least 30%; the ceiling is ours, so the hook strip never sits on the subject's face). When no model can
look, nothing is published.
"""
from __future__ import annotations

import io
import logging
import re
from pathlib import Path

log = logging.getLogger(__name__)

PER_PROMPT = 5
SIDE = 768
FLAGS = ("nudity", "sexual", "gore", "malformed", "text", "religious", "kids_look")
# The cast has no one under 17. In dry run 39886731532 the editor described two cast shots as "two younger boys" and
# "a child" yet passed them (kids_look is about style), so a caption naming a child refuses the picture. Asking the
# editor about children outright got every request blocked (dry run 39892698527); its own caption is the signal.
CHILD_WORDS = re.compile(r"\b(child|children|kids?|toddlers?|(little|small|young|younger) (boys?|girls?)|"
                         r"schoolboys?|schoolgirls?)\b", re.I)
# A cast shot must show each painted character's signature prop or colour; a video needs PROP_RATE of its cast shots
# to (after up to look.ALTERNATES repaints each); a shot that never does is dropped.
PROP_RATE = 0.85
# The local fallback editor may pass paintings for a published Short only once vision-bench shows it refusing what
# the Gemini editor refuses (the child shots of dry run 39886731532 above all).
LOCAL_TRUSTED = False
HOOK_SUBJECT = (0.30, 0.90)  # share of the frame the hook painting's main subject covers

SCHEMA = {
    "type": "object",
    "properties": {
        "pictures": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "n": {"type": "integer"},
                    "shows": {"type": "string"},
                    **{f: {"type": "boolean"} for f in FLAGS},
                    "props_ok": {"type": "boolean"},
                    "fits": {"type": "boolean"},
                    "subject_share": {"type": "number"},
                    "reason": {"type": "string"},
                },
                "required": ["n", "shows", *FLAGS, "props_ok", "fits", "subject_share", "reason"],
            },
        },
    },
    "required": ["pictures"],
}

PROMPT = """You are the picture editor of "सन्नाटपुर की रातें", Hindi 90s-nostalgia mystery Shorts for adults, set in
an invented 1996 north-Indian village. An AI model painted each picture below for one narrated line; it will fill
the screen while that line plays. Look at the pixels carefully.

Story: {story}
Characters: {cast}

For each picture answer:
- shows: one short sentence describing what is actually visible.
- nudity: true if anyone is nude or nearly nude, or shows a bare breast, buttocks or genitals.
- sexual: true for kissing, embrace in a sexual way, seductive poses or a sexualised focus on the body.
- gore: true for blood, wounds, severed body parts or corpses.
- malformed: true if a main figure's face or body is visibly broken: extra or missing limbs or fingers, melted or
  doubled faces, an animal character painted as a person in clothes or with a human face.
- text: true if any legible or garbled letters, words, signs, captions, a watermark, a brand logo or a label appear.
- religious: true for any shrine, temple, mosque, idol, deity, holy man, prayer, holy thread, tilak, rosary, cross,
  crescent, sacred sign or grave.
- kids_look: true if it looks made for children: chibi or big-eyed cartoon faces, toddler proportions, a kids'
  picture-book or nursery style. The young people are 17-18 with adult proportions.
- props_ok: for each character the line says should appear, true only if that character is visible and shows at
  least one of their listed signature props or colours. True when the line lists no characters.
- fits: true if the picture plausibly shows this line's moment with this story's characters and setting, in a
  painted (not photographic, not cartoon) style. False for an unrelated scene, the wrong characters, a modern
  object the story doesn't have, or a sheet of several pictures.
- subject_share: the share of the whole picture (0.0-1.0) that its main subject (the object or person the line is
  about) covers, by area of its outline.
- reason: why, in a few words.

Pictures:
{lines}"""


def _small(path: Path) -> bytes:
    from PIL import Image

    image = Image.open(path).convert("RGB")
    image.thumbnail((SIDE, SIDE))
    buf = io.BytesIO()
    image.save(buf, "JPEG", quality=85)
    return buf.getvalue()


def rejected(verdict: dict, cast_shot: bool = False, hook: bool = False) -> str | None:
    """Why a verdict keeps its picture out of a Short, or None when the picture may be used. A cast shot must also
    pass prop identity, and the hook's painting must have its subject cover HOOK_SUBJECT of the frame (a missing
    answer counts as a failure for both)."""
    for flag in FLAGS:
        if verdict.get(flag):
            return f"{flag}: {verdict.get('reason') or verdict.get('shows')}"
    if CHILD_WORDS.search(verdict.get("shows") or ""):
        return f"child: the editor sees a child ({verdict.get('shows')})"
    if cast_shot and verdict.get("props_ok") is not True:
        return f"props: the characters' signature props or colours are missing ({verdict.get('reason') or ''})"
    if not verdict.get("fits"):
        return f"does not fit the line: {verdict.get('reason') or verdict.get('shows')}"
    share = verdict.get("subject_share")
    if hook and not (isinstance(share, (int, float)) and HOOK_SUBJECT[0] <= share <= HOOK_SUBJECT[1]):
        return (f"the hook's subject covers {share!r} of the frame, needs {HOOK_SUBJECT[0]:.0%}-"
                f"{HOOK_SUBJECT[1]:.0%}")
    return None


def expected(ids: list[str]) -> str:
    """Who a cast shot should show and what identifies each, for the prompt."""
    from . import bible

    known = bible.cast()
    return "; ".join(f"{known[i]['name']['en']} (any of: {bible.signature(i)})" for i in ids if i in known)


def judge(items: list[tuple], story: str, cast: str, ask) -> list[dict]:
    """One verdict per (picture file, narrated line[, who should appear]), in order. ask(parts, schema) answers like gemini.look; a missing
    or malformed verdict counts as a rejection."""
    verdicts: list[dict] = []
    for start in range(0, len(items), PER_PROMPT):
        chunk = items[start:start + PER_PROMPT]
        lines = "\n".join(f"{n}. narrated line: {item[1]}" + (f"\n   should appear: {item[2]}" if len(item) > 2 and
                                                              item[2] else "")
                          for n, item in enumerate(chunk, 1))
        parts: list = [PROMPT.format(story=story, cast=cast, lines=lines)]
        for n, item in enumerate(chunk, 1):
            parts += [f"Picture {n}:", _small(item[0])]
        answer = ask(parts, SCHEMA)
        got = {v.get("n"): v for v in (answer or {}).get("pictures", []) if isinstance(v, dict)}
        for n in range(1, len(chunk) + 1):
            verdicts.append(got.get(n) or {"n": n, "shows": "", "fits": False, "reason": "no verdict"})
    return verdicts


class Eye:
    """The picture editor: Gemini first, then Gemma 4 with its vision projector on the runner (llama.cpp; no account,
    key or quota), started only if needed. Once Gemini can't answer, the rest of the run stays local. Records which
    model answered each call (used)."""

    def __init__(self, local: str | None = None):
        from . import llm

        self.local_name = local or llm.VISION_DEFAULT
        self.local = None
        self.gemini_down = False
        self.used: list[str] = []

    def __call__(self, parts: list, schema: dict) -> dict:
        from . import gemini, llm

        if not self.gemini_down and gemini.available():
            try:
                answer = gemini.look(parts, schema)
                self.used.append("gemini")
                return answer
            except gemini.Unavailable as exc:
                log.warning("no Gemini model can look (%s); the local picture editor takes over", str(exc)[:300])
                self.gemini_down = True
        if self.local is None:
            try:
                self.local = llm.Model(self.local_name, vision=True).__enter__()
            except RuntimeError as exc:
                raise gemini.Unavailable(f"Gemini can't look and {exc}"[:600]) from exc
        self.used.append(self.local.name)
        return self.local.look(parts, schema)

    def close(self) -> None:
        if self.local is not None:
            self.local.__exit__(None, None, None)
            self.local = None

    def __enter__(self) -> "Eye":
        return self

    def __exit__(self, *exc) -> None:
        self.close()
