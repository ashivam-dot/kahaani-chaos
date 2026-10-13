import numpy as np

from kahaani import music


def rms(x):
    return float(np.sqrt((x ** 2).mean()))


def test_shape_level_and_fades():
    bed = music.score(6.0, "kc-1")
    assert bed.shape == (int(6.0 * music.SR), 2) and bed.dtype == np.float32
    assert abs(np.abs(bed).max() - 0.5) < 1e-3
    assert np.abs(bed[:50]).max() < 0.01 and np.abs(bed[-50:]).max() < 0.01


def test_the_same_story_scores_the_same_and_another_differently():
    assert np.array_equal(music.score(3.0, "kc-1"), music.score(3.0, "kc-1"))
    assert not np.array_equal(music.score(3.0, "kc-1"), music.score(3.0, "kc-2"))


def test_the_bell_strikes_at_the_twist():
    sr, at = music.SR, 4.0
    plain, rung = music.score(8.0, "kc-1"), music.score(8.0, "kc-1", bell_at=at)
    before = slice(int(2.5 * sr), int(3.8 * sr))
    after = slice(int(at * sr), int((at + 1.0) * sr))
    ratio_plain = rms(plain[after]) / rms(plain[before])
    ratio_rung = rms(rung[after]) / rms(rung[before])
    assert ratio_rung > 1.5 * ratio_plain


def test_a_bell_dies_away():
    b = music.bell(880.0, 4.0)
    assert rms(b[: music.SR // 2]) > 5 * rms(b[-music.SR // 2:])
