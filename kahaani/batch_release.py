"""Release adapter for exact, reviewed Sannatpur preview artifacts. No gates are waived."""
import json
import os
from dataclasses import asdict
from pathlib import Path

from . import cli, config, gate, ledger, vision
from .spec import Story

REPO = "ashivam-dot/kahaani-chaos"
WORKFLOW = "run.yml"
CHANNEL_ID = config.EXPECTED_CHANNEL_ID


def paused():
    return os.environ.get("PAUSED", "true").lower() != "false"


def artifact_names(job):
    return [f"short-{job['run_id']}"]


def _read(folder, name):
    found = list(folder.rglob(name))
    if len(found) != 1:
        raise ValueError(f"expected one {name}, found {len(found)}")
    return json.loads(found[0].read_text())


def validate(job, folder):
    health = _read(folder, "dry-produce-health.json")
    if not health.get("made") or health.get("held") or health.get("error") or health.get("ok") is not True:
        raise ValueError("preview did not make a finished passing Short")
    if not health.get("picture_editor") or (not vision.LOCAL_TRUSTED and
                                            any(m != "gemini" for m in health["picture_editor"])):
        raise ValueError("preview used an uncalibrated picture editor")
    story_path = next(folder.rglob("story.json"))
    story = Story.load(story_path)
    if story.premise != job["premise"]:
        raise ValueError("artifact premise differs from the batch intent")
    models = story.writer.get("models") or []
    if not models or any(not m.startswith("gemini") for m in models):
        raise ValueError(cli.LOCAL_HOLD)
    history = [r for r in ledger.history() if r.get("id") != story.id]
    problems = gate.check(asdict(story), cli.premise_of(story), history, rotation=True)
    timing, stats = _read(folder, "timing.json"), _read(folder, "render.json")
    checks = _read(folder, "picture-checks.json")
    problems += gate.runtime_problems(stats.get("runtime")) + gate.timing_problems(story, timing)
    if why := gate.voice_ok(timing.get("voice")):
        problems.append(why)
    problems += checks.get("problems", ["missing picture and sound verdict"])
    if problems:
        raise ValueError("; ".join(problems))
    videos = list(folder.rglob("short.mp4"))
    if len(videos) != 1:
        raise ValueError("no unique finished MP4")
    return videos[0], {"channel": "Sannatpur Ki Raatein", "audience": "Hindi, 13+, general audience",
                       "world": "A fictional north-Indian village in 1996; adult Prabhat remembers his youth.",
                       "story": asdict(story), "picture_observations": _read(folder, "pictures.json"),
                       "disclosure": "AI चित्र और आवाज़ · काल्पनिक कहानी", "expected_narrator": "adult male Prabhat"}


def taken():
    return {r["slot"] for r in ledger.published() if r.get("slot")}


def release_ready(data, job):
    before = data["jobs"][:data["jobs"].index(job)]
    if any(j["stage"] not in ("public", "scheduled") for j in before):
        return False
    # Restore a real two-episode reviewed buffer before the first new-format release.
    return sum(j["stage"] in ("reviewed", "upload_intent", "public", "scheduled") for j in data["jobs"]) >= 2


def poll_delivery(job):
    from . import youtube

    if config.CHANNEL_ID != CHANNEL_ID:
        raise ValueError("configured channel does not match Sannatpur")
    api = youtube.client()
    youtube.identity(api)
    rows = api.videos().list(part="snippet,status", id=job["delivery"]["video_id"]).execute()["items"]
    return rows[0] if len(rows) == 1 else {}


def publish(job, folder, when):
    from . import youtube

    if config.CHANNEL_ID != config.EXPECTED_CHANNEL_ID:
        raise ValueError("Sannatpur's configured channel differs from its pinned identity")
    validate(job, folder)  # refresh rotation/variation immediately before touching the channel
    story = Story.load(next(folder.rglob("story.json")))
    timing = _read(folder, "timing.json")
    result = youtube.publish(story, next(folder.rglob("short.mp4")), timing["voice"], publish_at=when)
    api = youtube.client()
    youtube.identity(api)
    video = api.videos().list(part="snippet,status", id=result["video_id"]).execute()["items"][0]
    problems = youtube.readback_problems(video, None if result["privacy"] == "public" else when)
    if problems:
        raise youtube.ReadbackMismatch("final batch readback: " + "; ".join(problems))
    st = video["status"]
    result["owner_readback"] = {"channel_id": video["snippet"]["channelId"],
                                **{k: st.get(k) for k in ("privacyStatus", "publishAt", "madeForKids",
                                                         "selfDeclaredMadeForKids", "containsSyntheticMedia",
                                                         "uploadStatus")}}
    released = result.get("released_at") or when or ledger.now()
    ledger.record_publish({**cli.summary(story), "slot": when, "published_at": released,
                           "voice": timing["voice"]["engine"], "batch_run": job["run_id"],
                           "av_review_sha256": job["review"]["video_sha256"], **result})
    return result
