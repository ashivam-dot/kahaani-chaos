import copy
import json
from pathlib import Path

import pytest

from kahaani import cli, config, ledger

ROOT = Path(__file__).resolve().parents[1]
STORY = ROOT / ".github" / "replay" / "sikko-wala-kuan.json"
CHANNEL = config.EXPECTED_CHANNEL_ID


def story_dict() -> dict:
    return copy.deepcopy(json.loads(STORY.read_text(encoding="utf-8")))


def draft() -> dict:
    """The reviewed story as the writer would return it."""
    keys = ("title", "hook", "beats", "cast", "subgenre", "ending", "twist_beat", "description", "hashtags")
    d = story_dict()
    return {k: d[k] for k in keys}


EDITOR_OK = {"logic_ok": True, "twist_clear": True, "payoff_answers_hook": True, "natural_hindi": True,
             "title_spoils_twist": False, "red_line": False, "problems": []}


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    """Every test gets its own state and work folders, no keys and no channel id."""
    for name in ("GEMINI_API_KEY", "YOUTUBE_OAUTH_JSON", "KC_CHANNEL_ID", "GITHUB_OUTPUT"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(ledger, "STATE", tmp_path / "state")
    monkeypatch.setattr(cli, "WORK", tmp_path / "work")
    monkeypatch.setattr(config, "CHANNEL_ID", "TBD")
    return tmp_path
