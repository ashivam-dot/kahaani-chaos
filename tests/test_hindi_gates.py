"""A Devanagari fixture for every text gate (PLAN.md §7.3, §7.4): each one must reach its comparator as a non-empty
set of Hindi tokens and must fire. A tokeniser like \\w+ or [a-z0-9]+ sees nothing in "साइकिल की लाइट" (vowel signs
are not \\w), so every comparison would be against an empty set and every duplicate would pass; these tests are the
proof that does not happen. CI runs them before anything is published."""
import pytest

from kahaani import cli, gate, hindi, variation, voice, writer
from kahaani.spec import Story

from .conftest import EDITOR_OK, story_dict

SCRIPT = story_dict()
TITLE = SCRIPT["title"]


def premise(d=None):
    return cli.premise_of(Story.from_dict(d or story_dict()))


@pytest.fixture
def spy(monkeypatch):
    """Every call to hindi.words made by a gate, with what it returned."""
    calls = []
    real = hindi.words

    def words(text):
        got = real(text)
        calls.append((text, got))
        return got

    monkeypatch.setattr(hindi, "words", words)
    return calls


def devanagari(calls):
    return [(t, got) for t, got in calls if t and hindi.devanagari_share(t) > 0.5]


def test_the_tokenizer_sees_devanagari():
    import re

    assert re.findall(r"[a-z0-9]+", "साइकिल की लाइट") == []  # the trap these gates must never fall into
    assert hindi.words("साइकिल की लाइट, बिना पैडल!") == ["साइकिल", "की", "लाइट", "बिना", "पैडल"]
    assert hindi.words("ख़ून") == hindi.words("खून") and hindi.words("कुआँ") == hindi.words("कुआं")
    assert hindi.words("😨 | #") == []


def test_the_fixture_passes_every_gate(spy):
    assert gate.check(story_dict(), premise(), [], rotation=True) == []
    seen = devanagari(spy)
    assert seen and all(got for _, got in seen), [t for t, got in seen if not got][:3]


# (a) red lines and religion, in Hindi
@pytest.mark.parametrize("line, topic", [
    ("उसने भगवान से दुआ माँगी।", "religion"), ("पुराने मंदिर के पास कुआँ था।", "religion"),
    ("ज़मीन पर ख़ून फैला था।", "gore"), ("वह ठाकुर का कुआँ था।", "caste"),
    ("यह एक सच्ची कहानी है।", "a claim that it really happened"), ("उस बच्चे को मार दिया गया।", "harm to a child"),
    ("चुड़ैल पुल पर खड़ी थी।", "a banned being"), ("ओझा ने झाड़-फूँक की।", "ritual"),
])
def test_gate_a_hindi_red_lines(spy, line, topic):
    d = story_dict()
    d["beats"][3]["text"] = line
    found = gate.check(d, premise(), [], rotation=False)
    assert any("red line" in p and topic in p for p in found), found
    assert any(t == line and got for t, got in spy)


def test_gate_a_an_exclamation_is_refused_with_a_fix():
    d = story_dict()
    d["beats"][3]["text"] = "हे भगवान, यह क्या हुआ!"
    found = gate.check(d, premise(), [], rotation=False)
    assert any("हाय, बाप रे or अरे" in p for p in found)


# (b) the real world: real places, people and brands
@pytest.mark.parametrize("line", ["वह दिल्ली से आया था।", "दूरदर्शन पर समाचार आ रहे थे।", "गंगा का पानी ठंडा था।"])
def test_gate_b_real_world_names(line):
    d = story_dict()
    d["beats"][3]["text"] = line
    assert any("the real world" in p for p in gate.check(d, premise(), [], rotation=False))


# (d) continuity: the names and the rule come from the bible
def test_gate_d_continuity():
    d = story_dict()
    d["beats"][3]["text"] = "शबनम ने टॉर्च जलाई।"
    d["niyam_id"] = "N99"
    found = gate.check(d, premise(), [], rotation=False)
    assert any("retired name 'शबनम'" in p for p in found) and any("'N99' is not a rule" in p for p in found)


