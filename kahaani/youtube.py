"""Identity-pinned YouTube publishing: upload private with the slot as publishAt (or make public at once when the
slot has passed), then read the video back and refuse to count it published unless its status is what was asked.

Every write is refused unless the OAuth token belongs to config.CHANNEL_ID (KC_CHANNEL_ID), so the pipeline can never
post to another channel; while it is unset nothing can be published at all. Every upload is declared not made for
kids, declares altered or synthetic content, and says in Hindi that the story is fiction told with AI pictures and
an AI voice. Uploads never notify subscribers (config.NOTIFY_SUBSCRIBERS). After the read-back the channel posts its
own CTA comment and adds the Short to its format's playlist when one is configured; both fail soft (the publish job
tries a pending one again on later runs). A video found already public on the channel is left public and reported as
such, never pulled back to a schedule. A read-back that still does not match after a few polls makes the video
private (no publishAt) before it is refused, so a wrong status never goes out on its own. The credential comes only
from the YOUTUBE_OAUTH_JSON environment variable and is never logged.
"""
from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path

from . import config, gate
from .spec import Story

DESCRIPTION_BYTES = 5000  # the API counts UTF-8 bytes, and a Devanagari letter is three of them
DISCLOSURE = "यह एक काल्पनिक कहानी है। इसके चित्र AI से बने हैं (Z-Image-Turbo) और आवाज़ AI की है ({voice})।"
VOICE_NAME = {"gemini-narrator": "Google Gemini TTS", "chatterbox-narrator-clone": "Chatterbox Multilingual"}
DEFAULT_TAGS = ("सन्नाटपुर", "सन्नाटपुर की रातें", "हिंदी कहानी", "रहस्यमयी कहानी", "90s गाँव", "पुरानी यादें",
                "hindi story", "sannatpur", "90s nostalgia")
SERIES_TAG = "#सन्नाटपुर"
# The channel's own first comment: an open-question ending asks its own question; every other ending asks this.
CTA = "आपके गाँव में भी कोई ऐसी चीज़ थी, जिसका कोई नियम था? नीचे लिखिए 👇"
SCOPES = ("https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube",
          "https://www.googleapis.com/auth/youtube.force-ssl",
          "https://www.googleapis.com/auth/yt-analytics.readonly")


class WrongChannel(RuntimeError):
    pass


class ReadbackMismatch(RuntimeError):
    """The uploaded video's status is not what was asked: never count it published."""


def client(service: str = "youtube", version: str = "v3"):
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    raw = os.environ.get("YOUTUBE_OAUTH_JSON") or ""
    if not raw:
        raise RuntimeError("no YouTube sign-in: YOUTUBE_OAUTH_JSON is not set")
    creds = Credentials.from_authorized_user_info(json.loads(raw))
    if not creds.valid:
        creds.refresh(Request())
    return build(service, version, credentials=creds, cache_discovery=False)


def analytics_client():
    """YouTube Analytics v2 on the same sign-in; raises when the token lacks the yt-analytics.readonly scope."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    raw = os.environ.get("YOUTUBE_OAUTH_JSON") or ""
    if not raw:
        raise RuntimeError("no YouTube sign-in: YOUTUBE_OAUTH_JSON is not set")
    info = json.loads(raw)
    scopes = info.get("scopes") or []
    if scopes and SCOPES[-1] not in scopes:
        raise PermissionError("the YouTube token has no yt-analytics.readonly scope (re-run the OAuth consent)")
    creds = Credentials.from_authorized_user_info(info)
    if not creds.valid:
        creds.refresh(Request())
    return build("youtubeAnalytics", "v2", credentials=creds, cache_discovery=False)


def check_identity(items: list[dict]) -> dict:
    """The channel the token signs in to, if and only if it is the configured one."""
    if not config.channel_id_ready():
        raise WrongChannel("the channel id is not configured (KC_CHANNEL_ID): refusing every write")
    if len(items) != 1 or items[0].get("id") != config.CHANNEL_ID:
        raise WrongChannel("signed in to the wrong channel: refusing every write")
    return items[0]


def identity(api) -> dict:
    return check_identity(api.channels().list(part="snippet,statistics,contentDetails", mine=True).execute()
                          .get("items", []))


def recent(api, channel: dict, limit: int = 50) -> list[dict]:
    uploads = channel["contentDetails"]["relatedPlaylists"]["uploads"]
    rows = api.playlistItems().list(part="contentDetails", playlistId=uploads, maxResults=limit).execute() \
        .get("items", [])
    ids = [r["contentDetails"]["videoId"] for r in rows]
    if not ids:
        return []
    return api.videos().list(part="snippet,status,statistics", id=",".join(ids)).execute().get("items", [])


def find(api, channel: dict, story_id: str) -> dict | None:
    hits = [v for v in recent(api, channel) if config.MARKER + story_id in (v["snippet"].get("tags") or [])]
    if len(hits) > 1:
        raise RuntimeError(f"{story_id} is on the channel twice: resolve by hand before publishing again")
    return hits[0] if hits else None


def hashtag(text: str) -> str:
    """#जादुईकहानी style: letters, vowel signs and digits only (Devanagari marks are not \\w in Python)."""
    return re.sub(r"[^0-9A-Za-z\u0900-\u097F]", "", text.replace("।", ""))


