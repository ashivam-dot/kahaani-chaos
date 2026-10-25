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
    assert len(plan[0]["alternates"]) == look.ALTERNATES and plan[5]["cast"] == []
    assert len(plan[5]["alternates"]) == look.ALTERNATES
    assert len({b["seed"] for b in plan}) == len(plan)
    assert plan == look.plan(d["id"], d["beats"], d["cast"])


def test_bible_characters_use_their_image_token():
    from kahaani import bible

    p = look.prompt("Jhabbu on the bridge", [{"name": "jhabbu", "expression": "calm"}], [{"id": "jhabbu", "name": "झब्बू"}])
    assert bible.image_token("jhabbu").strip().rstrip(".") in p and "झब्बू" not in p


def test_a_writing_watchman_is_not_also_told_to_carry_the_register_and_lantern():
    scene = "Jhabbu sits at dawn, dipping a pen in ink to write in his register, an unlit lantern beside him."
    p = look.prompt(scene, [{"name": "jhabbu"}], [{"id": "jhabbu", "name": "झब्बू"}])
    assert "Exactly one person, Jhabbu" in p
    assert "under one arm" not in p and "holding a brass hurricane lantern" not in p
    assert "red woollen muffler" in p and "ledger with a red spine resting before him" in p
    assert "unlit brass hurricane lantern" in p and look.DAWN_STYLE in p


def test_pencil_register_scene_does_not_demand_an_extra_carrier_hand():
    # Actual e10 cloud/local paintings added a third arm to carry the cast's lantern.
    scene = ("Inside the post office, Jhabbu sits at the sorting table with his red-bound khaki register "
             "open under the gentle lantern beam, pencil in hand as soft moonlight touches his shoulder.")
    prompt = look.prompt(scene, [{"name": "jhabbu"}], [{"id": "jhabbu", "name": "Jhabbu"}])
    assert "Exactly one person, Jhabbu, seated and writing" in prompt
    assert "under one arm" not in prompt and "holding a brass hurricane lantern" not in prompt
    assert "red woollen muffler" in prompt and "lantern and bamboo staff" in prompt
    carrying = look.character({'id': 'jhabbu'}, 'Jhabbu raises his lantern by the sorting table.')
    assert 'holding a brass hurricane lantern' in carrying


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


def test_staff_room_stays_enclosed_without_outdoor_style_at_night_and_dawn():
    for scene, style in [('Wide interior shot of the college staff room at night.', look.INDOOR_STYLE),
                         ('The staff-room ceiling fan stops in pale dawn light.', look.INDOOR_DAWN_STYLE)]:
        prompt = look.prompt(scene, [], [])
        assert style in prompt and 'visible solid ceiling' in prompt
        assert look.STYLE not in prompt and look.DAWN_STYLE not in prompt
    outdoor = look.prompt('The young people stand outside the college at dawn.', [], [])
    assert look.DAWN_STYLE in outdoor and look.INDOOR_STYLE not in outdoor


def test_watchman_can_help_someone_when_scene_sets_down_his_props():
    scene = 'Jhabbu holds Shailesh by the wrist. The brass lantern and bamboo staff rest beside the table.'
    token = look.character({'id': 'jhabbu'}, scene)
    assert 'resting beside him' in token
    assert 'holding a brass hurricane lantern' not in token and 'under one arm' not in token
    assert 'red woollen muffler' in token and 'ledger with a red spine' in token


def test_separate_grounded_prop_sentences_free_the_watchmans_hands_only_when_both_are_down():
    scene = 'The brass lantern rests on the floor beside the table. A bamboo staff leans against the wall.'
    token = look.character({'id': 'jhabbu'}, scene)
    assert 'resting beside him' in token and 'holding a brass hurricane lantern' not in token
    carrying = look.character({'id': 'jhabbu'}, 'The lantern rests on the table. Jhabbu carries his bamboo staff.')
    assert 'resting beside him' not in carrying


def test_reflected_light_and_dark_surroundings_do_not_switch_a_lit_bulb_off():
    for scene in [
        "The warm yellow light from the booth bulb reflects off his steel-frame glasses.",
        "The bulb illuminates the dark booth.",
        "A lantern lights the dark street.",
    ]:
        assert not look.UNLIT.search(scene)
        assert look.OUT not in look.prompt(scene, [], [])
    for scene in ["its dynamo light dark", "the lamp is switched off", "the bulb has gone dark",
                  "an unlit lantern beside him", "the headlight turns off"]:
        assert look.UNLIT.search(scene), scene


def test_object_only_call_meter_can_repaint_under_the_same_human_presence_gate():
    beat = {'scene':'Inside the booth, the analog call meter is fixed to the wall.', 'people':[]}
    plan = look.plan('pco-recovery', [beat], [])
    assert plan[0]['cast'] == [] and look.NOBODY in plan[0]['prompt']
    assert len(set([plan[0]['seed']] + plan[0]['alternates'])) == look.ALTERNATES + 1
