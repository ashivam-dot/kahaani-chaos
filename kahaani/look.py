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
# Outdoor village scenery in the house style overrode e09's staff-room scenes and put its ceiling fan in open sky.
# Keep the palette and brushwork, but let an explicit interior determine the surroundings.
INDOOR = re.compile(r"\b(interior|indoors|inside|staff[ -]room|classroom|bedroom|kitchen|enclosed room)\b", re.I)
# An object's interior (e.g. a toy boat's hull) does not make its outdoor surroundings a room.
# Only an explicit scene declaration overrides the existing interior detection.
OUTDOORS = re.compile(r"\bthe scene is outdoors\b", re.I)
INDOOR_STYLE = ("Enclosed 1996 north-Indian village interior, solid plaster walls and a visible solid ceiling,"
                " one warm practical light, cool blue light entering through the windows, lifted shadows."
                " Painterly visible brushwork, readable mid-tones, no crushed blacks, vertical 9:16 composition"
                " with the subject in the upper two thirds and calm space low in the frame."
                " Painterly-cinematic, realistic adult proportions, not photoreal, not a cartoon")
INDOOR_DAWN_STYLE = INDOOR_STYLE.replace(
    "one warm practical light, cool blue light entering through the windows",
    "pale gold dawn light entering through the windows, soft blue shadows, unlit lamps")
