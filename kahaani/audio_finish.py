"""Measured two-pass audio finishing; an explicit preview repair never changes video or narration timing."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import re
import subprocess


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def normalize(source: Path, target: Path, *, video: bool = False) -> dict:
    """Measure the complete finite mix, then normalize from those measurements with AAC peak headroom."""
    base = "loudnorm=I=-14:TP=-2:LRA=9"
    measured = subprocess.run([
        "ffmpeg", "-hide_banner", "-nostats", "-i", str(source), "-vn", "-af",
        base + ":print_format=json", "-f", "null", "-"], capture_output=True, text=True,
        check=True, timeout=180).stderr
    stats = json.JSONDecoder().raw_decode(measured[measured.rfind("{"):])[0]
    keys = (("measured_I", "input_i"), ("measured_TP", "input_tp"),
            ("measured_LRA", "input_lra"), ("measured_thresh", "input_thresh"), ("offset", "target_offset"))
    if any(not math.isfinite(float(stats[value])) for _, value in keys):
        raise ValueError("audio finishing cannot normalize a silent or unmeasurable mix")
    filters = base + ":linear=true:" + ":".join(f"{key}={stats[value]}" for key, value in keys)
    command = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", "-i", str(source)]
    command += ["-map", "0:v:0", "-map", "0:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k"] if video \
        else ["-vn", "-c:a", "pcm_s16le"]
    command += ["-af", filters, "-ar", "48000", "-ac", "2"]
    if video:
        command += ["-movflags", "+faststart"]
    subprocess.run([*command, str(target)], capture_output=True, check=True, timeout=180)
    return {"measurement": stats, "filter": filters}


def video_digest(path: Path) -> str:
    return subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(path),
                           "-map", "0:v:0", "-c:v", "copy", "-f", "hash", "-hash", "sha256", "-"],
                          capture_output=True, text=True, check=True, timeout=120).stdout.strip()


def finish_preview(job: dict, folder: Path) -> None:
    """Repair only an explicitly hash-bound audio-only hold. The complete new MP4 still needs AV approval."""
    intent = job.get("audio_finish")
    if not intent:
        return
    from . import compose, gate
    from .spec import Story

    def one(name):
        files = list(folder.rglob(name))
        if len(files) != 1:
            raise ValueError(f"audio repair expected one {name}")
        return files[0]

    mp4 = one("short.mp4")
    receipt_path = mp4.parent / "audio-finish.json"
    if receipt_path.exists():
        receipt = json.loads(receipt_path.read_text())
        if receipt.get("source_files") != intent.get("source_files") or digest(mp4) != receipt.get("output_sha256"):
            raise ValueError("audio repair receipt differs from this media or intent")
        return
    required = {"short.mp4", "story.json", "timing.json", "pictures.json", "picture-checks.json",
                "dry-produce-health.json"}
    if set(intent.get("source_files", {})) != required:
        raise ValueError("audio repair lacks its complete original media/report binding")
    for name, expected in intent["source_files"].items():
        if digest(one(name)) != expected:
            raise ValueError(f"audio repair original {name} differs from the reviewed hold")
    health_path, checks_path = one("dry-produce-health.json"), one("picture-checks.json")
    health, checks = json.loads(health_path.read_text()), json.loads(checks_path.read_text())
    failures = checks.get("problems")
    level_failure = (r"(?:integrated loudness -?\d+(?:\.\d+)? LUFS, needs "
                     + re.escape(f"{compose.LUFS[0]:.0f} to {compose.LUFS[1]:.0f}")
                     + r"|true peak -?\d+(?:\.\d+)? dBTP, needs at most " + re.escape(str(compose.TRUE_PEAK)) + ")")
    if health.get("dry") is not True or health.get("ok") is not True or health.get("made") \
            or health.get("error") or not health.get("held") \
            or not failures or not all(re.fullmatch(level_failure, x) for x in failures):
        raise ValueError("audio finishing accepts only an otherwise passing audio-level hold")
    story = Story.load(one("story.json"))
    timing = json.loads(one("timing.json").read_text())
    if story.premise != job["premise"] or gate.timing_problems(story, timing) or gate.voice_ok(timing.get("voice")):
        raise ValueError("audio repair story, timing or narration is not eligible")
    frames = math.ceil((timing["duration"] + compose.END_CARD) * compose.FPS)
    if checks.get("frames") != frames or compose.count_frames(mp4) != frames:
        raise ValueError("audio repair cannot correct a video frame-count defect")
    before = video_digest(mp4)
    temporary = mp4.with_name("audio-finish-tmp.mp4")
    try:
        normalization = normalize(mp4, temporary, video=True)
        sound = compose.loudness(temporary)
        bed = compose.bed_level(checks.get("levels"), sound)
        problems = compose.audio_problems(sound, bed)
        if problems or compose.count_frames(temporary) != frames or video_digest(temporary) != before:
            raise ValueError("audio finishing failed unchanged sound/video gates: " + "; ".join(problems))
        runtime = compose.length(temporary)
        if gate.runtime_problems(runtime):
            raise ValueError("audio finishing changed the valid runtime")
        receipt = {"source_run": job["run_id"], "source_files": intent["source_files"],
                   "source_health": health, "source_picture_checks": checks, "video_bitstream_sha256": before,
                   "output_sha256": digest(temporary), "loudness": sound, "bed_lufs": bed,
                   "normalization": normalization, "requires_new_complete_av_review": True}
        temporary.replace(mp4)
        receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
        checks = {**checks, "problems": [], "loudness": sound, "bed_lufs": bed, "audio_finish": "audio-finish.json"}
        checks_path.write_text(json.dumps(checks, ensure_ascii=False, indent=2) + "\n")
        voice = {k: timing["voice"].get(k) for k in ("engine", "identity", "served_model", "wpm", "coverage", "tempo")}
        stats = {"duration": round(timing["duration"] + compose.END_CARD, 2), "frames": frames,
                 "pictures": len(story.beats), "fps": compose.FPS, "size": [compose.W, compose.H],
                 "runtime": runtime, "voice": voice}
        (mp4.parent / "render.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2) + "\n")
        health = {k: v for k, v in health.items() if k != "held"}
        health["made"] = {"id": story.id, "title": story.title, "duration": stats["duration"],
                          "voice": voice["engine"], "wpm": voice["wpm"]}
        health["steps"] += ["Explicit hash-bound two-pass audio repair; original video bitstream unchanged"]
        health_path.write_text(json.dumps(health, ensure_ascii=False, indent=2) + "\n")
    finally:
        temporary.unlink(missing_ok=True)
