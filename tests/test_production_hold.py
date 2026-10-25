import json
from pathlib import Path

import pytest

from kahaani import gate, premises
from .conftest import story_dict


def test_quarantined_object_stays_in_the_bible_but_never_reenters_ordinary_or_explicit_production():
    entries = {e['id']: e for e in premises.bank()}
    assert entries['e08']['production_hold']
    assert 'e08' not in {e['id'] for e in premises.unused([])}
    assert any('production hold' in p for p in premises.fits(entries['e08'], []))
    with pytest.raises(premises.NoPremise):
        premises.select([], [entries['e08']])


def test_quarantine_does_not_prevent_a_valid_ten_entry_buffer():
    history = []
    for _ in range(10):
        entry = premises.select(history)
        assert entry['id'] != 'e08' and not premises.fits(entry, history)
        history.append(premises.row(entry, history))


@pytest.mark.parametrize('rotation', [False, True])
def test_even_a_full_replay_cannot_skip_a_production_hold(rotation):
    from kahaani import cli
    from kahaani.spec import Story
    draft = story_dict()
    entry = cli.premise_of(Story.from_dict(draft))
    assert not gate.check(draft, entry, [], rotation=rotation)
    found = gate.check(draft, {**entry, 'production_hold':'Exact image geometry is wrong'}, [], rotation=rotation)
    assert found == ['production hold: Exact image geometry is wrong']


def test_replanned_unbooked_batch_preserves_every_slot_and_all_sequence_rules():
    root = Path(__file__).resolve().parents[1]
    plan = json.loads((root/'strategy/batch-2026-10-25.json').read_text())
    jobs = plan['jobs']
    assert len(jobs) == 21 and len({j['premise'] for j in jobs}) == 21
    assert 'e08' not in {j['premise'] for j in jobs}
    replacement = next(j for j in jobs if j['premise']=='e32')
    assert replacement['target'] == '2026-10-28T07:30:00Z'
    bank = {e['id']:e for e in premises.bank()}
    history = []
    for job in jobs:
        entry = bank[job['premise']]
        assert not premises.fits(entry, history), job['premise']
        brief = root/job['inputs']['replay']
        if 'batch-2026-10-25' in str(brief):
            packet = json.loads(brief.read_text())
            assert packet['preview_entry'] == job['premise']
            assert packet['predecessors'] == [r['premise'] for r in history]
        history.append(premises.row(entry, history))
