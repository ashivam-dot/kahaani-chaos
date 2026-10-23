from kahaani import look

from .conftest import story_dict

CAST = [{"name": "Dhaniram", "look": "plump middle-aged moneylender with a thick moustache, brown waistcoat"},
        {"name": "Billi", "look": "a thin grey village cat with one torn ear"},
        {"name": "Meera", "look": "young woman in a fish-pattern scarf, braided hair"}]


def test_prompt_order_and_parts():
    p = look.prompt("Wide shot of a misty lane at night", [{"name": "dhaniram", "expression": "greedy grin"}], CAST)
    assert p.startswith("Wide shot of a misty lane at night. Characters: Dhaniram: plump middle-aged")
    assert "brown waistcoat, greedy grin expression." in p
    assert p.index(look.STYLE) < p.index(look.AVOID) < p.index(look.NEVER) and p.endswith(look.NEVER)
    assert look.FACES in p
    assert look.CLOSE not in p and look.NOBODY not in p


def test_the_hook_is_a_close_up():
    p = look.prompt("Dhaniram stares at the well", [{"name": "Dhaniram", "expression": "greedy"}], CAST, hook=True)
    assert look.CLOSE in p and look.NOBODY not in p


def test_a_scene_without_people_says_so_and_never_asks_for_a_face():
    hook = look.prompt("A brass kettle pours tea into a clay cup", [], CAST, hook=True)
    assert look.CLOSE_THING in hook and look.CLOSE not in hook and look.NOBODY in hook
    assert "Characters" not in hook and "face fill" not in hook
    later = look.prompt("An empty lane in the mist", [], CAST)
    assert look.NOBODY in later and look.CLOSE_THING not in later


def test_animals_are_pinned_as_real_animals():
    assert look.animal(CAST[1]["look"]) and not look.animal(CAST[2]["look"])
    assert look.character(CAST[1]).endswith(look.REAL)
    assert look.REAL not in look.character(CAST[2])
    already = {"name": "Kauwa", "look": "a real black crow, not a person"}
    assert look.REAL not in look.character(already)


def test_people_outside_the_cast_and_missing_expressions():
    p = look.prompt("A room", [{"name": "Ghost", "expression": "sad"}, {"name": "Meera", "expression": ""}], CAST)
    assert "Ghost" not in p and "braided hair, calm expression" in p


def test_plan_has_one_seeded_prompt_per_beat():
    d = story_dict()
    plan = look.plan(d["id"], d["beats"], d["cast"])
    assert [b["beat"] for b in plan] == list(range(len(d["beats"])))
    assert look.CLOSE_THING in plan[0]["prompt"] and look.NOBODY in plan[0]["prompt"]
    assert look.CLOSE_THING not in plan[1]["prompt"] and look.NOBODY not in plan[1]["prompt"]
    assert "sheepish expression" in plan[4]["prompt"] and "Shailesh:" in plan[4]["prompt"]
    assert plan[3]["cast"] == ["jhabbu", "prabhat", "nuzhat"] and len(plan[3]["alternates"]) == look.ALTERNATES
    # the hook's bicycle light glows on its own, so it gets spare seeds for the picture editor too
    assert len(plan[0]["alternates"]) == look.ALTERNATES and plan[5]["cast"] == [] and "alternates" not in plan[5]
    assert len({b["seed"] for b in plan}) == len(plan)
    assert plan == look.plan(d["id"], d["beats"], d["cast"])


def test_bible_characters_use_their_image_token():
    from kahaani import bible

    p = look.prompt("Jhabbu on the bridge", [{"name": "jhabbu", "expression": "calm"}], [{"id": "jhabbu", "name": "झब्बू"}])
    assert bible.image_token("jhabbu").strip().rstrip(".") in p and "झब्बू" not in p


def test_the_scene_never_calls_the_cast_kids():
    from kahaani import look as lk

    out = lk.prompt("Jhabbu raises his lantern over the kids as a boy and a girl watch.", [], []).split(". ")[0]
    assert "kids" not in out and " boy " not in out and " girl " not in out
    assert "young people" in out and "young man" in out and "young woman" in out


def test_a_thing_moving_by_itself_has_nobody_on_it():
    from kahaani import look as lk

    assert lk.ALONE in lk.prompt("Shailesh lunges to grab the rolling bicycle.", [], [])
    assert lk.ALONE not in lk.prompt("The bicycle stands on the bridge.", [], [])


def test_a_dawn_beat_gets_the_dawn_look_and_a_dark_lamp_stays_dark():
    from kahaani import look as lk

    scene = "Dawn light over the brick canal bridge. prabhat stands near the stationary bicycle, its dynamo light dark."
    out = lk.prompt(scene, [], [])
    assert lk.DAWN_STYLE in out and lk.STYLE not in out and lk.OUT in out
    night = lk.prompt("The bicycle's headlight shines yellow on the bridge at night.", [], [])
    assert lk.STYLE in night and lk.OUT not in night


def test_a_beat_where_something_moves_by_itself_is_painted_with_nobody_in_it():
    from kahaani import look as lk

    scene = "The bicycle is rolling slowly across the bridge. Prabhat has stood up, looking startled and pointing."
    people = [{"name": "prabhat", "expression": "startled"}]
    cast = [{"id": "prabhat", "name": "Prabhat", "look": "a young man in a mustard sweater"}]
    got = lk.prompt(scene, people, cast)
    assert "stands empty across the bridge" in got and "Prabhat has stood up" not in got
    assert lk.NOBODY in got and "Characters:" not in got
    assert lk.present(people, cast, scene) == [] and lk.present(people, cast, "Prabhat sits on the bridge.") == ["prabhat"]
    assert lk.unpeopled("Prabhat watches the lamp. He gasps.") == "Prabhat watches the lamp."


def test_a_by_itself_beat_paints_the_thing_standing_empty_not_moving():
    scene = ("The bicycle is rolling slowly across the bridge. Prabhat has stood up, pointing at the cycle. "
             "The dynamo light flickers and hums as the wheel turns by itself.")
    from kahaani import look as lk

    text = lk.prompt(scene, [{"name": "prabhat", "expression": "startled"}], [])
    assert "rolling" not in text and "bicycle stands empty across the bridge" in text
    assert lk.EMPTY in text and "Prabhat" not in text
