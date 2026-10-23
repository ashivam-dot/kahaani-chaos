import numpy as np
import pytest

from kahaani import voice
from kahaani.spec import Story

from .conftest import story_dict


@pytest.fixture
def story():
    return Story.from_dict(story_dict())


def test_the_voice_is_the_auditioned_narrator():
    assert voice.VOICE == "Charon"
    assert "remembering" in voice.DIRECTION and tuple(voice.TARGET_WPM) == (155, 175)
    assert tuple(voice.HOOK_WPM) == (170, 185)


def test_the_transcript_holds_a_pause_before_the_twist(story):
    lines = voice.transcript(story).split("\n")
    assert len(lines) == len(story.beats)
    assert lines[story.twist_beat - 2].endswith(" …")
    assert sum(line.endswith(" …") for line in lines) == 1


def test_numbers_are_spoken_in_hindi():
    assert voice.spoken_numbers("3 सिक्के") == "तीन सिक्के"


def test_a_missing_reference_clip_is_reported(tmp_path, monkeypatch):
    monkeypatch.setattr(voice, "REFERENCE", tmp_path / "narrator_ref.wav")
    assert voice.missing_fallback() == "the clone's reference clip is missing (tts/voices/narrator_ref.wav)"
    assert voice.ready().startswith("hold: no narrator voice: GEMINI_API_KEY is not set and the clone's reference")


def test_without_any_narrator_synthesis_holds_cleanly(tmp_path, monkeypatch, story):
    monkeypatch.setattr(voice, "REFERENCE", tmp_path / "narrator_ref.wav")
    with pytest.raises(voice.VoiceHold, match="hold: no narrator voice: GEMINI_API_KEY is not set, and the clone's"):
        voice.synthesize(story, tmp_path / "out")


def test_a_key_alone_is_enough_to_plan(monkeypatch, tmp_path):
    monkeypatch.setattr(voice, "REFERENCE", tmp_path / "narrator_ref.wav")
    monkeypatch.setenv("GEMINI_API_KEY", "test-placeholder")
    assert voice.ready() is None


def _tone(path, silence, seconds, sr=24000):
    import numpy as np
    import soundfile as sf

    t = np.arange(int(seconds * sr)) / sr
    sf.write(path, np.concatenate([np.zeros(int(silence * sr)), 0.5 * np.sin(2 * np.pi * 220 * t)]), sr)


def _words(hook_end, n=10):
    first = [{"text": "क", "beat": 0, "start": hook_end * i / n, "end": hook_end * (i + 1) / n} for i in range(n)]
    return first + [{"text": "ख", "beat": 1, "start": hook_end + 0.3, "end": hook_end + 0.6}]


def test_the_hook_is_timed_from_the_waveform_not_whisper(tmp_path, story):
    # Dry run 39866905046: Whisper put the first word at 0.0 s inside the 0.2 s lead-in, so the take measured 191 wpm
    # and passed, then the finished narration measured 204 wpm from the real onset and was held.
    wav = tmp_path / "n.wav"
    _tone(wav, 0.25, 4.0)
    words = _words(3.14)
    assert voice.measure(story, words, [])["hook_wpm"] == 191.1
    assert voice.measure(story, words, [], wav)["hook_wpm"] == 207.6


def test_a_rushed_hook_is_slowed_alone(tmp_path, monkeypatch):
    wav = tmp_path / "n.wav"
    _tone(wav, 0.25, 4.0)
    words = _words(3.14)

    def listen(path, tokens):
        import soundfile as sf

        stretch = sf.info(str(path)).duration / 4.25
        return [w | {"start": w["start"] * stretch, "end": w["end"] * stretch} if w["beat"] == 0 else w
                for w in words], [1.0, 1.0], [], 165.0

    monkeypatch.setattr(voice, "_listen", listen)
    _, _, _, factor = voice._hook_paced(wav, [], words, [1.0, 1.0], [], tmp_path)
    assert voice.TEMPO_LIMITS[0] <= factor < 1.0
    assert not (tmp_path / "narration-hook.wav").exists() and not (tmp_path / "hook.wav").exists()
    in_band = _words(10 * 60 / 178 + 0.25)
    assert voice._hook_paced(wav, [], in_band, [1.0, 1.0], [], tmp_path)[3] == 1.0


