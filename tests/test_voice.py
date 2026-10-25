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


@pytest.mark.parametrize('clone_passes', [True, False])
def test_final_gemini_rejection_uses_same_narrator_fallback_and_still_gates_it(
        tmp_path, monkeypatch, story, clone_passes):
    from copy import deepcopy
    passing = {'onset': .2, 'hook_wpm': 175., 'body_wpm': 165.,
               'coverage': 1., 'cer': .05, 'max_gap': .8}
    out = tmp_path / 'out'
    out.mkdir()
    rejected_audio = b'exact failed final Gemini audio'
    monkeypatch.setattr(voice.gemini, 'key', lambda: 'configured')
    monkeypatch.setattr(voice, 'reference_ready', lambda: True)
    monkeypatch.setattr(voice, 'missing_fallback', lambda: None)
    def gemini_story(story, folder):
        (folder / 'narration.wav').write_bytes(rejected_audio)
        return {'voice': {'checks': passing | {'cer': .325}}}
    monkeypatch.setattr(voice, '_gemini_story', gemini_story)
    calls = []
    def clone(story, folder):
        calls.append('same-narrator-clone')
        checks = deepcopy(passing)
        if not clone_passes:
            checks['max_gap'] = 1.22
        return {'voice': {'engine': 'chatterbox-narrator-clone', 'checks': checks}}
    monkeypatch.setattr(voice, '_chatterbox_story', clone)
    if clone_passes:
        assert voice.synthesize(story, out)['voice']['engine'] == 'chatterbox-narrator-clone'
    else:
        with pytest.raises(voice.VoiceHold, match='silence of 1.22'):
            voice.synthesize(story, out)
    assert calls == ['same-narrator-clone']
    assert (out / 'gemini-rejected.wav').read_bytes() == rejected_audio


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


def test_quiet_pause_repair_preserves_speech_and_moves_all_word_times(tmp_path):
    import soundfile as sf
    sr = voice.SAMPLE_RATE
    tone = (0.4 * np.sin(2 * np.pi * 220 * np.arange(sr) / sr)).astype(np.float32)
    audio = np.concatenate([np.zeros(int(.2 * sr)), tone, np.zeros(int(1.42 * sr)), tone])
    path = tmp_path / 'pause.wav'
    sf.write(path, audio, sr)
    before, _ = sf.read(path, dtype='float32')
    words = [{'text': 'पहले', 'start': .2, 'end': 1.2, 'beat': 0},
             {'text': 'बाद', 'start': 2.62, 'end': 3.62, 'beat': 1}]
    spoken = [(w['text'], w['start'], w['end']) for w in words]
    assert voice.silences(path)[1] > voice.MAX_GAP
    shifted, heard, receipt = voice._shorten_pauses(path, words, spoken)
    after, _ = sf.read(path, dtype='float32')
    assert receipt and receipt['source_audio_sha256'] != receipt['audio_sha256']
    assert voice.silences(path)[1] <= voice.MAX_GAP
    cut = receipt['removed'][0]
    a, b = round(cut['start'] * sr), round(cut['end'] * sr)
    assert np.array_equal(after, np.concatenate([before[:a], before[b:]]))
    assert shifted[0] == words[0]
    assert shifted[1]['start'] == pytest.approx(words[1]['start'] - (b-a)/sr, abs=.001)
    assert heard[1][1:] == (shifted[1]['start'], shifted[1]['end'])


def test_pause_editor_uses_the_final_gates_voiced_sample_grid(tmp_path):
    # Actual e07 rebuild held at 1.22 s with no edit. A file-zero frame grid
    # can see only 1.20 s, while the final gate starts its grid at voiced onset.
    import soundfile as sf
    sr = voice.SAMPLE_RATE
    path = tmp_path / 'offset.wav'
    sf.write(path, np.concatenate([np.zeros(round(.201 * sr)), np.full(sr, .4),
                                   np.zeros(round(1.221 * sr)), np.full(sr, .4)]), sr)
    words = [{'text': 'पहले', 'start': .201, 'end': 1.201, 'beat': 0},
             {'text': 'बाद', 'start': 2.422, 'end': 3.422, 'beat': 1}]
    spoken = [(w['text'], w['start'], w['end']) for w in words]
    before, _ = sf.read(path, dtype='float32')
    assert voice.silences(path)[1] == 1.22
    shifted, heard, receipt = voice._shorten_pauses(path, words, spoken)
    assert receipt and voice.silences(path)[1] <= voice.MAX_GAP
    after, _ = sf.read(path, dtype='float32')
    cut = receipt['removed'][0]
    a, b = round(cut['start'] * sr), round(cut['end'] * sr)
    assert np.count_nonzero(before) == np.count_nonzero(after) == 2 * sr
    assert np.array_equal(after, np.concatenate([before[:a], before[b:]]))
    assert shifted[0] == words[0]
    assert shifted[1]['start'] == pytest.approx(words[1]['start'] - (b-a)/sr, abs=.001)
    assert heard[1][1:] == (shifted[1]['start'], shifted[1]['end'])


