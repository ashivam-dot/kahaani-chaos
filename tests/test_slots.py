from datetime import datetime, timedelta, timezone

import pytest

from kahaani import config, slots

UTC = timezone.utc


def at(text):
    return datetime.fromisoformat(text).replace(tzinfo=UTC)


@pytest.mark.parametrize("now, slot", [
    ("2026-10-13T05:30", "2026-10-13T07:00:00Z"),  # 11:00 IST -> 12:30 IST
    ("2026-10-13T13:45", "2026-10-13T15:00:00Z"),  # 19:15 IST -> 20:30 IST
    ("2026-10-13T19:00", "2026-10-14T07:00:00Z"),  # 00:30 IST on the 14th -> that day's 12:30
    ("2026-10-13T17:30", "2026-10-14T07:00:00Z"),  # 23:00 IST: the 20:30 slot is past its grace
])
def test_the_next_slot_is_scheduled(now, slot):
    assert slots.due(at(now), set()) == {"slot": slot, "publish_at": slot}


def test_slots_are_ist_times():
    first = slots.around(at("2026-10-13T05:30"))[2]
    assert first.astimezone(config.IST).strftime("%H:%M") == "12:30"
    assert slots.iso(first) == "2026-10-13T07:00:00Z"


def test_a_filled_slot_is_not_filled_twice():
    assert slots.due(at("2026-10-13T05:30"), {"2026-10-13T07:00:00Z"}) is None


def test_a_slot_missed_within_grace_goes_public_now():
    assert slots.due(at("2026-10-13T07:40"), set()) == {"slot": "2026-10-13T07:00:00Z", "publish_at": None}
    late = at("2026-10-13T07:00") + slots.GRACE + timedelta(minutes=1)
    assert slots.due(late, set())["slot"] == "2026-10-13T15:00:00Z"


def test_a_filled_missed_slot_moves_on_to_the_next():
    assert slots.due(at("2026-10-13T07:40"), {"2026-10-13T07:00:00Z"}) == {
        "slot": "2026-10-13T15:00:00Z", "publish_at": "2026-10-13T15:00:00Z"}


def test_a_slot_too_close_to_schedule_goes_public_now():
    assert slots.due(at("2026-10-13T06:50"), set()) == {"slot": "2026-10-13T07:00:00Z", "publish_at": None}


def test_taken_and_buffer():
    assert slots.taken([{"slot": "a"}, {"id": "x"}]) == {"a"}
    assert not slots.buffer_full([{}])
    assert slots.buffer_full([{}] * config.BUFFER_TARGET)