def description(story: Story, voice: dict) -> str:
    tags = [hashtag(h) for h in [SERIES_TAG] + story.hashtags + ["#shorts"]]
    lines = [story.description, "",
             DISCLOSURE.format(voice=VOICE_NAME.get(voice.get("engine"), "AI")),
             "इसके पात्र, जगहें और घटनाएँ कल्पना हैं; किसी असली व्यक्ति या घटना से इनका कोई संबंध नहीं है।", "",
             " ".join("#" + t for t in dict.fromkeys(tags) if t)]
    # YouTube rejects < and > in descriptions.
    text = "\n".join(lines).replace("<", "‹").replace(">", "›")
    if len(text.encode()) > DESCRIPTION_BYTES:
        raise ValueError(f"description is {len(text.encode())} bytes; YouTube allows {DESCRIPTION_BYTES}")
    return text


def tags(story: Story) -> list[str]:
    marker = config.MARKER + story.id
    out, total = [], len(marker) + 2
    for t in [*DEFAULT_TAGS, story.object_token, *(m.replace("-", " ") for m in story.motifs), config.NAME]:
        t = (t or "").replace("<", "").replace(">", "").replace(",", " ").strip()
        if not t or t in out or gate.mfk_metadata(t) or total + len(t) + 2 > 480:
            continue
        out.append(t)
        total += len(t) + 2
    return out + [marker]


STATUS = {"selfDeclaredMadeForKids": False, "containsSyntheticMedia": True, "embeddable": True,
          "publicStatsViewable": True}


def body(story: Story, voice: dict, publish_at: str | None) -> dict:
    """The videos.insert body: private, scheduled at publish_at when given. Refuses to build one that is not declared
    synthetic and not made for kids, or whose metadata reads as made for kids."""
    status = {"privacyStatus": "private", **STATUS}
    if publish_at:
        status["publishAt"] = publish_at
    fmt = config.FORMATS.get(story.format or config.FORMAT, config.FORMATS[config.FORMAT])
    out = {"snippet": {"title": story.title, "description": description(story, voice), "tags": tags(story),
                       "categoryId": fmt.category, "defaultLanguage": config.LANGUAGE,
                       "defaultAudioLanguage": config.LANGUAGE},
           "status": status}
    assert out["status"]["containsSyntheticMedia"] is True and out["status"]["selfDeclaredMadeForKids"] is False
    kids = gate.mfk_metadata(" ".join([story.title, out["snippet"]["description"], *out["snippet"]["tags"]]))
    if kids:
        raise ValueError(f"metadata reads as made for kids: {kids}")
    return out


def _instant(when: str | None) -> str | None:
    """RFC 3339 normalised to ...Z seconds, so 2026-10-24T13:30:00.000Z and +00:00 forms compare equal."""
    if not when:
        return None
    at = datetime.fromisoformat(when.replace("Z", "+00:00"))
    return at.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _released(when: str | None, now: datetime | None = None) -> bool:
    if not when:
        return True
    return datetime.fromisoformat(when.replace("Z", "+00:00")) <= (now or datetime.now(timezone.utc))


