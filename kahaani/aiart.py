"""The paintings the paint jobs made for a story: collected, screened by the vision check, and turned into one picture
per beat. A refused cast shot falls back on its repaints (up to look.ALTERNATES, painted by the same paint job with
other seeds); a beat whose painting is missing or still refused is dropped and repeats the nearest earlier passing
one. Fiction has no archive to fall back on, so a story with too few passing paintings, or none for its hook, is
held.
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


def _paintings(art_dir: Path | None, story: str, beats: int):
    if not art_dir or not art_dir.is_dir():
        return
    for meta in sorted(art_dir.rglob("beat*.json")):
        try:
            info = json.loads(meta.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        image = meta.with_suffix(".png")
        if info.get("story") == story and 0 <= int(info.get("beat", -1)) < beats and image.exists():
            yield int(info["beat"]), int(info.get("alt") or 0), image


def collect(art_dir: Path | None, story: str, beats: int) -> dict[int, Path]:
    """Beat number -> painted file, for pictures painted for this story (a stale artifact never leaks in)."""
    return {beat: image for beat, alt, image in _paintings(art_dir, story, beats) if alt == 0}


def alternates(art_dir: Path | None, story: str, beats: int) -> dict[int, list[Path]]:
    """Beat number -> its repaints, in seed order."""
    found: dict[int, list[tuple[int, Path]]] = {}
    for beat, alt, image in _paintings(art_dir, story, beats):
        if alt:
            found.setdefault(beat, []).append((alt, image))
    return {b: [p for _, p in sorted(v)] for b, v in found.items()}


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


def prop_rate(report: list[dict]) -> float | None:
    """Share of cast shots whose final painting passed prop identity (None when the story has no cast shot)."""
    shots = [r for r in report if r.get("cast")]
    return sum(r.get("props_ok") is True and not r["rejected"] for r in shots) / len(shots) if shots else None


def pictures(found: dict[int, Path], texts: list[str], folder: Path, story: str, cast: str, ask,
             report: list[dict] | None = None, spares: dict[int, list[Path]] | None = None,
             who: dict[int, list[str]] | None = None, scenes: list[str] | None = None,
             hook_check: bool = True) -> list[Path]:
    """One screened, upscaled picture path per beat. who: beat -> the cast ids its painting should show (a cast shot
    must pass prop identity); spares: beat -> repaints tried in order when a painting is refused; scenes: the planned
    picture per beat, which the editor checks the painting against; hook_check=False skips the first picture's
    subject-share check (the wordless format opens on a wide establishing shot)."""
    folder.mkdir(parents=True, exist_ok=True)
    who, spares = who or {}, spares or {}
    scene = (lambda i: scenes[i] if scenes and i < len(scenes) else "")
    order = sorted(found)
    items = []
    for i in order:
        target = folder / f"beat{i:02d}.jpg"
        _prepare(found[i], target)
        items.append((target, texts[i], vision.expected(who.get(i, [])), scene(i)))
    verdicts = vision.judge(items, story, cast, ask) if items else []
    passed = set()
    rows = []
    for i, verdict in zip(order, verdicts):
        why = vision.rejected(verdict, bool(who.get(i)), hook_check and i == 0, scene(i))
        tried = 0
        for spare in spares.get(i, [])[:look_alternates()] if why else []:
            tried += 1
            candidate = folder / f"beat{i:02d}-alt{tried}.jpg"
            _prepare(spare, candidate)
            again = vision.judge([(candidate, texts[i], vision.expected(who.get(i, [])), scene(i))], story, cast,
                                 ask)[0]
            again_why = vision.rejected(again, bool(who.get(i)), hook_check and i == 0, scene(i))
            log.warning("painting for beat %d refused (%s); repaint %d %s", i + 1, why, tried,
                        "passed" if again_why is None else "refused too")
            verdict, why = again, again_why
            if why is None:
                candidate.replace(folder / f"beat{i:02d}.jpg")
                break
        rows.append({"beat": i + 1, "shows": verdict.get("shows"), "rejected": why, "cast": who.get(i, []),
                     "props_ok": verdict.get("props_ok"), "repaints_tried": tried})
        if why is None:
            passed.add(i)
        else:
            log.warning("painting for beat %d dropped: %s", i + 1, why)
    if report is not None:
        report.extend(rows)
    return [folder / f"beat{i:02d}.jpg" for i in assign(passed, len(texts))]


def look_alternates() -> int:
    from . import look

    return look.ALTERNATES
