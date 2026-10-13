"""How the channel's AI paintings look: one house style for every picture, and each story's cast sheet, so a character
looks the same in every beat. The writer describes each beat's scene and everyone's expression in English; this
module turns that into the image model's prompt.

Z-Image-Turbo runs at cfg 1.0, which ignores a negative prompt, so what must not appear is said in the prompt itself.
"""
from __future__ import annotations

import re
import zlib

STYLE = ("Cinematic Indian folk-fantasy painting: moody lantern light and cold moonlight, drifting mist, a teal and"
         " amber palette, deep soft shadows, painterly visible brushwork, rich atmosphere, vertical 9:16 composition"
         " with the subject in the upper two thirds. Painterly, not photoreal, not a cartoon")
CLOSE = "Intimate close-up, the impossible detail and the face fill the frame, eyes sharp and expressive."
AVOID = ("No text, no letters, no words, no watermark, no signature, no frame. No blood, no gore, no nudity, fully"
         " clothed people. Natural anatomy: no extra limbs, no extra fingers, no deformed hands. Not a cartoon, not"
         " anime, not a 3D render.")
ANIMALS = re.compile(r"\b(cat|kitten|dog|puppy|crow|owl|parrot|peacock|sparrow|vulture|eagle|pigeon|hen|rooster|"
                     r"cow|buffalo|goat|sheep|horse|donkey|camel|elephant|tiger|leopard|lion|monkey|langur|bear|"
                     r"fox|jackal|deer|snake|cobra|frog|fish|tortoise|turtle|rat|mouse|squirrel|bird)s?\b(?!-)", re.I)
REAL = " (a real animal, not a person: no clothes, no human body or face)"


def animal(look: str) -> bool:
    """Whether a look describes an animal: judged on its first clause, so 'an old man, a crow on his shoulder' is
    not one, and never on a compound like 'fish-pattern'."""
    return bool(ANIMALS.search(re.split(r"[,;:]", look, maxsplit=1)[0]))


def character(entry: dict) -> str:
    """One cast member's fixed look; an animal is pinned as a real animal, or the model paints an animal-headed man."""
    look = entry["look"].strip().rstrip(".")
    if animal(look) and "not a person" not in look.lower():
        look += REAL
    return f"{entry['name']}: {look}"


def prompt(scene: str, people: list[dict], cast: list[dict], *, hook: bool = False) -> str:
    """Style + scene + each present character's fixed look and expression now + what must not appear."""
    looks = {c["name"].strip().lower(): c for c in cast}
    parts = [scene.strip().rstrip(".") + "."]
    if hook:
        parts.append(CLOSE)
    present = [(looks[p["name"].strip().lower()], p.get("expression", "").strip()) for p in people
               if p.get("name", "").strip().lower() in looks]
    if present:
        parts.append("Characters: " + "; ".join(f"{character(c)}, {mood or 'calm'} expression" for c, mood in present)
                     + ".")
    parts += [STYLE + ".", AVOID]
    return " ".join(parts)


def seed(story: str, beat: int) -> int:
    return zlib.crc32(f"{story}:{beat}".encode()) % 2_000_000_000


def plan(story: str, beats: list[dict], cast: list[dict]) -> list[dict]:
    """One image prompt and seed per beat."""
    return [{"beat": i, "prompt": prompt(b["scene"], b.get("people") or [], cast, hook=i == 0), "seed": seed(story, i)}
            for i, b in enumerate(beats)]