def readback_problems(video: dict, when: str | None, now: datetime | None = None) -> list[str]:
    """Where the uploaded video (videos.list snippet,status) differs from what was asked (empty = it matches): its
    channel, made for kids (both flags False), privacy (private until publishAt, public after), publishAt, and an
    upload YouTube failed or rejected. Ported from Pangaea Nights."""
    st = video.get("status", {})
    out = []
    if video.get("snippet", {}).get("channelId") != config.CHANNEL_ID:
        out.append("the video is on another channel")
    if st.get("madeForKids") is not False:
        out.append(f"madeForKids is {st.get('madeForKids')!r}, not False")
    if st.get("selfDeclaredMadeForKids") is not False:
        out.append(f"selfDeclaredMadeForKids is {st.get('selfDeclaredMadeForKids')!r}, not False")
    if _released(when, now):
        if st.get("privacyStatus") not in (("private", "public") if when else ("public",)):
            out.append(f"privacyStatus is {st.get('privacyStatus')!r} after the release time")
    elif st.get("privacyStatus") != "private":
        out.append(f"privacyStatus is {st.get('privacyStatus')!r}, not 'private' before release")
    if when and _instant(st.get("publishAt")) != _instant(when) and \
            not (_released(when, now) and st.get("privacyStatus") == "public"):
        out.append(f"publishAt is {st.get('publishAt')!r}, not {when!r}")
    if st.get("uploadStatus") in ("failed", "rejected", "deleted"):
        why = st.get("failureReason") or st.get("rejectionReason")
        out.append(f"uploadStatus is {st['uploadStatus']!r}{f' ({why})' if why else ''}")
    if "containsSyntheticMedia" in st and st["containsSyntheticMedia"] is not True:
        out.append("containsSyntheticMedia is not True")
    return out


def _insert(api, mp4: Path, request_body: dict, pause=time.sleep) -> str:
    """Resumable upload that survives 5xx answers and dropped connections (ported from Pangaea Nights: its second
    test upload died on ssl.SSLEOFError, and next_chunk resumes the same session)."""
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaFileUpload

    media = MediaFileUpload(str(mp4), mimetype="video/mp4", chunksize=4 * 1024 * 1024, resumable=True)
    request = api.videos().insert(part="snippet,status", body=request_body,
                                  notifySubscribers=config.NOTIFY_SUBSCRIBERS, media_body=media)
    response, errors = None, 0
    while response is None:
        try:
            _, response = request.next_chunk(num_retries=5)
        except HttpError as e:
            if e.resp.status in (500, 502, 503, 504) and errors < 8:
                errors += 1
                pause(min(60, 2 ** errors))
                continue
            raise
        except OSError:
            if errors >= 8:
                raise
            errors += 1
            pause(min(60, 2 ** errors))
    return response["id"]


def cta(story: Story) -> str:
    last = story.beats[-1].text.strip() if story.beats else ""
    if story.ending == "open-question" and last.endswith("?"):
        question = re.split(r"(?<=[।!?])\s+", last)[-1]
        return f"{question} 👇"
    return CTA


def first_comment(api, video_id: str, text: str) -> str:
    """Post the channel's own first comment once: 'posted', 'exists', or 'pending: <reason>' (YouTube may refuse
    comments on a still-private video). Never raises."""
    try:
        rows = api.commentThreads().list(part="snippet", videoId=video_id, maxResults=50,
                                         textFormat="plainText").execute().get("items", [])
        for r in rows:
            top = r["snippet"]["topLevelComment"]["snippet"]
            mine = top.get("authorChannelId", {}).get("value") == config.CHANNEL_ID
            if mine and top.get("textOriginal", top.get("textDisplay", "")).strip() == text:
                return "exists"
        api.commentThreads().insert(part="snippet", body={"snippet": {
            "videoId": video_id, "topLevelComment": {"snippet": {"textOriginal": text}}}}).execute()
        return "posted"
    except Exception as exc:  # fail soft: a missing comment never un-publishes a Short
        status = getattr(getattr(exc, "resp", None), "status", None)
        return f"pending: HTTP {status}" if status else f"pending: {type(exc).__name__}"


def add_to_playlist(api, video_id: str, playlist_id: str | None) -> str:
    """'added', 'exists', 'skipped: no playlist' or 'pending: <reason>'. Never raises."""
    if not playlist_id:
        return "skipped: no playlist"
    try:
        rows = api.playlistItems().list(part="contentDetails", playlistId=playlist_id, maxResults=50).execute() \
            .get("items", [])
        if any(r.get("contentDetails", {}).get("videoId") == video_id for r in rows):
            return "exists"
        api.playlistItems().insert(part="snippet", body={"snippet": {
            "playlistId": playlist_id, "resourceId": {"kind": "youtube#video", "videoId": video_id}}}).execute()
        return "added"
    except Exception as exc:
        status = getattr(getattr(exc, "resp", None), "status", None)
        return f"pending: HTTP {status}" if status else f"pending: {type(exc).__name__}"