# (f) variation: a known-duplicate Hindi script and title are rejected
def test_gate_f_a_duplicate_script_and_title_are_rejected(spy):
    row = variation.row(story_dict(), premise())
    dup = {**row, "id": "kc-dup", "format": "micro", "object_token": "लालटेन", "anomaly": "x", "location": "y",
           "opening": "z", "resolution": "kindness", "ending": "register-line", "skeleton": "S3"}
    found = variation.problems(row, [dup])
    assert any("repeats 'kc-dup'" in p for p in found) and any("title is too close" in p for p in found)
    assert variation.grams(row["script"]) and set(hindi.words(row["title"]))
    assert all(got for t, got in devanagari(spy))


def test_gate_f_through_the_full_gate():
    d = story_dict()
    history = [{"id": "kc-dup", "format": "micro", "script": " ".join(b["text"] for b in d["beats"]),
                "title": d["title"], "skeleton": "S3"}]
    found = gate.check(d, premise(), history)
    assert any("repeats 'kc-dup'" in p for p in found) and any("title is too close" in p for p in found)


# (g) the hook: object and anomaly in the first ten spoken words, the hook strip, and the title rules
def test_gate_g_the_hook_names_the_object():
    d = story_dict()
    d["beats"][0]["text"] = "उस रात पुल पर कुछ अजीब हुआ, बहुत अजीब।"
    assert any("must name the object 'साइकिल'" in p for p in gate.check(d, premise(), [], rotation=False))
    d["beats"][0]["text"] = "पुल पर साइकिलें अपने आप चमक उठीं।"  # the object with a plural ending still counts
    assert not any("must name the object" in p for p in gate.check(d, premise(), [], rotation=False))


def test_gate_g_the_title_names_the_object_early():
    assert gate.object_in_title(TITLE, "साइकिल")
    assert not gate.object_in_title("उस रात नहर के पुल पर खड़ी पुरानी साइकिल जल उठी! 🚲", "साइकिल")
    assert gate.object_in_title("PCO बूथ की घंटी आधी रात को बजी! 📞", "PCO बूथ")


# (h) made for kids: the metadata blocklist, and the editor's kids_directed flag
@pytest.mark.parametrize("text", ["बच्चों के लिए डरावनी कहानी", "सोने से पहले की कहानी", "एक नैतिक कहानी", "kids story"])
def test_gate_h_metadata_blocklist(text):
    assert gate.mfk_metadata(text)
    d = story_dict()
    d["description"] = "नहर के पुल पर एक साइकिल की कहानी। " + text
    assert any("made for kids" in p for p in gate.check(d, premise(), [], rotation=False))


def test_gate_h_the_editor_reads_it_as_for_kids():
    verdict = {**EDITOR_OK, "kids_directed": True}
    found = writer.edit(story_dict(), lambda messages, schema: verdict, premise())
    assert any("made for kids" in p for p in found)


def test_gate_h_ordinary_hindi_is_not_for_kids():
    assert gate.mfk_metadata(SCRIPT["description"]) == [] and gate.mfk_metadata(TITLE) == []


# (i) pace and ASR, on Devanagari
def test_gate_i_character_error_rate_on_devanagari():
    script = Story.from_dict(story_dict()).narration
    assert voice.cer(script, script) == 0.0
    assert 0 < voice.cer(script, script.replace("साइकिल", "सायकिल").replace("लाइट", "लाईट")) < voice.CER
    assert voice.cer(script, "नमस्ते दोस्तों आज की बात") > voice.CER
    assert voice.cer("ख़ून", "खून") == 0.0


def test_gate_i_measured_narration_bands():
    story = Story.from_dict(story_dict())
    words, spoken, t = [], [], 0.25
    for i, beat in enumerate(story.beats):
        step = 60 / (176 if i == 0 else 165)
        for w in beat.text.split():
            words.append({"text": w, "start": t, "end": t + step * 0.8, "beat": i, "heard": True})
            spoken.append((w, t, t + step * 0.8))
            t += step
    m = voice.measure(story, words, spoken)
    assert voice.problems(m) == [], m
    assert m["coverage"] >= voice.COVERAGE and m["cer"] == 0.0
    assert voice.problems({**m, "onset": 0.6}) and voice.problems({**m, "body_wpm": 120.0})
    assert voice.problems({**m, "body_wpm": 200.0}) and voice.problems({**m, "max_gap": 1.5})
    assert voice.problems({**m, "coverage": 0.9}) and voice.problems({**m, "cer": 0.2})
    assert voice.problems({**m, "hook_wpm": 140.0}) and voice.problems({**m, "hook_wpm": 215.0})


