"""Finishing measures the finite soundtrack and never clears a different kind of hold."""
import json

import numpy as np
import pytest
import soundfile as sf

from kahaani import audio_finish, compose


def test_two_pass_finishes_the_whole_padded_mix(tmp_path):
    sr = 24000
    t = np.arange(4 * sr) / sr
    signal = .03 * np.sin(2 * np.pi * 220 * t)
    signal[2 * sr:3 * sr] *= 3
    source, target = tmp_path / "unmastered.wav", tmp_path / "finished.wav"
    sf.write(source, np.r_[signal, np.zeros(sr)], sr)
    result = audio_finish.normalize(source, target)
    assert float(result["measurement"]["input_i"]) < -20
    assert not compose.audio_problems(compose.loudness(target), bed=-30)
    assert abs(sf.info(target).duration - 5) < .01


def test_silence_is_held_instead_of_amplified(tmp_path):
    source = tmp_path / "silent.wav"
    sf.write(source, np.zeros(24000), 24000)
    with pytest.raises(ValueError, match="silent or unmeasurable"):
        audio_finish.normalize(source, tmp_path / "finished.wav")


def held(tmp_path, problems):
    reports = {"dry-produce-health.json": {"dry": True, "ok": True, "held": "picture and sound checks"},
               "picture-checks.json": {"problems": problems}, "story.json": {}, "timing.json": {},
               "pictures.json": []}
    (tmp_path / "short.mp4").write_bytes(b"must not be decoded for an ineligible repair")
    for name, data in reports.items():
        (tmp_path / name).write_text(json.dumps(data))
    files = {name: audio_finish.digest(tmp_path / name) for name in ["short.mp4", *reports]}
    return {"premise": "e02", "run_id": 123, "audio_finish": {"source_files": files}}


@pytest.mark.parametrize("problem", ["missing frames", "mean luma 50", "true peak bad; wrong picture",
                                    "music bed is too loud", ""])
def test_audio_repair_cannot_clear_picture_frame_or_balance_holds(tmp_path, problem):
    job = held(tmp_path, ["integrated loudness -15.1 LUFS, needs -15 to -13", problem])
    with pytest.raises(ValueError, match="otherwise passing audio-level hold"):
        audio_finish.finish_preview(job, tmp_path)


def test_changed_source_report_cannot_use_an_earlier_audio_intent(tmp_path):
    job = held(tmp_path, ["integrated loudness -15.1 LUFS"])
    (tmp_path / "pictures.json").write_text('[{"changed":true}]')
    with pytest.raises(ValueError, match="original pictures.json differs"):
        audio_finish.finish_preview(job, tmp_path)


def test_missing_original_binding_cannot_start_a_repair(tmp_path):
    job = held(tmp_path, ["integrated loudness -15.1 LUFS"])
    del job["audio_finish"]["source_files"]["story.json"]
    with pytest.raises(ValueError, match="complete original media/report binding"):
        audio_finish.finish_preview(job, tmp_path)


@pytest.mark.parametrize("changed", [False, True])
def test_archived_finished_media_is_reused_only_for_its_exact_receipt(tmp_path, changed):
    job = held(tmp_path, ["integrated loudness -15.1 LUFS"])
    receipt = {"source_files": job["audio_finish"]["source_files"],
               "output_sha256": audio_finish.digest(tmp_path / "short.mp4")}
    (tmp_path / "audio-finish.json").write_text(json.dumps(receipt))
    if changed:
        (tmp_path / "short.mp4").write_bytes(b"different finished media")
        with pytest.raises(ValueError, match="receipt differs"):
            audio_finish.finish_preview(job, tmp_path)
    else:
        # An exact archive survives a runner restart without another audio encode.
        audio_finish.finish_preview(job, tmp_path)


def test_coordinator_recovers_finished_archive_instead_of_encoding_the_original_again(tmp_path, monkeypatch):
    from ops import cloud_batch

    monkeypatch.setattr(cloud_batch, "ROOT", tmp_path)
    calls = []
    def gh(*args, **kwargs):
        calls.append(args)
        assert args[:2] == ("release", "download")
    monkeypatch.setattr(cloud_batch, "gh", gh)
    job = {"run_id": 123, "audio_finish": {"source_files": {}}, "archive": "batch-reviewed-123"}
    cloud_batch.materialize("ashivam-dot/kahaani-chaos", None, job)
    assert len(calls) == 1 and "short.mp4" in calls[0] and "*.json" in calls[0]
