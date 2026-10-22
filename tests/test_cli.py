import json
from datetime import datetime, timezone

import pytest

from kahaani import aiart, cli, compose, config, learn, ledger, premises, store, voice, writer, youtube
from kahaani.spec import Story

from .conftest import CHANNEL, EDITOR_OK, STORY, draft, story_dict

NARRATOR = {"engine": "gemini-narrator", "identity": "narrator", "served_model": "m", "wpm": 165.0,
            "coverage": [0.98], "tempo": 1.0, "checks": {"onset": 0.2, "hook_wpm": 176.0, "body_wpm": 165.0,
                                                          "coverage": 0.98, "cer": 0.04, "max_gap": 0.6}}
REPLAY_ID = "replay-dynamo-wali-cycle"


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
    assert status["paint"] and status["story"] == REPLAY_ID
    art = json.loads((tmp_path / "plan" / "art-plan.json").read_text(encoding="utf-8"))
    assert art["story"] == status["story"] and len(art["beats"]) == 6 and art["steps"] == 4
    assert [len(b.get("alternates", [])) for b in art["beats"]] == [0, 2, 2, 2, 2, 0]
    out = outputs(tmp_path / "out.txt")
    assert out["paint"] == "true" and json.loads(out["chunks"]) == [str(i) for i in range(6)]


def test_a_reviewed_replay_may_be_published_once(tmp_path):
    status = cli.plan(tmp_path / "plan", dry=False, replay=STORY)
    assert status["paint"] and status["story"] == REPLAY_ID
    ledger.add_ready({"id": REPLAY_ID, "premise": story_dict()["premise"], "made_at": "2026-10-13"})
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
    assert status["paint"] and status["premise"] == "e01" and "bank_low" not in status
    story = Story.load(tmp_path / "plan" / "story.json")
    assert story.id.startswith("kc-") and story.id.endswith("-e01")
    assert story.motifs == [] and story.writer["models"] == ["gemini-test"]
    entry = premises.bank()[0]
    assert (story.format, story.skeleton, story.object_token, story.place_id) == (
        config.FORMAT, entry["title_skeleton"], entry["object_token"], entry["place_id"])
    assert story.hook_strip and story.niyam_id == entry["niyam_id"] and story.heart_type == entry["heart_type"]


class LocalPen(FakePen):
    used = ["gemini-test", "qwen2.5-local"]


def test_hindi_from_the_local_model_holds_and_keeps_the_premise(tmp_path, monkeypatch):
    monkeypatch.setattr(voice, "ready", lambda: None)
    monkeypatch.setattr(writer, "Pen", LocalPen)
    status = cli.plan(tmp_path / "plan")
    assert status["held"] == cli.LOCAL_HOLD and not status["paint"]
    cli.render(tmp_path / "plan", None, tmp_path / "work")
    assert ledger.load("tries", {}) == {}
    assert cli.plan(tmp_path / "dry", dry=True)["paint"]


def test_a_low_bank_is_reported(tmp_path, monkeypatch):
    ledger.save("published", [{"id": f"kc-{e['id']}", "premise": e["id"], "made_at": f"2026-01-{i:02d}"}
                              for i, e in enumerate(premises.bank()[:31])])
    plan = make_plan(tmp_path, monkeypatch)
    status = json.loads((plan / "status.json").read_text(encoding="utf-8"))
    assert "only 9 unused" in status["bank_low"]
    fake_render(monkeypatch)
    health = cli.render(plan, tmp_path / "art", tmp_path / "work")
    assert "only 9 unused" in health["bank_low"]


def test_a_refused_premise_hands_the_slot_to_the_next_one(tmp_path, monkeypatch):
    monkeypatch.setattr(voice, "ready", lambda: None)
    monkeypatch.setattr(writer, "Pen", FakePen)
    real, refused = writer.write, []

    def picky(premise, history, ask):
        if len(refused) < 1:
            refused.append(premise["id"])
            raise writer.WriterHold(f"hold: no draft of {premise['id']} passed after 2 repairs: logic gap")
        return real(premise, history, ask)

    monkeypatch.setattr(writer, "write", picky)
    bank = premises.bank()
    monkeypatch.setattr(premises, "bank", lambda: [bank[1], bank[0], *bank[2:]])  # the fixture is e01's draft
    status = cli.plan(tmp_path / "plan")
    assert status["paint"] and refused == ["e02"] and status["premise"] == "e01"
    assert status["passed_over"] == [[refused[0], f"hold: no draft of {refused[0]} passed after 2 repairs: logic gap"]]
    fake_render(monkeypatch)
    assert cli.render(tmp_path / "plan", tmp_path / "art", tmp_path / "work")["ok"]
    tries = ledger.load("tries", {})
    assert tries[refused[0]]["count"] == 1 and status["premise"] not in tries


