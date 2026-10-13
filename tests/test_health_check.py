import importlib.util
import json
from datetime import datetime, timedelta, timezone

from .conftest import ROOT

spec = importlib.util.spec_from_file_location("health_check", ROOT / ".github" / "health_check.py")
health_check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(health_check)

NOW = datetime(2026, 10, 13, 12, 0, tzinfo=timezone.utc)


def write(tmp_path, runs):
    path = tmp_path / "health.json"
    path.write_text(json.dumps(runs))
    return path


def at(hours_ago):
    return (NOW - timedelta(hours=hours_ago)).isoformat()


def test_no_record_is_quiet(tmp_path):
    assert health_check.problem(tmp_path / "health.json", NOW) is None


def test_healthy(tmp_path):
    runs = {"produce": {"at": at(5), "ok": True}, "publish": {"at": at(2), "ok": True}}
    assert health_check.problem(write(tmp_path, runs), NOW) is None


def test_silence_over_thirty_hours(tmp_path):
    runs = {"produce": {"at": at(31), "ok": True}, "publish": {"at": at(30.5), "ok": True}}
    assert "No run recorded for 30.5 hours" in health_check.problem(write(tmp_path, runs), NOW)


def test_failure_and_hold_are_both_reported(tmp_path):
    runs = {"produce": {"at": at(5), "ok": False, "error": "boom"},
            "publish": {"at": at(2), "ok": True, "held": "hold: the buffer is empty"}}
    found = health_check.problem(write(tmp_path, runs), NOW)
    assert "Last produce run failed: boom" in found and "publish run is holding: hold: the buffer is empty" in found
