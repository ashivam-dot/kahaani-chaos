import copy
import json
from pathlib import Path

import pytest

from kahaani import cli, config, ledger

ROOT = Path(__file__).resolve().parents[1]
STORY = ROOT / ".github" / "replay" / "dynamo-wali-cycle.json"
CHANNEL = config.EXPECTED_CHANNEL_ID


def story_dict() -> dict:
    return copy.deepcopy(json.loads(STORY.read_text(encoding="utf-8")))


def draft() -> dict:
    """The reviewed story as the writer would return it."""
    keys = ("title", "hook", "hook_strip", "object_token", "anomaly", "niyam_id", "resolution", "ending", "twist_beat",
            "heart_beat", "cast", "beats", "description", "hashtags")
    d = story_dict()
    return {k: d[k] for k in keys}


EDITOR_OK = {"logic_ok": True, "rule_clear": True, "hook_has_anomaly": True, "heart_lands": True,
             "natural_hindi": True, "canon_ok": True, "kids_directed": False, "title_spoils_turn": False,
             "red_line": False, "problems": []}


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    """Every test gets its own state and work folders, no keys and no channel id."""
    for name in ("GEMINI_API_KEY", "YOUTUBE_OAUTH_JSON", "KC_CHANNEL_ID", "GITHUB_OUTPUT", "KC_PLAYLIST_MICRO"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(ledger, "STATE", tmp_path / "state")
    monkeypatch.setattr(cli, "WORK", tmp_path / "work")
    monkeypatch.setattr(config, "CHANNEL_ID", "TBD")
    return tmp_path
