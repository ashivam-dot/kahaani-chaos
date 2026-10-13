"""The paintings the paint jobs made for a story: collected, screened by the vision check, and turned into one picture
per beat. A beat whose painting is missing or refused repeats the nearest earlier passing one. Fiction has no archive
to fall back on, so a story with too few passing paintings, or none for its hook, is held.
"""
from __future__ import annotations

import json
import logging
import math
from pathlib import Path

from . import vision

log = logging.getLogger("kahaani.aiart")

MIN_SHARE = 0.7
# The paint jobs render 576x1024; the plate is cut from it with room for camera moves.
UPSCALE = (1152, 2048)


class PictureHold(RuntimeError):
    """Too few paintings passed: hold the story."""


def collect(art_dir: Path | None, story: str, beats: int) -> dict[int, Path]:
    """Beat number -> painted file, for pictures painted for this story (a stale artifact never leaks in)."""
    found: dict[int, Path] = {}
    if not art_dir or not art_dir.is_dir():
        return found
    for meta in sorted(art_dir.rglob("beat*.json")):
        try:
            info = json.loads(meta.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        image = meta.with_suffix(".png")
        if info.get("story") == story and 0 <= int(info.get("beat", -1)) < beats and image.exists():
            found[int(info["beat"])] = image
    return found


def _prepare(source: Path, target: Path) -> None:
    from PIL import Image, ImageFilter

    image = Image.open(source).convert("RGB")
    if image.size != UPSCALE:
        image = image.resize(UPSCALE, Image.Resampling.LANCZOS).filter(
            ImageFilter.UnsharpMask(radius=2, percent=60, threshold=2))
    image.save(target, quality=94)


def assign(passed: set[int], beats: int) -> list[int]:
    """The painting each beat shows: its own when it passed, else the nearest earlier one that did. Raises PictureHold
    when fewer than MIN_SHARE of the beats passed or the hook's painting did not."""
    need = math.ceil(MIN_SHARE * beats)
    if len(passed) < need or 0 not in passed:
        raise PictureHold(f"hold: only {len(passed)} of {beats} paintings passed (need {need} and the hook's)")
    out: list[int] = []
    for i in range(beats):
        out.append(i if i in passed else out[-1])
    return out


def pictures(found: dict[int, Path], texts: list[str], folder: Path, story: str, cast: str, ask,
             report: list[dict] | None = None) -> list[Path]:
    """One screened, upscaled picture path per beat."""
    folder.mkdir(parents=True, exist_ok=True)
    order = sorted(found)
    items = []
    for i in order:
        target = folder / f"beat{i:02d}.jpg"
        _prepare(found[i], target)
        items.append((target, texts[i]))
    verdicts = vision.judge(items, story, cast, ask) if items else []
    passed = set()
    for i, (path, _), verdict in zip(order, items, verdicts):
        why = vision.rejected(verdict)
        if report is not None:
            report.append({"beat": i + 1, "shows": verdict.get("shows"), "rejected": why})
        if why is None:
            passed.add(i)
        else:
            log.warning("painting for beat %d refused: %s", i + 1, why)
    return [folder / f"beat{i:02d}.jpg" for i in assign(passed, len(texts))]
