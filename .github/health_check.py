"""Open (or update) an alert issue when the pipeline is silent, its last production or publish run failed, or it is
holding.

python3 .github/health_check.py state/health.json  (a missing file means no run has been recorded yet: no alert)
"""
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

SILENT_H = 30
TITLE = "Kahaani Chaos needs attention"


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
    return "\n".join(found) or None


def main() -> None:
    found_problem = problem(Path(sys.argv[1]), datetime.now(timezone.utc))
    print(found_problem or "healthy")
    if not found_problem:
        return
    found = subprocess.run(["gh", "issue", "list", "--state", "open", "--label", "alert", "--search", TITLE,
                            "--json", "number", "--jq", ".[0].number"], capture_output=True, text=True).stdout.strip()
    if found:
        subprocess.run(["gh", "issue", "comment", found, "--body", found_problem], check=True)
    else:
        subprocess.run(["gh", "issue", "create", "--label", "alert", "--title", TITLE, "--body", found_problem],
                       check=True)


if __name__ == "__main__":
    main()
