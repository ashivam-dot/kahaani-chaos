"""The never-stop buffer's files: each finished Short (MP4, story.json, timing.json) waits as the assets of a draft
GitHub Release tagged ready-<id>, through the gh CLI and the workflow's GITHUB_TOKEN. Drafts stay invisible to the
public until deleted, so a story is never seen before its slot.
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from . import config

FILES = ("short.mp4", "story.json", "timing.json")


def tag(story_id: str) -> str:
    return f"ready-{story_id}"


def _gh(*args: str, run=subprocess.run) -> str:
    done = run(["gh", *args, "--repo", config.REPO], capture_output=True, text=True, check=False)
    if done.returncode != 0:
        raise RuntimeError(f"gh {args[0]} {args[1]} failed: {(done.stderr or done.stdout).strip()[-300:]}")
    return done.stdout


def put(story_id: str, folder: Path, title: str, run=subprocess.run) -> str:
    files = [str(folder / f) for f in FILES]
    missing = [f for f in files if not Path(f).exists()]
    if missing:
        raise FileNotFoundError(f"cannot store {story_id}: missing {missing}")
    _gh("release", "create", tag(story_id), *files, "--draft", "--title", f"ready: {title}",
        "--notes", "A finished Short waiting for its slot; deleted once it is published.", run=run)
    return tag(story_id)


def fetch(story_id: str, folder: Path, run=subprocess.run) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    _gh("release", "download", tag(story_id), "--dir", str(folder), "--clobber", run=run)
    missing = [f for f in FILES if not (folder / f).exists()]
    if missing:
        raise FileNotFoundError(f"release {tag(story_id)} lacks {missing}")
    return folder


def drop(story_id: str, run=subprocess.run) -> None:
    _gh("release", "delete", tag(story_id), "--yes", run=run)
