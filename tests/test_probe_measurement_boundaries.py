"""Measurement boundaries retain actual input provenance and refuse missing evidence."""
from copy import deepcopy

import pytest

from ah.diagnostics import runtime_trace as rt
from ah.formalizer.kernel import BoundedExecutor, ProbeLimits
from ah.formalizer.pipeline import t0
from ah.formalizer.real_backend import RealBackendSelector
from ah.formalizer.runtime_tracing import phase, traced
from ah.formalizer.selection_exchange import exchange
from ah.formalizer.selection_labels import build_label_selection_prompt
from ah.formalizer.selection_protocol import DecisionSchema, Relation
from ah.formalizer.state import Decision
from tools.audit_formalizer_probe_controls import export_annotations, score_annotations
from tools.audit_formalizer_runtime import collect_exchanges, digest, load_runtime, summarize


class Backend:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def generate(self, prompt, **kwargs):
        self.calls.append((prompt, deepcopy(kwargs)))
        return self.response


def prompt_for(frame='decision'):
    ids = ('candidate:first', 'candidate:second')
    schema = DecisionSchema('measurement-fixture', {
        cid: Relation(cid, label, 0, (), label)
        for cid, label in zip(ids, ('first reading', 'second reading'), strict=True)})
    prompt = build_label_selection_prompt(slot_id='structural_partition', frame_id=frame,
        context_span='Иван пришёл, и Мария ушла.', mentions={}, schema=schema, candidates=ids)
    return prompt, schema, ids


def decide(selector, frame='decision'):
    prompt, schema, ids = prompt_for(frame)
    state = t0('Иван пришёл, и Мария ушла.')
    decision = Decision('structural_partition', frame, ids)
    bounded = selector if isinstance(selector, BoundedExecutor) else BoundedExecutor(selector, ProbeLimits())
    with phase('T2_REGIONS'), rt.bind(decision_ref=frame, slot=decision.slot_id):
        reply = exchange(state, bounded, decision, prompt, schema, ids, 8192)
    return reply


def capture(path, work):
    @traced('MEASUREMENT_BOUNDARY_FIXTURE')
    def run():
        work()

    with rt.RuntimeTrace(path) as writer, rt.use_trace(writer):
        run()
    return load_runtime(path)


def annotate(exported):
    result = deepcopy(exported)
    result.update(corpus_kind='SYNTHETIC_FIXTURE',
        provenance='Authored measurement-boundary regression fixture; not a live model quality claim.')
    for sample in result['samples']:
        sample['annotation'] = {
            'reviewer': 'unit fixture author',
            'rationale': 'The authored positive fixture specifies the first candidate independently of the reply.',
            'expected_outcome': 'ONE_SELECTED',
            'expected_selected': [sample['selection_audit']['candidates'][0]],
        }
    return result


def test_controls_bind_actual_custom_system_role_and_effective_settings_and_reject_tampering(tmp_path):
    backend = Backend('1')
    system = 'Custom policy\tточные данные\nA second system line.'
    settings = {'temperature': 0.25, 'top_p': 0.7, 'max_new_tokens': 97, 'enable_thinking': False}
    selector = RealBackendSelector(backend, model_key='model:custom', system=system,
        role='review-fixture', generation_settings=settings)

    def work():
        selector.start_run('custom-context')
        assert decide(selector).outcome == 'ONE_SELECTED'

    loaded = capture(tmp_path / 'custom.tsv', work)
    exported = export_annotations(loaded)
    sample, = exported['samples']
    context, = sample['backend_input_context']
    actual_prompt, actual_kwargs = backend.calls[0]
    assert sample['prompt'] == str(actual_prompt)
    assert context['system'] == actual_kwargs['system'] == system
    assert context['role'] == actual_kwargs['role'] == 'review-fixture'
    assert context['generation_settings'] == actual_kwargs['override']
    assert context['generation_settings']['max_new_tokens'] == 32
    assert selector.generation_settings['max_new_tokens'] == 97
    assert sample['backend_context_source'] == 'CAPTURED_CALL'
    assert sample['backend_context_sha256'] == digest(sample['backend_input_context'])
    assert 'raw_response' not in sample
    scored = score_annotations(loaded, annotate(exported))
    assert scored['metrics'][0]['exact_all_annotations']['value'] == 1

    for field, replacement in (
        ('system', 'Changed policy'),
        ('role', 'changed-role'),
        ('generation_settings', {**actual_kwargs['override'], 'temperature': 0.9}),
    ):
        changed = annotate(exported)
        edited = changed['samples'][0]
        edited['backend_input_context'][0][field] = replacement
        # Even self-consistent replacement hashes cannot detach the annotation
        # from the actual system/role/settings in the immutable source trace.
        edited['backend_context_sha256'] = digest(edited['backend_input_context'])
        edited['payload_sha256'] = digest({key: edited[key] for key in (
            'prompt', 'selection_audit', 'backend_input_context', 'model_key', 'params_hash')})
        with pytest.raises(ValueError, match='annotation binding mismatch'):
            score_annotations(loaded, changed)


