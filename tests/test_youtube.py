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
    """Just enough of the YouTube Data API client for publish(): one channel, its uploads, insert and update, comment
    threads and playlist items. `drift` is applied to the stored status after every write (a channel that does not
    keep what was asked)."""

    def __init__(self, channel=CHANNEL, uploads=(), drift=None, comments_fail=False):
        self.channel = channel
        self.store = {v["id"]: v for v in uploads}
        self.inserted, self.updated, self.comments, self.filed = [], [], [], []
        self.playlists = {}
        self.drift, self.comments_fail = drift or {}, comments_fail

    def channels(self):
        item = {"id": self.channel, "contentDetails": {"relatedPlaylists": {"uploads": "UU1"}}}
        return SimpleNamespace(list=lambda **kw: Call({"items": [item]}))

    def playlistItems(self):
        def listing(playlistId, **kw):
            ids = list(self.store) if playlistId == "UU1" else self.playlists.get(playlistId, [])
            return Call({"items": [{"contentDetails": {"videoId": v}} for v in ids]})

        def insert(part, body):
            snip = body["snippet"]
            self.filed.append(snip)
            self.playlists.setdefault(snip["playlistId"], []).append(snip["resourceId"]["videoId"])
            return Call({})

        return SimpleNamespace(list=listing, insert=insert)

    def commentThreads(self):
        def listing(videoId, **kw):
            return Call({"items": [{"snippet": {"topLevelComment": {"snippet": {
                "authorChannelId": {"value": self.channel}, "textOriginal": c}}}} for v, c in self.comments
                if v == videoId]})

        def insert(part, body):
            if self.comments_fail:
                raise RuntimeError("comments are disabled")
            snip = body["snippet"]
            self.comments.append((snip["videoId"], snip["topLevelComment"]["snippet"]["textOriginal"]))
            return Call({})

        return SimpleNamespace(list=listing, insert=insert)

    def videos(self):
        return SimpleNamespace(list=self._list, insert=self._insert, update=self._update)

    def _list(self, part, id, **kw):
        return Call(lambda: {"items": [self.store[i] for i in id.split(",") if i in self.store]})

    def _insert(self, part, body, notifySubscribers, media_body):
        self.inserted.append({**body, "notify": notifySubscribers})
        status = {k: v for k, v in body["status"].items() if k != "containsSyntheticMedia"}
        self.store["vid1"] = {"id": "vid1", "snippet": {"channelId": self.channel, "tags": body["snippet"]["tags"]},
                              "status": {**status, "madeForKids": False, "uploadStatus": "processed", **self.drift}}
        return SimpleNamespace(next_chunk=lambda num_retries: (None, {"id": "vid1"}))

    def _update(self, part, body):
        self.updated.append(body)
        status = {k: v for k, v in body["status"].items() if k != "containsSyntheticMedia"}
        self.store[body["id"]]["status"].update({**status, **self.drift})
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
    assert "#सन्नाटपुर" in snippet["description"].split("\n")[-1].split()[0]
    assert status == {"privacyStatus": "private", "publishAt": "2026-10-13T07:00:00Z", "selfDeclaredMadeForKids": False,
                      "containsSyntheticMedia": True, "embeddable": True, "publicStatsViewable": True}
    assert snippet["categoryId"] == "24" and snippet["defaultLanguage"] == snippet["defaultAudioLanguage"] == "hi"
    assert snippet["title"] == story.title
    assert snippet["tags"][-1] == config.MARKER + story.id and "सन्नाटपुर" in snippet["tags"]
    assert story.object_token in snippet["tags"]
    assert not any(youtube.gate.mfk_metadata(t) for t in snippet["tags"])
    text = snippet["description"]
    assert "काल्पनिक कहानी" in text and "AI से बने" in text and "Google Gemini TTS" in text
    assert "किसी असली व्यक्ति या घटना से" in text and "#shorts" in text and "#90sकीयादें" in text
    assert "publishAt" not in youtube.body(story, NARRATOR, None)["status"]


def test_scheduled_publish(pinned, story, mp4):
    api = FakeYouTube()
    result = youtube.publish(story, mp4, NARRATOR, publish_at="2026-10-13T07:00:00Z", api=api, pause=lambda s: None)
    assert result == {"video_id": "vid1", "url": "https://www.youtube.com/shorts/vid1", "privacy": "scheduled",
                      "publish_at": "2026-10-13T07:00:00Z", "synthetic_declared": True, "comment": "posted",
                      "comment_text": youtube.CTA, "playlist": "skipped: no playlist"}
    assert api.inserted[0]["status"]["publishAt"] == "2026-10-13T07:00:00Z" and api.updated == []
    assert api.inserted[0]["notify"] is False
    assert api.comments == [("vid1", youtube.CTA)]


def test_immediate_publish_goes_public(pinned, story, mp4):
    api = FakeYouTube()
    result = youtube.publish(story, mp4, NARRATOR, api=api, pause=lambda s: None)
    assert result["privacy"] == "public"
    assert api.updated[0]["status"]["privacyStatus"] == "public"
    assert api.updated[0]["status"]["containsSyntheticMedia"] is True


def test_release_makes_a_scheduled_upload_public_now(pinned, story, mp4):
    api = FakeYouTube()
    youtube.publish(story, mp4, NARRATOR, publish_at="2099-10-13T07:00:00Z", api=api, pause=lambda s: None)
    result = youtube.release("vid1", api=api, pause=lambda s: None)
    assert result["privacy"] == "public" and api.store["vid1"]["status"]["privacyStatus"] == "public"
    assert api.updated[-1]["status"]["containsSyntheticMedia"] is True
    with pytest.raises(youtube.WrongChannel):
        youtube.release("missing", api=api, pause=lambda s: None)


