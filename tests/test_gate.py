import pytest

from kahaani import cli, gate
from kahaani.spec import Story

from .conftest import story_dict


def premise(d=None):
    return cli.premise_of(Story.from_dict(d or story_dict()))


def problems(d, history=(), rotation=True, entry=None):
    return gate.check(d, entry or premise(d), list(history), rotation=rotation)


def has(found, fragment):
    return any(fragment in p for p in found)


def test_the_reviewed_story_passes():
    assert problems(story_dict()) == []


def test_explicit_repair_directions_keep_story_and_visual_checks():
    from dataclasses import asdict
    from pathlib import Path
    replay = Path(__file__).resolve().parents[1] / '.github/replay/sannatpur-fan-e09-repair.json'
    story = Story.load(replay)
    assert not gate.check(asdict(story), cli.premise_of(story), [], rotation=False)
    draft = asdict(story)
    draft['beats'][4]['scene'] += ' ' + 'unnecessary ' * 30
    found = problems(draft, rotation=False)
    assert has(found, 'painter scene has') and not has(found, 'scene contains Devanagari')
    draft['beats'][4]['scene'] = 'प्रभात पंखे को देखता है।'
    assert has(problems(draft, rotation=False), 'scene contains Devanagari')
    draft = asdict(story)
    draft['beats'][4]['scene'] += ' At a temple door.'
    assert has(problems(draft, rotation=False), 'scene touches')


def test_word_and_beat_bands_have_floor_and_ceiling():
    d = story_dict()
    d["beats"] = d["beats"][:4]
    found = problems(d)
    assert has(found, "needs 5-7 beats") and has(found, "needs 85-130 spoken Hindi words")
    d = story_dict()
    d["beats"] = d["beats"] + [dict(d["beats"][4]), dict(d["beats"][4])]
    found = problems(d)
    assert has(found, "needs 5-7 beats, has 8") and has(found, "needs 85-130 spoken Hindi words")


def test_hook_length_object_and_host_openers():
    d = story_dict()
    d["beats"][0]["text"] = "एक दो तीन चार पाँच छह सात आठ नौ दस साइकिल"
    found = problems(d)
    assert has(found, "the hook) has 11 words") and has(found, "must name the object")
    d = story_dict()
    d["beats"][0]["text"] = "नमस्ते, पुल पर साइकिल की लाइट जल उठी।"
    assert has(problems(d), "opens like a host")


def test_the_memory_opens_with_the_year():
    d = story_dict()
    d["beats"][1]["text"] = d["beats"][1]["text"].replace("उन्नीस सौ छियानवे की सर्दी।", "उस साल की सर्दी।")
    assert has(problems(d, rotation=False), "beat 2 opens the memory with the year")


@pytest.mark.parametrize("line", ["इसे लाइक करो।", "चैनल पर और कहानियाँ हैं।", "क्या आप जानते थे यह सब?",
                                  "कहानी केऑस की यह कहानी है।"])
def test_banned_asks(line):
    d = story_dict()
    d["beats"][3]["text"] = line
    assert has(problems(d), "no greetings, channel name")


def test_english_words_digits_and_retired_names():
    d = story_dict()
    d["beats"][3]["text"] = "अंशु के हाथ में 2 सिक्के थे, sir।"
    found = problems(d)
    assert has(found, "English words") and has(found, "has digits") and has(found, "retired name 'अंशु'")


@pytest.mark.parametrize("scene, bad", [
    ("Close-up of a priest at a temple door at night with a lantern and mist over the lane.", True),
    ("Wide shot of a lane with blood on the ground under the moonlight and mist over it.", True),
    ("A Hero cycles logo on a bicycle frame by the canal bridge at night in the mist.", True),
    ("Wide shot of a blood-red moon over several stable old houses in the mist tonight.", False),
])
def test_english_red_lines_in_scenes(scene, bad):
    d = story_dict()
    d["beats"][2]["scene"] = scene
    assert has(problems(d), "scene touches") is bad


def test_people_must_be_cast_ids_with_an_expression():
    d = story_dict()
    d["beats"][3]["people"] = [{"name": "stranger", "expression": "sly"}, {"name": "jhabbu", "expression": ""}]
    found = problems(d)
    assert has(found, "'stranger', who is not in the cast") and has(found, "no expression for 'jhabbu'")


def test_cast_must_come_from_the_bible():
    d = story_dict()
    d["cast"].append({"id": "monty", "name": "मोंटी", "look": "boy"})
    found = problems(d)
    assert has(found, "'monty' is not a bible character")


@pytest.mark.parametrize("turn", [2, 6, 0, None, "4"])
def test_the_turn_lands_inside_the_story(turn):
    d = story_dict()
    d["twist_beat"] = turn
    assert has(problems(d), "turn_beat")


def test_the_heart_comes_at_or_after_the_turn():
    d = story_dict()
    d["heart_beat"] = 2
    assert has(problems(d), "heart_beat must come at or after the turn")


@pytest.mark.parametrize("ending, last, fragment", [
    ("loop-back", "अगली सुबह सब शांत था।", "loop-back ending's last beat echoes frame 0"),
    ("register-line", "अगली सुबह सब शांत था।", "has झब्बू write one line in his रजिस्टर"),
    ("open-question", "अगली सुबह सब शांत था।", "asks the viewer one question"),
    ("next-raat-tease", "अगली सुबह सब शांत था।", "full night comes on शनिवार"),
])
def test_each_ending_needs_its_last_line(ending, last, fragment):
    d = story_dict()
    d["ending"], d["beats"][-1]["text"] = ending, last
    found = problems(d, rotation=False, entry={**premise(), "ending_type": ending})
    assert has(found, fragment)


