import hashlib
import json
import subprocess
from types import SimpleNamespace

import pytest

from kahaani import art_precheck, gemini, imagegen, look, vision
from .conftest import story_dict


def painting(tmp_path):
    story = story_dict()
    source = tmp_path / 'story.json'
    source.write_text(json.dumps(story))
    image = tmp_path / 'beat00.png'
    image.write_bytes(b'exact painting bytes')
    prompt = look.plan(story['id'], story['beats'], story['cast'])[0]['prompt']
    image.with_suffix('.json').write_text(json.dumps({'story': story['id'], 'beat': 0, 'prompt': prompt}))
    return source, image


def test_early_check_uses_actual_scene_and_current_human_gate(tmp_path, monkeypatch):
    source, image = painting(tmp_path)
    monkeypatch.setattr(gemini, 'available', lambda: True)
    def judge(items, story, cast, ask):
        assert items[0][1] == story_dict()['beats'][0]['text']
        assert items[0][3] == story_dict()['beats'][0]['scene']
        assert ask == gemini.look
        return [{'human_present': True, 'ridden': False, 'fits': True, 'shows': 'a visible hand'}]
    monkeypatch.setattr(vision, 'judge', judge)
    receipt = art_precheck.check(source, image, 0)
    assert receipt['skip_remaining_spares'] is False
    assert receipt['release_approval'] is False
    assert 'unplanned human' in receipt['reason']


def test_changed_prompt_cannot_skip_spares(tmp_path, monkeypatch):
    source, image = painting(tmp_path)
    monkeypatch.setattr(gemini, 'available', lambda: True)
    image.with_suffix('.json').write_text(json.dumps({'story': story_dict()['id'], 'beat': 0, 'prompt': 'different'}))
    with pytest.raises(ValueError, match='exact story'):
        art_precheck.check(source, image, 0)


@pytest.mark.parametrize('sha,approval,decision,expected', [
    ('exact', False, True, True), ('wrong', False, True, False),
    ('exact', True, True, False), ('exact', False, False, False),
])
def test_skip_requires_exact_positive_nonrelease_receipt(tmp_path, monkeypatch, sha, approval, decision, expected):
    source, image = painting(tmp_path)
    monkeypatch.setenv('GEMINI_API_KEY', 'dummy-test-key')
    receipt = {'image_sha256': hashlib.sha256(image.read_bytes()).hexdigest() if sha == 'exact' else sha,
               'release_approval': approval, 'skip_remaining_spares': decision}
    def run(args, **kwargs):
        assert kwargs['timeout'] == 120 and kwargs['capture_output'] and kwargs['check']
        assert str(source) in args and str(image) in args
        return SimpleNamespace(stdout=json.dumps(receipt))
    monkeypatch.setattr(subprocess, 'run', run)
    assert imagegen.skip_spares(source, image, 0) is expected


@pytest.mark.parametrize('error', [subprocess.TimeoutExpired('editor', 120),
                                  subprocess.CalledProcessError(1, 'editor'), ValueError('malformed')])
def test_outage_retains_spares(tmp_path, monkeypatch, error):
    source, image = painting(tmp_path)
    monkeypatch.setenv('GEMINI_API_KEY', 'dummy-test-key')
    def fail(*args, **kwargs):
        raise error
    monkeypatch.setattr(subprocess, 'run', fail)
    assert imagegen.skip_spares(source, image, 0) is False


def test_painter_only_skips_unused_spares_after_acceptance(tmp_path, monkeypatch):
    plan = tmp_path / 'plan.json'
    plan.write_text(json.dumps({'story': 'test-story', 'beats': [
        {'prompt': 'same prompt', 'seed': 7, 'alternates': [8, 9]}]}))
    seeds = []
    def generate(prompt, out, **kwargs):
        seeds.append(kwargs['seed'])
        out.write_bytes(b'painting')
        return {'seconds': 1, 'model': 'zimage'}
    monkeypatch.setattr(imagegen, 'generate', generate)
    monkeypatch.setattr(imagegen, 'skip_spares', lambda story, image, beat: len(seeds) == 2)
    assert imagegen.main(['beats', '--prompts', str(plan), '--out', str(tmp_path / 'art'),
                          '--root', str(tmp_path), '--alternates', '2', '--review-story', str(plan)]) == 0
    assert seeds == [7, 8]
    assert (tmp_path / 'art/beat00.json').exists()
    assert (tmp_path / 'art/beat00-alt1.json').exists()
    assert not (tmp_path / 'art/beat00-alt2.png').exists()