def test_actual_e07_boundary_budgets_inserted_silence_without_editing_either_clip(tmp_path):
    from pathlib import Path
    import soundfile as sf
    fixture = Path(__file__).parent / 'fixtures/e07-join-silence.wav'
    original = tmp_path / 'original.wav'
    original.write_bytes(fixture.read_bytes())
    assert voice.silences(original)[1] == 1.22
    # The actual full-take Whisper interval covers the otherwise quiet centre.
    assert voice._shorten_pauses(original, [], [('protected', 1.02, 2.1)])[2] == {}
    assert original.read_bytes() == fixture.read_bytes()
    audio, sr = sf.read(original, dtype='float32')
    a, b = round(1.5 * sr), round(2.4 * sr)
    assert np.count_nonzero(audio[a:b]) == 0
    clips = [(audio[:a],), (audio[b:],)]
    pauses, receipt = voice._boundary_pauses(clips, [.9, .35])
    assert 0 < pauses[0] < .9 and pauses[1] == .35
    assert receipt['adjustments'][0]['existing_quiet_edges'] > .2
    zeros = np.zeros(int(pauses[0] * sr), np.float32)
    joined = np.concatenate([clips[0][0], zeros, clips[1][0]])
    assert np.array_equal(joined[:a], audio[:a])
    assert np.array_equal(joined[a + len(zeros):], audio[b:])
    assert np.count_nonzero(joined) == np.count_nonzero(audio)
    final = tmp_path / 'joined.wav'
    sf.write(final, joined, sr)
    assert voice.silences(final)[1] <= voice.MAX_GAP
    slowed = voice._tempo(final, voice.TEMPO_LIMITS[0], tmp_path / 'slowest.wav')
    assert voice.silences(slowed)[1] <= voice.MAX_GAP


@pytest.mark.parametrize('gap,spoken', [(1.42, [('protected', 1.6, 2.1)]), (2.4, [])])
def test_word_overlaps_and_large_delivery_gaps_are_never_trimmed(tmp_path, gap, spoken):
    import soundfile as sf
    path = tmp_path / 'protected.wav'
    sr = voice.SAMPLE_RATE
    sf.write(path, np.concatenate([np.ones(sr) * .4, np.zeros(round(gap*sr)), np.ones(sr) * .4]), sr)
    original = path.read_bytes()
    assert voice._shorten_pauses(path, [], spoken)[2] == {}
    assert path.read_bytes() == original


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


def test_an_off_pace_take_is_retimed_without_listening(tmp_path, monkeypatch):
    # Run 40094273058: a 179.6 wpm take was kept at its pace because the re-listen jittered; the Short held at 181.9.
    import soundfile as sf

    wav = tmp_path / "n.wav"
    _tone(wav, 0.25, 4.0)
    words = _words(3.14)
    monkeypatch.setattr(voice, "_listen", lambda *a: (_ for _ in ()).throw(AssertionError("listened again")))
    before = sf.info(str(wav)).duration
    w2, cov, wpm, factor = voice._paced(wav, [], words, [0.9, 0.8], [], 179.6, tmp_path)
    assert abs(factor - voice.AIM_WPM / 179.6) < 1e-3 and cov == [0.9, 0.8]
    assert voice.TARGET_WPM[0] <= wpm <= voice.TARGET_WPM[1]
    assert abs(sf.info(str(wav)).duration - before / factor) < 0.05
    assert all(abs(b["end"] - a["end"] / factor) < 0.002 for a, b in zip(words, w2))
    assert voice._paced(wav, [], words, [1.0], [], 165.0, tmp_path)[3] == 1.0


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


def test_clone_final_join_repairs_a_quiet_gap_without_changing_speech(tmp_path, monkeypatch, story):
    import soundfile as sf
    sr = voice.SAMPLE_RATE
    tone = np.ones(sr, dtype=np.float32) * .4
    clip = tmp_path / 'clone.wav'
    sf.write(clip, np.concatenate([tone, np.zeros(round(1.24 * sr)), tone]), sr)
    reference = tmp_path / 'tts/voices/narrator_ref.wav'
    reference.parent.mkdir(parents=True)
    reference.write_bytes(b'fixed narrator identity')
    monkeypatch.setattr(voice, 'REFERENCE', reference)
    monkeypatch.setattr(voice, 'TTS_DIR', tmp_path / 'tts')
    monkeypatch.setattr(voice, '_chatterbox', lambda lines, out, seed: [{'file':str(clip)} for _ in lines])
    def listen(path, tokens):
        return ([{'text':'पहले','start':0.,'end':1.,'beat':0},
                 {'text':'बाद','start':2.24,'end':3.24,'beat':0}], [1.],
                [('पहले',0.,1.),('बाद',2.24,3.24)], 165.)
    monkeypatch.setattr(voice, '_listen', listen)
    monkeypatch.setattr(voice, '_wpm', lambda *args: 165.)
    monkeypatch.setattr(voice.align, 'heard', lambda path: [])
    monkeypatch.setattr(voice, '_hook_paced', lambda wav,tokens,words,cov,spoken,out,factor: (words,cov,spoken,1.))
    timing = voice._chatterbox_story(story, tmp_path/'out')
    record = timing['voice']
    assert record['engine']=='chatterbox-narrator-clone' and record['reference_sha256']
    assert record['checks']['max_gap'] <= voice.MAX_GAP
    assert len(record['pause_edit']['removed']) == len(story.beats)
    audio, _ = sf.read(tmp_path/'out/narration.wav', dtype='float32')
    assert np.count_nonzero(audio) == len(story.beats) * 2 * sr
    assert timing['duration'] == pytest.approx(len(audio)/sr, abs=.001)
    assert timing['words'][-1]['end'] <= timing['duration']