def test_an_upload_already_on_the_channel_is_not_uploaded_again(pinned, story, mp4):
    existing = {"id": "old", "snippet": {"channelId": CHANNEL, "tags": [config.MARKER + story.id]},
                "status": {"privacyStatus": "private", "uploadStatus": "processed", "madeForKids": False,
                           "selfDeclaredMadeForKids": False}}
    api = FakeYouTube(uploads=[existing])
    result = youtube.publish(story, mp4, NARRATOR, publish_at="2026-10-13T07:00:00Z", api=api, pause=lambda s: None)
    assert api.inserted == [] and result["video_id"] == "old"
    assert api.updated[0]["status"]["publishAt"] == "2026-10-13T07:00:00Z"


def test_the_short_is_filed_in_the_series_playlist_once(pinned, story, mp4, monkeypatch):
    monkeypatch.setenv("KC_PLAYLIST_MICRO", "PLmicro")
    api = FakeYouTube()
    first = youtube.publish(story, mp4, NARRATOR, publish_at="2099-10-13T13:30:00Z", api=api, pause=lambda s: None)
    again = youtube.publish(story, mp4, NARRATOR, publish_at="2099-10-13T13:30:00Z", api=api, pause=lambda s: None)
    assert (first["playlist"], again["playlist"]) == ("added", "exists")
    assert (first["comment"], again["comment"]) == ("posted", "exists")
    assert api.playlists == {"PLmicro": ["vid1"]} and len(api.inserted) == 1


def test_a_refused_comment_never_unpublishes(pinned, story, mp4):
    api = FakeYouTube(comments_fail=True)
    result = youtube.publish(story, mp4, NARRATOR, publish_at="2099-10-13T13:30:00Z", api=api, pause=lambda s: None)
    assert result["comment"].startswith("pending:") and result["privacy"] == "scheduled"


def test_an_open_question_ending_asks_its_own_question_below(story):
    story.ending = "open-question"
    story.beats[-1].text = "साइकिल फिर पुल पर खड़ी थी। आप होते तो पीछे भागते?"
    assert youtube.cta(story) == "आप होते तो पीछे भागते? 👇"
    story.ending = "loop-back"
    assert youtube.cta(story) == youtube.CTA


def test_made_for_kids_metadata_is_refused(story):
    story.description += " बच्चों के लिए कार्टून कहानी।"
    with pytest.raises(ValueError, match="made for kids"):
        youtube.body(story, NARRATOR, None)


def test_the_credential_comes_only_from_the_environment():
    with pytest.raises(RuntimeError, match="YOUTUBE_OAUTH_JSON is not set"):
        youtube.client()


def test_an_upload_already_public_is_left_public_and_reported(pinned, story, mp4):
    existing = {"id": "old", "snippet": {"channelId": CHANNEL, "tags": [config.MARKER + story.id],
                                         "publishedAt": "2026-10-12T13:31:04Z"},
                "status": {"privacyStatus": "public", "uploadStatus": "processed", "madeForKids": False,
                           "selfDeclaredMadeForKids": False}}
    api = FakeYouTube(uploads=[existing])
    result = youtube.publish(story, mp4, NARRATOR, publish_at="2099-10-13T13:30:00Z", api=api, pause=lambda s: None)
    assert result["already_public"] is True and result["privacy"] == "public"
    assert result["released_at"] == "2026-10-12T13:31:04Z" and api.updated == [] and api.inserted == []


def test_a_scheduled_publish_with_an_equal_instant_is_not_rewritten(pinned, story, mp4):
    existing = {"id": "old", "snippet": {"channelId": CHANNEL, "tags": [config.MARKER + story.id]},
                "status": {"privacyStatus": "private", "publishAt": "2099-10-13T13:30:00.000Z",
                           "uploadStatus": "processed", "madeForKids": False, "selfDeclaredMadeForKids": False}}
    api = FakeYouTube(uploads=[existing])
    youtube.publish(story, mp4, NARRATOR, publish_at="2099-10-13T13:30:00Z", api=api, pause=lambda s: None)
    assert api.updated == []


def test_a_read_back_that_lags_is_polled_until_it_matches(pinned, story, mp4):
    api = FakeYouTube()
    real = api._list
    lag = iter([{"privacyStatus": "private"}])

    def lagging(part, id, **kw):
        out = real(part, id, **kw)
        if part == "snippet,status":
            stale = next(lag, None)
            if stale:
                video = out.execute()["items"][0]
                return Call({"items": [{**video, "status": {**video["status"], **stale}}]})
        return out

    api._list = lagging
    waits = []
    result = youtube.publish(story, mp4, NARRATOR, api=api, pause=waits.append)
    assert result["privacy"] == "public" and len(waits) >= 2


def test_a_read_back_mismatch_makes_the_video_private(pinned, story, mp4):
    api = FakeYouTube(drift={"madeForKids": True})
    with pytest.raises(youtube.ReadbackMismatch, match="made private"):
        youtube.publish(story, mp4, NARRATOR, publish_at="2099-10-13T13:30:00Z", api=api, pause=lambda s: None)
    last = api.updated[-1]["status"]
    assert last["privacyStatus"] == "private" and "publishAt" not in last
    assert api.comments == []