# Punctuation joins, inflections, brands, hashtags and nasal spellings: each one used to slip past a whole-word gate.
@pytest.mark.parametrize("line, topic", [
    ("उसने कहा—भगवान जाने।", "religion"), ("भगवान…कहाँ हो?", "religion"), ("ओझा-तांत्रिक आया।", "ritual"),
    ("लाश।और फिर चुप्पी।", "gore"), ("मस्जिदों के पीछे गली थी।", "religion"), ("पुजारियों ने देखा।", "religion"),
    ("साधुओं की टोली गुज़री।", "religion"), ("हत्याओं की बात होती थी।", "gore"), ("लाशों का ढेर था।", "gore"),
    ("झाड़-फूँक करवाई।", "ritual"), ("भूत-प्रेत की बात थी।", "a banned being"), ("हिंदुओं का मोहल्ला था।", "caste"),
])
def test_red_lines_through_punctuation_and_endings(line, topic):
    assert any(topic in p for p in gate.red_lines_hi(line)), (line, gate.red_lines_hi(line))


@pytest.mark.parametrize("line", ["रामू ने लालटेन उठाई।", "उषा दीदी ने दरवाज़ा खोला।", "फिल्म का हीरो हँसा।",
                                  "ग्रामीण बस रुकी।", "चाचा ने चाय पी।"])
def test_everyday_words_are_not_red_lines(line):
    assert gate.red_lines_hi(line) == [], gate.red_lines_hi(line)


@pytest.mark.parametrize("line", ["उसकी एटलस साइकिल चमकी।", "रसना का गिलास भरा था।", "हीरो साइकिल पुल पर खड़ी थी।",
                                  "विविध भारती पर गाना बजा।", "बजाज स्कूटर रुका।", "उषा की मशीन चल पड़ी।",
                                  "मर्फी रेडियो बोल उठा।", "पारले-जी का पैकेट गिरा।"])
def test_bible_brands_in_hindi(line):
    assert any("the real world" in p for p in gate.red_lines_hi(line)), line


def test_every_bible_brand_has_a_hindi_spelling():
    from kahaani import bible

    assert set(bible.brands()) <= set(gate.BRANDS_HI), set(bible.brands()) - set(gate.BRANDS_HI)


def test_hashtags_cannot_hide_a_blocked_word():
    assert gate.hashtag_problems(["#बच्चोंकीकहानी"]) and gate.hashtag_problems(["#kidsstory"])
    assert gate.hashtag_problems(["#truestory"]) and gate.hashtag_problems(["#सच्चीघटना"])
    assert gate.hashtag_problems(["#एटलससाइकिल"]) and gate.hashtag_problems(["#मंदिरकीघंटी"])
    assert gate.hashtag_problems(["#सन्नाटपुर", "#ग्रामीणकहानी", "#90sगाँव"]) == []
    d = story_dict()
    d["hashtags"] = d["hashtags"] + ["#बच्चोंकीकहानी"]
    assert any("hashtag" in p for p in gate.check(d, premise(), [], rotation=False))


def test_english_red_lines_in_metadata_hold():
    d = story_dict()
    d["description"] = d["description"] + " A true story from the temple."
    found = gate.check(d, premise(), [], rotation=False)
    assert any("true story" in p for p in found) and any("religion" in p for p in found)


def test_channel_and_video_in_metadata_hold_but_not_in_the_story():
    d = story_dict()
    d["description"] = d["description"] + " इस चैनल पर और भी।"
    assert any("चैनल" in p for p in gate.check(d, premise(), [], rotation=False))
    assert gate.banned("टीवी पर एक पुराना वीडियो चल रहा था।") == []


