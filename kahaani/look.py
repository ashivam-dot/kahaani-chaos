"""How the channel's AI paintings look: the bible's house style for every picture (bright moonlit 1996 north-Indian
village, one warm practical light, lifted shadows, painterly-cinematic, realistic adult proportions), and the cast's
fixed tokens from bible/cast.yaml, so a character is carried by props, colours and silhouette rather than a face.
Faces stay small, backlit or three-quarters away by default. The writer describes each beat's scene and everyone's
expression in English; this module turns that into the image model's prompt.

Z-Image-Turbo runs at cfg 1.0, which ignores a negative prompt, so what must not appear is said in the prompt itself.
"""
from __future__ import annotations

import re
import zlib

from . import bible

STYLE = (bible.house_style().rstrip(".") + ". Painterly visible brushwork, readable mid-tones, no crushed blacks,"
         " vertical 9:16 composition with the subject in the upper two thirds and calm space low in the frame."
         " Painterly-cinematic, not photoreal, not a cartoon")
# Frame 0 is the peak image: the impossible moment itself, readable at phone size.
CLOSE = ("Peak moment, close on the impossible object doing the impossible, lit by the warm light; any face small in"
         " the frame, backlit or three-quarters away.")
CLOSE_THING = "Peak moment, close on the impossible object doing the impossible, lit by the warm light."
FACES = "Faces small in the frame, backlit or turned three-quarters away; props and silhouettes carry who is who."
# Kept out of every picture in words, since cfg 1.0 ignores a negative prompt (bible/world.yaml look.never).
NEVER = ("Realistic adult proportions, no chibi, no big eyes, not a kids' book, not anime, not a 3D render. No shrine,"
         " idol, religious sign or holy thread. No brand, logo or label.")
# The model fills an empty scene with a stranger (a woman pouring the tea), which the vision check then refuses.
NOBODY = "No people: no human figure, face, hand or arm anywhere in the picture."
AVOID = ("No text, no letters, no words, no watermark, no signature, no frame. No blood, no gore, no nudity, fully"
         " clothed people. Natural anatomy: no extra limbs, no extra fingers, no deformed hands. Not a cartoon, not"
         " anime, not a 3D render.")
ANIMALS = re.compile(r"\b(cat|kitten|dog|puppy|crow|owl|parrot|peacock|sparrow|vulture|eagle|pigeon|hen|rooster|"
                     r"cow|buffalo|goat|sheep|horse|donkey|camel|elephant|tiger|leopard|lion|monkey|langur|bear|"
                     r"fox|jackal|deer|snake|cobra|frog|fish|tortoise|turtle|rat|mouse|squirrel|bird)s?\b(?!-)", re.I)
REAL = " (a real animal, not a person: no clothes, no human body or face)"
# The house style is a moonlit night with one warm light, so a "next morning, its light dark" ending came back at night
# with the lamp on and the editor dropped it (dry run 39953890527, beat 7): a dawn scene gets the dawn look, and a
# light the scene says is out is said to be out.
DAWN = re.compile(r"\b(dawn|daybreak|sunrise|morning|daylight|daytime)\b", re.I)
DAWN_STYLE = ("Early-morning 1996 north-Indian village at dawn, pale gold sunrise light and soft blue shadows, no"
              " moon and no lamp lit, lifted shadows, painterly-cinematic, realistic adult proportions. Painterly"
              " visible brushwork, readable mid-tones, no crushed blacks, vertical 9:16 composition with the subject"
              " in the upper two thirds and calm space low in the frame. Painterly-cinematic, not photoreal, not a"
              " cartoon")
UNLIT = re.compile(r"\b(light|lamp|headlight|bulb|lantern|torch)\b[^.]{0,30}\b(dark|off|unlit|dead)\b|"
                   r"\b(dark|unlit|switched-off|dead)\s+(\w+\s+)?(light|lamp|headlight|bulb|lantern|torch)\b", re.I)
