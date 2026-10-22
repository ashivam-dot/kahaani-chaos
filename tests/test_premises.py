import pytest

from kahaani import bible, config, gate, hindi, ledger, premises


def made(entry, history, n=0):
    return {**premises.row(entry, history), "id": f"s{n}", "made_at": f"{n:04d}"}


def test_the_bank_has_forty_clean_distinct_entries():
    bank = premises.bank()
    assert len(bank) == 40 and len({e["id"] for e in bank}) == 40
    for e in bank:
        assert e["ending_type"] in gate.ENDINGS and e["resolution_type"] in gate.RESOLUTIONS, e["id"]
        assert e["title_skeleton"] in gate.SKELETONS and e["niyam_id"] in bible.niyam(), e["id"]
        assert e["place_id"] in bible.places(), e["id"]
        assert hindi.words(e["object_token"]) and hindi.words(e["anomaly"]), e["id"]
        for field in ("hook_line", "logline", "heart_beat", "title"):
            assert not gate.red_lines_hi(e[field]) and not gate.banned(e[field]), (e["id"], field)
    titles = [hindi.norm(e["title"]) for e in bank]
    assert len(set(titles)) == len(titles)


def test_first_pick_follows_bank_order():
    assert premises.select([])["id"] == "e01"


def test_every_entry_is_used_once_and_every_pick_keeps_the_rotation():
    history = []
    for n in range(40):
        pick = premises.select(history)
        assert premises.fits(pick, history) == [], (n, pick["id"])
        history.append(made(pick, history, n))
    assert sorted(r["premise"] for r in history) == sorted(e["id"] for e in premises.bank())
    for a, b in zip(history, history[1:]):
        assert a["ending"] != b["ending"] and a["resolution"] != b["resolution"]
    for a, b, c in zip(history, history[1:], history[2:]):
        assert c["skeleton"] not in (a["skeleton"], b["skeleton"])
    for i, r in enumerate(history):
        recent = history[max(0, i - premises.RECENT):i]
        assert hindi.norm(r["object_token"]) not in {hindi.norm(x["object_token"]) for x in recent}
    assert "next-raat-tease" not in {r["ending"] for r in history}
    with pytest.raises(premises.NoPremise):
        premises.select(history)


def test_a_recent_skeleton_ending_or_object_is_refused():
    e01 = premises.bank()[0]
    history = [made(e01, [])]
    found = premises.fits({**e01, "id": "x"}, history)
    assert any("title skeleton" in f for f in found) and any("ending" in f for f in found)
    assert any("object_token" in f for f in found) and any("resolution" in f for f in found)


def test_a_tease_becomes_the_next_ending_until_f3_exists():
    tease = next(e for e in premises.bank() if e["ending_type"] == "next-raat-tease")
    assert premises.ending_for(tease, []) == "loop-back"
    history = [{"format": config.FORMAT, "ending": "loop-back"}]
    assert premises.ending_for(tease, history) == "register-line"
    assert premises.premise_for(tease, history)["ending_type"] == "register-line"


def test_old_kahaani_rows_do_not_count_for_rotation():
    e01 = premises.bank()[0]
    old = [{"premise": "p001", "skeleton": e01["title_skeleton"], "ending": e01["ending_type"]}]
    assert premises.fits(e01, old) == []


def test_learned_lift_steers_the_pick():
    lifts = {("skeleton", "S3"): 1.3}
    pick = premises.select([], lift=lambda f, v: lifts.get((f, v), 1.0))
    assert pick["title_skeleton"] == "S3"


def test_given_up_entries_are_skipped():
    for _ in range(ledger.TRIES):
        ledger.retry("e01", "hold: test")
    assert premises.select([])["id"] != "e01"


def test_no_premise_left():
    with pytest.raises(premises.NoPremise):
        premises.select([], premises=[])


def test_low_bank_raises_a_health_note():
    bank = premises.bank()
    assert premises.low([]) is None
    history = [{"premise": e["id"]} for e in bank[:31]]
    assert "only 9 unused" in premises.low(history)
    assert premises.low([{"premise": e["id"]} for e in bank[:30]]) is None