def test_the_hook_limit_counts_the_body_tempo(tmp_path, monkeypatch):
    # Dry run 39886731532: a 210 wpm hook sped up 1.09x with the body could only come back 0.85x, to 194.
    wav = tmp_path / "n.wav"
    _tone(wav, 0.25, 4.0)
    words = _words(10 * 60 / 229 + 0.25)
    monkeypatch.setattr(voice, "_listen", lambda path, tokens: (
        [w | {"end": w["end"] * 1.3} if w["beat"] == 0 else w for w in words], [1.0], [], 165.0))
    factor = voice._hook_paced(wav, [], words, [1.0], [], tmp_path, 1.0905)[3]
    assert factor < voice.TEMPO_LIMITS[0] and factor * 1.0905 >= voice.TEMPO_LIMITS[0] - 1e-4


def test_the_hook_retime_moves_the_timings_without_listening(tmp_path, monkeypatch, story):
    # Dry run 39930652897: the re-listen after re-timing a 193.5 wpm hook was thrown away and the Short held at 193.5.
    import soundfile as sf

    wav = tmp_path / "n.wav"
    _tone(wav, 0.25, 4.0)
    words = _words(10 * 60 / 194 + 0.25)
    monkeypatch.setattr(voice, "_listen", lambda *a: (_ for _ in ()).throw(AssertionError("listened again")))
    before = sf.info(str(wav)).duration
    w2, _, s2, factor = voice._hook_paced(wav, [], words, [1.0], [("क", 3.9, 4.0)], tmp_path)
    added = sf.info(str(wav)).duration - before
    assert 0.9 < factor < 1.0 and added > 0
    assert voice.HOOK_WPM[0] <= voice.measure(story, w2, [], wav)["hook_wpm"] <= voice.HOOK_WPM[1] + 0.5
    later = [(a, b) for a, b in zip(words, w2) if a["beat"] > 0]
    assert all(abs(b["start"] - a["start"] - added) < 0.01 for a, b in later)
    assert abs(s2[0][1] - 3.9 - added) < 0.01


def test_the_hook_retime_keeps_the_pause_before_line_two(tmp_path, monkeypatch, story):
    # Dry run 39969216681: cut at the middle of the pause, a x0.867 re-time stretched it from 1.11 s past the 1.2 s limit.
    wav = tmp_path / "n.wav"
    _tone(wav, 0.25, 4.0)
    words = _words(10 * 60 / 194 + 0.25)
    w2, _, _, factor = voice._hook_paced(wav, [], words, [1.0], [("क", 3.9, 4.0)], tmp_path)
    gap = lambda ws: next(w for w in ws if w["beat"] == 1)["start"] - [w for w in ws if w["beat"] == 0][-1]["end"]
    assert factor < 1.0
    assert abs(gap(w2) - gap(words)) <= voice.HOOK_TAIL * (1 / factor - 1) + 0.002


def test_a_clone_beat_is_cut_to_its_words_so_a_trailing_breath_adds_no_silence():
    sr = voice.SAMPLE_RATE
    audio = np.ones(int(3.0 * sr), np.float32)
    words = [{"text": "a", "start": 0.5, "end": 0.9, "beat": 1}, {"text": "b", "start": 1.0, "end": 1.6, "beat": 1}]
    cut, moved = voice._trim(audio, words)
    assert abs(len(cut) / sr - (1.6 + voice.WORD_TAIL - 0.5 + voice.WORD_HEAD)) < 0.01
    assert moved[0]["start"] == voice.WORD_HEAD and moved[1]["end"] == round(1.6 - 0.5 + voice.WORD_HEAD, 3)
    assert voice._trim(audio, []) == (audio, [])
