import json
from datetime import datetime, timezone

import pytest

from kahaani import aiart, cli, compose, config, learn, ledger, premises, store, voice, writer, youtube
from kahaani.spec import Story

from .conftest import CHANNEL, EDITOR_OK, STORY, draft, story_dict

NARRATOR = {"engine": "gemini-narrator", "identity": "narrator", "served_model": "m", "wpm": 150.0,
            "coverage": [0.9], "tempo": 1.0}


class FakePen:
    used = ["gemini-test"]

    def __init__(self, *a):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        pass

    def chat(self, messages, schema=None, **kw):
        return draft() if schema is writer.SCHEMA else EDITOR_OK


def outputs(path):
    return dict(line.split("=", 1) for line in path.read_text().splitlines())


def test_plan_a_replay(tmp_path, monkeypatch):
    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "out.txt"))
    status = cli.plan(tmp_path / "plan", dry=True, replay=STORY)
    assert status["paint"] and status["story"] == "replay-sikko-wala-kuan"
    art = json.loads((tmp_path / "plan" / "art-plan.json").read_text(encoding="utf-8"))
    assert art["story"] == status["story"] and len(art["beats"]) == 12 and art["steps"] == 4
    out = outputs(tmp_path / "out.txt")
    assert out["paint"] == "true" and json.loads(out["chunks"]) == [str(i) for i in range(12)]


def test_a_reviewed_replay_may_be_published_once(tmp_path):
    status = cli.plan(tmp_path / "plan", dry=False, replay=STORY)
    assert status["paint"] and status["story"] == "replay-sikko-wala-kuan"
    ledger.add_ready({"id": "replay-sikko-wala-kuan", "premise": story_dict()["premise"], "made_at": "2026-10-13"})
    again = cli.plan(tmp_path / "again", dry=False, replay=STORY)
    assert "already made" in again["error"] and not again["paint"]


def test_a_replay_never_reuses_a_premise(tmp_path):
    ledger.add_ready({"id": "kc-other", "premise": story_dict()["premise"], "made_at": "2026-10-13"})
    status = cli.plan(tmp_path / "plan", dry=False, replay=STORY)
    assert "already made" in status["error"] and not status["paint"]
    assert cli.plan(tmp_path / "dry", dry=True, replay=STORY)["paint"]


def test_plan_skips_when_the_buffer_is_full(tmp_path):
    for i in range(config.BUFFER_TARGET):
        ledger.add_ready({"id": f"r{i}", "made_at": f"2026-10-1{i}"})
    status = cli.plan(tmp_path / "plan")
    assert status["skip"].startswith("buffer full") and not status["paint"]


def test_plan_holds_without_a_narrator(tmp_path, monkeypatch):
    monkeypatch.setattr(voice, "REFERENCE", tmp_path / "narrator_ref.wav")
    status = cli.plan(tmp_path / "plan")
    assert status["held"].startswith("hold: no narrator voice")


def test_plan_writes_the_next_premise(tmp_path, monkeypatch):
    monkeypatch.setattr(voice, "ready", lambda: None)
    monkeypatch.setattr(writer, "Pen", FakePen)
    status = cli.plan(tmp_path / "plan")
    assert status["paint"] and status["premise"] == "p001" and "refill" not in status
    story = Story.load(tmp_path / "plan" / "story.json")
    assert story.id.startswith("kc-") and story.id.endswith("-p001")
    assert story.motifs == premises.bank()[0]["motifs"] and story.writer["models"] == ["gemini-test"]


def make_plan(tmp_path, monkeypatch, dry=False):
    monkeypatch.setattr(voice, "ready", lambda: None)
    monkeypatch.setattr(writer, "Pen", FakePen)
    cli.plan(tmp_path / "plan", dry=dry)
    return tmp_path / "plan"


def fake_render(monkeypatch, pictures=None):
    def synth(story, work):
        (work / "timing.json").write_text(json.dumps({"voice": NARRATOR}))
        return {"voice": NARRATOR, "duration": 60.0, "words": [], "beats": []}

    def comp(story, timing, pics, work):
        (work / "short.mp4").write_bytes(b"mp4")
        return {"duration": 62.4, "frames": 1872, "pictures": len(set(pics)), "fps": 30, "size": [1080, 1920]}

    def same(found, texts, folder, *a):
        return [folder / "b.jpg"] * len(texts)

    monkeypatch.setattr(aiart, "pictures", pictures or same)
    monkeypatch.setattr(voice, "synthesize", synth)
    monkeypatch.setattr(compose, "render", comp)
    stored = []
    monkeypatch.setattr(store, "put", lambda sid, folder, title: stored.append(sid) or store.tag(sid))
    return stored


def test_render_stores_the_short_in_the_buffer(tmp_path, monkeypatch):
    plan = make_plan(tmp_path, monkeypatch)
    stored = fake_render(monkeypatch)
    health = cli.render(plan, tmp_path / "art", tmp_path / "work")
    assert health["ok"] and not health.get("held"), health
    row = ledger.ready()[0]
    assert stored == [row["id"]] and row["tag"] == f"ready-{row['id']}" and row["voice"] == "gemini-narrator"
    assert row["premise"] == "p001" and row["ending"] == "twist-reveal"
    assert ledger.load("health", {})["produce"]["made"]["id"] == row["id"]