def test_nasal_half_letters_fold_to_anusvara():
    assert hindi.norm("हिन्दू") == hindi.norm("हिंदू") and hindi.norm("सम्बन्ध") == hindi.norm("संबंध")
    assert hindi.norm("पण्डित") == hindi.norm("पंडित") and hindi.norm("कम्बल") == hindi.norm("कंबल")
    assert hindi.norm("अन्य") != hindi.norm("अंय")  # न् before य is not a nasal of its class
    assert any("caste" in p for p in gate.red_lines_hi("हिन्दू मोहल्ला"))


def test_hindi_words_split_at_every_join_and_drop_emoji():
    assert hindi.words("भूत-प्रेत…कहाँ—गया।फिर") == ["भूत", "प्रेत", "कहां", "गया", "फिर"]
    assert hindi.words("साइकिल😶‍🌫️जली👍🏽 1️⃣ 🇮🇳") == ["साइकिल", "जली"]


def test_an_object_that_bends_still_names_itself():
    assert gate.object_in_title("कुएँ ने रात को आवाज़ दी… और गाँव जाग गया! 😨", "कुआँ")
    assert gate.object_in_title("पंखे ने आधी रात को उल्टा घूमना शुरू किया! 🌀", "पंखा")
    assert not gate.object_in_title("पंडित ने कहा… पूरे गाँव में बत्ती गुल! 😨", "पंखा")


def test_skeleton_of_reads_the_agent_not_any_ne():
    assert gate.skeleton_of("रेडियो ने आधी रात को अपने आप गाना बदल दिया! 📻") == "S2"
    assert gate.skeleton_of("प्रभात ने साइकिल रोकी… और लाइट बिना पैडल के जल उठी! 🚲") == "S1"
    assert gate.skeleton_of("रेडियो अपने आप क्यों बोल उठा? 📻") == "S3"


def test_gate_i_final_bands_are_the_format_bands():
    m = {"onset": 0.2, "hook_wpm": 176.0, "body_wpm": 165.0, "coverage": 0.98, "cer": 0.05, "max_gap": 0.9}
    assert voice.problems(m, final=True) == []
    # Inside the hard band (good enough to choose a take) but off the format's 155-175 by more than the slack.
    assert voice.problems({**m, "body_wpm": 145.0}) == []
    assert voice.problems({**m, "body_wpm": 145.0}, final=True)
    assert voice.problems({**m, "body_wpm": 185.0}, final=True)
    assert voice.problems({**m, "hook_wpm": 158.0}, final=True)
    assert voice.problems({**m, "hook_wpm": 198.0}, final=True)


def test_gate_i_whisper_digits_are_read_as_hindi_words():
    assert voice.cer("उन्नीस सौ छियानवे की रात", " ".join(w for w, *_ in voice.as_words(
        [("1996", 0.0, 0.5), ("की", 0.5, 0.7), ("रात", 0.7, 1.0)]))) == 0.0
    assert voice.as_words([("१९९६", 0.0, 0.5)])[0][0] == "उन्नीस सौ छियानवे"


def test_gate_i_onset_and_silence_come_from_the_waveform(tmp_path):
    import numpy as np
    import soundfile as sf

    sr = 24000
    tone = lambda s: 0.3 * np.sin(2 * np.pi * 220 * np.arange(int(s * sr)) / sr)  # noqa: E731
    gap = lambda s: np.zeros(int(s * sr))  # noqa: E731
    sf.write(tmp_path / "a.wav", np.concatenate([gap(0.5), tone(1.0), gap(1.5), tone(1.0)]).astype(np.float32), sr)
    onset, longest = voice.silences(tmp_path / "a.wav")
    assert abs(onset - 0.5) < 0.02 and abs(longest - 1.5) < 0.05
    story = Story.from_dict(story_dict())
    m = voice.measure(story, [{"text": "x", "start": 0.1, "end": 0.4, "beat": 0}], [("x", 0.1, 0.4)],
                      tmp_path / "a.wav")
    assert m["onset_whisper"] == 0.1 and m["onset"] == onset
    found = voice.problems(m)
    assert any("speech starts" in p for p in found) and any("silence of" in p for p in found)
