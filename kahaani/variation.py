"""The anti-template audit (PLAN.md §7.4 gate f): a new F1 Short against the last RECENT Shorts of the same format.

- object, anomaly, place (location) and opening (first two spoken words) differ from each of the last RECENT;
- resolution type and ending type differ from the previous Short's (there are only four of each, so "differs from
  each of the last ten" could never hold; the rotation is what keeps them apart);
- the script's Hindi word 3-grams overlap no recent script by more than JACCARD (Jaccard);
- a title skeleton appears at most once in any three consecutive Shorts.

Tokens come from kahaani.hindi.words. A script or title that yields no tokens is itself a problem: an empty set would
make every overlap zero and pass anything.
"""
from __future__ import annotations

from . import config, hindi

RECENT = 10
JACCARD = 0.25
TITLE_JACCARD = 0.5
SKELETON_WINDOW = 2
N = 3


def grams(text: str, n: int = N) -> set[tuple[str, ...]]:
    """Word n-grams of a Hindi text, normalised (nukta and chandrabindu folded, punctuation stripped)."""
    w = hindi.words(text)
    return {tuple(w[i:i + n]) for i in range(len(w) - n + 1)}


def jaccard(a: set, b: set) -> float:
    if not a or not b:
        raise ValueError("an empty token set cannot be compared")
    return len(a & b) / len(a | b)


def row(draft: dict, premise: dict) -> dict:
    """What the audit compares for a draft (or a Story as a dict) and its bank entry."""
    from .gate import skeleton_of

    beats = draft.get("beats") or []
    return {"object_token": premise.get("object_token") or draft.get("object_token"),
            "anomaly": premise.get("anomaly") or draft.get("anomaly"),
            "location": premise.get("location") or draft.get("location"),
            "resolution": draft.get("resolution"), "ending": draft.get("ending"),
            "skeleton": skeleton_of(draft.get("title", "")), "title": draft.get("title", ""),
            "opening": hindi.opening(beats[0].get("text", "") if beats else ""),
            "script": " ".join(b.get("text", "") for b in beats)}


def problems(new: dict, history: list[dict]) -> list[str]:
    rows = [r for r in history if r.get("format") == config.FORMAT]
    recent = rows[-RECENT:]
    found = []
    mine = grams(new.get("script", ""))
    if not mine:
        found.append("the script has no Hindi word 3-grams to compare (empty token set)")
    titled = set(hindi.words(new.get("title", "")))
    if not titled:
        found.append("the title has no Hindi words to compare (empty token set)")
    for field, label in (("object_token", "object"), ("anomaly", "anomaly"), ("location", "location"),
                         ("opening", "opening")):
        value = hindi.norm(new.get(field) or "")
        if value and value in {hindi.norm(r.get(field) or "") for r in recent}:
            found.append(f"the {label} {new.get(field)!r} was used in one of the last {RECENT} Shorts")
    if rows:
        for field, label in (("resolution", "resolution type"), ("ending", "ending type")):
            if new.get(field) and new.get(field) == rows[-1].get(field):
                found.append(f"the {label} {new[field]!r} is the previous Short's; rotate it")
    if new.get("skeleton") and new["skeleton"] in [r.get("skeleton") for r in rows[-SKELETON_WINDOW:]]:
        found.append(f"title skeleton {new['skeleton']} ran in the last {SKELETON_WINDOW} Shorts (at most 1 in 3)")
    for r in recent:
        theirs = grams(r.get("script") or "")
        if mine and theirs and (j := jaccard(mine, theirs)) > JACCARD:
            found.append(f"the script repeats {r.get('id')!r} (3-gram overlap {j:.2f} > {JACCARD})")
        other = set(hindi.words(r.get("title") or ""))
        if titled and other and len(titled & other) / len(titled | other) > TITLE_JACCARD:
            found.append(f"the title is too close to {r.get('id')!r}'s ({r.get('title')!r})")
    return found
