import numpy as np
import pytest

from kahaani import card, moment

QUAD = [[0.2, 0.2], [0.6, 0.2], [0.6, 0.4], [0.2, 0.4]]


def spec_of(kind):
    return next(e["anomaly"] for e in moment.bank() if e["anomaly"]["card"] == kind)["spec"]


@pytest.mark.parametrize("kind", ["timetable", "clock", "calendar"])
def test_each_card_kind_renders_with_the_odd_part_inside_it(kind):
    try:
        spec = spec_of(kind)
    except StopIteration:
        pytest.skip(f"no bank entry uses a {kind} yet")
    img, boxes = card.render(kind, spec)
    assert img.mode == "RGBA" and img.width > 100 and img.height > 100
    x0, y0, x1, y1 = boxes["answer"]
    assert 0 <= x0 < x1 <= img.width and 0 <= y0 < y1 <= img.height


def test_an_unknown_card_kind_is_refused():
    with pytest.raises(ValueError):
        card.render("poster", {})


def test_only_a_clock_changes_with_time():
    assert card.state("clock", 3.4) == 3 and card.state("clock", 4.1) == 4
    assert card.state("timetable", 3.4) == card.state("timetable", 9.0) == 0


def test_composite_keeps_the_plate_shape_and_changes_only_the_quad_area():
    plate = np.full((320, 180, 3), 120, np.uint8)
    img, _ = card.render("timetable", spec_of("timetable"))
    out = card.composite(plate, img, QUAD, seed=1)
    assert out.shape == plate.shape and out.dtype == np.uint8
    changed = np.abs(out.astype(int) - plate.astype(int)).sum(axis=2) > 0
    assert changed.any()
    ys, xs = np.nonzero(changed)
    assert xs.min() >= 0.2 * 180 - 6 and xs.max() <= 0.6 * 180 + 6
    assert ys.min() >= 0.2 * 320 - 6 and ys.max() <= 0.4 * 320 + 6


def test_the_answer_card_is_a_full_frame_with_a_circle_on_the_odd_part():
    e = moment.bank()[0]
    prev = {"kind": e["anomaly"]["card"], "spec": e["anomaly"]["spec"]}
    frame, info = card.answer_card(prev, e["anomaly"]["tail_hi"], e["anomaly"]["register_line_hi"], (540, 960))
    assert frame.shape == (960, 540, 3)
    assert info["iou"] > 0.3
