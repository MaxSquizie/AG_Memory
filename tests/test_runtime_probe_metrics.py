"""Metrics use real exchange boundaries and independent, byte-bound annotations."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from ah.diagnostics import runtime_trace as rt
from ah.formalizer.kernel import BoundedExecutor, ProbeLimits
from ah.formalizer.pipeline import t0
from ah.formalizer.real_backend import RealBackendSelector
from ah.formalizer.runtime_tracing import traced, phase
from ah.formalizer.selection_exchange import exchange
from ah.formalizer.selection_labels import build_label_selection_prompt
from ah.formalizer.selection_protocol import DecisionSchema, Relation
from ah.formalizer.state import Decision
from tools.audit_formalizer_runtime import load_runtime, collect_exchanges, summarize, main as audit_main
from tools.audit_formalizer_probe_controls import export_annotations, score_annotations


def capture(tmp_path, responses, domains, *, replay=False):
    raw = iter(responses)
    physical = []
    prompts = []
    path = tmp_path / 'runtime.tsv'

    def generate(prompt, **kwargs):
        physical.append(prompt)
        return next(raw)

    @traced('TEST_INTERPRETATION')
    def run():
        state = t0('Иван пришёл, и Мария ушла.')
        selector = RealBackendSelector(SimpleNamespace(generate=generate), model_key='scripted-test')
        selector.start_run('metric-run')
        bounded = BoundedExecutor(selector, ProbeLimits())
        with phase('T4_RESOLUTION'):
            for index, ids in enumerate(domains):
                key = 'decision:' + str(index)
                schema = DecisionSchema('test-schema', {cid: Relation(cid, cid, 0, (), cid) for cid in ids})
                prompt = build_label_selection_prompt(slot_id='structural_partition', frame_id=key,
                    context_span=state.text, mentions={}, schema=schema, candidates=ids)
                prompts.append(prompt)
                decision = Decision('structural_partition', key, ids)
                with rt.bind(decision_ref=key, slot=decision.slot_id):
                    exchange(state, bounded, decision, prompt, schema, ids, 8192)
            if replay:
                selector._adapter.select(prompts[0], 'metric-run', ordinal=1)

    with rt.RuntimeTrace(path) as writer, rt.use_trace(writer):
        run()
    return path, physical, prompts


def annotate(exported, expected):
    result = deepcopy(exported)
    result['corpus_kind'] = 'SYNTHETIC_FIXTURE'
    result['provenance'] = 'Authored unit fixture, not a live quality evaluation.'
    for sample, (outcome, selected) in zip(result['samples'], expected, strict=True):
        sample['annotation'] = {'reviewer': 'test fixture', 'rationale': 'Known artificial response scenario',
                                'expected_outcome': outcome, 'expected_selected': selected}
    return result


def test_real_executor_payload_delegation_and_replay_are_counted_once(tmp_path, monkeypatch):
    path, physical, prompts = capture(tmp_path, ['1', '0', '?', '1,2'],
        [('a',), ('b',), ('c',), ('d', 'e')], replay=True)
    loaded = load_runtime(path)
    exchanges = collect_exchanges(loaded['rows'])
    assert len(exchanges) == 5 and len(physical) == 4
    assert [e['prompt'] for e in exchanges] == [*map(str, prompts), str(prompts[0])]
    assert [e['classification']['outcome'] for e in exchanges] == [
        'CHOSEN_ONE', 'NONE_FIT', 'INSUFFICIENT_CONTEXT', 'CHOSEN_MULTIPLE', 'CHOSEN_ONE']
    assert [e['sample_kind'] for e in exchanges] == ['INITIAL'] * 4 + ['REPLAY']
    assert all(e['pipeline_stage'] == 'T4_RESOLUTION' for e in exchanges)
    assert all(e['slot']['family'] == 'RELATION' for e in exchanges)
    # A later analysis environment cannot silently replace the recorded registry.
    from ah.formalizer import probe_families
    monkeypatch.setattr(probe_families, 'FAMILIES', {})
    report = summarize(loaded)
    assert report['provider_invocations'] == 5
    assert report['physical_generation_requests'] == 4
    assert len(report['catalogs'][0]['slots']) == 66
    absent = next(row for row in report['coverage'] if row['slot'] == 'reference')
    assert absent['status'] == 'NOT_OBSERVED_IN_EXPORT'
    assert absent['language_support'] == 'NOT_EVALUATED'
    assert report['claims']['model_confidence'] == 'NOT_MEASURED'
    assert report['evidence_gaps']['exchanges_without_prompt'] == 0
    assert audit_main([str(path), '--out', str(tmp_path / 'audit')]) == 0
    assert (tmp_path / 'audit' / 'budgets.tsv').is_file()


def test_negative_positive_unknown_and_multiple_controls_keep_distinct_meanings(tmp_path):
    path, _, _ = capture(tmp_path, ['1', '0', '?', '1,2'], [('a', 'a2'), ('b', 'b2'), ('c', 'c2'), ('d', 'e')])
    loaded = load_runtime(path)
    exported = export_annotations(loaded)
    assert len(exported['samples']) == 4
    assert all('raw_response' not in row and row['annotation'] is None for row in exported['samples'])
    gold = annotate(exported, [('NONE_FIT', []), ('ONE_SELECTED', ['b']),
                               ('INSUFFICIENT_CONTEXT', []), ('MULTIPLE_ADMISSIBLE', ['d', 'e'])])
    result = score_annotations(loaded, gold)
    metric, = result['metrics']
    assert metric['false_acceptance_among_decisive_negative_replies']['value'] == 1
    assert metric['false_rejection_among_decisive_positive_replies']['value'] == .5
    assert metric['exact_all_annotations']['value'] == .5
    assert result['runtime_error_prevalence'] == 'NOT_ESTIMATED'
    assert result['g5_holdout_claim'] is False


def test_abstention_on_negative_control_is_neither_rejection_nor_zero_denominator_accuracy(tmp_path):
    path, _, _ = capture(tmp_path, ['?'], [('a',)])
    loaded = load_runtime(path)
    gold = annotate(export_annotations(loaded), [('NONE_FIT', [])])
    result = score_annotations(loaded, gold)
    metric, = result['metrics']
    assert metric['negative_abstentions'] == 1
    assert metric['false_acceptance_among_decisive_negative_replies'] == {
        'numerator': 0, 'denominator': 0, 'value': None}
    assert result['samples'][0]['exact'] is False


def test_format_repair_keeps_first_failure_as_a_separate_sample(tmp_path):
    path, _, _ = capture(tmp_path, ['not a label', '1'], [('a',)])
    loaded = load_runtime(path)
    exchanges = collect_exchanges(loaded['rows'])
    assert [e['sample_kind'] for e in exchanges] == ['INITIAL', 'FORMAT_REPAIR']
    gold = annotate(export_annotations(loaded), [('ONE_SELECTED', ['a'])] * 2)
    result = score_annotations(loaded, gold)
    by_kind = {row['sample_kind']: row for row in result['metrics']}
    assert by_kind['INITIAL']['observed_outcomes'] == {'MALFORMED': 1}
    assert by_kind['INITIAL']['exact_among_valid_replies']['value'] is None
    assert by_kind['FORMAT_REPAIR']['exact_all_annotations']['value'] == 1


@pytest.mark.parametrize('corruption,match', [
    ('source', 'source trace hash'), ('duplicate', 'duplicate annotated'),
    ('prompt', 'binding mismatch'), ('order', 'binding mismatch'),
    ('unknown_id', 'unknown candidate'), ('cardinality', 'cardinality mismatch'),
    ('unreviewed', 'independently annotated'),
])
def test_controls_reject_unbound_or_invalid_gold(tmp_path, corruption, match):
    path, _, _ = capture(tmp_path, ['1'], [('a', 'b')])
    loaded = load_runtime(path)
    gold = annotate(export_annotations(loaded), [('ONE_SELECTED', ['a'])])
    sample = gold['samples'][0]
    if corruption == 'source':
        gold['source_trace_sha256'] = '0' * 64
    elif corruption == 'duplicate':
        gold['samples'].append(deepcopy(sample))
    elif corruption == 'prompt':
        sample['prompt'] += ' changed'
    elif corruption == 'order':
        sample['selection_audit']['candidates'].reverse()
    elif corruption == 'unknown_id':
        sample['annotation']['expected_selected'] = ['unseen']
    elif corruption == 'cardinality':
        sample['annotation']['expected_outcome'] = 'NONE_FIT'
    elif corruption == 'unreviewed':
        sample['annotation'] = None
    with pytest.raises(ValueError, match=match):
        score_annotations(loaded, gold)


def test_budget_summary_counts_only_deltas_not_alias_snapshots(tmp_path):
    path = tmp_path / 'budgets.tsv'
    with rt.RuntimeTrace(path) as writer, rt.use_trace(writer), rt.bind(trace_id='t'):
        rt.emit('budget_configured', budget_level='STATE_CALLS', budget_ref='shared', budget_epoch=0,
                counters={'llm_calls': 2}, limits={'llm_limit': 8})
        for state_ref in ('parent', 'child'):
            rt.emit('state_field', state_ref=state_ref, collection='budget', value={'llm_calls': 2})
        rt.emit('budget_charged', budget_level='STATE_CALLS', budget_ref='shared', budget_epoch=0,
                scope='RUN', pipeline_stage='T4_RESOLUTION', before={'llm_calls': 2},
                delta={'llm_calls': 1}, after={'llm_calls': 3})
        rt.emit('budget_charged', budget_level='PROVIDER', budget_ref='p', budget_epoch=0,
                scope='RUN', pipeline_stage='T4_RESOLUTION', replay=True,
                delta={'estimated_tokens': 10})
    report = summarize(load_runtime(path))
    levels = {r['budget_level']: r for r in report['budget_metrics']}
    assert levels['STATE_CALLS']['delta'] == {'llm_calls': 1}
    assert levels['PROVIDER']['delta'] == {'estimated_tokens': 10}
    assert levels['PROVIDER']['replay'] is True
