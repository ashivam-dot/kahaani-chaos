import json

import pytest
from PIL import Image

from kahaani import aiart, vision


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
                              "gore": False, "malformed": start + k == 7, "text": False, "subject_share": 0.5}
                             for k in range(1, n + 1)]}

    report = []
    found = aiart.collect(art, "kc-1", 10)
    pics = aiart.pictures(found, list("abcdefghij"), tmp_path / "pics", "story", "cast", ask, report)
    assert [int(p.stem[4:]) for p in pics] == [0, 1, 2, 2, 4, 5, 6, 6, 8, 9]
    assert Image.open(pics[0]).size == aiart.UPSCALE
    assert not any(r["rejected"] for r in report)
    assert sorted(r["beat"] for r in report if r.get("original_rejected")) == [4, 8]
    assert next(r["source_beat"] for r in report if r["beat"] == 8) == 7


def test_repaints_are_collected_apart_from_the_painting(tmp_path):
    paint(tmp_path, "kc-1", 1)
    Image.new("RGB", (576, 1024), (90, 90, 90)).save(tmp_path / "beat01-alt2.png")
    (tmp_path / "beat01-alt2.json").write_text(json.dumps({"story": "kc-1", "beat": 1, "alt": 2}))
    Image.new("RGB", (576, 1024), (90, 90, 90)).save(tmp_path / "beat01-alt1.png")
    (tmp_path / "beat01-alt1.json").write_text(json.dumps({"story": "kc-1", "beat": 1, "alt": 1}))
    assert aiart.collect(tmp_path, "kc-1", 3) == {1: tmp_path / "beat01.png"}
    assert aiart.alternates(tmp_path, "kc-1", 3) == {1: [tmp_path / "beat01-alt1.png", tmp_path / "beat01-alt2.png"]}


def verdict(n, props_ok=True, share=0.5):
    return {"n": n, "shows": "Jhabbu on the bridge", "fits": True, "nudity": False, "sexual": False, "gore": False,
            "malformed": False, "text": False, "religious": False, "kids_look": False, "doubled": False,
            "ridden": False, "props_ok": props_ok,
            "subject_share": share, "reason": "" if props_ok else "no lantern"}


def test_a_cast_shot_without_its_props_is_repainted_at_most_twice(tmp_path):
    art = tmp_path / "art"
    art.mkdir()
    for i in range(3):
        paint(art, "kc-1", i)
    spares = {1: [art / "beat00.png", art / "beat02.png", art / "beat00.png"]}
    answers = iter([[True, False, True], [False], [True]])

    def ask(parts, schema):
        return {"pictures": [verdict(k, ok) for k, ok in enumerate(next(answers), 1)]}

    report = []
    pics = aiart.pictures(aiart.collect(art, "kc-1", 3), list("abc"), tmp_path / "pics", "story", "cast", ask, report,
                          spares=spares, who={1: ["jhabbu"]})
    assert [int(p.stem[4:]) for p in pics] == [0, 1, 2]
    assert report[1]["repaints_tried"] == 2 and report[1]["rejected"] is None and report[1]["props_ok"] is True
    assert aiart.prop_rate(report) == 1.0


def test_prop_rate_counts_cast_shots_only():
    report = [{"cast": [], "rejected": None, "props_ok": None},
              {"cast": ["jhabbu"], "rejected": None, "props_ok": True},
              {"cast": ["nuzhat"], "rejected": "props: no torch", "props_ok": False}]
    assert aiart.prop_rate(report) == 0.5
    assert aiart.prop_rate(report[:1]) is None


def test_a_shot_dropped_for_something_else_is_not_a_prop_miss():
    # Run 40101837936: four cast shots, all with their props, one refused as doubled: held at 75%.
    ok = {"cast": ["jhabbu"], "rejected": None, "props_ok": True}
    doubled = {"cast": ["jhabbu", "prabhat"], "rejected": "doubled: the red cap appears twice", "props_ok": True}
    assert aiart.prop_rate([ok, ok, ok, doubled]) == 1.0
    assert aiart.prop_rate([doubled]) is None
    missing = {"cast": ["nuzhat"], "rejected": "props: no braid", "props_ok": False}
    assert aiart.prop_rate([ok, ok, ok, doubled, missing]) == 0.75


def test_the_hook_painting_needs_its_subject_to_fill_the_frame():
    assert aiart.vision.rejected(verdict(1), hook=True) is None
    for share in (0.1, 0.95, None):
        assert "hook's subject" in aiart.vision.rejected(verdict(1, share=share), hook=True)
    assert aiart.vision.rejected(verdict(1, share=0.1)) is None  # only the hook's painting is frame 0


def test_a_tiny_hook_subject_holds_the_story(tmp_path):
    art = tmp_path / "art"
    art.mkdir()
    for i in range(3):
        paint(art, "kc-1", i)

    def ask(parts, schema):
        return {"pictures": [verdict(k, share=0.1) for k in range(1, 4)]}

    with pytest.raises(aiart.PictureHold, match="the hook's"):
        aiart.pictures(aiart.collect(art, "kc-1", 3), list("abc"), tmp_path / "pics", "story", "cast", ask)


def test_a_caption_naming_a_child_refuses_the_picture():
    from kahaani import vision

    ok = {f: False for f in vision.FLAGS} | {"fits": True, "props_ok": True, "shows": ""}
    assert vision.rejected(ok | {"shows": "Two young men walking along a canal path."}, True) is None
    assert vision.rejected(ok | {"shows": "A young woman with a torch beside a bicycle."}, True) is None
    assert vision.rejected(ok | {"shows": "A teenage boy in a red cap beside a teenage girl."}, True) is None
    for shows in ("An older man holding a lantern stopping two younger boys on a path.",
                  "An older man with a lantern talking to a child and a young woman near a bicycle.",
                  "Jhabbu stands with a lantern while a girl in green and a boy in yellow look on."):
        assert vision.rejected(ok | {"shows": shows}, True).startswith("child")
    assert "child" not in vision.PROMPT.lower().replace("children: chibi", "")


