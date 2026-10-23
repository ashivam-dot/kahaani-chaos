"""When a Short goes out: the format's IST slots (config.SLOTS; F1 is 13:00 and 19:00 IST daily), each filled at most once
from the ready buffer.

A slot that passed less than GRACE ago and was never filled is filled now (public at once); otherwise the next slot
is scheduled with YouTube's publishAt, or made public at once when it is less than LEAD away.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from . import config

LEAD = timedelta(minutes=15)
GRACE = timedelta(hours=2)


def iso(at: datetime) -> str:
    return at.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def around(now: datetime) -> list[datetime]:
    """The slots from yesterday to tomorrow (IST days), in time order."""
    today = now.astimezone(config.IST).date()
    days = [today + timedelta(days=d) for d in (-1, 0, 1)]
    return [datetime(d.year, d.month, d.day, h, m, tzinfo=config.IST) for d in days for h, m in config.SLOTS]


def due(now: datetime, taken: set[str]) -> dict | None:
    """{"slot", "publish_at"} for the slot to fill now (publish_at None means public at once), or None when the next
    slot is already filled."""
    slots = around(now)
    missed = [s for s in slots if now - GRACE < s <= now and iso(s) not in taken]
    if missed:
        return {"slot": iso(missed[-1]), "publish_at": None}
    upcoming = next(s for s in slots if s > now)
    if iso(upcoming) in taken:
        return None
    return {"slot": iso(upcoming), "publish_at": None if upcoming - now < LEAD else iso(upcoming)}


def slot_of(at: str) -> str | None:
    """The slot a video that went public at `at` (RFC 3339) filled: the last slot no later than LEAD after it, or
    None when no slot is that close (it went out more than a day after any slot)."""
    when = datetime.fromisoformat(at.replace("Z", "+00:00"))
    before = [s for s in around(when) if s <= when + LEAD]
    return iso(before[-1]) if before and when - before[-1] < timedelta(days=1) else None


def taken(rows: list[dict]) -> set[str]:
    return {r["slot"] for r in rows if r.get("slot")}


def buffer_full(ready: list[dict]) -> bool:
    return len(ready) >= config.BUFFER_TARGET
