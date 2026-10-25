"""Measured public-batch counts; no interpolation, learning or content changes."""
from datetime import datetime, timedelta, timezone

from . import config, ledger, youtube

REFRESH = timedelta(hours=3)
EARLY_SNAPSHOTS = 64  # eight days at this cadence; retain these and one latest observation


def instant(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def refresh(batch, at=None, api=None):
    at = at or datetime.now(timezone.utc)
    data = ledger.load("batch-observations", {"videos": {}})
    if data.get("at") and at - instant(data["at"]) < REFRESH:
        return None
    jobs = {j["delivery"]["video_id"]: j for j in batch["jobs"]
            if j["stage"] == "public" and j.get("delivery", {}).get("video_id")}
    if not jobs:
        return None
    api = api or youtube.client()
    channel = youtube.identity(api)
    if channel["id"] != config.EXPECTED_CHANNEL_ID:
        raise ValueError("batch observations belong to another channel")
    published = {r.get("video_id"): r for r in ledger.published()}
    recorded, missing = 0, []
    for video in youtube.recent(api, channel):
        vid = video["id"]
        if vid not in jobs or video.get("status", {}).get("privacyStatus") != "public":
            continue
        when = video.get("snippet", {}).get("publishedAt")
        stats = video.get("statistics") or {}
        if not when or stats.get("viewCount") is None:
            missing.append(vid)
            continue
        age = (at - instant(when)).total_seconds() / 3600
        if age < 0:
            continue
        point = {"observed_at": at.isoformat(), "age_h": age, "views": int(stats["viewCount"]),
                 "likes": int(stats["likeCount"]) if stats.get("likeCount") is not None else None,
                 "comments": int(stats["commentCount"]) if stats.get("commentCount") is not None else None}
        job, row = jobs[vid], published.get(vid, {})
        rec = data["videos"].setdefault(vid, {"id": row.get("id"), "premise": job["premise"],
                 "format": row.get("format"), "source_sha": job.get("source_sha"),
                 "published_at": when, "observations": []})
        if instant(rec["published_at"]) != instant(when):
            raise ValueError("public publication time changed; reconcile observation ages")
        points = rec["observations"] + [point]
        rec["observations"] = points[:EARLY_SNAPSHOTS] + points[-1:] if len(points) > EARLY_SNAPSHOTS else points
        recorded += 1
    data.update(at=at.isoformat(), channel_id=channel["id"], source="YouTube owner Data API",
                scope="Actual public-batch counts at recorded ages; Analytics metrics are unknown here",
                missing_counts=missing)
    ledger.save("batch-observations", data)
    return {"recorded": recorded, "missing_counts": len(missing)}