UNLIT = re.compile(r"\b(light|lamp|headlight|bulb|lantern|torch)\b"
                   r"(?:\s+(?:is|was|now|has|gone|goes|went|remains|stays|turns|turned|switched)){0,3}"
                   r"\s+(dark|off|unlit|dead)\b|"
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
# With anyone in the frame the image model put a rider on the rolling bicycle in all three paintings (dry run
# 39984130378, beat 2), so a beat where something moves by itself is painted as the object alone; the people
# react in the beats around it.
PERSON = re.compile(r"\b(he|she|they|his|her|their|him|man|men|woman|women|young|person|people|someone|everyone|"
                    r"jhabbu|prabhat|shailesh|nuzhat|stands?|stood|sits?|sat|looks?|looking|watch\w*|point\w*)\b",
                    re.I)
WRITING = re.compile(r"\b(writ(?:e|es|ing)|pen|ink|pencil)\b", re.I)
ELECTRIC_ONLY = re.compile(r"\belectric flashlight is the only practical light\b", re.I)
UNATTACHED_GLOW = re.compile(r"\bthe unattached glow is the only warm light\b", re.I)
WRISTS_ONLY = re.compile(r"\bonly hands and wrists are within the frame\b", re.I)
# The e16 restraining-grip repairs ignored their crop when the appended full-body
# cast tokens requested caps, glasses and flip-flops. This explicit close detail
# keeps the same clothing identities without requesting offscreen anatomy.
ARMS_ONLY = re.compile(r"\bonly arms and hands are within the frame\b", re.I)
ARM_DETAILS = {
    "prabhat": "Prabhat: one mustard-yellow knitted sweater cuff and the natural bare hand extending from it",
    "shailesh": "Shailesh: one adult upper arm covered by a striped cotton shirt sleeve",
}


# Told "no people", Z-Image still put a boy on the bicycle "rolling slowly across the bridge" in all three paintings
# (dry run 39998079552, beat 3): a moving vehicle reads as a ridden one. The painting is a still (the motion is the
# camera's), so a by-itself beat paints the thing standing empty in a deserted place.
MOVING = (  # "is rolling slowly", "rolls forward", then a bare "rolling" before its noun
    (re.compile(r"\b(?:is|are|was|were)\s+(?:slowly\s+|suddenly\s+)?(?:rolling|moving|creeping|gliding|lurching)"
                r"(?:\s+(?:slowly|forward|ahead|away|along))?\b", re.I), "stands empty"),
    (re.compile(r"\b(?:rolls|rolled|moves|moved|creeps|crept|glides|glided|lurches|lurched)"
                r"(?:\s+(?:slowly|forward|ahead|away|along))?\b", re.I), "stands empty"),
    (re.compile(r"\b(?:rolling|moving|creeping|gliding|lurching)\b", re.I), "empty"),
)
EMPTY = "A deserted, empty scene: nobody is there, and any seat or saddle in it is empty."


def solo(scene: str) -> bool:
    """Whether a beat shows something moving by itself, and so is painted with nobody in it."""
    return bool(BY_ITSELF.search(scene))


def unpeopled(scene: str) -> str:
    """The scene's sentences that do not put a person in the frame (the first sentence when all of them do), with
    whatever moves in them painted standing still and empty (MOVING)."""
    sentences = [x.strip() for x in re.split(r"(?<=[.!?])\s+", scene.strip()) if x.strip()]
    kept = [x for x in sentences if BY_ITSELF.search(x) or not PERSON.search(x)]
    text = " ".join(kept or sentences[:1])
    for pattern, word in MOVING:
        text = pattern.sub(word, text)
    return text


def grown(scene: str) -> str:
    for pattern, word in GROWN:
        scene = pattern.sub(word, scene)
    return scene


def picture_scene(scene: str) -> str:
    """The same scene for the painter and its editor, including deliberate object-only shots."""
    if solo(scene):
        return grown(unpeopled(scene)).rstrip(".") + ". " + ALONE + " " + EMPTY
    return grown(scene)


def animal(look: str) -> bool:
    """Whether a look describes an animal: judged on its first clause, so 'an old man, a crow on his shoulder' is
    not one, and never on a compound like 'fish-pattern'."""
    return bool(ANIMALS.search(re.split(r"[,;:]", look, maxsplit=1)[0]))


def _key(entry: dict) -> str:
    return (entry.get("id") or entry.get("name") or "").strip().lower()


def character(entry: dict, scene: str = "") -> str:
    """One cast member's fixed look (the bible's image token when the id is a bible character); an animal is pinned
    as a real animal, or the model paints an animal-headed man."""
    known = bible.cast().get(entry.get("id") or "")
    look = (known["image"] if known else entry["look"]).strip().rstrip(".")
    if entry.get("id") == "nuzhat" and ELECTRIC_ONLY.search(scene) and re.search(
            r"\bflashlight rests\b", scene, re.I):
        look = look.replace("holding a metal flashlight with a cracked lens throwing a split beam",
                            "her metal battery flashlight with a cracked lens resting beside her and throwing a split beam")
    if entry.get("id") == "jhabbu" and WRITING.search(scene):
        # The default carried props conflict with hands writing in the register. Both base/alternate
        # paintings of e02 rendered a standing carrier beside a second seated copy of the same man.
        look = look.replace("holding a brass hurricane lantern, bamboo staff with a small bell, "
                            "khaki ledger with a red spine under one arm",
                            "an open khaki ledger with a red spine resting before him, "
                            "brass hurricane lantern and bamboo staff with a small bell set beside him")
        if UNLIT.search(scene):
            look = look.replace("brass hurricane lantern", "unlit brass hurricane lantern")
    elif entry.get("id") == "jhabbu" and (re.search(
            r"\blantern and (?:bamboo )?staff rest\b", scene, re.I) or (
            re.search(r"\blantern\s+rests?\b", scene, re.I) and
            re.search(r"\bstaff\s+(?:rests?|leans?)\b", scene, re.I))):
        # Helping another person needs a free hand; do not simultaneously ask him to carry every prop.
        look = look.replace("holding a brass hurricane lantern, bamboo staff with a small bell, "
                            "khaki ledger with a red spine under one arm",
                            "brass hurricane lantern, bamboo staff with a small bell and khaki ledger "
                            "with a red spine resting beside him")
    name = known["name"]["en"] if known else entry.get("name", "")
    if animal(look) and "not a person" not in look.lower():
        look += REAL
    return f"{name}: {look}"


def prompt(scene: str, people: list[dict], cast: list[dict], *, hook: bool = False) -> str:
    """Style + scene + each present character's fixed look and expression now + what must not appear."""
    looks = {_key(c): c for c in cast}
    alone = solo(scene)
    if alone:
        people = []
    parts = [picture_scene(scene).strip().rstrip(".") + "."]
    if UNLIT.search(scene):
        parts.append(OUT)
    present = [(looks[p["name"].strip().lower()], p.get("expression", "").strip()) for p in people
               if p.get("name", "").strip().lower() in looks]
    arms_only = bool(ARMS_ONLY.search(scene)) and len(present) == 2 \
        and {c.get("id") for c, _ in present} == set(ARM_DETAILS)
    if hook:
        parts.append(CLOSE if present else CLOSE_THING)
    if arms_only:
        parts.append("Visible character details: " + "; ".join(ARM_DETAILS[c["id"]] for c, _ in present) + ".")
        parts.append("Only the two friends' arm detail is visible. Their heads, faces, torsos and legs are "
                     "outside this tight crop. The mustard-cuffed hand grips the striped upper arm.")
    elif present:
        parts.append("Characters: " + "; ".join(f"{character(c, scene)}, {mood or 'calm'} expression" for c, mood in present)
                     + ".")
        if len(present) == 1 and present[0][0].get("id") == "jhabbu" \
                and WRITING.search(scene):
            parts.append("Exactly one person, Jhabbu, seated and writing. All details describe this same man. "
                         "Nobody else is present; his lantern and staff rest beside him.")
        if len(present) == 1 and present[0][0].get("id") == "prabhat_adult" and WRISTS_ONLY.search(scene):
            parts.append("Only one pair of middle-aged hands and wrists is visible, with the faded blue notebook "
                         "and steel-rimmed glasses. The face, head, shoulders and torso are outside the frame.")
        else:
            parts.append(FACES)
    else:
        parts.append(NOBODY)
    if INDOOR.search(scene) and not OUTDOORS.search(scene):
        style = INDOOR_DAWN_STYLE if DAWN.search(scene) else INDOOR_STYLE
    else:
        style = DAWN_STYLE if DAWN.search(scene) else STYLE
    if ELECTRIC_ONLY.search(scene):
        style = style.replace("one warm practical light (lantern, torch or bulb)",
                              "one warm-white electric battery-flashlight beam")
        style = style.replace("one warm practical light", "one warm-white electric battery-flashlight beam")
    if not present and not DAWN.search(scene) and UNATTACHED_GLOW.search(scene):
        # E21's autonomous ladder light became a physical oil lamp because the house
        # style explicitly requested one. Preserve the palette without adding a fixture.
        style = style.replace("one warm practical light (lantern, torch or bulb)",
                              "one warm unattached self-luminous glow")
        style = style.replace("one warm practical light", "one warm unattached self-luminous glow")
    parts += [style + ".", AVOID, NEVER]
    return " ".join(parts)


def seed(story: str, beat: int) -> int:
    return zlib.crc32(f"{story}:{beat}".encode()) % 2_000_000_000


# A cast shot that fails the prop-identity check may be repainted this many times (PLAN.md §7.4 gate l).
ALTERNATES = 2


def present(people: list[dict], cast: list[dict], scene: str = "") -> list[str]:
    """The cast ids visible in a beat's painting (nobody, when something in it moves by itself)."""
    if solo(scene):
        return []
    ids = {_key(c) for c in cast}
    return [p["name"].strip().lower() for p in people if p.get("name", "").strip().lower() in ids]


def plan(story: str, beats: list[dict], cast: list[dict]) -> list[dict]:
    """One image prompt and bounded spare seeds per beat. The exact early picture check skips unused spares;
    an object-only still life needs the same recovery path as cast and moving-object shots."""
    out = []
    for i, b in enumerate(beats):
        who = present(b.get("people") or [], cast, b["scene"])
        row = {"beat": i, "prompt": prompt(b["scene"], b.get("people") or [], cast, hook=i == 0), "seed": seed(story, i),
               "cast": who}
        row["alternates"] = [seed(story, i * 100 + k) for k in range(1, ALTERNATES + 1)]
        out.append(row)
    return out