def test_ending_resolution_and_rule_must_be_the_entrys():
    d = story_dict()
    d["ending"], d["resolution"], d["niyam_id"] = "open-question", "bargain", "N01"
    found = problems(d, rotation=False, entry=premise())
    assert has(found, "ending_type must be 'loop-back'") and has(found, "resolution_type must be 'leave-it-be'")
    assert has(found, "niyam_id must be 'N06'")
    d["niyam_id"] = "N99"
    assert has(problems(d, rotation=False, entry=premise()), "'N99' is not a rule in canon.json")


def test_hook_strip_band():
    d = story_dict()
    for strip, bad in (("लाइट", True), ("बिना पैडल जली लाइट", False), ("एक दो तीन चार पाँच छह", True),
                       ("बिना पैडल 2 लाइट", True), ("बिना पैडल जली लाइट 🚲", True)):
        d["hook_strip"] = strip
        assert has(problems(d, rotation=False), "hook_strip must be") is bad, strip


@pytest.mark.parametrize("title, fragment", [
    ("साइकिल रोकी… और उसकी लाइट बिना पैडल के जल उठी! 🚲", None),
    ("साइकिल ने रात में अपनी लाइट ख़ुद जला ली 😨 | सन्नाटपुर", None),
    ("साइकिल की लाइट बिना पैडल के किसने जलाई? 🚲", None),
    ("साइकिल रोकी… और उसकी लाइट बिना पैडल के जल उठी!", "needs 1-2 emoji"),
    ("साइकिल रोकी… और उसकी लाइट बिना पैडल के जल उठी! 🚲😨", None),
    ("साइकिल रोकी… और उसकी लाइट बिना पैडल के जल उठी! 🚲😨⏰", "needs 1-2 emoji"),
    ("साइकिल रोकी… और उसकी लाइट बिना पैडल के जल उठी! ⏰", None),
    ("साइकिल रोकी… और उसकी लाइट बिना पैडल के जल उठी! 😶‍🌫️", None),
    ("साइकिल | रोकी और उसकी लाइट बिना पैडल के जल उठी! 🚲", "only appear as the suffix"),
    ("Cycle की light अपने आप जल उठी, bina pedal! 🚲", "Devanagari"),
    ("साइकिल जली! 🚲", "characters"),
    ("साइकिल " * 12 + "! 🚲", "characters"),
    ("उस रात नहर के पुल पर खड़ी पुरानी साइकिल की लाइट जल उठी! 🚲", "within its first 5 words"),
    ("साइकिल रोकी… और #लाइट बिना पैडल के जल उठी! 🚲", "may not contain"),
    ("साइकिल और चौकीदार की वो अजीब रात, बिना पैडल के! 🚲", "never goes in a title"),
])
def test_title_rules(title, fragment):
    found = gate.title_problems(title, "साइकिल")
    assert (found == []) if fragment is None else has(found, fragment), found


def test_title_skeletons():
    assert gate.skeleton_of("साइकिल रोकी… और उसकी लाइट जल उठी! 🚲") == "S1"
    assert gate.skeleton_of("साइकिल ने अपनी लाइट ख़ुद जला ली 😨 | सन्नाटपुर") == "S2"
    assert gate.skeleton_of("साइकिल की लाइट किसने जलाई? 🚲") == "S3"
    assert has(gate.title_problems("साइकिल की लाइट बिना पैडल के किसने जलाई? 🚲", "साइकिल", "S1"),
               "must follow skeleton S1")


def test_every_bank_title_passes_its_own_rules():
    from kahaani import bible

    for e in bible.micro_bank():
        assert gate.title_problems(e["title"], e["object_token"], e["title_skeleton"]) == [], e["id"]


def test_description_must_be_hindi_and_not_for_kids():
    d = story_dict()
    d["description"] = "A bicycle lamp lights itself on the canal bridge."
    assert has(problems(d), "description must be")
    d = story_dict()
    d["description"] += " बच्चों के लिए कार्टून कहानी।"
    assert has(problems(d), "reads as made for kids")


def test_runtime_and_payoff_bands():
    story = Story.from_dict(story_dict())
    spans = [[i * 7.0, i * 7.0 + 7.0] for i in range(len(story.beats))]
    assert gate.timing_problems(story, {"duration": 42.0, "beats": spans}) == []
    assert has(gate.timing_problems(story, {"duration": 27.0, "beats": spans}), "F1 needs 30-58 s")
    # The ceiling is on the Short, end card included: a 57 s narration makes a 59.4 s Short.
    assert has(gate.timing_problems(story, {"duration": 57.0, "beats": spans}), "F1 needs 30-58 s")
    assert gate.timing_problems(story, {"duration": 55.0, "beats": spans}) == []
    assert gate.runtime_problems(45.0) == [] and gate.runtime_problems(59.4) and gate.runtime_problems(None)
    late = [[0, 5], [5, 10], [10, 15], [40, 44], [44, 48], [48, 50]]
    assert has(gate.timing_problems(story, {"duration": 50.0, "beats": late}), "after 75%")


def test_only_the_narrator_may_be_published():
    assert gate.voice_ok({"engine": "gemini-narrator", "identity": "narrator"}) is None
    assert gate.voice_ok({"engine": "chatterbox-narrator-clone", "identity": "narrator"}) is None
    assert gate.voice_ok({"engine": "chatterbox-builtin", "identity": "builtin"})
    assert gate.voice_ok(None)
