"""Identity-pinned YouTube publishing: upload private with the slot as publishAt (or make public at once when the
slot has passed), then verify.

Every write is refused unless the OAuth token belongs to config.CHANNEL_ID (KC_CHANNEL_ID), so the pipeline can never
post to another channel; while it is unset nothing can be published at all. Every upload is declared not made for
kids, declares altered or synthetic content, and says in Hindi that the story is fiction told with AI pictures and
an AI voice. The credential comes only from the YOUTUBE_OAUTH_JSON environment variable and is never logged.
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

from . import config, gate
from .spec import Story

DESCRIPTION_BYTES = 5000  # the API counts UTF-8 bytes, and a Devanagari letter is three of them
DISCLOSURE = "यह एक काल्पनिक कहानी है। इसके चित्र AI से बने हैं (Z-Image-Turbo) और आवाज़ AI की है ({voice})।"
VOICE_NAME = {"gemini-narrator": "Google Gemini TTS", "chatterbox-narrator-clone": "Chatterbox Multilingual"}
DEFAULT_TAGS = ("हिंदी कहानी", "जादुई कहानी", "रहस्यमयी कहानी", "hindi story", "kahani", "twist story")


class WrongChannel(RuntimeError):
    pass


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
    tags = [hashtag(h) for h in story.hashtags + ["#shorts"]]
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
    for t in [*DEFAULT_TAGS, *(m.replace("-", " ") for m in story.motifs), config.NAME]:
        t = t.replace("<", "").replace(">", "").replace(",", " ").strip()
        if not t or t in out or total + len(t) + 2 > 480:
            continue
        out.append(t)
        total += len(t) + 2
    return out + [marker]


STATUS = {"selfDeclaredMadeForKids": False, "containsSyntheticMedia": True, "embeddable": True,
          "publicStatsViewable": True}


def body(story: Story, voice: dict, publish_at: str | None) -> dict:
    """The videos.insert body: private, scheduled at publish_at when given."""
    status = {"privacyStatus": "private", **STATUS}
    if publish_at:
        status["publishAt"] = publish_at
    return {"snippet": {"title": story.title, "description": description(story, voice), "tags": tags(story),
                        "categoryId": config.CATEGORY, "defaultLanguage": config.LANGUAGE,
                        "defaultAudioLanguage": config.LANGUAGE},
            "status": status}


def publish(story: Story, mp4: Path, voice: dict, publish_at: str | None = None, api=None, max_wait: int = 900,
            pause=time.sleep) -> dict:
    """Upload and schedule for publish_at (RFC 3339 UTC, in the future), or make public now when it is None."""
    refused = gate.voice_ok(voice)
    if refused:
        raise ValueError(refused)
    api = api or client()
    channel = identity(api)
    existing = find(api, channel, story.id)
    if existing:
        video_id = existing["id"]
    else:
        from googleapiclient.http import MediaFileUpload

        media = MediaFileUpload(str(mp4), mimetype="video/mp4", chunksize=4 * 1024 * 1024, resumable=True)
        request = api.videos().insert(part="snippet,status", body=body(story, voice, publish_at),
                                      notifySubscribers=True, media_body=media)
        response = None
        while response is None:
            _, response = request.next_chunk(num_retries=3)
        video_id = response["id"]
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
    if publish_at:
        if status.get("publishAt") != publish_at and status.get("privacyStatus") != "public":
            api.videos().update(part="status", body={"id": video_id, "status": {
                "privacyStatus": "private", "publishAt": publish_at, **STATUS}}).execute()
            status = api.videos().list(part="status", id=video_id).execute()["items"][0]["status"]
        if not status.get("publishAt") and status.get("privacyStatus") != "public":
            raise RuntimeError(f"video {video_id} was not scheduled")
        return {"video_id": video_id, "url": url, "privacy": "scheduled", "publish_at": publish_at,
                "synthetic_declared": True}
    if status.get("privacyStatus") != "public":
        api.videos().update(part="status",
                            body={"id": video_id, "status": {"privacyStatus": "public", **STATUS}}).execute()
    # videos.list can report the old privacy for a while after the update.
    for wait in (0, 5, 10, 20, 30):
        pause(wait)
        final = api.videos().list(part="status", id=video_id).execute()["items"][0]
        if final["status"]["privacyStatus"] == "public":
            break
    else:
        raise RuntimeError(f"video {video_id} did not go public ({final['status']['privacyStatus']})")
    # containsSyntheticMedia is write-only in practice: videos.list omits it even though Studio shows "AI use: Yes".
    return {"video_id": video_id, "url": url, "privacy": "public", "synthetic_declared": True}