def publish(story: Story, mp4: Path, voice: dict, publish_at: str | None = None, api=None, max_wait: int = 900,
            pause=time.sleep) -> dict:
    """Upload and schedule for publish_at (RFC 3339 UTC, in the future), or make public now when it is None."""
    refused = gate.voice_ok(voice)
    if refused:
        raise ValueError(refused)
    api = api or client()
    channel = identity(api)
    existing = find(api, channel, story.id)
    video_id = existing["id"] if existing else _insert(api, mp4, body(story, voice, publish_at), pause)
    deadline = time.monotonic() + max_wait
    while True:
        video = api.videos().list(part="snippet,status,processingDetails", id=video_id).execute()["items"][0]
        if video["snippet"]["channelId"] != config.CHANNEL_ID:
            raise WrongChannel("uploaded video is on another channel")
        status = video["status"]
        processing = video.get("processingDetails", {}).get("processingStatus")
        if status.get("uploadStatus") in ("failed", "rejected", "deleted") or processing in ("failed", "terminated"):
            why = status.get("rejectionReason") or status.get("failureReason")
            raise RuntimeError(f"YouTube rejected the upload: {why}")
        if status.get("uploadStatus") == "processed" or processing == "succeeded":
            break
        if time.monotonic() > deadline:
            raise RuntimeError("still processing; the next run will finish publishing it")
        pause(15)
    url = f"https://www.youtube.com/shorts/{video_id}"
    # containsSyntheticMedia is write-only in practice: videos.list omits it even though Studio shows "AI use".
    if existing and status.get("privacyStatus") == "public":
        # An earlier run made it public and died before the ledger heard: it is out, whatever slot was asked.
        when = None
        result = {"video_id": video_id, "url": url, "privacy": "public", "synthetic_declared": True,
                  "already_public": True,
                  "released_at": _instant(video["snippet"].get("publishedAt")) or _instant(datetime.now(
                      timezone.utc).isoformat())}
    elif publish_at:
        when = publish_at
        if status.get("privacyStatus") != "private" or _instant(status.get("publishAt")) != _instant(publish_at):
            api.videos().update(part="status", body={"id": video_id, "status": {
                "privacyStatus": "private", "publishAt": publish_at, **STATUS}}).execute()
        result = {"video_id": video_id, "url": url, "privacy": "scheduled", "publish_at": publish_at,
                  "synthetic_declared": True}
    else:
        when = None
        if status.get("privacyStatus") != "public":
            api.videos().update(part="status",
                                body={"id": video_id, "status": {"privacyStatus": "public", **STATUS}}).execute()
        result = {"video_id": video_id, "url": url, "privacy": "public", "synthetic_declared": True}
    # videos.list can report the old status for a while after an update.
    for wait in READBACK_WAITS:
        pause(wait)
        video = api.videos().list(part="snippet,status", id=video_id).execute()["items"][0]
        problems = readback_problems(video, when)
        if not problems:
            break
    else:
        kept = hold_private(api, video_id)
        raise ReadbackMismatch(f"read-back of {video_id} does not match ({kept}): " + "; ".join(problems))
    fmt = config.FORMATS.get(story.format or config.FORMAT, config.FORMATS[config.FORMAT])
    result["comment_text"] = cta(story)
    result["comment"] = first_comment(api, video_id, result["comment_text"])
    result["playlist"] = add_to_playlist(api, video_id, fmt.playlist_id)
    return result


def release(video_id: str, api=None, pause=time.sleep) -> dict:
    """Make a scheduled upload public now (the owner's release_now list), read back like publish()."""
    api = api or client()
    identity(api)
    items = api.videos().list(part="snippet,status", id=video_id).execute()["items"]
    if not items or items[0]["snippet"]["channelId"] != config.CHANNEL_ID:
        raise WrongChannel(f"{video_id} is not on the channel")
    if items[0]["status"].get("privacyStatus") != "public":
        api.videos().update(part="status",
                            body={"id": video_id, "status": {"privacyStatus": "public", **STATUS}}).execute()
    for wait in READBACK_WAITS:
        pause(wait)
        video = api.videos().list(part="snippet,status", id=video_id).execute()["items"][0]
        problems = readback_problems(video, None)
        if not problems:
            break
    else:
        kept = hold_private(api, video_id)
        raise ReadbackMismatch(f"read-back of {video_id} does not match ({kept}): " + "; ".join(problems))
    return {"privacy": "public", "released_at": _instant(datetime.now(timezone.utc).isoformat())}


READBACK_WAITS = (0, 5, 10, 20, 30)


def hold_private(api, video_id: str) -> str:
    """Make a video that failed its read-back private with no publishAt, so it never goes out on a wrong status."""
    try:
        api.videos().update(part="status", body={"id": video_id, "status": {"privacyStatus": "private",
                                                                            **STATUS}}).execute()
        return "made private"
    except Exception as exc:
        return f"could not make it private: {type(exc).__name__}"
