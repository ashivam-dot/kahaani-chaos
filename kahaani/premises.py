"""The premise bank and which premise comes next.

The bank is kahaani/premises.json plus premises Gemini wrote later (state/premises.json). A premise is used once. The
next one may not share a motif with the last RECENT_MOTIFS Shorts or a sub-genre with the last RECENT_SUBGENRES;
among the rest, a sub-genre's learned lift times how long it has rested decides, then bank order. When fewer than
LOW unused premises remain, Gemini writes more, each checked against the red lines and deduplicated.
"""
from __future__ import annotations

import difflib
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path

from . import gate, hindi, learn, ledger

BANK = Path(__file__).resolve().parent / "premises.json"
RECENT_MOTIFS = 10
RECENT_SUBGENRES = 2
LOW = 15
ASK_FOR = 20
REST_STEP, REST_CAP = 0.15, 10
SIMILAR = 0.6
MOTIF = re.compile(r"^[a-z]+(?:-[a-z]+)*$")
log = logging.getLogger("kahaani.premises")


class NoPremise(LookupError):
    """No unused premise fits the rotation rules."""


def bank() -> list[dict]:
    return json.loads(BANK.read_text(encoding="utf-8")) + ledger.load("premises", [])


def unused(history: list[dict], premises: list[dict] | None = None) -> list[dict]:
    spent = {r.get("premise") for r in history} | ledger.given_up()
    return [p for p in (premises if premises is not None else bank()) if p["id"] not in spent]


def _rest(subgenre: str, history: list[dict]) -> float:
    """1 + REST_STEP per Short since the sub-genre last ran (a sub-genre never run has rested REST_CAP)."""
    since = next((n for n, r in enumerate(reversed(history)) if r.get("subgenre") == subgenre), REST_CAP)
    return 1 + REST_STEP * min(since, REST_CAP)


def select(history: list[dict], premises: list[dict] | None = None, lift=learn.lift) -> dict:
    pool = unused(history, premises)
    motifs = {m for r in history[-RECENT_MOTIFS:] for m in r.get("motifs") or []}
    subgenres = {r.get("subgenre") for r in history[-RECENT_SUBGENRES:]}
    fit = [p for p in pool if p["subgenre"] not in subgenres and not motifs & set(p["motifs"])]
    if not fit:
        raise NoPremise(f"{len(pool)} unused premises, none clear of the recent motifs and sub-genres")
    order = {p["id"]: i for i, p in enumerate(pool)}
    return max(fit, key=lambda p: (lift(p["subgenre"]) * _rest(p["subgenre"], history), -order[p["id"]]))


SCHEMA = {"type": "object", "properties": {"premises": {"type": "array", "items": {"type": "object", "properties": {
    "hi": {"type": "string"}, "en": {"type": "string"}, "subgenre": {"type": "string", "enum": list(gate.SUBGENRES)},
    "motifs": {"type": "array", "items": {"type": "string"}}}, "required": ["hi", "en", "subgenre", "motifs"]}}},
    "required": ["premises"]}
PROMPT = """Write {n} new ORIGINAL one-line premises for Hindi magical and mysterious twist-story Shorts (60-90 s).
Folk-fantasy and mystery for a general Hindi audience aged 13+, set in ordinary Indian villages, small towns and
cities: a kindness or a greed meets magic (jadui-inaam), a cursed or strange object (shraapit-cheez), a gentle or
eerie ghost or village mystery (bhoot-rahasya), a time slip or loop (samay-chakra), a clever trick (chatur-chaal).
Spread them evenly across the five sub-genres.

Each premise: "hi" one spoken-Hindi sentence in Devanagari stating the impossible turn; "en" a short English gloss;
"subgenre"; "motifs" 2-3 lowercase hyphenated English tags naming its concrete things (e.g. "wall-clock", "crow").

Never: gods, avatars, saints, holy men, scriptures, temples, prayers or religious miracles; real people, real places
as real events, news or "true story" claims; gore, killing shown, sexual content, harm to children, self-harm;
caste, religion or regional stereotypes. Do not reuse any of these existing premises or their twists:
{existing}"""


def similar(a: dict, b: dict) -> bool:
    ratio = difflib.SequenceMatcher(None, hindi.norm(a["hi"]), hindi.norm(b["hi"])).ratio()
    en = difflib.SequenceMatcher(None, a["en"].lower(), b["en"].lower()).ratio()
    return max(ratio, en) >= SIMILAR


def clean(new: list[dict], existing: list[dict], stamp: str) -> list[dict]:
    """The new premises that are well formed, clear of the red lines and unlike every existing one."""
    kept: list[dict] = []
    for p in new:
        motifs = [m.strip().lower() for m in p.get("motifs") or []]
        p = {"hi": " ".join(str(p.get("hi", "")).split()), "en": " ".join(str(p.get("en", "")).split()),
             "subgenre": p.get("subgenre"), "motifs": motifs}
        if (p["subgenre"] not in gate.SUBGENRES or not 2 <= len(motifs) <= 3 or not all(map(MOTIF.match, motifs))
                or hindi.devanagari_share(p["hi"]) < 0.9 or not p["en"]):
            continue
        if gate.red_lines_hi(p["hi"]) or gate.red_lines_en(p["en"]) or gate.banned(p["hi"]):
            continue
        if any(similar(p, q) for q in existing + kept):
            continue
        kept.append({"id": f"g{stamp}-{len(kept) + 1:02d}", **p})
    return kept


def refill(history: list[dict], ask) -> int:
    """Ask for more premises when few are left; returns how many were added. ask(messages, schema) -> dict."""
    everything = bank()
    if len(unused(history, everything)) >= LOW:
        return 0
    existing = "\n".join(f"- {p['en']}" for p in everything)
    answer = ask([{"role": "user", "content": PROMPT.format(n=ASK_FOR, existing=existing)}], SCHEMA)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M")
    added = clean(answer.get("premises") or [], everything, stamp)
    if added:
        ledger.save("premises", ledger.load("premises", []) + added)
    log.info("premise refill: %d of %d new premises kept", len(added), len(answer.get("premises") or []))
    return len(added)
