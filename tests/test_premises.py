import itertools
import json
from collections import Counter

import pytest

from kahaani import gate, ledger, premises


def row(p, n=0):
    return {"id": f"s{n}", "premise": p["id"], "subgenre": p["subgenre"], "motifs": p["motifs"], "made_at": f"{n:04d}"}


def test_the_bank_has_sixty_clean_distinct_premises():
    bank = json.loads(premises.BANK.read_text(encoding="utf-8"))
    assert len(bank) == 60 and len({p["id"] for p in bank}) == 60
    assert Counter(p["subgenre"] for p in bank) == {s: 12 for s in gate.SUBGENRES}
    for p in bank:
        assert 2 <= len(p["motifs"]) <= 3 and all(map(premises.MOTIF.match, p["motifs"])), p["id"]
        assert p["hi"] and p["en"], p["id"]
        assert not gate.red_lines_hi(p["hi"]) and not gate.red_lines_en(p["en"]) and not gate.banned(p["hi"]), p["id"]
    assert [(a["id"], b["id"]) for a, b in itertools.combinations(bank, 2) if premises.similar(a, b)] == []


def test_first_pick_follows_bank_order():
    assert premises.select([])["id"] == "p001"


def test_recent_subgenres_and_motifs_are_refused():
    bank = premises.bank()
    first = premises.select([])
    history = [row(first)]
    nxt = premises.select(history)
    assert nxt["subgenre"] != first["subgenre"] and not set(nxt["motifs"]) & set(first["motifs"])


def test_rotation_over_many_shorts_keeps_every_rule():
    history = []
    for n in range(30):
        pick = premises.select(history)
        assert pick["id"] not in {r["premise"] for r in history}
        assert pick["subgenre"] not in {r["subgenre"] for r in history[-premises.RECENT_SUBGENRES:]}
        assert not set(pick["motifs"]) & {m for r in history[-premises.RECENT_MOTIFS:] for m in r["motifs"]}
        history.append(row(pick, n))
    assert set(r["subgenre"] for r in history[:5]) == set(gate.SUBGENRES)


def test_learned_lift_steers_the_pick():
    lifts = {"bhoot-rahasya": 1.35}
    pick = premises.select([], lift=lambda s: lifts.get(s, 1.0))
    assert pick["subgenre"] == "bhoot-rahasya"


def test_a_rested_subgenre_beats_a_slightly_better_recent_one():
    bank = premises.bank()
    by = {s: [p for p in bank if p["subgenre"] == s] for s in gate.SUBGENRES}
    history = [row(by["jadui-inaam"][1], 0), row(by["samay-chakra"][0], 1), row(by["chatur-chaal"][0], 2)]
    pick = premises.select(history, lift=lambda s: 1.1 if s == "jadui-inaam" else 1.0)
    assert pick["subgenre"] in ("shraapit-cheez", "bhoot-rahasya")


def test_given_up_premises_are_skipped():
    for _ in range(ledger.TRIES):
        ledger.retry("p001", "hold: test")
    assert premises.select([])["id"] != "p001"


def test_no_premise_left():
    with pytest.raises(premises.NoPremise):
        premises.select([], premises=[])


def test_clean_keeps_only_valid_new_premises():
    existing = [{"id": "p1", "hi": "एक बिल्ली रोज़ रात चाय की दुकान पर सिक्के छोड़ जाती है।",
                 "en": "A cat leaves coins at a tea stall every night."}]
    new = [
        {"hi": "पुरानी घड़ी हर रात तेरह बजाती है और गली एक घंटा पीछे चली जाती है।",
         "en": "An old clock strikes thirteen and the lane slips an hour back.", "subgenre": "samay-chakra",
         "motifs": ["wall-clock", "lane"]},
        {"hi": "एक बिल्ली रोज़ रात चाय की दुकान पर सिक्के छोड़ जाती है।", "en": "A cat leaves coins at a tea stall.",
         "subgenre": "jadui-inaam", "motifs": ["cat", "coin"]},
        {"hi": "मंदिर की घंटी अपने आप बजती है।", "en": "A temple bell rings itself.", "subgenre": "bhoot-rahasya",
         "motifs": ["bell", "night"]},
        {"hi": "एक जादुई कलम जो सच लिखती है।", "en": "A pen that writes the truth.", "subgenre": "comedy",
         "motifs": ["pen", "ink"]},
        {"hi": "एक जादुई कलम जो सच लिखती है।", "en": "A pen that writes the truth.", "subgenre": "shraapit-cheez",
         "motifs": ["Pen Nib", "ink"]},
        {"hi": "पुरानी घड़ी हर रात तेरह बजाती है और गली एक घंटा पीछे जाती है।",
         "en": "An old clock strikes thirteen and the lane slips back.", "subgenre": "samay-chakra",
         "motifs": ["clock", "lane"]},
    ]
    kept = premises.clean(new, existing, "202610131200")
    assert [p["en"] for p in kept] == ["An old clock strikes thirteen and the lane slips an hour back."]
    assert kept[0]["id"] == "g202610131200-01"


def test_refill_only_when_few_are_left(tmp_path, monkeypatch):
    asked = []

    def ask(messages, schema):
        asked.append(messages)
        return {"premises": [{"hi": "रेलवे स्टेशन की आख़िरी बेंच पर बैठने वाला हर यात्री कल सुबह उठता है।",
                              "en": "Whoever sits on the last station bench wakes up yesterday morning.",
                              "subgenre": "samay-chakra", "motifs": ["station-bench", "train"]}]}

    assert premises.refill([], ask) == 0 and asked == []
    small = tmp_path / "bank.json"
    bank = json.loads(premises.BANK.read_text(encoding="utf-8"))[:3]
    small.write_text(json.dumps(bank), encoding="utf-8")
    monkeypatch.setattr(premises, "BANK", small)
    assert premises.refill([], ask) == 1
    assert len(premises.bank()) == 4 and ledger.load("premises", [])[0]["id"].startswith("g")
    assert "Whoever sits" not in asked[0][0]["content"]
    premises.refill([], ask)
    assert len(premises.bank()) == 4
    assert "Whoever sits on the last station bench" in asked[1][0]["content"]
