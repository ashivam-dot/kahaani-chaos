import copy

import pytest

from kahaani import gate, moment, premises
from kahaani.spec import Story


def story_of(n=1):
    bank = moment.bank()
    entry = next(e for e in bank if e["ep_n"] == n)
    prev = next((e for e in bank if e["ep_n"] == n - 1), None)
    return moment.build_story(entry, prev, f"kc-test-{n}")


def has(found, fragment):
    return any(fragment in p for p in found)


def test_every_bank_entry_fits_the_schema():
    assert len(moment.bank()) >= 3
    for entry in moment.bank():
        assert moment.schema_problems(entry) == [], entry["id"]


def test_the_bank_has_unique_ids_and_consecutive_episode_numbers():
    ns = [e["ep_n"] for e in moment.bank()]
    assert ns == sorted(set(ns)) and ns[0] == 1
    assert len({e["id"] for e in moment.bank()}) == len(ns)


def test_timeline_adds_up_and_the_first_episode_has_no_tail():
    first, second = moment.timeline(story_of(1)), moment.timeline(story_of(2))
    assert first["tail"] is None and second["tail"][1] - second["tail"][0] == moment.TAIL
    assert first["duration"] == pytest.approx(len(story_of(1).shots) * moment.SHOT + moment.END_CARD + moment.LOOP)
    assert second["duration"] - first["duration"] == pytest.approx(moment.TAIL)
    assert first["words"] == [] and first["voice"] == {"engine": "none", "identity": "wordless"}
    assert gate.MOMENT_DURATION[0] <= first["duration"] <= gate.MOMENT_DURATION[1]


def test_the_story_round_trips():
    s = story_of(2)
    back = Story.from_dict(s.__dict__ | {})
    assert back.__dict__ == s.__dict__
    assert s.mode == "moment" and s.format == "moment"


def test_select_takes_the_lowest_unused_and_skips_what_ran():
    assert moment.select([])["ep_n"] == 1
    ran = [{"format": "moment", "premise": "m01", "place_id": "halt", "anomaly_type": "timetable",
            "cta_arm": moment.bank()[0]["cta_arm"]}]
    assert moment.select(ran)["id"] != "m01"


def test_select_alternates_the_call_to_action_arm_when_it_can():
    bank = copy.deepcopy(moment.bank())
    for i, e in enumerate(bank):
        e["cta_arm"] = "AB"[i % 2]
    first = moment.select([], bank)
    ran = [{"format": "moment", "premise": first["id"], "place_id": first["place_id"],
            "anomaly_type": first["anomaly"]["card"], "cta_arm": first["cta_arm"]}]
    assert moment.select(ran, bank)["cta_arm"] != first["cta_arm"]


def test_the_same_place_cannot_come_back_at_once():
    e = moment.bank()[0]
    ran = [{"format": "moment", "premise": "x", "place_id": e["place_id"], "anomaly_type": "other"}]
    assert has(moment.caps_problems(e, ran), "place")
    with pytest.raises(premises.NoPremise):
        moment.select(ran, [e])


def test_the_same_card_type_is_spaced_out():
    e = moment.bank()[0]
    ran = [{"format": "moment", "premise": "x", "place_id": "elsewhere", "anomaly_type": e["anomaly"]["card"]}]
    assert has(moment.caps_problems(e, ran), "card type")


def test_sfx_cues_follow_the_shots_and_a_page_turn_opens_the_tail():
    cues = moment.sfx_cues(story_of(2))
    assert any(c["cue"] == "page_turn" for c in cues)
    assert not any(c["cue"] == "page_turn" for c in moment.sfx_cues(story_of(1)))
    assert all(c["at"] >= 0 for c in cues)


def test_the_card_is_a_small_part_of_the_first_frame():
    s = story_of(1)
    assert moment.exposure(s, s.shots[0]) <= gate.MOMENT_CARD_FRAME0


def good(n=1):
    return story_of(n).__dict__ | {}


def test_a_good_moment_passes_its_gate():
    assert gate.check_moment(good(), [], rotation=False) == []
    assert gate.check_moment(good(2), [], rotation=False) == []


