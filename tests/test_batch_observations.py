from datetime import datetime, timedelta, timezone

import pytest

from kahaani import batch_observations as observations, config, ledger, youtube


NOW = datetime(2026, 10, 25, 14, 0, tzinfo=timezone.utc)
PUBLISHED = NOW - timedelta(hours=48.5)
BATCH = {"jobs": [{"premise": "e21", "stage": "public", "source_sha": "pinned-source",
                    "delivery": {"video_id": "public"}},
                   {"premise": "e19", "stage": "scheduled", "delivery": {"video_id": "scheduled"}}]}


@pytest.fixture
def videos(monkeypatch):
    monkeypatch.setattr(youtube, "identity", lambda api: {"id": config.EXPECTED_CHANNEL_ID})
    rows = [{"id": vid, "status": {"privacyStatus": "public"},
             "snippet": {"publishedAt": PUBLISHED.isoformat()}, "statistics": {"viewCount": "113"}}
            for vid in ("public", "scheduled", "unrelated")]
    monkeypatch.setattr(youtube, "recent", lambda *a: rows)
    ledger.save("published", [{"video_id": "public", "id": "kc-e21", "format": "micro"}])
    return rows


def test_records_only_verified_public_batch_with_actual_ages(videos):
    assert observations.refresh(BATCH, NOW, api=object()) == {"recorded": 1, "missing_counts": 0}
    data = ledger.load("batch-observations", {})
    assert list(data["videos"]) == ["public"]
    rec = data["videos"]["public"]
    assert rec["format"] == "micro" and rec["source_sha"] == "pinned-source"
    assert rec["observations"] == [{"observed_at": NOW.isoformat(), "age_h": 48.5,
                                      "views": 113, "likes": None, "comments": None}]
    assert ledger.load("performance", None) is None


def test_hidden_views_and_nonpublic_media_are_not_zero_observations(videos):
    videos[0]["statistics"] = {}
    assert observations.refresh(BATCH, NOW, api=object()) == {"recorded": 0, "missing_counts": 1}
    data = ledger.load("batch-observations", {})
    assert data["videos"] == {} and data["missing_counts"] == ["public"]
    videos[0]["status"]["privacyStatus"] = "private"
    videos[0]["statistics"] = {"viewCount": "0"}
    observations.refresh(BATCH, NOW + timedelta(hours=3), api=object())
    assert ledger.load("batch-observations", {})["videos"] == {}


def test_refresh_throttle_prevents_extra_api_reads(videos, monkeypatch):
    observations.refresh(BATCH, NOW, api=object())
    monkeypatch.setattr(youtube, "identity", lambda *a: pytest.fail("API within throttle"))
    assert observations.refresh(BATCH, NOW + timedelta(hours=2), api=object()) is None


def test_retains_early_measured_windows_and_bounds_storage(videos):
    for i in range(80):
        observations.refresh(BATCH, PUBLISHED + timedelta(hours=3 * i), api=object())
    points = ledger.load("batch-observations", {})["videos"]["public"]["observations"]
    assert len(points) == observations.EARLY_SNAPSHOTS + 1
    assert {p["age_h"] for p in points} >= {24, 27, 30, 48, 51, 54}
    assert points[-1]["age_h"] == 237


def test_changed_publication_time_requires_reconciliation(videos):
    observations.refresh(BATCH, NOW, api=object())
    videos[0]["snippet"]["publishedAt"] = (PUBLISHED + timedelta(hours=1)).isoformat()
    with pytest.raises(ValueError, match="publication time changed"):
        observations.refresh(BATCH, NOW + timedelta(hours=3), api=object())
