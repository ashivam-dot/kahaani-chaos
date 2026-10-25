import pytest

from kahaani import bible, premises, writer

from .conftest import EDITOR_OK, draft

PREMISE = premises.premise_for(bible.micro_bank()[0], [])


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
    d["beats"][0]["text"] = "उस रात नहर के पुराने पुल पर खड़ी प्रभात की साइकिल की लाइट बिना पैडल जल उठी।"
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


def test_overlong_hindi_hook_repair_supplies_exact_valid_bank_opening():
    from kahaani import hindi

    entry = next(p for p in premises.bank() if p["id"] == "e07")
    premise = premises.premise_for(entry, [])
    previous = writer.tidy(long_hook())
    message = writer.messages(premise, [], ["beat 1 (the hook) has 11 words; at most 10"], previous)[-1]["content"]
    assert len(hindi.words(premise["hook_line"])) == 10
    assert f"verbatim as beat 1's spoken text: {premise['hook_line']}" in message
    assert "actual Hindi hook tokens" in message and "1: उस" in message
    assert previous["beats"][0]["text"] == long_hook()["beats"][0]["text"]


def test_overlong_bank_hook_is_never_offered_as_a_valid_repair():
    premise = {**PREMISE, "hook_line": long_hook()["beats"][0]["text"]}
    message = writer.messages(premise, [], ["overlong hook"], writer.tidy(long_hook()))[-1]["content"]
    assert "actual Hindi hook tokens" in message and "Use this bank opening verbatim" not in message


def test_editor_problems_are_sent_back_for_a_repair():
    unclear = {**EDITOR_OK, "rule_clear": False, "problems": ["Beat 4 should say what Jhabbu tells them."]}
    room = Room([draft(), draft()], [unclear, EDITOR_OK])
    out, log = writer.write(PREMISE, [], room)
    assert log[0]["problems"] == ["Beat 4 should say what Jhabbu tells them.",
                                  "the rule of the night does not clearly solve it"]
    assert log[1]["problems"] == []


def test_a_repair_that_cuts_scenes_short_keeps_the_previous_scenes():
    lazy = draft()
    for b in lazy["beats"][1:]:
        b["scene"], b["people"] = "Same as before.", []
    room = Room([long_hook(), lazy])
    out, log = writer.write(PREMISE, [], room)
    assert [entry["stage"] for entry in log] == ["gates", "editor"] and log[-1]["problems"] == []
    assert [b["scene"] for b in out["beats"]] == [b["scene"] for b in draft()["beats"]]
    assert out["beats"][1]["people"] == draft()["beats"][1]["people"]


def test_a_repair_with_a_new_beat_count_is_taken_as_written():
    shorter = draft()
    shorter["beats"] = shorter["beats"][:-1]
    shorter["beats"][1]["scene"] = "Same."
    assert writer.carry(draft(), writer.tidy(shorter))["beats"][1]["scene"] == "Same."


def test_hold_after_two_repairs():
    room = Room([long_hook()] * 3)
    with pytest.raises(writer.WriterHold, match="hold: no draft of e01 passed after 2 repairs"):
        writer.write(PREMISE, [], room)
    assert sum(schema is writer.SCHEMA for _, schema in room.calls) == writer.REPAIRS + 1


def test_the_editor_flags_spoilers_and_red_lines():
    spoiled = {**EDITOR_OK, "title_spoils_turn": True, "red_line": True, "canon_ok": False}
    found = writer.edit(draft(), lambda m, s: spoiled, PREMISE)
    assert found == ["the draft contradicts the bible (people, props or the rule)",
                     "the title or description gives the turn away", "the editor found a red-line topic"]


def test_tidy_takes_the_hook_from_beat_one():
    d = draft()
    d["hook"] = "something else"
    d["twist_beat"] = "4"
    d["beats"][0]["text"] = "  पुल पर   साइकिल की लाइट बिना पैडल जल उठी। "
    d["hashtags"] = ["#कहानी", "no hash", "#a b", 3]
    out = writer.tidy(d)
    assert out["hook"] == out["beats"][0]["text"] == "पुल पर साइकिल की लाइट बिना पैडल जल उठी।"
    assert out["twist_beat"] == 4 and out["hashtags"] == ["#कहानी"]


def test_tidy_takes_the_cast_looks_from_the_bible():
    d = draft()
    d["cast"] = ["jhabbu"]
    out = writer.tidy(d)
    ids = [c["id"] for c in out["cast"]]
    assert ids[0] == "jhabbu" and set(ids) == {"jhabbu", "prabhat", "nuzhat", "shailesh"}
    assert out["cast"][0]["look"] == bible.image_token("jhabbu") and out["cast"][0]["name"] == "झब्बू"


def test_the_writer_schema_asks_for_every_f1_field():
    need = {"title", "hook_strip", "object_token", "anomaly", "niyam_id", "resolution_type", "ending_type",
            "turn_beat", "heart_beat", "cast", "beats", "description", "hashtags"}
    assert need <= set(writer.SCHEMA["properties"]) and need <= set(writer.SCHEMA["required"])


def test_the_brief_carries_the_entry_the_bible_and_used_openings():
    history = [{"format": "micro", "ending": "register-line", "opening": "उस रात"}]
    brief = writer.messages(PREMISE, history)[1]["content"]
    assert PREMISE["ending_type"] in brief and "'उस रात'" in brief and PREMISE["logline"] in brief
    assert PREMISE["object_token"] in brief and PREMISE["niyam_id"] in brief and "झब्बू" in brief
    assert PREMISE["title_skeleton"] in brief