def test_a_moment_with_a_bad_title_is_held():
    d = good()
    d["title"] = "छोटा शीर्षक"
    assert has(gate.check_moment(d, [], rotation=False), "title")


def test_too_few_shots_are_held():
    d = good()
    d["shots"] = d["shots"][:8]
    assert gate.check_moment(d, [], rotation=False)


def good_stats():
    return {"runtime": 23.8, "duration": 23.8, "changes_per_10s": 8.0, "flicker_step": 0.02,
            "loudness": {"lufs": -14.1, "true_peak": -1.4}, "quiet_stretch": 0.3, "motif_lufs": -20.0,
            "tail": 0.0, "loop_diff": 9.0}


def test_render_stats_inside_their_bands_pass():
    assert gate.check_moment(good(), [], good_stats(), rotation=False) == []


@pytest.mark.parametrize("key,value,fragment", [
    ("changes_per_10s", 3.0, "picture"),
    ("changes_per_10s", 20.0, "picture"),
    ("quiet_stretch", 4.0, "quiet"),
    ("loudness", {"lufs": -20.0, "true_peak": -3.0}, "LUFS"),
    ("loudness", {"lufs": -14.0, "true_peak": 0.5}, "peak"),
    ("flicker_step", 0.2, "flicker"),
])
def test_render_stats_outside_their_bands_are_held(key, value, fragment):
    stats = good_stats() | {key: value}
    assert has(gate.check_moment(good(), [], stats, rotation=False), fragment)


def test_a_moment_voice_must_be_the_wordless_record():
    assert gate.voice_ok({"engine": "none", "identity": "wordless"}, "moment") is None
    assert gate.voice_ok({"engine": "none", "identity": "wordless"}) is not None
    assert gate.voice_ok({"engine": "edge", "identity": "narrator"}, "moment") is not None


def moment_ledger_row(entry):
    return {"format": "moment", "id": f"kc-{entry['id']}", "premise": entry["id"], "place_id": entry["place_id"],
            "anomaly_type": entry["anomaly"]["card"], "cta_arm": entry["cta_arm"]}


def test_the_card_gap_never_exceeds_what_the_bank_can_fill():
    assert moment.card_apart() <= len({e["anomaly"]["card"] for e in moment.bank()}) - 1
    assert moment.card_apart(moment.bank()[:1]) == 1


def test_every_episode_of_the_bank_can_be_planned_in_turn():
    history = []
    for _ in moment.bank():
        entry = moment.select(history)
        history.append(moment_ledger_row(entry))
    assert [r["premise"] for r in history] == [e["id"] for e in sorted(moment.bank(), key=lambda e: e["ep_n"])]


def test_a_hold_names_why_no_moment_fits():
    history = [moment_ledger_row(e) for e in moment.bank()]
    with pytest.raises(premises.NoPremise, match="bank is spent|none clear"):
        moment.select(history)


def test_a_replay_of_a_published_moment_is_refused(tmp_path, monkeypatch):
    from kahaani import config, ledger

    monkeypatch.setattr(config, "FORMAT", "moment")
    s = story_of(1)
    s.save(tmp_path / "story.json")
    ledger.add_ready({"id": s.id, "premise": s.premise, "made_at": "2026-10-13", "format": "moment"})
    status = moment.plan(tmp_path / "plan", dry=False, replay=tmp_path / "story.json")
    assert "already made" in status["error"] and not status["paint"]
    assert moment.plan(tmp_path / "dry", dry=True, replay=tmp_path / "story.json")["paint"]


def test_banned_words_and_red_lines_in_a_moment_are_held():
    d = good()
    d["description"] = d["description"] + " like subscribe share"
    assert gate.check_moment(d, [], rotation=False)
    d = good()
    d["stills"] = [dict(d["stills"][0], scene="a cartoon with a gun and blood on the wall")] + d["stills"][1:]
    assert has(gate.check_moment(d, [], rotation=False), "still prompt") or gate.check_moment(d, [], rotation=False)
