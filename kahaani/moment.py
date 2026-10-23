"""Format M, "सन्नाटपुर, 1996: एक चीज़ ग़लत है": one wordless night in four or five paintings cut into 16 shots, with one
impossible detail drawn by code (card.py) onto a plain wall. Every on-screen string comes from the hand-approved bank
(bible/moment_bank.json); no model writes any Hindi here.

select() picks the next unused bank entry under the premise caps, plan() writes story.json (mode "moment") and
art-plan.json (one prompt per still), and timeline() is what voice.synthesize is for the other format: the shot spans
and the end card, with no speech.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np

from . import bible, config, ledger, look, premises, slots, music
from .spec import Story

BANK = bible.ROOT / "moment_bank.json"
SHOT = 1.3  # seconds a shot is held; 16 of them with the end card is what clears 6 picture changes per 10 s
END_CARD = 2.5
TAIL = 2.0  # the previous episode's answer (from #02 on)
LOOP = 0.5  # soft return to frame 0
PLACE_APART = 3  # episodes between two uses of a place
CARD_APART = 5  # ... of a card type
POWER_CUT_IN = 5  # at most one power cut in this many
ARMS = ("A", "B")


class Unfit(ValueError):
    """The bank entry breaks the schema (a bank edit that would make a broken Short)."""


@lru_cache(maxsize=None)
def bank() -> list[dict]:
    return json.loads(BANK.read_text(encoding="utf-8"))["entries"]


def _rows(history: list[dict]) -> list[dict]:
    return [r for r in history if (r.get("format") or "") == "moment"]


def card_apart(entries: list[dict] | None = None) -> int:
    """Episodes between two uses of a card type: CARD_APART, but never more than the kinds in the bank allow (3 kinds
    and a gap of 5 held every plan after #03 in the review's dry run)."""
    kinds = len({e["anomaly"]["card"] for e in (entries if entries is not None else bank())})
    return max(1, min(CARD_APART, kinds - 1))


def caps_problems(entry: dict, history: list[dict], entries: list[dict] | None = None) -> list[str]:
    """Why this entry may not come next (empty = it may): the premise caps of the format bible."""
    rows = _rows(history)
    apart = card_apart(entries)
    found = []
    if entry["place_id"] in {r.get("place_id") for r in rows[-(PLACE_APART - 1):]}:
        found.append(f"place {entry['place_id']} ran in the last {PLACE_APART - 1} episodes")
    kind = entry["anomaly"]["card"]
    if kind in {r.get("anomaly_type") for r in rows[-apart:]}:
        found.append(f"card type {kind} ran in the last {apart} episodes")
    if entry.get("premise_tag") == "power_cut" and "power_cut" in {r.get("premise_tag") for r in rows[-(POWER_CUT_IN - 1):]}:
        found.append(f"a power-cut premise ran in the last {POWER_CUT_IN - 1} episodes (at most 1 in {POWER_CUT_IN})")
    return found


def select(history: list[dict], entries: list[dict] | None = None) -> dict:
    """The next unused bank entry that clears the caps: the lowest episode number, preferring the call-to-action arm
    that did not run last (A and B alternate; the ask is the only thing that differs between them)."""
    rows = _rows(history)
    spent = {r.get("premise") for r in rows} | ledger.given_up()
    pool = sorted((e for e in (entries if entries is not None else bank()) if e["id"] not in spent),
                  key=lambda e: e["ep_n"])
    pool_all = entries if entries is not None else bank()
    why = {e["id"]: caps_problems(e, history, pool_all) for e in pool}
    fit = [e for e in pool if not why[e["id"]]]
    if not fit:
        reasons = "; ".join(f"{i}: {', '.join(p)}" for i, p in why.items())
        raise premises.NoPremise(f"{len(pool)} unused moments, none clear of the premise caps ({reasons or 'bank is spent'})")
    last = rows[-1].get("cta_arm") if rows else None
    return sorted(fit, key=lambda e: (e["cta_arm"] == last, e["ep_n"]))[0]


def previous(history: list[dict], entries: list[dict] | None = None) -> dict | None:
    """The bank entry of the episode made last: its answer is the tail of this one (None for the first)."""
    rows = _rows(history)
    by_id = {e["id"]: e for e in (entries if entries is not None else bank())}
    return by_id.get(rows[-1].get("premise")) if rows else None


def _cast() -> list[dict]:
    known = bible.cast()["jhabbu"]
    return [{"id": "jhabbu", "name": known["name"]["en"], "look": known["image"].strip()}]


def build_story(entry: dict, prev: dict | None, story_id: str) -> Story:
    """The Story for a bank entry. Shots get their spans here (SHOT seconds each, back to back)."""
    shots = [{**s, "t0": round(i * SHOT, 3), "t1": round((i + 1) * SHOT, 3)} for i, s in enumerate(entry["shots"])]
    anomaly = entry["anomaly"]
    cards = [{"kind": anomaly["card"], "spec": anomaly["spec"], "role": "anomaly",
              "placements": anomaly["placements"]}]
    if prev:
        cards.append({"kind": prev["anomaly"]["card"], "spec": prev["anomaly"]["spec"], "role": "previous",
                      "text": f"#{prev['ep_n']:02d} का जवाब: {prev['anomaly']['tail_hi']}",
                      "register": prev["anomaly"]["register_line_hi"], "ep_n": prev["ep_n"]})
    stills = [{"scene": p, "people": entry["cast_people"] if i == entry["cast_shot_index"] else []}
              for i, p in enumerate(entry["still_prompts"])]
    return Story(id=story_id, premise=entry["id"], title=entry["title"], hook=entry["hook_strip"], beats=[],
                 cast=_cast(), subgenre=entry["premise_tag"], ending="loop-back", twist_beat=0,
                 description=entry["description_hi"], hashtags=entry["hashtags"], writer={"models": [], "log": "bank"},
                 format="moment", hook_strip=entry["hook_strip"], anomaly=anomaly["card"], skeleton=entry["skeleton"],
                 place_id=entry["place_id"], mode="moment", stills=stills, shots=shots, cards=cards,
                 cta_arm=entry["cta_arm"], cta_text=entry["end_card_hi"], first_comment_hi=entry["first_comment_hi"],
                 anomaly_type=anomaly["card"], answer_hi=anomaly["answer_hi"],
                 register_line_hi=anomaly["register_line_hi"], ep_n=entry["ep_n"], stamp=entry["time_stamp"],
                 cite_niyam_id="N21" if entry.get("thread") else "")


def card_of(story: Story, role: str = "anomaly") -> dict | None:
    return next((c for c in story.cards if c.get("role") == role), None)


def _mask(quad: list[list[float]], size: tuple[int, int] = (90, 160)) -> np.ndarray:
    m = np.zeros((size[1], size[0]), np.uint8)
    cv2.fillPoly(m, [np.array([[x * size[0], y * size[1]] for x, y in quad], np.int32)], 1)
    return m


def exposure(story: Story, shot: dict) -> float:
    """The share of this shot's frame the anomaly card covers (0 when its still has no card or the crop misses it)."""
    card = card_of(story)
    if not card:
        return 0.0
    x0, y0, w = shot["box"]
    gx, gy = 90, 160
    best = 0.0
    for p in card["placements"]:
        if p["still"] != shot["still"]:
            continue
        m = _mask(p["quad"], (gx, gy))
        c = m[round(y0 * gy):round((y0 + w) * gy), round(x0 * gx):round((x0 + w) * gx)]
        best = max(best, float(c.sum()) / max(c.size, 1))
    return best


def sfx_cues(story: Story) -> list[dict]:
    """Every foley cue on the Short's clock: [{"cue", "at", "dur"}], the shots' cues, the page turn that opens the
    previous answer, and nothing else (the motif ring on from its shot into the end card)."""
    out = []
    for s in story.shots:
        for cue in s.get("sfx") or []:
            out.append({"cue": cue[0], "at": round(s["t0"] + cue[1], 3), "dur": cue[2] if len(cue) > 2 else None})
    tl = timeline(story)
    if tl["tail"]:
        out.append({"cue": "page_turn", "at": tl["tail"][0], "dur": None})
    return sorted(out, key=lambda c: c["at"])


def timeline(story: Story) -> dict:
    """What voice.synthesize returns for the other format: the whole Short on one clock, with no words and a voice
    record that says so. end/tail/loop are [start, end] seconds (tail is None for the first episode)."""
    spans = [[s["t0"], s["t1"]] for s in story.shots]
    t = spans[-1][1]
    end = [t, round(t + END_CARD, 3)]
    tail = [end[1], round(end[1] + TAIL, 3)] if card_of(story, "previous") else None
    stop = tail[1] if tail else end[1]
    return {"duration": round(stop + LOOP, 3), "beats": spans, "words": [], "end": end, "tail": tail,
            "loop": [stop, round(stop + LOOP, 3)], "voice": {"engine": "none", "identity": "wordless"}}


def art_plan(story: Story) -> dict:
    """One prompt and seed per still, through look.py (a cast still is a hand and a lantern, never a face)."""
    from . import imagegen

    rows = look.plan(story.id, [dict(s) for s in story.stills], story.cast, hook=False)
    for row, still in zip(rows, story.stills):
        if row["cast"]:
            row["prompt"] = look.hand_prompt(still["scene"])
    return {"story": story.id, "model": "zimage", "steps": imagegen.MODELS["zimage"]["steps"],
            "width": imagegen.WIDTH, "height": imagegen.HEIGHT, "beats": rows}


def plan(out: Path, dry: bool = False, replay: Path | None = None) -> dict:
    """story.json, art-plan.json and status.json in out. The paint matrix runs over the stills (status "beats")."""
    import traceback

    from . import cli, gate

    out.mkdir(parents=True, exist_ok=True)
    status: dict = {"at": ledger.now(), "dry": dry, "paint": False}
    try:
        history = ledger.history()
        if not dry and slots.buffer_full(ledger.ready(config.FORMAT)):
            status["skip"] = f"buffer full ({len(ledger.ready(config.FORMAT))} ready)"
            return status
        if replay:
            story = Story.load(replay)
            if not dry and any(r.get("id") == story.id or r.get("premise") == story.premise for r in history):
                raise ValueError(f"replay {story.id} (premise {story.premise}) was already made for the channel")
        else:
            entry = select(history)
            prev = previous(history)
            if prev is None and _rows(history):
                raise premises.NoPremise(f"the last episode's premise {_rows(history)[-1].get('premise')!r} is not in "
                                         "the bank, so its answer (the next tail) cannot be shown")
            stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M")
            story = build_story(entry, prev, f"kc-{stamp}-{entry['id']}")
        problems = gate.check_moment(asdict(story), history, rotation=not dry)
        if problems:
            raise ValueError("the moment fails the gates: " + "; ".join(problems))
        story.save(out / "story.json")
        (out / "art-plan.json").write_text(json.dumps(cli.art_plan(story), indent=1, ensure_ascii=False),
                                           encoding="utf-8")
        status.update(paint=True, story=story.id, premise=story.premise, beats=len(story.stills))
        return status
    except premises.NoPremise as exc:
        status["held"] = f"hold: {exc}"[:500]
        return status
    except Exception as exc:
        status.update(error=f"{type(exc).__name__}: {exc}"[:500], trace=traceback.format_exc()[-2000:])
        return status
    finally:
        (out / "status.json").write_text(json.dumps(status, indent=1, ensure_ascii=False), encoding="utf-8")
        cli._outputs(paint=str(status["paint"]).lower(),
                     chunks=json.dumps([str(i) for i in range(status.get("beats", 0))]))


def schema_problems(entry: dict) -> list[str]:
    """What is wrong with one bank entry (the bank test and gate.check_moment both ask)."""
    found = []
    for key in ("id", "ep_n", "place_id", "time_stamp", "premise_tag", "hook_strip", "still_prompts", "shots",
                "cast_shot_index", "cast_people", "anomaly", "cta_arm", "end_card_hi", "title", "skeleton",
                "first_comment_hi", "description_hi", "hashtags"):
        if key not in entry:
            found.append(f"{entry.get('id', '?')}: missing {key}")
    if found:
        return found
    n = len(entry["still_prompts"])
    if entry["cta_arm"] not in ARMS:
        found.append(f"{entry['id']}: cta_arm {entry['cta_arm']!r} is not one of {ARMS}")
    anomaly = entry["anomaly"]
    for key in ("card", "spec", "placements", "answer_hi", "tail_hi", "register_line_hi"):
        if key not in anomaly:
            found.append(f"{entry['id']}: anomaly lacks {key}")
    if found:
        return found
    for s in entry["shots"]:
        if not 0 <= s["still"] < n:
            found.append(f"{entry['id']}: a shot uses still {s['still']} of {n}")
        x0, y0, w = s["box"]
        if not (0 <= x0 and 0 <= y0 and 0 < w <= 1 and x0 + w <= 1.0001 and y0 + w <= 1.0001):
            found.append(f"{entry['id']}: crop box {s['box']} leaves the still")
        for cue in s["sfx"]:
            if cue[0] not in music.CUES + ("motif",):
                found.append(f"{entry['id']}: unknown foley cue {cue[0]!r}")
    for p in anomaly["placements"]:
        if len(p["quad"]) != 4 or not 0 <= p["still"] < n:
            found.append(f"{entry['id']}: bad card placement {p}")
    return found