def test_after_three_refused_premises_the_run_holds_and_counts_each_once(tmp_path, monkeypatch):
    monkeypatch.setattr(voice, "ready", lambda: None)
    monkeypatch.setattr(writer, "Pen", FakePen)

    def never(premise, history, ask):
        raise writer.WriterHold(f"hold: no draft of {premise['id']} passed")

    monkeypatch.setattr(writer, "write", never)
    status = cli.plan(tmp_path / "plan")
    assert status["held"] == f"hold: no draft of {status['premise']} passed" and len(status["passed_over"]) == 3
    assert len({p for p, _ in status["passed_over"]}) == 3
    cli.render(tmp_path / "plan", None, tmp_path / "work")
    assert {p: r["count"] for p, r in ledger.load("tries", {}).items()} == {p: 1 for p, _ in status["passed_over"]}


def make_plan(tmp_path, monkeypatch, dry=False):
    monkeypatch.setattr(voice, "ready", lambda: None)
    monkeypatch.setattr(writer, "Pen", FakePen)
    cli.plan(tmp_path / "plan", dry=dry)
    return tmp_path / "plan"


def fake_render(monkeypatch, pictures=None):
    def synth(story, work):
        (work / "timing.json").write_text(json.dumps({"voice": NARRATOR}))
        spans = [[i * 7.0, i * 7.0 + 7.0] for i in range(len(story.beats))]
        return {"voice": NARRATOR, "duration": 7.0 * len(story.beats), "words": [], "beats": spans}

    def comp(story, timing, pics, work):
        (work / "short.mp4").write_bytes(b"mp4")
        return {"duration": timing["duration"] + 2.4, "frames": 1332, "pictures": len(set(pics)), "fps": 30,
                "size": [1080, 1920]}

    def same(found, texts, folder, *a, **kw):
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
    assert row["premise"] == "e01" and row["ending"] == "loop-back" and row["format"] == config.FORMAT
    assert row["skeleton"] == "S1" and row["object_token"] == "साइकिल" and row["script"]
    assert ledger.load("health", {})["produce"]["made"]["id"] == row["id"]


def test_a_dry_render_touches_no_state(tmp_path, monkeypatch):
    plan = make_plan(tmp_path, monkeypatch, dry=True)
    stored = fake_render(monkeypatch)
    health = cli.render(plan, tmp_path / "art", tmp_path / "work", dry=True)
    assert health["ok"] and stored == [] and ledger.ready() == []
    assert not ledger.STATE.exists() and (cli.WORK / "dry-produce-health.json").exists()


def test_too_few_pictures_hold_and_count_a_try(tmp_path, monkeypatch):
    plan = make_plan(tmp_path, monkeypatch)

    def refuse(*a, **kw):
        raise aiart.PictureHold("hold: only 3 of 6 paintings passed")

    fake_render(monkeypatch, pictures=refuse)
    health = cli.render(plan, tmp_path / "art", tmp_path / "work")
    assert health["ok"] and health["held"].startswith("hold: only 3")
    assert ledger.load("tries", {})["e01"]["count"] == 1 and ledger.ready() == []


def test_low_prop_identity_holds(tmp_path, monkeypatch):
    plan = make_plan(tmp_path, monkeypatch)
    fake_render(monkeypatch)
    monkeypatch.setattr(aiart, "prop_rate", lambda report: 0.5)
    health = cli.render(plan, tmp_path / "art", tmp_path / "work")
    assert health["held"].startswith("hold: prop identity 50%") and health["prop_identity"] == 0.5
    assert ledger.ready() == []


def test_a_narration_outside_the_runtime_band_holds(tmp_path, monkeypatch):
    plan = make_plan(tmp_path, monkeypatch)
    fake_render(monkeypatch)

    def long(story, work):
        spans = [[i * 11.0, i * 11.0 + 11.0] for i in range(len(story.beats))]
        return {"voice": NARRATOR, "duration": 66.0, "words": [], "beats": spans}

    monkeypatch.setattr(voice, "synthesize", long)
    health = cli.render(plan, tmp_path / "art", tmp_path / "work")
    assert "F1 needs 30-58 s" in health["held"] and ledger.ready() == []


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
    assert health["ok"] and published == [(sid, "2026-10-13T13:30:00Z")] and dropped == [sid]
    assert ledger.ready() == [] and ledger.published()[0]["slot"] == "2026-10-13T13:30:00Z"
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
    cli.publish(datetime(2026, 10, 13, 14, 10, tzinfo=timezone.utc))
    assert published == [(sid, None)]
