from datetime import datetime, timedelta, timezone

import pytest

from kahaani import config, slots

UTC = timezone.utc


def at(text):
    return datetime.fromisoformat(text).replace(tzinfo=UTC)


@pytest.mark.parametrize("now, slot", [
    ("2026-10-13T01:30", "2026-10-13T13:30:00Z"),  # 07:00 IST production -> that evening's 19:00 IST
    ("2026-10-13T12:00", "2026-10-13T13:30:00Z"),  # 17:30 IST publish-only run
    ("2026-10-13T16:00", "2026-10-14T13:30:00Z"),  # 21:30 IST: tonight's slot is past its grace
    ("2026-10-13T19:00", "2026-10-14T13:30:00Z"),  # 00:30 IST on the 14th -> that day's 19:00
])
def test_the_next_slot_is_scheduled(now, slot):
    assert slots.due(at(now), set()) == {"slot": slot, "publish_at": slot}


def test_f1_has_one_daily_slot_at_seven_pm_ist():
    assert tuple(config.SLOTS) == ((19, 0),)
    today = [s for s in slots.around(at("2026-10-13T05:30")) if s.date().isoformat() == "2026-10-13"]
    assert [s.astimezone(config.IST).strftime("%H:%M") for s in today] == ["19:00"]
    assert slots.iso(today[0]) == "2026-10-13T13:30:00Z"


def test_a_filled_slot_is_not_filled_twice():
    assert slots.due(at("2026-10-13T05:30"), {"2026-10-13T13:30:00Z"}) is None


def test_a_slot_missed_within_grace_goes_public_now():
    assert slots.due(at("2026-10-13T14:10"), set()) == {"slot": "2026-10-13T13:30:00Z", "publish_at": None}
    late = at("2026-10-13T13:30") + slots.GRACE + timedelta(minutes=1)
    assert slots.due(late, set())["slot"] == "2026-10-14T13:30:00Z"


def test_a_filled_missed_slot_moves_on_to_the_next():
    assert slots.due(at("2026-10-13T14:10"), {"2026-10-13T13:30:00Z"}) == {
        "slot": "2026-10-14T13:30:00Z", "publish_at": "2026-10-14T13:30:00Z"}


def test_a_slot_too_close_to_schedule_goes_public_now():
    assert slots.due(at("2026-10-13T13:20"), set()) == {"slot": "2026-10-13T13:30:00Z", "publish_at": None}


def test_the_publish_crons_reach_the_slot_in_time():
    # run.yml's publish-only crons (12:00 and 13:15 UTC) both schedule tonight's slot, at least LEAD ahead
    for now in ("2026-10-13T12:00", "2026-10-13T13:14"):
        assert slots.due(at(now), set())["publish_at"] == "2026-10-13T13:30:00Z"


def test_taken_and_buffer():
    assert slots.taken([{"slot": "a"}, {"id": "x"}]) == {"a"}
    assert not slots.buffer_full([{}])
    assert slots.buffer_full([{}] * config.BUFFER_TARGET)
