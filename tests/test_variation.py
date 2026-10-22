import pytest

from kahaani import cli, config, gate, variation
from kahaani.spec import Story

from .conftest import story_dict


def premise():
    return cli.premise_of(Story.from_dict(story_dict()))


def earlier(**over):
    """A previous F1 Short that shares nothing with the fixture."""
    row = {"id": "kc-old", "format": config.FORMAT, "object_token": "लालटेन", "anomaly": "लौ का उल्टा जलना",
           "location": "पुराना कुआँ", "resolution": "kindness", "ending": "register-line", "skeleton": "S3",
           "title": "लालटेन की लौ नीचे की तरफ़ क्यों जलती है? 🏮", "opening": "कुएँ पर",
           "script": "कुएँ पर रखी लालटेन की लौ उल्टी जल रही थी। झब्बू ने उसे छुआ तक नहीं, बस रजिस्टर खोला।"}
    return {**row, **over}


def mine():
    return variation.row(story_dict(), premise())


def test_the_fixture_row_has_real_hindi_tokens():
    row = mine()
    assert row["object_token"] == "साइकिल" and row["skeleton"] == "S1" and row["opening"]
    assert len(variation.grams(row["script"])) > 50
    assert variation.problems(row, [earlier()]) == []


def test_an_identical_script_is_rejected():
    row = mine()
    found = variation.problems(row, [earlier(script=row["script"], id="kc-dup")])
    assert any("repeats 'kc-dup'" in p and "1.00" in p for p in found)


def test_a_lightly_reworded_script_is_still_rejected():
    row = mine()
    reworded = row["script"].replace("साइकिल", "सायकिल").replace("।", ",")
    found = variation.problems(row, [earlier(script=reworded, id="kc-near")])
    assert any("repeats 'kc-near'" in p for p in found)


def test_nukta_and_chandrabindu_do_not_hide_a_repeat():
    row = mine()
    folded = row["script"].replace("ड़", "ड").replace("ँ", "ं").replace("ख़", "ख")
    assert variation.problems(row, [earlier(script=folded, id="kc-fold")])


def test_a_duplicate_title_is_rejected():
    row = mine()
    found = variation.problems(row, [earlier(title=row["title"], id="kc-t")])
    assert any("title is too close to 'kc-t'" in p for p in found)


@pytest.mark.parametrize("field", ["object_token", "anomaly", "location", "opening"])
def test_recent_object_anomaly_place_and_opening_are_refused(field):
    row = mine()
    assert any(f"was used in one of the last {variation.RECENT}" in p
               for p in variation.problems(row, [earlier(**{field: row[field]})]))


def test_something_older_than_the_window_may_return():
    row = mine()
    history = [earlier(object_token=row["object_token"], id="kc-0")] + \
        [earlier(id=f"kc-{i}", object_token=f"चीज़{i}", anomaly=f"अजीब{i}", location=f"जगह{i}", opening=f"शुरू{i}",
                 skeleton="S3" if i % 2 else "S2", resolution="kindness", ending="register-line",
                 script=f"यह बिल्कुल अलग कहानी {i} है जिसमें कोई और बात होती है", title=f"अलग शीर्षक {i}")
         for i in range(1, variation.RECENT + 1)]
    assert variation.problems(row, history) == []


def test_resolution_and_ending_rotate_against_the_previous_short_only():
    row = mine()
    found = variation.problems(row, [earlier(resolution=row["resolution"], ending=row["ending"])])
    assert any("resolution type" in p for p in found) and any("ending type" in p for p in found)
    older = [earlier(resolution=row["resolution"], ending=row["ending"], id="a"), earlier(id="b")]
    assert variation.problems(row, older) == []


def test_a_title_skeleton_runs_at_most_once_in_three():
    row = mine()
    assert variation.problems(row, [earlier(skeleton="S1", id="a"), earlier(id="b", skeleton="S2")])
    assert variation.problems(row, [earlier(skeleton="S1", id="a"), earlier(id="b", skeleton="S2"),
                                    earlier(id="c", skeleton="S3")]) == []


def test_other_formats_do_not_count():
    row = mine()
    assert variation.problems(row, [earlier(format="", script=row["script"], object_token=row["object_token"])]) == []


def test_an_empty_token_set_is_a_problem_not_a_pass():
    with pytest.raises(ValueError):
        variation.jaccard(set(), {("a",)})
    found = variation.problems({"script": "।। … साइकिल!", "title": "😨 …"}, [earlier()])
    assert any("empty token set" in p for p in found)
    assert sum("empty token set" in p for p in found) == 2


def test_the_gate_runs_the_audit_with_the_ledger_history():
    d = story_dict()
    history = [earlier(script=" ".join(b["text"] for b in d["beats"]), id="kc-dup")]
    assert any("repeats 'kc-dup'" in p for p in gate.check(d, premise(), history))
