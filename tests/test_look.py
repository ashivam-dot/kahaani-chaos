from kahaani import look

from .conftest import story_dict

CAST = [{"name": "Dhaniram", "look": "plump middle-aged moneylender with a thick moustache, brown waistcoat"},
        {"name": "Billi", "look": "a thin grey village cat with one torn ear"},
        {"name": "Meera", "look": "young woman in a fish-pattern scarf, braided hair"}]


def test_prompt_order_and_parts():
    p = look.prompt("Wide shot of a misty lane at night", [{"name": "dhaniram", "expression": "greedy grin"}], CAST)
    assert p.startswith("Wide shot of a misty lane at night. Characters: Dhaniram: plump middle-aged")
    assert "brown waistcoat, greedy grin expression." in p
    assert p.index(look.STYLE) < p.index(look.AVOID) and p.endswith(look.AVOID)
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
    assert "frozen in dawning fear, staring down expression" in plan[8]["prompt"]
    assert len({b["seed"] for b in plan}) == len(plan)
    assert plan == look.plan(d["id"], d["beats"], d["cast"])
