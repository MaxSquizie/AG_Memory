"""Controlled contracts for reconstructed changes; no language-model claim.

Run with the project's dependencies installed and src/ on PYTHONPATH.
"""
import json
import runpy
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[2]
fixture = runpy.run_path(str(ROOT / 'tests/test_clarification_1221.py'))
from ah.perception import PerceptionResult, StructuralClarificationSpec, StructuralClarificationOption
from ah.formalizer.runtime_adapter import NativePerceptionResult
from ah.agent.orchestrator_base import AgentOrchestrator as Base
from ah.agent.orchestrator import AgentOrchestrator as Public
from ah.diagnostics.formalization_trace import FormalizationTraceBuilder


def spec(tag):
    return StructuralClarificationSpec('COMPONENT', tag, 'source', tuple(
        StructuralClarificationOption(tag + str(n), f'{tag} choice {n}') for n in (1, 2)))


def result(requests=()):
    p = PerceptionResult(source_text='source', native_clarifications=tuple(requests))
    return replace(p, native_receipt=NativePerceptionResult(p, 'fixture', 1, 'RESOLUTION_ONLY'))


class Perception:
    native_available = True

    def __init__(self, initial, continued):
        self.initial, self.continued = initial, continued

    def parse(self, text, context):
        return self.initial

    def parse_with_structural_resolution(self, *args):
        return self.continued

    def native_clarification_current(self, key):
        return True


checks = []
for cls in (Base, Public):
    for case in ('initial_partial', 'continued_partial', 'continued_choice', 'failed_question'):
        helper = fixture['Clarification1221Tests']()
        core, context, integration = helper._runtime()
        perception = Perception(result(() if case == 'initial_partial' else (spec('first'),)),
                                result((spec('second'),) if case in ('continued_choice', 'failed_question') else ()))
        orchestrator, agent = helper._orchestrator(core, context, integration, perception)
        orchestrator.__class__ = cls
        first = orchestrator.handle_user_text('source')
        trace = FormalizationTraceBuilder(core).build(first.formalization_integration,
            trace_id='first', source='CONTROLLED', title=case, source_text='source',
            native_receipt=first.formalization_perception.native_receipt)
        assert trace.status == ('RESOLUTION_ONLY' if case == 'initial_partial' else 'CLARIFICATION_REQUIRED')
        if case == 'initial_partial':
            assert agent.respond_calls == 0 and 'Не удалось' in first.response_text
        else:
            assert len(context.pending_clarification_refs) == 1
            if case == 'failed_question':
                def fail(request):
                    raise RuntimeError('controlled response failure')
                agent.clarify = fail
            second = orchestrator.handle_user_text('1')
            assert second.clarification_resolution is not None
            assert second.clarification_perception.native_receipt.terminal == 'RESOLUTION_ONLY'
            assert second.formalization_integration.experience_ref == first.integration.experience_ref
            assert agent.respond_calls == 0
            trace = FormalizationTraceBuilder(core).build(second.formalization_integration,
                trace_id='second', source='CONTROLLED', title=case, source_text='source',
                native_receipt=second.formalization_perception.native_receipt)
            assert trace.status == ('RESOLUTION_ONLY' if case == 'continued_partial' else 'CLARIFICATION_REQUIRED')
            if case == 'continued_partial':
                assert 'Не удалось' in second.response_text and not context.pending_clarification_refs
            elif case == 'continued_choice':
                assert second.clarification_request.mention == 'second'
                assert context.pending_clarification_refs == [second.clarification_request.ambiguous_ref]
                assert agent.clarify_calls == 2
            else:
                assert second.response_error and second.response_text is None
                assert not context.pending_clarification_refs
        checks.append({'route': cls.__module__, 'case': case, 'passed': True})

from ah.formalizer.pipeline import t0
from ah.formalizer.regions import TextRegion
from ah.formalizer.state import TokenEvidence
from ah.formalizer.structural_tasks import choose
from ah.formalizer.clarification_liveness import obsolete


class Selector:
    selection_reply_format = 'SELECT_LABELS_V1'

    def __init__(self, answers):
        self.answers = iter(answers)
        self.calls = 0

    def select(self, prompt):
        self.calls += 1
        return next(self.answers)


for answers, expected in [(['0', '0'], 0), (['?'], 0), (['1,2', '0'], 1)]:
    state = t0('source')
    state.evidence = [TokenEvidence('source', 't', 0, 6)]
    region = TextRegion('r', 'SENTENCE', (0, 6), ('t',), None)
    release = SimpleNamespace(sha256='release', entries=lambda kind: [{'max_rule_steps': 100}])
    selector = Selector(answers)
    options = [{'candidate_id': str(i), 'label': 'reading ' + str(i)} for i in range(4)]
    cfg = {'max_candidates': 2, 'context_chars': 1000}
    assert choose(state, release, selector, region, cfg, 'relation', options, 'Select the reading') is None
    assert len(state.clarification_candidates) == expected
    if expected:
        offer = state.clarification_candidates[0]
        assert offer['decision_ref'].startswith('task-domain:')
        assert {o['candidate_id'] for o in offer['options']} == {'0', '1'}
        assert not obsolete({**offer, 'generation_snapshot': {'syntax_trace': state.syntax_trace}})
    pages = [r['decision_ref'] for r in state.syntax_trace if r.get('kind') == 'STRUCTURAL_TASK' and 'page' in r]
    assert all(obsolete({'decision_ref': p, 'generation_snapshot': {'syntax_trace': state.syntax_trace}}) for p in pages)
    before = selector.calls
    choose(state, release, selector, region, cfg, 'relation', options, 'Select the reading')
    assert selector.calls == before and len(state.clarification_candidates) == expected
    checks.append({'case': 'page_owner_live_and_replay', 'answers': answers, 'passed': True})

from ah.core.journal import JournalChannel, JournalIntegrityError
from ah.formalizer.provider_call_log import ProviderCallLog
with TemporaryDirectory() as directory:
    path = Path(directory) / 'journal'
    journal = JournalChannel(path)
    journal.append('other', {'kind': 'UNRELATED', 'value': 1})
    log = ProviderCallLog(journal)
    call = log.begin('fixture', 'digest', run_id='run', ordinal=1)
    assert log.received(call, raw_response='1')
    assert ProviderCallLog(journal).lookup('run', 1)['raw_response'] == '1'
    try:
        log.failed(call)
    except ValueError as exc:
        assert str(exc) == 'PROVIDER_TERMINAL_REWRITE'
    else:
        raise AssertionError('terminal rewrite admitted')
    raw = path.read_text()
    assert 'UNRELATED' in raw
    path.write_text(raw.replace('UNRELATED', 'CORRUPTED'))
    try:
        ProviderCallLog(JournalChannel(path))
    except JournalIntegrityError:
        pass
    else:
        raise AssertionError('filtered scan hid journal corruption')
checks.append({'case': 'provider_replay_terminal_and_whole_stream_integrity', 'passed': True})

print(json.dumps({'evidence': 'CONTROLLED_CONTRACTS_NOT_MODEL_QUALITY', 'checks': checks}, ensure_ascii=False, indent=2))
