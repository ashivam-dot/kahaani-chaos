"""Looks at every painting before it can reach a Short: refuses nudity, sexual content, gore, malformed bodies, text
in the picture, and a picture that doesn't show its line. When no model can look, nothing is published.
"""
from __future__ import annotations

import io
from pathlib import Path

PER_PROMPT = 5
SIDE = 768
FLAGS = ("nudity", "sexual", "gore", "malformed", "text")

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
                    "fits": {"type": "boolean"},
                    "reason": {"type": "string"},
                },
                "required": ["n", "shows", *FLAGS, "fits", "reason"],
            },
        },
    },
    "required": ["pictures"],
}

PROMPT = """You are the picture editor of a Hindi YouTube Shorts channel of original magical and mysterious folk
stories for a 13+ audience. An AI model painted each picture below for one narrated line; it will fill the screen
while that line plays. Look at the pixels carefully.

Story: {story}
Characters: {cast}

For each picture answer:
- shows: one short sentence describing what is actually visible.
- nudity: true if anyone is nude or nearly nude, or shows a bare breast, buttocks or genitals.
- sexual: true for kissing, embrace in a sexual way, seductive poses or a sexualised focus on the body.
- gore: true for blood, wounds, severed body parts or corpses.
- malformed: true if a main figure's face or body is visibly broken: extra or missing limbs or fingers, melted or
  doubled faces, an animal character painted as a person in clothes or with a human face.
- text: true if any legible or garbled letters, words, signs, captions or a watermark appear.
- fits: true if the picture plausibly shows this line's moment with this story's characters and setting, in a
  painted (not photographic, not cartoon) style. False for an unrelated scene, the wrong characters, a modern
  object the story doesn't have, or a sheet of several pictures.
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


def rejected(verdict: dict) -> str | None:
    """Why a verdict keeps its picture out of a Short, or None when the picture may be used."""
    for flag in FLAGS:
        if verdict.get(flag):
            return f"{flag}: {verdict.get('reason') or verdict.get('shows')}"
    if not verdict.get("fits"):
        return f"does not fit the line: {verdict.get('reason') or verdict.get('shows')}"
    return None


def judge(items: list[tuple[Path, str]], story: str, cast: str, ask) -> list[dict]:
    """One verdict per (picture file, narrated line), in order. ask(parts, schema) answers like gemini.look; a missing
    or malformed verdict counts as a rejection."""
    verdicts: list[dict] = []
    for start in range(0, len(items), PER_PROMPT):
        chunk = items[start:start + PER_PROMPT]
        lines = "\n".join(f"{n}. narrated line: {line}" for n, (_, line) in enumerate(chunk, 1))
        parts: list = [PROMPT.format(story=story, cast=cast, lines=lines)]
        for n, (path, _) in enumerate(chunk, 1):
            parts += [f"Picture {n}:", _small(path)]
        answer = ask(parts, SCHEMA)
        got = {v.get("n"): v for v in (answer or {}).get("pictures", []) if isinstance(v, dict)}
        for n in range(1, len(chunk) + 1):
            verdicts.append(got.get(n) or {"n": n, "shows": "", "fits": False, "reason": "no verdict"})
    return verdicts
