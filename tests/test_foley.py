import numpy as np

from kahaani import music


def rms_db(x):
    return 20 * np.log10(max(float(np.sqrt((x ** 2).mean())), 1e-9))


CUES = [{"cue": "bulb_hum", "at": 0.0}, {"cue": "crickets", "at": 0.0}, {"cue": "glass_clink", "at": 2.0, "dur": 0.4},
        {"cue": "motif", "at": 4.0}]


def test_foley_makes_two_stereo_tracks_of_the_asked_length():
    bed, mo = music.foley(CUES, 6.0, "seed")
    assert bed.shape == mo.shape == (int(6.0 * music.SR), 2)
    assert bed.dtype == mo.dtype == np.float32


def test_foley_is_not_silent_and_the_motif_sits_under_the_foley():
    bed, mo = music.foley(CUES, 6.0, "seed")
    assert rms_db(bed) > -50
    assert 0 < np.abs(mo).max() < np.abs(bed).max()
    assert np.abs(mo[: int(3.5 * music.SR)]).max() == 0


def test_foley_is_the_same_for_the_same_seed_and_not_for_another():
    a, _ = music.foley(CUES, 3.0, "one")
    b, _ = music.foley(CUES, 3.0, "one")
    c, _ = music.foley(CUES, 3.0, "two")
    assert np.array_equal(a, b) and not np.array_equal(a, c)


def test_a_motif_is_four_minor_notes():
    assert len(music.MOTIF_NOTES) == 4
    root, third = music.MOTIF_NOTES[0], music.MOTIF_NOTES[1]
    assert third - root == 3
