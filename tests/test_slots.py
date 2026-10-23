from datetime import datetime, timedelta, timezone

import pytest

from kahaani import config, slots

UTC = timezone.utc


def at(text):
    return datetime.fromisoformat(text).replace(tzinfo=UTC)


@pytest.mark.parametrize("now, slot", [
    ("2026-10-13T01:30", "2026-10-13T07:30:00Z"),  # 07:00 IST production -> that day's 13:00 IST
    ("2026-10-13T10:00", "2026-10-13T13:30:00Z"),  # 15:30 IST: the 13:00 slot is past its grace -> 19:00
    ("2026-10-13T12:00", "2026-10-13T13:30:00Z"),  # 17:30 IST publish-only run
    ("2026-10-13T16:00", "2026-10-14T07:30:00Z"),  # 21:30 IST: tonight's slot is past its grace
    ("2026-10-13T19:30", "2026-10-14T07:30:00Z"),  # 01:00 IST production on the 14th -> that day's 13:00
])
def test_the_next_slot_is_scheduled(now, slot):
    assert slots.due(at(now), set()) == {"slot": slot, "publish_at": slot}


def test_f1_has_two_daily_slots_at_one_and_seven_pm_ist():
    assert tuple(config.SLOTS) == ((13, 0), (19, 0))
    today = [s for s in slots.around(at("2026-10-13T05:30")) if s.date().isoformat() == "2026-10-13"]
    assert [s.astimezone(config.IST).strftime("%H:%M") for s in today] == ["13:00", "19:00"]
    assert [slots.iso(s) for s in today] == ["2026-10-13T07:30:00Z", "2026-10-13T13:30:00Z"]


def test_a_filled_slot_is_not_filled_twice():
    assert slots.due(at("2026-10-13T05:30"), {"2026-10-13T07:30:00Z"}) is None


def test_a_slot_missed_within_grace_goes_public_now():
    assert slots.due(at("2026-10-13T14:10"), set()) == {"slot": "2026-10-13T13:30:00Z", "publish_at": None}
    late = at("2026-10-13T13:30") + slots.GRACE + timedelta(minutes=1)
    assert slots.due(late, set())["slot"] == "2026-10-14T07:30:00Z"


def test_a_filled_missed_slot_moves_on_to_the_next():
    assert slots.due(at("2026-10-13T14:10"), {"2026-10-13T13:30:00Z"}) == {
        "slot": "2026-10-14T07:30:00Z", "publish_at": "2026-10-14T07:30:00Z"}


def test_a_slot_too_close_to_schedule_goes_public_now():
    assert slots.due(at("2026-10-13T13:20"), set()) == {"slot": "2026-10-13T13:30:00Z", "publish_at": None}


def test_the_publish_crons_reach_the_slot_in_time():
    # run.yml's publish-only crons schedule the coming slot at least LEAD ahead: 06:00 and 07:00 UTC for 13:00 IST,
    # 12:00 and 13:15 UTC for 19:00 IST (13:14: a cron that starts a minute early still makes it)
    for now, slot in (("2026-10-13T06:00", "2026-10-13T07:30:00Z"), ("2026-10-13T07:00", "2026-10-13T07:30:00Z"),
                      ("2026-10-13T12:00", "2026-10-13T13:30:00Z"), ("2026-10-13T13:14", "2026-10-13T13:30:00Z")):
        assert slots.due(at(now), set())["publish_at"] == slot


def test_taken_and_buffer():
    assert slots.taken([{"slot": "a"}, {"id": "x"}]) == {"a"}
    assert not slots.buffer_full([{}])
    assert slots.buffer_full([{}] * config.BUFFER_TARGET)


@pytest.mark.parametrize("now", ["2026-10-18T06:00", "2026-10-15T18:30", "2026-10-17T18:30", "2026-10-13T18:30"])
def test_a_weekday_format_always_finds_its_next_slot(now, monkeypatch):
    """Moment is 21:30 IST on Tue, Thu, Sat: Sunday and the night after a slot have no slot within a day."""
    monkeypatch.setattr(config, "FORMAT", "moment")
    monkeypatch.setattr(config, "SLOTS", config.FORMATS["moment"].slots)
    due = slots.due(at(now), set())
    assert due and datetime.fromisoformat(due["slot"].replace("Z", "+00:00")) > at(now)
    assert datetime.fromisoformat(due["slot"].replace("Z", "+00:00")).astimezone(config.IST).weekday() in (1, 3, 5)
