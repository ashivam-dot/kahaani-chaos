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
FLAGS = ("nudity", "sexual", "gore", "malformed", "text", "religious", "kids_look", "doubled")
# The cast has no one under 17. In dry run 39886731532 the editor described two cast shots as "two younger boys" and
# "a child" yet passed them (kids_look is about style), so a caption naming a child refuses the picture. Asking the
# editor about children outright got every request blocked (dry run 39892698527); its own caption is the signal.
# A bare "boy" or "girl" counts too (vision-bench on 39886731532: Gemma described the shrunken teens as "a girl in
# green and a boy in yellow"); a correct render reads "young man" or "young woman", and "teenage boy" is allowed.
CHILD_WORDS = re.compile(r"\b(child|children|kids?|toddlers?|schoolboys?|schoolgirls?|"
                         r"(?<!teenage )(?<!teen )(boys?|girls?))\b", re.I)
# e10 (40158580419): the caption saw two mustard-sweater Prabhats beside Jhabbu,
# but doubled was False. A plural group in one recurring character's signature clothes
# is independently contradictory. Generic groups and differently dressed friends stay valid.
DOUBLED_CLOTHES = re.compile(
    r"\b(?:two|three|four|[2-4])\s+(?:(?:young|adult|teenage)\s+)?(?:men|women|people|figures)"
    r"\s+(?:in|wearing)\s+(?:matching\s+)?(?:"
    r"mustard(?:[- ]yellow)?(?:\s+knitted)?\s+sweaters|"
    r"(?:bottle[- ])?green\s+dupattas|red\s+(?:cricket\s+)?caps|red\s+(?:woollen\s+)?mufflers)\b", re.I)
# A cast shot must show each painted character's signature prop or colour; a video needs PROP_RATE of its cast shots
# to (after up to look.ALTERNATES repaints each); a shot that never does is dropped.
PROP_RATE = 0.85
# The local fallback editor may pass paintings for a published Short only once vision-bench shows it refusing what
# the Gemini editor refuses (the child shots of dry run 39886731532 above all). Benches 39927624755, 39927635163 and
# 39927645982 (Gemma 4 12B, 21 shots): it refused every shot Gemini refused, both child shots included, and refused 3
# that Gemini passed, so it errs strict and costs only repaints.
LOCAL_TRUSTED = True
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
                    "ridden": {"type": "boolean"},
                    "human_present": {"type": "boolean"},
                    "poster_depiction_only": {"type": "boolean"},
                    "setting_ok": {"type": "boolean"},
                    "structure_ok": {"type": "boolean"},
                    "action_ok": {"type": "boolean"},
                    "props_ok": {"type": "boolean"},
                    "fits": {"type": "boolean"},
                    "subject_share": {"type": "number"},
                    "reason": {"type": "string"},
                },
                "required": ["n", "shows", *FLAGS, "ridden", "human_present", "poster_depiction_only", "setting_ok", "structure_ok", "action_ok", "props_ok", "fits", "subject_share", "reason"],
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
- shows: one short sentence describing what is actually visible. Describe each person by how they look (for
  example "an old man in a red muffler", "a young woman in green"), never by a character's name.
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
- doubled: true if the same person (same clothes and props) appears twice in one picture. Count each distinct
  body: an old man beside two young men both in mustard sweaters contains two Prabhats, even if their faces differ.
- ridden: true if anyone sits on, rides, pedals, pushes, steers or holds a bicycle, cart or other vehicle.
- human_present: true if any human figure, face, hand, arm or other human body part is visible, even if the rest
  of that person is outside the frame. A hand holding a supposedly empty moving object is human presence.
- poster_depiction_only: true ONLY when every visible human-shaped form is a flat fictional drawing contained
  entirely inside one visibly bounded paper poster attached to a wall, with all four paper edges visible.
  False for a living person, a hand holding the paper, an unbounded painting filling the frame, a cast-sheet
  collage, or a figure extending outside the paper. This never excuses text, wrong action or a missing poster.
- setting_ok: true only if the actual surroundings match the planned picture. An indoor staff-room scene must
  have enclosing walls/ceiling; people in an open village street under the moon do not match it. Light entering
  a room through a window is different from an outdoor sky behind the people.
