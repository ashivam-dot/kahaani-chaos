"""Open (or update) an alert issue when the pipeline is silent, its last production or publish run failed, or it is
holding, and for the F1 warnings (PLAN.md §7.8): the micro-entry bank running low, a read-back mismatch, the Analytics
scope missing, and the ready buffer below target once the day's production window is over. Close it once healthy.

python3 .github/health_check.py state/health.json  (a missing file means no run has been recorded yet: no alert;
ready.json and performance.json are read from the same folder)
"""
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

SILENT_H = 30
TITLE = "Sannatpur Ki Raatein needs attention"
BUFFER_TARGET = 2  # kahaani.config.FORMATS["micro"].buffer
# Production runs at 01:30 and 07:30 UTC and the slot is 13:30 UTC: between these hours the buffer should be full.
BUFFER_HOURS = (10, 13)


def _load(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def problem(path: Path, now: datetime) -> str | None:
    if not path.exists():
        print("no run recorded yet (state/health.json is missing)")
        return None
    runs = json.loads(path.read_text(encoding="utf-8"))
    if not runs:
        return None
    latest = max(datetime.fromisoformat(h["at"]) for h in runs.values())
    age = (now - latest).total_seconds() / 3600
    if age > SILENT_H:
        return f"No run recorded for {age:.1f} hours (last at {latest.isoformat()})."
    found = []
    for kind, health in sorted(runs.items()):
        if not health.get("ok"):
            found.append(f"Last {kind} run failed: {health.get('error')}")
        elif health.get("held"):
            found.append(f"The {kind} run is holding: {health['held']}")
        if health.get("bank_low"):
            found.append(f"Micro bank: {health['bank_low']}")
        if health.get("readback"):
            found.append(f"Read-back mismatch on the last upload: {health['readback']}. Set PAUSED=true and check it "
                         "in Studio.")
    analytics = _load(path.parent / "performance.json", {}).get("analytics") or ""
    if analytics.startswith("missing"):
        found.append(f"Analytics scope missing: {analytics} (re-run the OAuth consent with yt-analytics.readonly).")
    ready = _load(path.parent / "ready.json", None)
    if ready is not None and BUFFER_HOURS[0] <= now.hour <= BUFFER_HOURS[1] and len(ready) < BUFFER_TARGET:
        found.append(f"The ready buffer has {len(ready)} Shorts after the day's production; target {BUFFER_TARGET}.")
    return "\n".join(found) or None


def main() -> None:
    found_problem = problem(Path(sys.argv[1]), datetime.now(timezone.utc))
    print(found_problem or "healthy")
    found = subprocess.run(["gh", "issue", "list", "--state", "open", "--label", "alert", "--search", TITLE,
                            "--json", "number", "--jq", ".[0].number"], capture_output=True, text=True).stdout.strip()
    if not found_problem:
        if found:
            subprocess.run(["gh", "issue", "close", found, "--comment", "Healthy again: the last runs succeeded."],
                           check=True)
        return
    if found:
        subprocess.run(["gh", "issue", "comment", found, "--body", found_problem], check=True)
    else:
        subprocess.run(["gh", "issue", "create", "--label", "alert", "--title", TITLE, "--body", found_problem],
                       check=True)


if __name__ == "__main__":
    main()
