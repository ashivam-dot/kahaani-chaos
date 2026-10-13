import json

import pytest
from PIL import Image

from kahaani import aiart


def test_every_beat_shows_its_own_painting_when_all_pass():
    assert aiart.assign(set(range(5)), 5) == [0, 1, 2, 3, 4]


def test_a_refused_beat_repeats_the_nearest_earlier_passing_painting():
    assert aiart.assign({0, 1, 2, 4, 5, 6, 8, 9}, 10) == [0, 1, 2, 2, 4, 5, 6, 6, 8, 9]


def test_hold_below_seventy_percent():
    assert aiart.assign({0, 1, 2, 3, 4, 5, 6}, 10)
    with pytest.raises(aiart.PictureHold):
        aiart.assign({0, 1, 2, 3, 4, 5}, 10)


def test_hold_when_the_hook_fails():
    with pytest.raises(aiart.PictureHold, match="the hook"):
        aiart.assign(set(range(1, 12)), 12)


def paint(folder, story, beat, color=(40, 60, 90)):
    Image.new("RGB", (576, 1024), color).save(folder / f"beat{beat:02d}.png")
    (folder / f"beat{beat:02d}.json").write_text(json.dumps({"story": story, "beat": beat}))


def test_collect_ignores_other_stories(tmp_path):
    for i in range(3):
        paint(tmp_path, "kc-1", i)
    paint(tmp_path, "kc-old", 3)
    assert sorted(aiart.collect(tmp_path, "kc-1", 4)) == [0, 1, 2]
    assert aiart.collect(None, "kc-1", 4) == {}


def test_pictures_screens_and_falls_back(tmp_path):
    art = tmp_path / "art"
    art.mkdir()
    for i in range(10):
        if i != 3:
            paint(art, "kc-1", i)
    seen = []

    def ask(parts, schema):
        n = sum(1 for p in parts if isinstance(p, bytes))
        start = len(seen)
        seen.extend(range(n))
        return {"pictures": [{"n": k, "shows": "a well", "fits": True, "nudity": False, "sexual": False,
                              "gore": False, "malformed": start + k == 7, "text": False} for k in range(1, n + 1)]}

    report = []
    found = aiart.collect(art, "kc-1", 10)
    pics = aiart.pictures(found, list("abcdefghij"), tmp_path / "pics", "story", "cast", ask, report)
    assert [int(p.stem[4:]) for p in pics] == [0, 1, 2, 2, 4, 5, 6, 6, 8, 9]
    assert Image.open(pics[0]).size == aiart.UPSCALE
    assert [r["beat"] for r in report if r["rejected"]] == [8]
