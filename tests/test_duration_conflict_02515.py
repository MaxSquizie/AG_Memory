"""Whole duration identity and unresolved-conflict attention in the real pipeline."""
import pytest

from ah.inference import InferenceEngine
from ah.config import IgnitionSettings, SeedSettings, WorkspaceSettings
from ah.ignition import IgnitionEngine
from ah.integration import SeedReason
from ah.integration.template_completion import TemplateCompletionService
from ah.llm.process_backend import LLMResponse
from ah.model import ActantRole
from ah.perception import LLMPerceptionService, LLMPerceptionSettings
from test_full_ellipsis_pipeline_02514 import ROOT, SemanticFixture
from test_ellipsis_canonical_02513 import runtime


class DurationFixture(SemanticFixture):
    def generate(self, prompt, *, system='', override=None, role='generic'):
        if role == 'perception_role_cue':
            target = prompt.split('TARGET:\n', 1)[1].split('\n', 1)[0]
            if target in {'2', '3'}:
                self.calls.append((role, prompt))
                assert 'QUANTITY_OR_MEASURE' in prompt
                return LLMResponse('QUANTITY_OR_MEASURE', {})
            if target in {'два часа', 'три часа', 'пять минут', '2 часа', '3 часа',
                          'два дня', 'три дня', 'на два часа', 'часа'}:
                self.calls.append((role, prompt))
                assert 'ELAPSED_DURATION' in prompt
                return LLMResponse('ELAPSED_DURATION', {})
        return super().generate(prompt, system=system, override=override, role=role)


def perception():
    return LLMPerceptionService(DurationFixture(), LLMPerceptionSettings(
        protocol='adaptive_v3', probe_prompt_dir=ROOT/'prompts/perception',
        probe_retry_attempts=0, morphology_backend='pymorphy3'))


@pytest.mark.parametrize('value', ['два часа', 'три часа', 'пять минут', '2 часа', '3 часа', 'два дня', 'три дня'])
@pytest.mark.parametrize('pattern', ['Мария ждала {value}.', '{value} ждала Мария.'])
def test_duration_preserves_measure_and_source_through_commit(value, pattern):
    core, context, integration = runtime()
    service = perception()
    text = pattern.format(value=value)
    parsed = service.parse(text, context)
    assert len(parsed.assertions) == 1
    duration = next(a for a in parsed.assertions[0].actants if a.role is ActantRole.DURATION)
    assert duration.lookup_text.casefold() == value.casefold()
    assert duration.evidence.text.casefold() == value.casefold()
    assert text[duration.evidence.start:duration.evidence.end] == duration.evidence.text
    assert duration.nominal_relations == ()
    completed = TemplateCompletionService(integration, service).complete(parsed)
    result = integration.integrate_external(completed, context)
    node = core.store.get_hypernode(result.assertions[0].ref.uid)
    entity = core.store.get_element_any_domain(node.actants[ActantRole.DURATION].uid)
    assert entity.properties['name'].value.casefold() == value.casefold()


def test_different_durations_are_distinct_and_repeat_is_idempotent():
    core, context, integration = runtime()
    service = perception()
    completion = TemplateCompletionService(integration, service)
    refs = []
    values = []
    for value in ['два часа', 'три часа', 'два часа']:
        commit = integration.integrate_external(completion.complete(
            service.parse(f'Мария ждала {value}.', context)), context)
        ref = commit.assertions[0].ref
        refs.append(ref)
        values.append(core.store.get_hypernode(ref.uid).actants[ActantRole.DURATION])
    assert refs[0] != refs[1] and refs[0] == refs[2]
    assert values[0] != values[1] and values[0] == values[2]


def test_real_polarity_conflict_reaches_ignition_without_selecting_truth():
    from ah.conflict import ConflictEngine
    from ah.inference import LogicalStatus, StopReason
    from test_v4_conflict_engine_1500 import _env, _solve
    core, context, integration, inference = _env()
    service = perception()
    completion = TemplateCompletionService(integration, service)
    ignition = IgnitionEngine(core, IgnitionSettings(seeds=SeedSettings(correction=0.73)), WorkspaceSettings())
    commits = []
    for text in ['Иван читает книгу.', 'Иван не читает книгу.']:
        commit = integration.integrate_external(completion.complete(service.parse(text, context)), context)
        ignition.apply_seed_requests(commit.activation_seeds)
        commits.append(commit)
    conflict = commits[-1].conflicts[0]
    assert any(s.reason is SeedReason.CONFLICT and s.ref == conflict.ref
               for s in commits[-1].activation_seeds)
    ignition.tick()
    assert core.store.runtime_state(conflict.ref.uid).excitation > 0
    for commit in commits:
        ref = commit.assertions[0].ref
        assert ConflictEngine(core).is_conflicted(ref)
        outcome = _solve(inference, ref)
        assert outcome.status is LogicalStatus.UNKNOWN
        assert outcome.stop_reason is StopReason.CONFLICTED


@pytest.mark.parametrize('dash', ['—', '–', '-'])
def test_ellipsis_transfers_role_without_collapsing_duration_values(dash):
    core, context, integration = runtime()
    service = perception()
    parsed = service.parse(f'Мария ждала два часа, а Иван {dash} три часа.', context)
    assert len(parsed.assertions) == 2
    values = [next(a.lookup_text for a in assertion.actants if a.role is ActantRole.DURATION)
              for assertion in parsed.assertions]
    assert values == ['два часа', 'три часа']
    commit = integration.integrate_external(TemplateCompletionService(integration, service).complete(parsed), context)
    refs = [core.store.get_hypernode(a.ref.uid).actants[ActantRole.DURATION] for a in commit.assertions]
    assert refs[0] != refs[1]