def test_a_dry_render_touches_no_state(tmp_path, monkeypatch):
    plan = make_plan(tmp_path, monkeypatch, dry=True)
    stored = fake_render(monkeypatch)
    health = cli.render(plan, tmp_path / "art", tmp_path / "work", dry=True)
    assert health["ok"] and stored == [] and ledger.ready() == []
    assert not ledger.STATE.exists() and (cli.WORK / "dry-produce-health.json").exists()


def test_too_few_pictures_hold_and_count_a_try(tmp_path, monkeypatch):
    plan = make_plan(tmp_path, monkeypatch)

    def refuse(*a):
        raise aiart.PictureHold("hold: only 3 of 12 paintings passed")

    fake_render(monkeypatch, pictures=refuse)
    health = cli.render(plan, tmp_path / "art", tmp_path / "work")
    assert health["ok"] and health["held"].startswith("hold: only 3")
    assert ledger.load("tries", {})["p001"]["count"] == 1 and ledger.ready() == []


def test_a_voice_hold_does_not_spend_the_premise(tmp_path, monkeypatch):
    plan = make_plan(tmp_path, monkeypatch)
    fake_render(monkeypatch)

    def no_voice(story, work):
        raise voice.VoiceHold("hold: no narrator voice: quota, and the clip is missing")

    monkeypatch.setattr(voice, "synthesize", no_voice)
    health = cli.render(plan, tmp_path / "art", tmp_path / "work")
    assert health["held"].startswith("hold: no narrator voice") and ledger.load("tries", {}) == {}


def test_render_reports_a_held_plan(tmp_path):
    plan = tmp_path / "plan"
    plan.mkdir()
    (plan / "status.json").write_text(json.dumps({"held": "hold: no draft passed", "premise": "p004"}))
    health = cli.render(plan, None, tmp_path / "work")
    assert health["ok"] and health["held"] == "hold: no draft passed"
    assert ledger.load("health", {})["produce"]["held"] == "hold: no draft passed"


def test_render_fails_loudly_without_a_plan(tmp_path):
    health = cli.render(tmp_path / "nothing", None, tmp_path / "work")
    assert not health["ok"] and "plan failed" in health["error"]


NOW = datetime(2026, 10, 13, 5, 30, tzinfo=timezone.utc)


@pytest.fixture
def channel(monkeypatch):
    monkeypatch.setattr(config, "CHANNEL_ID", CHANNEL)
    monkeypatch.setattr(learn, "refresh", lambda api=None: None)


def buffered(monkeypatch, drop_fails=False):
    d = story_dict()
    ledger.add_ready({"id": d["id"], "premise": d["premise"], "made_at": "2026-10-12T06:00:00+00:00",
                      "tag": store.tag(d["id"])})

    def fetch(sid, folder):
        folder.mkdir(parents=True, exist_ok=True)
        Story.from_dict(d).save(folder / "story.json")
        (folder / "timing.json").write_text(json.dumps({"voice": NARRATOR}))
        (folder / "short.mp4").write_bytes(b"mp4")
        return folder

    dropped = []

    def drop(sid):
        if drop_fails:
            raise RuntimeError("gh: HTTP 502")
        dropped.append(sid)

    published = []

    def publish(story, mp4, voice, publish_at=None, api=None):
        published.append((story.id, publish_at))
        return {"video_id": "vid1", "url": "https://www.youtube.com/shorts/vid1", "privacy": "scheduled",
                "publish_at": publish_at, "synthetic_declared": True}

    monkeypatch.setattr(store, "fetch", fetch)
    monkeypatch.setattr(store, "drop", drop)
    monkeypatch.setattr(youtube, "publish", publish)
    return d["id"], dropped, published


def test_publish_holds_without_a_channel_id():
    assert cli.publish(NOW)["held"] == "hold: KC_CHANNEL_ID is not set"


def test_publish_holds_on_an_empty_buffer(channel):
    health = cli.publish(NOW)
    assert health["ok"] and health["held"].startswith("hold: the buffer is empty")


def test_publish_fills_the_slot_and_deletes_the_release(channel, monkeypatch):
    sid, dropped, published = buffered(monkeypatch)
    health = cli.publish(NOW)
    assert health["ok"] and published == [(sid, "2026-10-13T07:00:00Z")] and dropped == [sid]
    assert ledger.ready() == [] and ledger.published()[0]["slot"] == "2026-10-13T07:00:00Z"
    assert ledger.published()[0]["video_id"] == "vid1"
    assert cli.publish(NOW)["steps"] == ["the next slot is already filled"]


def test_a_release_left_behind_is_swept_next_time(channel, monkeypatch):
    sid, _, _ = buffered(monkeypatch, drop_fails=True)
    health = cli.publish(NOW)
    assert health["ok"] and ledger.published()[0]["release_left"] is True
    _, dropped, _ = buffered(monkeypatch)
    ledger.save("ready", [])
    cli.publish(NOW)
    assert dropped == [sid] and ledger.published()[0]["release_left"] is False


def test_a_missed_slot_is_published_at_once(channel, monkeypatch):
    sid, _, published = buffered(monkeypatch)
    cli.publish(datetime(2026, 10, 13, 7, 40, tzinfo=timezone.utc))
    assert published == [(sid, None)]
