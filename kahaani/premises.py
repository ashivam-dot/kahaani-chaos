"""Which micro-entry comes next: the F1 bank is bible/micro_bank.json (40 human-written seeds). Each entry is used
once (the ledger's history and given-up premises say which are spent).

Rotation against the earlier F1 Shorts, the same rules the variation gate enforces afterwards:
- the title skeleton is never the same as either of the last two (at most 1 in 3);
- the ending type and the resolution type are never the previous Short's;
- the object, anomaly and place are not among the last RECENT Shorts';
- a different heart type than the previous Short's is preferred.
A pick must also leave the rest of the bank completable under those rules (a short look-ahead), so the rotation never
corners itself with entries left. Among the picks that do, the learned lift of the title skeleton decides, then bank
order. The "next-raat-tease" ending is only allowed in a week with a long-form night on the same thread; until F3
exists it is swapped for the next ending in the rotation. When fewer than LOW entries are unused, the health check
raises an alert so the owner writes more into the bible.
"""
from __future__ import annotations

import logging

from . import bible, config, hindi, learn, ledger

RECENT = 10
LOW = 10
SKELETON_WINDOW = 2  # a skeleton may not repeat within the last two: at most 1 in 3
ENDINGS = ("loop-back", "register-line", "open-question", "next-raat-tease")
RESOLUTIONS = ("leave-it-be", "kindness", "bargain", "outsmart")
TEASE = "next-raat-tease"
LOOKAHEAD = 4000
log = logging.getLogger("kahaani.premises")


class NoPremise(LookupError):
    """No unused entry fits the rotation rules."""


def bank() -> list[dict]:
    return bible.micro_bank()


def f1(history: list[dict]) -> list[dict]:
    """The earlier Shorts of this format, in the order they were made (old Kahaani Chaos rows have no format)."""
    return [r for r in history if r.get("format") == config.FORMAT]


def unused(history: list[dict], premises: list[dict] | None = None) -> list[dict]:
    spent = {r.get("premise") for r in history} | ledger.given_up()
    return [p for p in (premises if premises is not None else bank()) if p["id"] not in spent]


def tease_allowed(entry: dict, history: list[dict]) -> bool:
    """Whether a long-form night on the entry's thread is scheduled this week. F3 is not built yet: never."""
    return False


def ending_for(entry: dict, history: list[dict]) -> str:
    """The ending this entry gets now: its own, except a tease without a long-form night becomes the next ending in
    the rotation that is not the previous Short's."""
    own = entry.get("ending_type")
    if own != TEASE or tease_allowed(entry, history):
        return own
    last = f1(history)[-1].get("ending") if f1(history) else None
    return next(e for e in ENDINGS if e != TEASE and e != last)


def _key(text: str | None) -> str:
    return hindi.norm(text or "")


def fits(entry: dict, history: list[dict]) -> list[str]:
    """Why this entry may not come next (empty = it may)."""
    rows = f1(history)
    recent = rows[-RECENT:]
    found = []
    if entry.get("title_skeleton") in {r.get("skeleton") for r in rows[-SKELETON_WINDOW:]}:
        found.append(f"title skeleton {entry.get('title_skeleton')} ran in the last {SKELETON_WINDOW}")
    if rows and ending_for(entry, history) == rows[-1].get("ending"):
        found.append(f"ending {rows[-1].get('ending')} ran last")
    if rows and entry.get("resolution_type") == rows[-1].get("resolution"):
        found.append(f"resolution {entry.get('resolution_type')} ran last")
    for field, mine in (("object_token", "object_token"), ("anomaly", "anomaly"), ("location", "location")):
        if _key(entry.get(mine)) in {_key(r.get(field)) for r in recent if r.get(field)}:
            found.append(f"{field} {entry.get(mine)!r} ran in the last {RECENT}")
    return found


def row(entry: dict, history: list[dict]) -> dict:
    """What a made Short records about its entry, so later picks and the variation gate can compare."""
    return {"premise": entry["id"], "format": config.FORMAT, "skeleton": entry.get("title_skeleton"),
            "ending": ending_for(entry, history), "resolution": entry.get("resolution_type"),
            "heart_type": entry.get("heart_type"), "object_token": entry.get("object_token"),
            "anomaly": entry.get("anomaly"), "location": entry.get("location"), "place_id": entry.get("place_id")}


def _completable(pool: list[dict], history: list[dict], budget: list[int]) -> bool:
    """Whether the pool can be used up in some order under the rotation rules (depth-first, within budget)."""
    if not pool:
        return True
    budget[0] -= 1
    if budget[0] <= 0:
        return True  # out of look-ahead: assume it can, rather than refuse a fitting pick
    for e in pool:
        if not fits(e, history):
            if _completable([p for p in pool if p is not e], history + [row(e, history)], budget):
                return True
    return False


def select(history: list[dict], premises: list[dict] | None = None, lift=learn.lift) -> dict:
    pool = unused(history, premises)
    fit = [p for p in pool if not fits(p, history)]
    if not fit:
        raise NoPremise(f"{len(pool)} unused micro entries, none clear of the rotation rules")
    order = {p["id"]: i for i, p in enumerate(pool)}
    last = f1(history)[-1] if f1(history) else {}
    ranked = sorted(fit, key=lambda p: (-lift("skeleton", p.get("title_skeleton")),
                                        p.get("heart_type") == last.get("heart_type"), order[p["id"]]))
    for p in ranked:
        rest = [q for q in pool if q is not p]
        if _completable(rest, history + [row(p, history)], [LOOKAHEAD]):
            return p
    return ranked[0]


def premise_for(entry: dict, history: list[dict]) -> dict:
    """The entry as the writer and the gates see it: with the ending it gets now."""
    return {**entry, "ending_type": ending_for(entry, history)}


def low(history: list[dict]) -> str | None:
    """A health warning when the bank is running out, else None."""
    left = len(unused(history))
    if left < LOW:
        return f"only {left} unused micro entries left in bible/micro_bank.json (alert below {LOW}): write more"
    return None
