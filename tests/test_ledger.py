from kahaani import ledger


def test_round_trip_keeps_hindi():
    ledger.save("published", [{"id": "a", "title": "कुआँ बोला! 😨"}])
    assert ledger.load("published", []) == [{"id": "a", "title": "कुआँ बोला! 😨"}]
    assert "कुआँ" in (ledger.STATE / "published.json").read_text(encoding="utf-8")
    assert ledger.load("missing", {"x": 1}) == {"x": 1}


def test_ready_buffer_to_published():
    ledger.add_ready({"id": "b", "made_at": "2026-10-13T06:00:00+00:00"})
    ledger.add_ready({"id": "a", "made_at": "2026-10-12T06:00:00+00:00"})
    ledger.add_ready({"id": "a", "made_at": "2026-10-12T06:00:00+00:00", "tag": "ready-a"})
    assert [r["id"] for r in ledger.ready()] == ["a", "b"] and ledger.ready()[0]["tag"] == "ready-a"
    ledger.record_publish({**ledger.ready()[0], "slot": "2026-10-13T07:00:00Z", "video_id": "v"})
    assert [r["id"] for r in ledger.ready()] == ["b"]
    assert ledger.published()[0]["video_id"] == "v"
    assert [r["id"] for r in ledger.history()] == ["a", "b"]
    ledger.mark("a", release_left=True)
    assert ledger.published()[0]["release_left"] is True


def test_premises_are_given_up_after_three_tries():
    assert ledger.retry("p001", "a") and ledger.retry("p001", "b")
    assert not ledger.retry("p001", "c")
    assert ledger.given_up() == {"p001"}


def test_health_keeps_both_runs():
    ledger.save_health("produce", {"ok": True, "at": "1"})
    ledger.save_health("publish", {"ok": False, "at": "2"})
    ledger.save_health("produce", {"ok": False, "at": "3"})
    assert ledger.load("health", {}) == {"produce": {"ok": False, "at": "3"}, "publish": {"ok": False, "at": "2"}}
