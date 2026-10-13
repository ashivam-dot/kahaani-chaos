import pytest

from kahaani import voice
from kahaani.spec import Story

from .conftest import story_dict


@pytest.fixture
def story():
    return Story.from_dict(story_dict())


def test_the_voice_is_a_placeholder_storyteller():
    assert voice.VOICE == "Algenib"
    assert "storyteller" in voice.DIRECTION and voice.TARGET_WPM == (140.0, 160.0)


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