def test_the_picture_editor_falls_back_to_the_local_model_and_stays_there(monkeypatch):
    from kahaani import gemini, llm, vision

    calls = []

    def no_gemini(parts, schema):
        calls.append("gemini")
        raise gemini.Unavailable("429")

    class Local:
        name = "gemma-4-12b"

        def __init__(self, name, vision=False):
            assert vision

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            calls.append("closed")

        def look(self, parts, schema):
            calls.append("local")
            return {"pictures": []}

    monkeypatch.setattr(gemini, "available", lambda: True)
    monkeypatch.setattr(gemini, "look", no_gemini)
    monkeypatch.setattr(llm, "Model", Local)
    with vision.Eye() as eye:
        assert eye(["x"], {}) == {"pictures": []} and eye(["y"], {}) == {"pictures": []}
    assert calls == ["gemini", "local", "local", "closed"] and eye.used == ["gemma-4-12b", "gemma-4-12b"]


def test_no_local_model_is_a_clean_hold(monkeypatch):
    from kahaani import gemini, llm, vision

    monkeypatch.setattr(gemini, "available", lambda: False)

    class Broken:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            raise RuntimeError("no local model would start")

    monkeypatch.setattr(llm, "Model", Broken)
    with pytest.raises(gemini.Unavailable, match="no local model would start"):
        vision.Eye()(["x"], {})


def test_the_editor_sees_the_planned_picture(tmp_path):
    # Dry run 39930652897: the line said the bicycle moves by itself, the painting had a boy riding it, and the editor
    # (shown only the Hindi line) passed it.
    art = tmp_path / "art"
    art.mkdir()
    paint(art, "kc-1", 0)
    prompts = []

    def ask(parts, schema):
        prompts.append(parts[0])
        return {"pictures": [{"n": 1, "shows": "a bicycle", "fits": True, "ridden": False,
                                         "subject_share": 0.5}]}

    aiart.pictures(aiart.collect(art, "kc-1", 1), ["a"], tmp_path / "pics", "story", "cast", ask,
                   scenes=["The bicycle rolling forward without a rider."])
    from kahaani import look

    assert f"planned picture: {look.picture_scene('The bicycle rolling forward without a rider.')}" in prompts[0]
    assert "someone the plan leaves" in vision.PROMPT


def test_a_replacement_must_fit_its_new_line_and_props(tmp_path):
    art = tmp_path / "art"
    art.mkdir()
    for i in range(4):
        paint(art, "kc-1", i)
    prompts = []

    def ask(parts, schema):
        prompts.append(parts[0])
        if len(prompts) == 1:
            return {"pictures": [verdict(k) | ({"fits": False} if k == 3 else {}) for k in range(1, 5)]}
        return {"pictures": [verdict(1) | {"fits": False, "reason": "the radio is not on the ground"}]}

    report = []
    with pytest.raises(aiart.PictureHold, match="replacement for beat 3 from beat 2.*radio"):
        aiart.pictures(aiart.collect(art, "kc-1", 4), ["hook", "friends", "radio on the ground", "ending"],
                       tmp_path / "pics", "story", "cast", ask, report, who={2: ["shailesh"]},
                       scenes=["bicycle", "friends on bridge", "A radio on the ground.", "dawn"])
    assert "narrated line: radio on the ground" in prompts[-1]
    assert "should appear: Shailesh" in prompts[-1]
    assert "planned picture: A radio on the ground." in prompts[-1]
    assert report[2]["source_beat"] == 2 and report[2]["rejected"]


def test_editor_checks_the_same_object_only_scene_the_painter_receives(tmp_path):
    art = tmp_path / "art"
    art.mkdir()
    paint(art, "kc-1", 0)
    prompts = []

    def ask(parts, schema):
        prompts.append(parts[0])
        return {"pictures": [verdict(1)]}

    raw = "The bicycle is rolling across the bridge. Prabhat is pointing. The dynamo light glows."
    aiart.pictures(aiart.collect(art, "kc-1", 1), ["cycle"], tmp_path / "pics", "story", "cast", ask,
                   scenes=[raw])
    planned = prompts[0].split("planned picture: ")[-1]
    assert "Prabhat is pointing" not in planned
    assert "bicycle stands empty" in planned and "dynamo light glows" in planned
    assert "nobody is there" in planned


def test_a_ridden_bicycle_is_refused_when_the_plan_says_it_moves_by_itself():
    # Dry run 39969216681, beat 3: told the plan, the editor captioned a ridden bicycle "rolls forward by itself".
    alone = "The black bicycle rolls forward on its own along the bridge. No one is touching or riding it."
    ridden = verdict(1) | {"ridden": True, "shows": "A bicycle rolls forward by itself while four people watch."}
    assert vision.rejected(ridden, scene=alone).startswith("ridden")
    assert vision.rejected(verdict(1) | {"ridden": True}, scene="Prabhat pedals his bicycle down the lane.") is None
    assert vision.rejected(verdict(1), scene=alone) is None
    assert vision.rejected({k: v for k, v in verdict(1).items() if k != "ridden"}, scene=alone).startswith("ridden")


def test_a_person_painted_twice_is_refused():
    assert vision.rejected(verdict(1) | {"doubled": True}).startswith("doubled")
