"""Cloud repair painting must never become a video or a publishing bypass."""
import json
from pathlib import Path
from unittest.mock import Mock

import pytest

from kahaani import aiart, batch_release, cli, compose, ledger, store, voice, writer
from .conftest import STORY


def brief(tmp_path, monkeypatch, beats=None, source=".github/replay/story.json"):
    monkeypatch.setattr(cli, "ROOT", tmp_path)
    target = tmp_path / ".github/replay/story.json"
    target.parent.mkdir(parents=True)
    target.write_bytes(STORY.read_bytes())
    packet = tmp_path / "brief.json"
    packet.write_text(json.dumps({"art_only": {"story": source, "beats": beats if beats is not None else [5]}}))
    return packet


def test_only_requested_beat_is_painted_without_writer(tmp_path, monkeypatch):
    packet = brief(tmp_path, monkeypatch)
    pen = Mock(side_effect=AssertionError("no writing during an exact repair"))
    monkeypatch.setattr(writer, "Pen", pen)
    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "outputs"))
    status = cli.plan(tmp_path / "plan", dry=True, replay=packet)
    assert status["art_only_beats"] == [5] and status["paint_beats"] == [5]
    assert json.loads(dict(line.split("=", 1) for line in (tmp_path / "outputs").read_text().splitlines())["chunks"]) == ["5"]
    assert (tmp_path / "plan/story.json").read_bytes() == (tmp_path / ".github/replay/story.json").read_bytes()
    pen.assert_not_called()


@pytest.mark.parametrize("beats", [[], [True], [-1], [6], [5, 5], "5", [1.0]])
def test_invalid_beats_cannot_request_a_matrix(tmp_path, monkeypatch, beats):
    status = cli.plan(tmp_path / "plan", dry=True, replay=brief(tmp_path, monkeypatch, beats))
    assert status.get("error") and not status["paint"]


@pytest.mark.parametrize("source", ["../story.json", ".github/replay/../story.json", ".github/replay/story.txt", "/etc/passwd"])
def test_source_must_stay_in_replay_json(tmp_path, monkeypatch, source):
    status = cli.plan(tmp_path / "plan", dry=True, replay=brief(tmp_path, monkeypatch, source=source))
    assert "within .github/replay" in status["error"] and not status["paint"]


def test_symlink_cannot_escape_replay(tmp_path, monkeypatch):
    packet = brief(tmp_path, monkeypatch)
    target = tmp_path / ".github/replay/story.json"
    target.unlink()
    target.symlink_to(STORY)
    status = cli.plan(tmp_path / "plan", dry=True, replay=packet)
    assert "within .github/replay" in status["error"]


def test_art_only_has_no_voice_render_store_or_live_path(tmp_path, monkeypatch):
    packet = brief(tmp_path, monkeypatch)
    assert "dry-run only" in cli.plan(tmp_path / "live", replay=packet)["error"]
    plan = tmp_path / "plan"
    status = cli.plan(plan, dry=True, replay=packet)
    forbidden = Mock(side_effect=AssertionError("art collection cannot produce or publish"))
    monkeypatch.setattr(aiart, "pictures", forbidden)
    monkeypatch.setattr(compose, "render", forbidden)
    monkeypatch.setattr(store, "put", forbidden)
    monkeypatch.setattr(voice, "synthesize", forbidden)
    monkeypatch.setattr(aiart, "collect", lambda *a: {5: Path("actual-cloud-art.png")})
    health = cli.render(plan, None, tmp_path / "work", dry=True)
    assert health["ok"] and health["art_only_beats"] == [5] and "made" not in health
    assert not list((tmp_path / "work").rglob("*.mp4")) and ledger.ready() == []
    with pytest.raises(ValueError):
        batch_release.validate({"premise": status["premise"]}, tmp_path / "work")
    live = cli.render(plan, None, tmp_path / "work")
    assert not live["ok"] and "can never publish" in live["error"]
    forbidden.assert_not_called()
    monkeypatch.setattr(aiart, "collect", lambda *a: {})
    missing = cli.render(plan, None, tmp_path / "missing", dry=True)
    assert not missing["ok"] and "missing" in missing["error"]


def test_art_only_does_not_bypass_story_gate(tmp_path, monkeypatch):
    packet = brief(tmp_path, monkeypatch)
    path = tmp_path / ".github/replay/story.json"
    story = json.loads(path.read_text())
    story["beats"][0]["text"] = ""
    path.write_text(json.dumps(story))
    status = cli.plan(tmp_path / "plan", dry=True, replay=packet)
    assert "fails the gates" in status["error"] and not status["paint"]