- structure_ok: true only if the objects have plausible construction and support, except for the exact anomaly
  explicitly required by the story. A ceiling fan must attach to a visible ceiling, not float in open sky.
  Reverse spinning does not imply floating. A lantern must rest on a surface, hang from a support, or be held.
- action_ok: true only if the main action is performed by the character the line and plan name, identifiable
  by their fixed clothing and props. If the line names red-cap Shailesh carrying a scale, mustard-sweater Prabhat
  handling it while Shailesh stands aside is false, even though all cast members are present. For object-only
  shots, check the object's planned state and action instead.
- props_ok: for each character the line says should appear, true only if that character is visible and shows at
  least one of their listed signature props or colours. True when the line lists no characters.
- fits: true if the picture plausibly shows this line's moment with this story's characters and setting, in a
  painted (not photographic, not cartoon) style. False for an unrelated scene, the wrong characters, a modern
  object the story doesn't have, or a sheet of several pictures. Also false when it contradicts the planned
  picture in a way a viewer would notice: the planned main action or object is missing, or someone the plan leaves
  out is the centre of it (dry run 39930652897: a boy riding the bicycle the line says moves by itself).
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


def rejected(verdict: dict, cast_shot: bool = False, hook: bool = False, scene: str = "") -> str | None:
    """Why a verdict keeps its picture out of a Short, or None when the picture may be used. A cast shot must also
    pass prop identity, and the hook's painting must have its subject cover HOOK_SUBJECT of the frame (a missing
    answer counts as a failure for both). A planned scene where something moves by itself refuses a picture where
    anyone rides or holds a vehicle: told the plan, the editor captioned a ridden bicycle "rolls forward by itself"
    and passed it (dry run 39969216681, beat 3), so that is a plain question decided here, not left to fits."""
    from .look import BY_ITSELF, POSTER_ONLY

    for flag in FLAGS:
        if verdict.get(flag):
            return f"{flag}: {verdict.get('reason') or verdict.get('shows')}"
    if cast_shot and DOUBLED_CLOTHES.search(verdict.get("shows") or ""):
        return f"doubled: the editor describes repeated signature clothes ({verdict.get('shows')})"
    if CHILD_WORDS.search(verdict.get("shows") or ""):
        return f"child: the editor sees a child ({verdict.get('shows')})"
    if scene and BY_ITSELF.search(scene) and verdict.get("ridden") is not False:
        return f"ridden: someone is on or holding what the plan says moves by itself ({verdict.get('shows')})"
    poster_only = (not cast_shot and POSTER_ONLY.search(scene)
                   and type(verdict.get("human_present")) is bool
                   and verdict.get("poster_depiction_only") is True)
    if scene and not cast_shot and verdict.get("human_present") is not False and not poster_only:
        return f"unplanned human: an object-only scene must confirm no visible human or body part ({verdict.get('shows')})"
    if scene and verdict.get("setting_ok") is not True:
        return f"setting: the planned surroundings are not confirmed ({verdict.get('shows')})"
    if scene and verdict.get("structure_ok") is not True:
        return f"structure: object construction and support are not confirmed ({verdict.get('shows')})"
    if scene and verdict.get("action_ok") is not True:
        return f"action: the planned actor and main action are not confirmed ({verdict.get('shows')})"
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
    """One verdict per (picture file, narrated line[, who should appear[, planned picture]]), in order. ask(parts, schema) answers like gemini.look; a missing
    or malformed verdict counts as a rejection."""
    from .look import POSTER_ONLY, picture_scene

    verdicts: list[dict] = []
    for start in range(0, len(items), PER_PROMPT):
        chunk = items[start:start + PER_PROMPT]
        lines = "\n".join(f"{n}. narrated line: {item[1]}"
                          + (f"\n   should appear: {item[2]}" if len(item) > 2 and item[2] else
                             ("\n   object-only poster scene: only a flat fictional figure inside clearly visible "
                              "paper edges on a wall; no physical person or body part outside the paper"
                              if len(item) > 3 and POSTER_ONLY.search(item[3]) else
                              "\n   object-only scene: no human figure, face, hand or arm may be visible")
                             if len(item) > 2 else "")
                          + (f"\n   planned picture: {picture_scene(item[3])}" if len(item) > 3 and item[3] else "")
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