OUT = "The light the scene names is switched off and unlit: no glow, no beam from it."
# The writer's "the kids" painted the seventeen-year-olds young (dry run 39939846588, beat 4), and a "rolling bicycle"
# came back with a rider nobody planned (beat 3). Both are fixed in the words the image model reads.
GROWN = ((re.compile(r"\b(kids|children|teens|teenagers)\b", re.I), "young people"),
         (re.compile(r"\b(kid|child|teen|teenager)\b", re.I), "young person"),
         (re.compile(r"\bboys\b", re.I), "young men"), (re.compile(r"\bboy\b", re.I), "young man"),
         (re.compile(r"\bgirls\b", re.I), "young women"), (re.compile(r"\bgirl\b", re.I), "young woman"))
BY_ITSELF = re.compile(r"\b(by itself|on its own|of its own|rolling|rolls|riderless|unmanned|self-\w+)\b", re.I)
ALONE = "Whatever moves by itself has nobody on it, pushing, pulling or holding it."


def grown(scene: str) -> str:
    for pattern, word in GROWN:
        scene = pattern.sub(word, scene)
    return scene


def animal(look: str) -> bool:
    """Whether a look describes an animal: judged on its first clause, so 'an old man, a crow on his shoulder' is
    not one, and never on a compound like 'fish-pattern'."""
    return bool(ANIMALS.search(re.split(r"[,;:]", look, maxsplit=1)[0]))


def _key(entry: dict) -> str:
    return (entry.get("id") or entry.get("name") or "").strip().lower()


def character(entry: dict) -> str:
    """One cast member's fixed look (the bible's image token when the id is a bible character); an animal is pinned
    as a real animal, or the model paints an animal-headed man."""
    known = bible.cast().get(entry.get("id") or "")
    look = (known["image"] if known else entry["look"]).strip().rstrip(".")
    name = known["name"]["en"] if known else entry.get("name", "")
    if animal(look) and "not a person" not in look.lower():
        look += REAL
    return f"{name}: {look}"


def prompt(scene: str, people: list[dict], cast: list[dict], *, hook: bool = False) -> str:
    """Style + scene + each present character's fixed look and expression now + what must not appear."""
    looks = {_key(c): c for c in cast}
    parts = [grown(scene).strip().rstrip(".") + "."]
    if BY_ITSELF.search(scene):
        parts.append(ALONE)
    if UNLIT.search(scene):
        parts.append(OUT)
    present = [(looks[p["name"].strip().lower()], p.get("expression", "").strip()) for p in people
               if p.get("name", "").strip().lower() in looks]
    if hook:
        parts.append(CLOSE if present else CLOSE_THING)
    if present:
        parts.append("Characters: " + "; ".join(f"{character(c)}, {mood or 'calm'} expression" for c, mood in present)
                     + ".")
        parts.append(FACES)
    else:
        parts.append(NOBODY)
    parts += [(DAWN_STYLE if DAWN.search(scene) else STYLE) + ".", AVOID, NEVER]
    return " ".join(parts)


def seed(story: str, beat: int) -> int:
    return zlib.crc32(f"{story}:{beat}".encode()) % 2_000_000_000


# A cast shot that fails the prop-identity check may be repainted this many times (PLAN.md §7.4 gate l).
ALTERNATES = 2


def present(people: list[dict], cast: list[dict]) -> list[str]:
    """The cast ids visible in a beat's painting."""
    ids = {_key(c) for c in cast}
    return [p["name"].strip().lower() for p in people if p.get("name", "").strip().lower() in ids]


def plan(story: str, beats: list[dict], cast: list[dict]) -> list[dict]:
    """One image prompt and seed per beat; a beat with cast in it also gets ALTERNATES spare seeds, painted when the
    paint job has time, for the prop-identity check to fall back on."""
    out = []
    for i, b in enumerate(beats):
        who = present(b.get("people") or [], cast)
        row = {"beat": i, "prompt": prompt(b["scene"], b.get("people") or [], cast, hook=i == 0), "seed": seed(story, i),
               "cast": who}
        if who:
            row["alternates"] = [seed(story, i * 100 + k) for k in range(1, ALTERNATES + 1)]
        out.append(row)
    return out
