"""The series bible for सन्नाटपुर की रातें, read from bible/ in this repo: the cast (cast.yaml), the world and what
never exists in it (world.yaml), the rules of the night and the fixed facts (canon.json), and the F1 micro-entry
bank (micro_bank.json). Everything the writer, the gates, the painter and the vision check know about the world comes
from here, so a change to the bible is a change to every later Short.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1] / "bible"
# Who may appear in an F1 painting; the adult narrator is only ever his hands and the old notebook.
ON_SCREEN = ("jhabbu", "prabhat", "nuzhat", "shailesh", "prabhat_adult")
NARRATOR = "prabhat_adult"


@lru_cache(maxsize=None)
def _yaml(name: str) -> dict:
    return yaml.safe_load((ROOT / name).read_text(encoding="utf-8"))


@lru_cache(maxsize=None)
def _json(name: str) -> dict:
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


def cast() -> dict[str, dict]:
    """Cast id -> its bible entry (name, age, props, colours, look, image token, voice, speech)."""
    return {c["id"]: c for c in _yaml("cast.yaml")["cast"]}


def minor_roles() -> list[str]:
    return list(_yaml("cast.yaml").get("minor_people", {}).get("roles_hi") or [])


def world() -> dict:
    return _yaml("world.yaml")


def places() -> dict[str, dict]:
    return {p["id"]: p for p in world()["places"]}


def canon() -> dict:
    return _json("canon.json")


def niyam() -> dict[str, dict]:
    return {n["id"]: n for n in canon()["niyam"]}


def micro_bank() -> list[dict]:
    return list(_json("micro_bank.json")["entries"])


def house_style() -> str:
    return world()["look"]["house_style"]


def never_look() -> str:
    return world()["look"]["never"]


def never() -> dict:
    return world()["never_exists"]


def banned_terms_hi() -> list[str]:
    """Every Hindi word or phrase from world.yaml's never_exists lists: religious places, people and acts, and
    banned beings. Parenthesised glosses ("बाबा (in the holy-man sense)") keep only their Hindi head."""
    ne = never()
    out: list[str] = []
    for group in ("religious_places", "religious_people_and_acts", "beings"):
        for term in ne.get(group, {}).get("hi", []):
            head = term.split("(")[0].strip()
            if " या " in head:  # "भगवान या कोई देवी-देवता"
                out += [t.strip() for t in head.split(" या ")[:1]]
                continue
            out.append(head)
    return [t for t in dict.fromkeys(out) if t]


def banned_beings_en() -> list[str]:
    return list(never().get("beings", {}).get("en", []))


def brands() -> list[str]:
    """Brand names (from never_exists.brands.map) that may never be named in text or shown in a picture."""
    out: list[str] = []
    for key in never().get("brands", {}).get("map", {}):
        out += [k.strip() for k in key.split("/")]
    return out


def image_token(cast_id: str) -> str:
    return cast()[cast_id]["image"]


def props(cast_id: str) -> list[dict]:
    return list(cast()[cast_id].get("props") or [])


def signature(cast_id: str) -> str:
    """The props and colours that identify a character in a painting (the vision check looks for any one)."""
    c = cast()[cast_id]
    return ", ".join([p["image"] for p in c.get("props") or []] + list(c.get("colours", {}).get("image") or []))


def writer_context(entry: dict) -> str:
    """The bible facts one micro-entry needs, in the writer's prompt: the frame, the cast, the place, the rule."""
    era = world()["era"]
    name = world()["name"]
    lines = [f"दुनिया: {name['hi']} ({name.get('label_hi', 'काल्पनिक गाँव')}), {era['year']} — {era['frame_hi']}"]
    lines.append("पात्र (नाम हमेशा यही, कोई और नाम नहीं):")
    for cid in ("jhabbu", "prabhat", "nuzhat", "shailesh"):
        c = cast()[cid]
        things = ", ".join(p["hi"] for p in c.get("props") or [])
        lines.append(f"- {cid} = {c['name']['hi']} ({c['age']}): {c['look_hi']} चीज़ें: {things}. "
                     f"बोली: {c.get('speech_hi', '')}")
    place = places().get(entry.get("place_id"), {})
    if place:
        lines.append(f"जगह: {place['hi']} — {place['hi_desc']}")
    rule = niyam().get(entry.get("niyam_id"), {})
    if rule:
        lines.append(f"इस रात का नियम {rule['id']}: {rule['hi']}")
    roles = minor_roles()
    if roles:
        lines.append("छोटे किरदार सिर्फ़ काम से बुलाए जाते हैं: " + ", ".join(roles))
    lines.append("कभी नहीं: " + ", ".join(banned_terms_hi()))
    return "\n".join(lines)
