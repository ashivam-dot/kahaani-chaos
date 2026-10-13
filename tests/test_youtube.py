from types import SimpleNamespace

import pytest

from kahaani import config, youtube
from kahaani.spec import Story

from .conftest import CHANNEL, story_dict

NARRATOR = {"engine": "gemini-narrator", "identity": "narrator"}


class Call:
    def __init__(self, value):
        self.value = value

    def execute(self):
        return self.value() if callable(self.value) else self.value


class FakeYouTube:
    """Just enough of the YouTube Data API client for publish(): one channel, its uploads, insert and update."""

    def __init__(self, channel=CHANNEL, uploads=()):
        self.channel = channel
        self.store = {v["id"]: v for v in uploads}
        self.inserted, self.updated = [], []

    def channels(self):
        item = {"id": self.channel, "contentDetails": {"relatedPlaylists": {"uploads": "UU1"}}}
        return SimpleNamespace(list=lambda **kw: Call({"items": [item]}))

    def playlistItems(self):
        items = [{"contentDetails": {"videoId": v}} for v in self.store]
        return SimpleNamespace(list=lambda **kw: Call({"items": items}))

    def videos(self):
        return SimpleNamespace(list=self._list, insert=self._insert, update=self._update)

    def _list(self, part, id, **kw):
        return Call(lambda: {"items": [self.store[i] for i in id.split(",") if i in self.store]})

    def _insert(self, part, body, notifySubscribers, media_body):
        self.inserted.append(body)
        self.store["vid1"] = {"id": "vid1", "snippet": {"channelId": self.channel, "tags": body["snippet"]["tags"]},
                              "status": {**body["status"], "uploadStatus": "processed"}}
        return SimpleNamespace(next_chunk=lambda num_retries: (None, {"id": "vid1"}))

    def _update(self, part, body):
        self.updated.append(body)
        self.store[body["id"]]["status"].update(body["status"])
        return Call({})


@pytest.fixture
def story():
    return Story.from_dict(story_dict())


@pytest.fixture
def mp4(tmp_path):
    path = tmp_path / "short.mp4"
    path.write_bytes(b"\0" * 1024)
    return path


@pytest.fixture
def pinned(monkeypatch):
    monkeypatch.setattr(config, "CHANNEL_ID", CHANNEL)


def test_the_expected_channel_id_is_well_formed(monkeypatch):
    assert not config.channel_id_ready()
    monkeypatch.setattr(config, "CHANNEL_ID", CHANNEL)
    assert config.channel_id_ready() and CHANNEL == "UCX-96TVtOBCEkDMloHuYAHw"


def test_every_write_is_refused_without_a_channel_id(story, mp4):
    api = FakeYouTube()
    with pytest.raises(youtube.WrongChannel):
        youtube.publish(story, mp4, NARRATOR, api=api)
    assert api.inserted == []


def test_every_write_is_refused_on_another_channel(pinned, story, mp4):
    api = FakeYouTube(channel="UC" + "x" * 22)
    with pytest.raises(youtube.WrongChannel):
        youtube.publish(story, mp4, NARRATOR, api=api)
    assert api.inserted == []


def test_only_the_narrator_voice_is_published(pinned, story, mp4):
    with pytest.raises(ValueError):
        youtube.publish(story, mp4, {"engine": "chatterbox-builtin", "identity": "builtin"}, api=FakeYouTube())


def test_upload_body(story):
    body = youtube.body(story, NARRATOR, "2026-10-13T07:00:00Z")
    status, snippet = body["status"], body["snippet"]
    assert status == {"privacyStatus": "private", "publishAt": "2026-10-13T07:00:00Z", "selfDeclaredMadeForKids": False,
                      "containsSyntheticMedia": True, "embeddable": True, "publicStatsViewable": True}
    assert snippet["categoryId"] == "24" and snippet["defaultLanguage"] == snippet["defaultAudioLanguage"] == "hi"
    assert snippet["title"] == story.title
    assert snippet["tags"][-1] == config.MARKER + story.id
    text = snippet["description"]
    assert "काल्पनिक कहानी" in text and "AI से बने" in text and "Google Gemini TTS" in text
    assert "किसी असली व्यक्ति या घटना से" in text and "#shorts" in text and "#जादुईकहानी" in text
    assert "publishAt" not in youtube.body(story, NARRATOR, None)["status"]


def test_scheduled_publish(pinned, story, mp4):
    api = FakeYouTube()
    result = youtube.publish(story, mp4, NARRATOR, publish_at="2026-10-13T07:00:00Z", api=api, pause=lambda s: None)
    assert result == {"video_id": "vid1", "url": "https://www.youtube.com/shorts/vid1", "privacy": "scheduled",
                      "publish_at": "2026-10-13T07:00:00Z", "synthetic_declared": True}
    assert api.inserted[0]["status"]["publishAt"] == "2026-10-13T07:00:00Z" and api.updated == []


def test_immediate_publish_goes_public(pinned, story, mp4):
    api = FakeYouTube()
    result = youtube.publish(story, mp4, NARRATOR, api=api, pause=lambda s: None)
    assert result["privacy"] == "public"
    assert api.updated[0]["status"]["privacyStatus"] == "public"
    assert api.updated[0]["status"]["containsSyntheticMedia"] is True


def test_an_upload_already_on_the_channel_is_not_uploaded_again(pinned, story, mp4):
    existing = {"id": "old", "snippet": {"channelId": CHANNEL, "tags": [config.MARKER + story.id]},
                "status": {"privacyStatus": "private", "uploadStatus": "processed"}}
    api = FakeYouTube(uploads=[existing])
    result = youtube.publish(story, mp4, NARRATOR, publish_at="2026-10-13T07:00:00Z", api=api, pause=lambda s: None)
    assert api.inserted == [] and result["video_id"] == "old"
    assert api.updated[0]["status"]["publishAt"] == "2026-10-13T07:00:00Z"


def test_the_credential_comes_only_from_the_environment():
    with pytest.raises(RuntimeError, match="YOUTUBE_OAUTH_JSON is not set"):
        youtube.client()
