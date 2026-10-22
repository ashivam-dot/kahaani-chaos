"""The channel's memory: the ready buffer, what was published, premises tried or given up, and the last runs' health.

In GitHub Actions the `state` directory is a checkout of the repo's `state` branch, committed back after each run.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

STATE = Path(__file__).resolve().parents[1] / "state"
TRIES = 3
# What a row keeps about a story so later stories can avoid repeating it.
SUMMARY = ("id", "premise", "title", "subgenre", "motifs", "ending", "opening", "made_at", "voice",
           # F1 micro-entry rotation (premises.fits, variation.problems)
           "format", "skeleton", "resolution", "heart_type", "object_token", "anomaly", "location", "place_id",
           "hook_strip", "script")


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def load(name: str, default):
    path = STATE / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def save(name: str, data) -> Path:
    STATE.mkdir(parents=True, exist_ok=True)
    path = STATE / f"{name}.json"
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def set_identity() -> None:
    """Give the state checkout a committer, so the workflow's `git pull --rebase` can replay its commit when the
    state branch moved during the run."""
    import subprocess

    if not (STATE / ".git").exists():
        return
    for key, value in (("user.name", "ashivam-dot"),
                       ("user.email", "335661989+ashivam-dot@users.noreply.github.com")):
        subprocess.run(["git", "-C", str(STATE), "config", key, value], check=False, capture_output=True)


def published() -> list[dict]:
    return load("published", [])


def ready() -> list[dict]:
    """The buffer: finished Shorts waiting for a slot, oldest first."""
    return sorted(load("ready", []), key=lambda r: r["made_at"])


def history() -> list[dict]:
    """Every story made, published or waiting, in the order it was made: what rotation rules compare against."""
    return sorted(published() + ready(), key=lambda r: r["made_at"])


def add_ready(row: dict) -> None:
    rows = [r for r in load("ready", []) if r["id"] != row["id"]] + [row]
    save("ready", rows)


def record_publish(entry: dict) -> None:
    """Move a story from the buffer to the published list."""
    save("ready", [r for r in load("ready", []) if r["id"] != entry["id"]])
    save("published", [r for r in published() if r["id"] != entry["id"]] + [entry])


def mark(story_id: str, **fields) -> None:
    rows = published()
    for r in rows:
        if r["id"] == story_id:
            r.update(fields)
    save("published", rows)


def retry(premise: str, reason: str) -> bool:
    """Count a failed try of a premise; after TRIES it is given up. True while it may still be tried."""
    tries = load("tries", {})
    row = {"count": tries.get(premise, {}).get("count", 0) + 1, "reason": reason[:300], "at": now()}
    tries[premise] = row
    save("tries", tries)
    return row["count"] < TRIES


def given_up() -> set[str]:
    return {p for p, row in load("tries", {}).items() if row["count"] >= TRIES}


def save_health(kind: str, health: dict) -> None:
    """health.json keeps the last production run and the last publish run side by side."""
    data = load("health", {})
    data[kind] = health
    save("health", data)