def test_source_window_controls_use_actual_exchange_hash_instead_of_provider_base_hash(tmp_path):
    backend = Backend('1')
    selector = RealBackendSelector(backend, model_key='model:window')
    expected_hashes = []

    def work():
        selector.start_run('window-context')
        selector.configure_probe_windows(('0', '1'), 512)
        for ordinal, key in enumerate(('0', '1'), 1):
            selector.enter_probe_window(key)
            assert decide(selector, frame='window:' + key).outcome == 'ONE_SELECTED'
            expected_hashes.append(selector._adapter._log.lookup('window-context', ordinal)['params_hash'])

    loaded = capture(tmp_path / 'window.tsv', work)
    exchanges = collect_exchanges(loaded['rows'])
    assert len(set(expected_hashes)) == 2
    assert [item['params_hash'] for item in exchanges] == expected_hashes
    assert all(item['base_params_hash'] == selector._adapter.params_hash for item in exchanges)
    assert all(item['params_hash'] != item['base_params_hash'] for item in exchanges)
    exported = export_annotations(loaded)
    assert [sample['params_hash'] for sample in exported['samples']] == expected_hashes
    assert len(summarize(loaded)['probe_metrics']) == 2
    annotated = annotate(exported)
    annotated['samples'][0]['params_hash'] = selector._adapter.params_hash
    with pytest.raises(ValueError, match='annotation binding mismatch: params_hash'):
        score_annotations(loaded, annotated)


def test_replay_only_trace_is_observed_but_not_scored_without_original_backend_context(tmp_path):
    backend = Backend('1')
    selector = RealBackendSelector(backend, model_key='model:replayed', system='Original policy')
    prompt, _, _ = prompt_for()
    with rt.use_trace(None):
        selector.start_run('replay-context')
        assert selector.select(prompt) == '1'

    def work():
        selector.start_run('replay-context')
        assert decide(selector).outcome == 'ONE_SELECTED'

    loaded = capture(tmp_path / 'replay-only.tsv', work)
    item, = collect_exchanges(loaded['rows'])
    assert len(backend.calls) == 1
    assert item['replay'] is True and item['sample_kind'] == 'REPLAY'
    assert item['classification']['outcome'] == 'CHOSEN_ONE'
    assert item['backend_input_context'] == []
    assert item['backend_context_source'] == 'NOT_RECORDED'
    assert item['backend_context_sha256'] is None
    report = summarize(loaded)
    assert report['provider_invocations'] == 1
    assert report['physical_generation_requests'] == 0
    exported = export_annotations(loaded)
    assert exported['samples'] == []
    assert exported['omitted_unscorable_provider_invocations'] == 1
    with pytest.raises(ValueError, match='at least one independently annotated sample'):
        score_annotations(loaded, annotate(exported))


def test_same_slot_models_and_generation_configurations_have_separate_metric_strata(tmp_path):
    selectors = [RealBackendSelector(Backend(response), model_key=model, system='Same policy',
                    generation_settings={'temperature': temperature, 'max_new_tokens': 80})
        for model, temperature, response in (
            ('model:A', 0.1, '1'), ('model:A', 0.5, '0'), ('model:B', 0.1, '1'))]

    def work():
        for index, selector in enumerate(selectors):
            selector.start_run('model-run:' + str(index))
            decide(selector, frame='model-question:' + str(index))

    loaded = capture(tmp_path / 'mixed-models.tsv', work)
    assert len({str(selector.backend.calls[0][0]) for selector in selectors}) == 1
    report = summarize(loaded)
    metrics = report['probe_metrics']
    assert len(metrics) == 3
    assert {row['raw_slot'] for row in metrics} == {'structural_partition'}
    assert all(row['counts']['provider_invocations'] == 1 for row in metrics)
    assert sorted(row['model_key'] for row in metrics) == ['model:A', 'model:A', 'model:B']
    scored = score_annotations(loaded, annotate(export_annotations(loaded)))
    assert len(scored['metrics']) == 3
    by_config = {(row['model_key'], row['params_hash']): row for row in scored['metrics']}
    for index, selector in enumerate(selectors):
        metric = by_config[(selector.model_key, selector._adapter.params_hash)]
        assert metric['annotated_samples'] == 1
        assert metric['exact_all_annotations'] == {
            'numerator': 0 if index == 1 else 1, 'denominator': 1,
            'value': 0 if index == 1 else 1}


def test_standalone_executor_protocol_is_visible_with_explicit_unscored_boundaries(tmp_path):
    class Executor:
        selection_reply_format = 'SELECT_LABELS_V1'

        def select(self, prompt):
            return '?'

    def work():
        assert decide(BoundedExecutor(Executor(), ProbeLimits())).outcome == 'INSUFFICIENT_CONTEXT'

    loaded = capture(tmp_path / 'executor-only.tsv', work)
    report = summarize(loaded)
    assert report['provider_invocations'] == report['physical_generation_requests'] == 0
    protocol, = report['selection_protocols']
    assert protocol['raw_slot'] == 'structural_partition'
    assert protocol['attempts'] == 1 and protocol['provider_invocations'] == 0
    assert protocol['validated_outcome'] == 'INSUFFICIENT_CONTEXT'
    coverage = next(row for row in report['coverage'] if row['slot'] == 'structural_partition')
    assert coverage['status'] == 'OBSERVED_PROTOCOL_ONLY'
    assert coverage['observed_selection_protocols'] == 1
    assert coverage['observed_provider_invocations'] == 0
    assert coverage['language_support'] == 'NOT_EVALUATED'
    expected_gaps = {'executor_requests_without_provider': 1, 'selection_protocols_without_provider': 1}
    assert {name: report['evidence_gaps'][name] for name in expected_gaps} == expected_gaps
    exported = export_annotations(loaded)
    assert exported['samples'] == []
    assert exported['omitted_unscorable_provider_invocations'] == 0
    assert exported['unscored_execution_boundaries'] == expected_gaps
