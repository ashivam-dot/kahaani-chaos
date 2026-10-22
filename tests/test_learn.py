from datetime import datetime, timezone
from types import SimpleNamespace

from kahaani import config, learn, ledger

from .conftest import CHANNEL


def video(i, skeleton, views, pct=None, subs=None):
    return {"id": f"kc-{i}", "skeleton": skeleton, "format": "micro", "views_48h": views, "viewed_pct": pct,
            "subs": subs}


def test_no_lift_below_min_samples():
    out = learn.learn([video(i, "S1", 100 + i) for i in range(learn.MIN_SAMPLES - 1)])
    assert out["lifts"] == {}


def test_views_only_score_without_analytics():
    vids = [video(i, "S1", 1000) for i in range(4)] + [video(i + 4, "S2", 100) for i in range(4)]
    out = learn.learn(vids)
    assert out["score"] == "views only (no Analytics)"
    s1, s2 = out["lifts"]["skeleton:S1"]["lift"], out["lifts"]["skeleton:S2"]["lift"]
    assert s1 > 1.0 > s2 and learn.LIFT_RANGE[0] <= s2 and s1 <= learn.LIFT_RANGE[1]


def test_viewed_percent_outweighs_raw_views():
    # S1 gets slightly more views but is abandoned; S2 is watched to the end and converts
    vids = [video(i, "S1", 600, pct=40.0, subs=0) for i in range(4)] + \
        [video(i + 4, "S2", 500, pct=95.0, subs=5) for i in range(4)]
    out = learn.learn(vids)
    assert out["score"].startswith("0.5 viewed%")
    assert out["lifts"]["skeleton:S2"]["lift"] > 1.0 > out["lifts"]["skeleton:S1"]["lift"]


def test_lift_reads_the_ledger_and_keeps_the_old_one_argument_form():
    ledger.save("performance", {"learned": {"lifts": {"skeleton:S2": {"lift": 9.0}, "subgenre:x": {"lift": 0.9}}}})
    assert learn.lift("skeleton", "S2") == learn.LIFT_RANGE[1]
    assert learn.lift("x") == 0.9 and learn.lift("skeleton", "S3") == 1.0


def test_analytics_rows_become_viewed_percent_and_subs():
    seen = {}

    def query(**kw):
        seen.update(kw)
        return SimpleNamespace(execute=lambda: {"rows": [["v1", 120, 71.5, 3]]})

    client = SimpleNamespace(reports=lambda: SimpleNamespace(query=query))
    assert learn.analytics(client, ["v1"], "2026-10-01", "2026-10-22") == {"v1": {"viewed_pct": 71.5, "subs": 3}}
    assert seen["metrics"] == "views,averageViewPercentage,subscribersGained" and seen["filters"] == "video==v1"


def test_a_missing_analytics_scope_is_recorded(monkeypatch):
    monkeypatch.setattr(config, "CHANNEL_ID", CHANNEL)
    from kahaani import youtube

    monkeypatch.setattr(youtube, "identity", lambda api: {"id": CHANNEL})
    monkeypatch.setattr(youtube, "recent", lambda api, ch: [{"id": "v1", "statistics": {"viewCount": "50"}}])
    ledger.save("published", [{"id": "kc-1", "video_id": "v1", "published_at": "2026-10-20T13:30:00+00:00",
                               "made_at": "2026-10-20", "skeleton": "S1"}])

    def no_scope():
        raise PermissionError("the token lacks yt-analytics.readonly")

    monkeypatch.setattr(youtube, "analytics_client", no_scope)
    learn.refresh(datetime(2026, 10, 23, tzinfo=timezone.utc), force=True, api=object())
    perf = ledger.load("performance", {})
    assert perf["analytics"].startswith("missing: PermissionError")
    assert perf["videos"]["v1"]["skeleton"] == "S1" and perf["videos"]["v1"]["views_48h"] is not None
    assert "Analytics: missing" in (ledger.STATE / "LEARNINGS.md").read_text(encoding="utf-8")
