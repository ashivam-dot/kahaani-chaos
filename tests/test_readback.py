"""The read-back gate: after every upload the video is read again and must match what was asked, or the run holds."""
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from kahaani import config, youtube
from kahaani.spec import Story

from .conftest import CHANNEL, story_dict
from .test_youtube import NARRATOR, FakeYouTube

BEFORE = datetime(2026, 10, 24, 12, 0, tzinfo=timezone.utc)
AFTER = datetime(2026, 10, 24, 14, 0, tzinfo=timezone.utc)
SLOT = "2026-10-24T13:30:00Z"


@pytest.fixture(autouse=True)
def pinned(monkeypatch):
    monkeypatch.setattr(config, "CHANNEL_ID", CHANNEL)


def video(**status):
    base = {"privacyStatus": "private", "publishAt": "2026-10-24T13:30:00.000Z", "madeForKids": False,
            "selfDeclaredMadeForKids": False, "uploadStatus": "processed"}
    return {"snippet": {"channelId": CHANNEL}, "status": {**base, **status}}


def test_a_matching_scheduled_video_passes():
    assert youtube.readback_problems(video(), SLOT, BEFORE) == []
    assert youtube.readback_problems(video(publishAt="2026-10-24T19:00:00+05:30"), SLOT, BEFORE) == []


@pytest.mark.parametrize("change, fragment", [
    ({"madeForKids": True}, "madeForKids is True"),
    ({"madeForKids": None}, "madeForKids is None"),
    ({"selfDeclaredMadeForKids": True}, "selfDeclaredMadeForKids is True"),
    ({"privacyStatus": "public"}, "not 'private' before release"),
    ({"privacyStatus": "unlisted"}, "not 'private' before release"),
    ({"publishAt": "2026-10-25T13:30:00Z"}, "publishAt is"),
    ({"publishAt": None}, "publishAt is"),
    ({"uploadStatus": "rejected", "rejectionReason": "duplicate"}, "uploadStatus is 'rejected' (duplicate)"),
    ({"containsSyntheticMedia": False}, "containsSyntheticMedia is not True"),
])
def test_every_drift_is_named(change, fragment):
    found = youtube.readback_problems(video(**change), SLOT, BEFORE)
    assert any(fragment in p for p in found), found


def test_after_the_slot_public_is_expected():
    assert youtube.readback_problems(video(privacyStatus="public", publishAt=None), SLOT, AFTER) == []
    assert youtube.readback_problems(video(privacyStatus="public", publishAt=None), None, AFTER) == []
    assert youtube.readback_problems(video(privacyStatus="private", publishAt=None), None, AFTER)


def test_another_channel_is_a_mismatch():
    v = video()
    v["snippet"]["channelId"] = "UC" + "x" * 22
    assert "the video is on another channel" in youtube.readback_problems(v, SLOT, BEFORE)


@pytest.mark.parametrize("drift, fragment", [
    ({"madeForKids": True}, "madeForKids"),
    ({"publishAt": "2099-10-14T13:30:00Z"}, "publishAt"),
    ({"privacyStatus": "unlisted"}, "privacyStatus"),
])
def test_publish_holds_when_the_channel_does_not_keep_what_was_asked(tmp_path, drift, fragment):
    story = Story.from_dict(story_dict())
    mp4 = tmp_path / "short.mp4"
    mp4.write_bytes(b"\0" * 1024)
    api = FakeYouTube(drift=drift)
    with pytest.raises(youtube.ReadbackMismatch, match=fragment):
        youtube.publish(story, mp4, NARRATOR, publish_at="2099-10-13T13:30:00Z", api=api, pause=lambda s: None)
    assert api.comments == [] and api.filed == []


def test_the_upload_survives_dropped_connections(tmp_path):
    from googleapiclient.errors import HttpError

    mp4 = tmp_path / "short.mp4"
    mp4.write_bytes(b"\0" * 1024)
    answers = [OSError("ssl eof"), HttpError(SimpleNamespace(status=503, reason="busy"), b""), (None, {"id": "v9"})]
    waits = []

    def chunk(num_retries):
        got = answers.pop(0)
        if isinstance(got, Exception):
            raise got
        return got

    api = SimpleNamespace(videos=lambda: SimpleNamespace(insert=lambda **kw: SimpleNamespace(next_chunk=chunk)))
    assert youtube._insert(api, mp4, {}, pause=waits.append) == "v9"
    assert waits == [2, 4]


def test_a_client_error_is_not_retried(tmp_path):
    from googleapiclient.errors import HttpError

    mp4 = tmp_path / "short.mp4"
    mp4.write_bytes(b"\0" * 1024)

    def chunk(num_retries):
        raise HttpError(SimpleNamespace(status=400, reason="bad"), b"")

    api = SimpleNamespace(videos=lambda: SimpleNamespace(insert=lambda **kw: SimpleNamespace(next_chunk=chunk)))
    with pytest.raises(HttpError):
        youtube._insert(api, mp4, {}, pause=lambda s: None)
