import pytest

from kahaani import gate, hindi

from .conftest import story_dict


def problems(d, history=(), rotation=True):
    return gate.check(d, {"subgenre": d["subgenre"]}, list(history), rotation=rotation)


def has(found, fragment):
    return any(fragment in p for p in found)


def test_the_reviewed_story_passes():
    assert problems(story_dict()) == []


def test_word_and_beat_counts():
    d = story_dict()
    d["beats"] = d["beats"][:6]
    found = problems(d)
    assert has(found, "needs 9-12 beats") and has(found, "spoken Hindi words in total")


def test_hook_length_and_host_openers():
    d = story_dict()
    d["beats"][0]["text"] = "एक दो तीन चार पाँच छह सात आठ नौ दस ग्यारह"
    assert has(problems(d), "the hook) has 11 words")
    d = story_dict()
    d["beats"][0]["text"] = "नमस्ते, इस कुएँ में सिक्का डालो।"
    assert has(problems(d), "opens like a host")


def test_greetings_are_allowed_after_the_hook():
    d = story_dict()
    d["beats"][4]["text"] = "धनीराम बोला, दोस्तों, परछाईं से किसका पेट भरता है? उसने एक सिक्का फेंका।"
    assert problems(d) == []


@pytest.mark.parametrize("line", ["इसे लाइक करो।", "चैनल पर और कहानियाँ हैं।", "क्या आप जानते थे यह सब?",
                                  "कहानी केऑस की यह कहानी है।"])
def test_banned_asks(line):
    d = story_dict()
    d["beats"][5]["text"] = line
    assert has(problems(d), "no greetings, channel name")


def test_english_words_and_digits_in_narration():
    d = story_dict()
    d["beats"][5]["text"] = "उसकी हथेली पर 2 सिक्के थे, sir।"
    found = problems(d)
    assert has(found, "English words") and has(found, "has digits")


@pytest.mark.parametrize("text, topic", [
    ("उसने भगवान से दुआ माँगी।", "religion"),
    ("पुराने मंदिर के पास कुआँ था।", "religion"),
    ("ज़मीन पर ख़ून फैला था।", "gore"),
    ("यह एक सच्ची कहानी है।", "really happened"),
    ("उस बच्चे को मार दिया गया।", "harm to a child"),
    ("वह ठाकुर का कुआँ था।", "caste"),
])
def test_hindi_red_lines(text, topic):
    d = story_dict()
    d["beats"][6]["text"] = text
    assert has(problems(d), topic)


def test_a_religious_exclamation_is_refused_with_a_fix_the_writer_can_apply():
    d = story_dict()
    d["beats"][6]["text"] = "या खुदा, यह क्या हो गया!"
    found = [p for p in problems(d) if "red line" in p]
    assert len(found) == 1 and "religion ('खुदा')" in found[0] and "even in an exclamation" in found[0]
    assert "बाप रे" in found[0]


def test_red_lines_compare_spellings_without_nukta():
    assert gate.red_lines_hi("खून") and gate.red_lines_hi("ख़ून")


def test_names_that_contain_a_god_are_not_red_lines():
    assert gate.red_lines_hi("धनीराम और रामू काका") == []


@pytest.mark.parametrize("scene, bad", [
    ("Close-up of a priest at a temple door at night with a lantern and mist.", True),
    ("Wide shot of a lane with blood on the ground under the moonlight and mist.", True),
    ("Wide shot of a blood-red moon over several stable old houses in the mist.", False),
])
def test_english_red_lines_in_scenes(scene, bad):
    d = story_dict()
    d["beats"][2]["scene"] = scene
    assert has(problems(d), "scene touches") is bad


def test_people_must_be_cast_with_an_expression():
    d = story_dict()
    d["beats"][3]["people"] = [{"name": "Stranger", "expression": "sly"}, {"name": "Dhaniram", "expression": ""}]
    found = problems(d)
    assert has(found, "'Stranger', who is not in the cast") and has(found, "no expression for 'Dhaniram'")


def test_cast_needs_an_english_look():
    d = story_dict()
    d["cast"][0]["look"] = "मोटा साहूकार"
    assert has(problems(d), "needs an English look")


@pytest.mark.parametrize("twist", [6, 12, 0, None, "10"])
def test_twist_lands_after_the_middle_and_before_the_last_beat(twist):
    d = story_dict()
    d["twist_beat"] = twist
    assert has(problems(d), "twist_beat")


def test_dilemma_ends_on_a_question():
    d = story_dict()
    d["ending"] = "dilemma"
    found = problems(d, rotation=False)
    assert has(found, "asks the viewer a question")
    d["beats"][-1]["text"] = "आप होते तो क्या उस कुएँ में सिक्का डालते?"
    assert problems(d, rotation=False) == []


def test_endings_rotate():
    assert gate.required_ending([]) == "twist-reveal"
    assert gate.required_ending([{"ending": "twist-reveal"}]) == "dilemma"
    assert gate.required_ending([{"ending": "dilemma"}]) == "loop-back"
    assert gate.required_ending([{"ending": "loop-back"}]) == "twist-reveal"
    d = story_dict()
    found = problems(d, history=[{"ending": "twist-reveal", "made_at": "x"}])
    assert has(found, "ending must be 'dilemma'")
    assert problems(d, history=[{"ending": "loop-back", "made_at": "x"}]) == []


def test_a_replay_skips_the_rotation_rules():
    d = story_dict()
    history = [{"ending": "twist-reveal", "opening": hindi.opening(d["beats"][0]["text"])}]
    assert problems(d, history=history, rotation=False) == []


def test_the_opening_may_not_repeat_a_recent_short():
    d = story_dict()
    history = [{"ending": "loop-back", "opening": hindi.opening(d["beats"][0]["text"])}]
    assert has(problems(d, history=history), "like a recent Short")


def test_subgenre_must_match_the_premise():
    d = story_dict()
    assert has(gate.check(d, {"subgenre": "samay-chakra"}, []), "subgenre must be 'samay-chakra'")


@pytest.mark.parametrize("title, fragment", [
    ("एक सिक्का डालो, दो पाओ… पर कुएँ ने क्या लिया? 😨", None),
    ("एक सिक्का डालो, दो पाओ! 😱", None),
    ("😱 एक सिक्का डालो, दो पाओ!", None),
    ("एक सिक्का डालो, दो पाओ", "exactly one emoji"),
    ("एक सिक्का डालो, दो पाओ 😨", "must end with"),
    ("एक सिक्का डालो, दो पाओ! 😨😱", "exactly one emoji"),
    ("Magic well का सिक्का! 😨", "Devanagari"),
    ("कुआँ " * 15 + "! 😨", "characters"),
    ("एक सिक्का #डालो! 😨", "may not contain"),
])
def test_title_rules(title, fragment):
    found = gate.title_problems(title)
    assert (found == []) if fragment is None else has(found, fragment)


def test_description_must_be_hindi():
    d = story_dict()
    d["description"] = "A greedy moneylender finds a magic well."
    assert has(problems(d), "description must be")


def test_only_the_narrator_may_be_published():
    assert gate.voice_ok({"engine": "gemini-narrator", "identity": "narrator"}) is None
    assert gate.voice_ok({"engine": "chatterbox-narrator-clone", "identity": "narrator"}) is None
    assert gate.voice_ok({"engine": "chatterbox-builtin", "identity": "builtin"})
    assert gate.voice_ok(None)
