"""Agreeing adjective hosts in source order, through the selector and journal."""
import json
import re
from types import SimpleNamespace

import pytest

from ah.formalizer.component_nominal_questions import select_units
from ah.formalizer.component_policy import _morph
from ah.formalizer.nominal_residual_descriptions import units
from test_composition_dispatcher import First, setup_morphology
from test_structural_relation_tasks import Script, relation, run


@pytest.mark.parametrize('text', ['Иван читает новую книгу', 'Иван читает книгу новую'])
def test_native_attribute_survives_lexical_route_and_is_recorded_once(text, tmp_path, monkeypatch):
    original = Script.generate

    def answer(self, prompt, **kwargs):
        result = original(self, prompt, **kwargs)
        if 'What role does «новую»' in prompt:
            return next(n for n, label in re.findall(r'^(\d+)\. (.*)', prompt, re.M)
                        if label.startswith('This occurrence belongs'))
        return result

    monkeypatch.setattr(Script, 'generate', answer)
    result, script = run(tmp_path, monkeypatch, text, relation('LEXICAL'))
    assert not result['diagnostics']['codes']
    assert not any(slot == 'nominal_attachment' for slot, _ in script.calls)
    reused = [r for r in result['runtime']['ir']['syntax_trace'] if r.get('kind') == 'ESTABLISHED_ATTRIBUTE_REUSED']
    assert len(reused) == 1
    records = [json.loads(line) for line in (tmp_path / 'journal.log').read_text().splitlines()]
    snapshot = next(r['payload']['snapshot'] for r in reversed(records)
                    if r['channel'] == 'canonical' and 'snapshot' in r['payload'])
    ledger = snapshot['store_metadata']['formalizer_state']
    link, = [r for r in ledger['usage_links'].values() if r['kind'] == 'NOMINAL']
    adjective = ledger['nodes'][link['node_ref']]
    predicate = ledger['nodes'][link['parent_ref']]
    assert link['host_ref'] == adjective['actants']['SUBJECT'] == predicate['actants']['OBJECT']
    assert adjective['lexical_lemma'] == 'новый' and predicate['template_ref'] == 'fixture:T:READ'
    assert {r['conclusion_ref'] for r in ledger['supports'].values()} == {link['parent_ref']}


@pytest.mark.parametrize('answer,expected', [('1', 'маму'), ('2', 'сестру'), ('?', None), ('1,2', None)])
def test_two_agreeing_hosts_need_one_addressed_choice(answer, expected):
    state, release, region, cfg = setup_morphology('Я встретил маму и сестру грустную')
    from ah.formalizer.morphology_provenance import capture
    capture(state, release=release)
    hosts = [t for t in state.evidence if t.span in ('маму', 'сестру')]
    adjective = state.evidence[-1]
    bindings = {t.token_id: _morph(next(v for v in t.variants if v.pos == 'NOUN' and 'acc' in v.cases))
                for t in hosts}
    frame = SimpleNamespace(frame_id='fixed-predicate', semantic={'morph_bindings': bindings})
    covers = [[u] for u in units(state.evidence, {adjective.token_id}, frame, [], state=state)]
    selector = First(answer)
    selected = select_units(state, release, selector, region, covers, frame, cfg)
    prompt, = selector.prompts
    assert 'Which occurrence does «грустную»' in prompt
    assert re.findall(r'^\d+\. (.+)$', prompt, re.M) == [f'«{t.span}» @{t.start}' for t in hosts]
    if expected is None:
        assert selected is None
    else:
        assert selected[0]['bound_host'] == next(t.token_id for t in hosts if t.span == expected)


def test_pair_becomes_available_only_when_both_occurrences_have_arrived():
    state, release, region, cfg = setup_morphology('Я встретил маму грустную и сестру')
    from ah.formalizer.morphology_provenance import capture
    capture(state, release=release)
    words = {t.span: t for t in state.evidence}
    heads = [words['маму'], words['сестру']]
    frame = SimpleNamespace(semantic={'morph_bindings': {
        t.token_id: _morph(next(v for v in t.variants if v.pos == 'NOUN' and 'acc' in v.cases))
        for t in heads}})
    arrived = []

    def stream():
        for token in state.evidence:
            arrived.append(token.span)
            yield token

    arrivals = [(u['bound_host'], arrived[-1])
                for u in units(stream(), {words['грустную'].token_id}, frame, [], state=state)]
    assert arrivals == [(heads[0].token_id, 'грустную'), (heads[1].token_id, 'сестру')]


def test_unconfirmed_single_host_can_still_be_rejected():
    state, release, region, cfg = setup_morphology('Я встретил маму грустную')
    from ah.formalizer.morphology_provenance import capture
    capture(state, release=release)
    host, adjective = state.evidence[-2:]
    reading = next(v for v in host.variants if v.pos == 'NOUN' and 'acc' in v.cases)
    frame = SimpleNamespace(frame_id='open-reading', semantic={'morph_bindings': {host.token_id: _morph(reading)}})
    covers = [[u] for u in units(state.evidence, {adjective.token_id}, frame, [], state=state)]
    selector = First('0')
    assert select_units(state, release, selector, region, covers, frame, cfg) is None
    assert len(selector.prompts) == 1
    assert not any(r.get('kind') == 'ESTABLISHED_ATTRIBUTE_REUSED' for r in state.syntax_trace)
