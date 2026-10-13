import pytest

from kahaani import writer

from .conftest import EDITOR_OK, draft

PREMISE = {"id": "p003", "subgenre": "jadui-inaam", "motifs": ["well", "coin", "shadow"],
           "hi": "एक कुआँ हर सिक्के को दुगना लौटाता है।", "en": "A well doubles every coin."}


class Room:
    """Plays writer and editor: the drafts in order, then the editor verdicts in order (the last repeats)."""

    def __init__(self, drafts, verdicts=(EDITOR_OK,)):
        self.drafts, self.verdicts, self.calls = list(drafts), list(verdicts), []

    def __call__(self, messages, schema):
        self.calls.append((messages, schema))
        if schema is writer.SCHEMA:
            return self.drafts.pop(0)
        return self.verdicts.pop(0) if len(self.verdicts) > 1 else self.verdicts[0]


def long_hook():
    d = draft()
    d["beats"][0]["text"] = "इस पुराने कुएँ में एक चाँदी का सिक्का डालो, तो दो चमकते सिक्के वापस आते हैं।"
    return d


def test_a_clean_draft_goes_through_the_editor():
    room = Room([draft()])
    out, log = writer.write(PREMISE, [], room)
    assert out["title"] == draft()["title"] and log == [{"attempt": 0, "stage": "editor", "problems": []}]
    assert [schema for _, schema in room.calls] == [writer.SCHEMA, writer.EDIT_SCHEMA]


def test_gate_problems_are_sent_back_for_a_repair():
    room = Room([long_hook(), draft()])
    out, log = writer.write(PREMISE, [], room)
    assert [entry["stage"] for entry in log] == ["gates", "editor"]
    repair = room.calls[1][0]
    assert repair[-2]["role"] == "assistant" and "the hook" in repair[-1]["content"]


def test_editor_problems_are_sent_back_for_a_repair():
    unclear = {**EDITOR_OK, "twist_clear": False, "problems": ["Beat 10 should say what the well took."]}
    room = Room([draft(), draft()], [unclear, EDITOR_OK])
    out, log = writer.write(PREMISE, [], room)
    assert log[0]["problems"] == ["Beat 10 should say what the well took.", "the twist is unclear"]
    assert log[1]["problems"] == []


def test_hold_after_two_repairs():
    room = Room([long_hook()] * 3)
    with pytest.raises(writer.WriterHold, match="hold: no draft of p003 passed after 2 repairs"):
        writer.write(PREMISE, [], room)
    assert sum(schema is writer.SCHEMA for _, schema in room.calls) == writer.REPAIRS + 1


def test_the_editor_flags_spoilers_and_red_lines():
    spoiled = {**EDITOR_OK, "title_spoils_twist": True, "red_line": True}
    found = writer.edit(draft(), lambda m, s: spoiled)
    assert found == ["the title or description gives the twist away", "the editor found a red-line topic"]


def test_tidy_takes_the_hook_from_beat_one():
    d = draft()
    d["hook"] = "something else"
    d["twist_beat"] = "10"
    d["beats"][0]["text"] = "  इस कुएँ   में एक सिक्का डालो, दो वापस आते हैं। "
    d["hashtags"] = ["#कहानी", "no hash", "#a b", 3]
    out = writer.tidy(d)
    assert out["hook"] == out["beats"][0]["text"] == "इस कुएँ में एक सिक्का डालो, दो वापस आते हैं।"
    assert out["twist_beat"] == 10 and out["hashtags"] == ["#कहानी"]


def test_the_brief_names_the_required_ending_and_used_openings():
    history = [{"ending": "twist-reveal", "opening": "इस कुएँ"}]
    brief = writer.messages(PREMISE, history)[1]["content"]
    assert "ENDING (dilemma)" in brief and "'इस कुएँ'" in brief and PREMISE["hi"] in brief
