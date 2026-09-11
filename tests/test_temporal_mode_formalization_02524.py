from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from ah.agent import InteractionContext
from ah.config import LLMRoleSettings, PersistenceSettings
from ah.core import AHCore, JsonPersistence, SequentialUidGenerator
from ah.diagnostics.acceptance_runner import _jsonable, canonical_ah_snapshot
from ah.diagnostics.semantic_oracle import SemanticOracleCase, evaluate_semantic_case
from ah.integration import IntegrationConfig, IntegrationService
from ah.llm import LLMResponse
from ah.model import ActantRole, Domain, Property
from ah.perception import (
    ActantCandidate,
    AssertionCandidate,
    AssertionStatus,
    PerceptionResult,
    PredicateCandidate,
    PredicateTemporalProfile,
    PropositionExprCandidate,
    PropositionOperator,
    PropositionRootCandidate,
    TemplateCandidate,
    TemporalMode,
    TemporalModeFormalizationError,
    TemporalModeFormalizer,
    TemporalModeProbeDecision,
    TransitionOperator,
)
from ah.perception.adaptive_parser import AdaptivePerceptionParser, AdaptiveSettings
from ah.perception.morphology import MorphInfo


class Morphology:
    name = "temporal-test"

    def __init__(self, readings=None):
        self.readings = {
            key.casefold(): tuple(value)
            for key, value in (readings or {}).items()
        }

    def analyze_all(self, word: str):
        return self.readings.get(word.casefold(), ())

    def analyze(self, word: str):
        values = self.analyze_all(word)
        return values[0] if values else None


def verbal(lemma: str, aspect: str, *, tense: str = "past") -> MorphInfo:
    return MorphInfo(
        lemma,
        "VERB",
        mood="indc",
        grammemes=frozenset({"VERB", aspect, tense, "indc"}),
        score=1.0,
    )


def occurrence(
    predicate: str = "работал",
    *,
    local_id: str = "A1",
    role: ActantRole | None = ActantRole.TIME,
    sense_hint: str | None = None,
    mode: TemporalMode | None = None,
    transition: TransitionOperator | None = None,
    status: AssertionStatus = AssertionStatus.ASSERTED,
    quoted: bool = False,
    alternatives: tuple[AssertionCandidate, ...] = (),
) -> AssertionCandidate:
    actants = [
        ActantCandidate(
            ActantRole.SUBJECT,
            mention="сервер",
            normalized_hint="сервер",
        )
    ]
    if role is not None:
        actants.append(
            ActantCandidate(role, mention="два часа", normalized_hint="два часа")
        )
    return AssertionCandidate(
        local_id,
        PredicateCandidate(
            predicate,
            predicate.casefold(),
            sense_hint=sense_hint,
            template_candidate=TemplateCandidate(tuple(item.role for item in actants)),
        ),
        tuple(actants),
        alternatives=alternatives,
        temporal_mode=mode,
        transition_operator=transition,
        status=status,
        quoted=quoted,
    )


def result(item: AssertionCandidate) -> PerceptionResult:
    return PerceptionResult("Сервер работал два часа.", assertions=(item,))


def test_stable_perfective_aspect_is_deterministic_event() -> None:
    morph = Morphology({"запустился": (verbal("запуститься", "perf"),)})
    item = occurrence("запустился")
    parsed = TemporalModeFormalizer(morph).formalize(
        result(item),
        resolver=lambda *_args: pytest.fail("stable perfective must not be probed"),
    )
    assert parsed.assertions[0].temporal_mode is TemporalMode.EVENT


@pytest.mark.parametrize("sense", ("RESULT_STATE", "IMPLICIT", "NOMINAL_PREDICATION"))
def test_structural_nominal_or_result_state_is_deterministic_state(sense: str) -> None:
    parsed = TemporalModeFormalizer(Morphology()).formalize(
        result(occurrence("быть", sense_hint=sense))
    )
    assert parsed.assertions[0].temporal_mode is TemporalMode.STATE


def test_ambiguous_morphology_uses_one_typed_semantic_decision() -> None:
    morph = Morphology({"работал": (verbal("работать", "impf"),)})
    calls = []

    def resolve(source, item, profile):
        calls.append((source, item.predicate.surface, profile))
        return TemporalModeProbeDecision.PROCESS

    parsed = TemporalModeFormalizer(morph).formalize(
        result(occurrence()), resolver=resolve
    )
    assert parsed.assertions[0].temporal_mode is TemporalMode.PROCESS
    assert len(calls) == 1
    assert calls[0][2].aspects == ("impf",)


def test_unresolved_observable_occurrence_fails_closed() -> None:
    with pytest.raises(TemporalModeFormalizationError, match="bounded semantic"):
        TemporalModeFormalizer(Morphology()).formalize(result(occurrence()))
    with pytest.raises(TemporalModeFormalizationError, match="ambiguous"):
        TemporalModeFormalizer(Morphology()).formalize(
            result(occurrence()),
            resolver=lambda *_args: TemporalModeProbeDecision.AMBIGUOUS,
        )


def test_unobservable_and_nonfactual_occurrences_are_not_classified() -> None:
    calls = 0

    def resolve(*_args):
        nonlocal calls
        calls += 1
        return TemporalModeProbeDecision.EVENT

    items = (
        occurrence(role=None),
        occurrence(status=AssertionStatus.EMBEDDED),
        occurrence(quoted=True),
    )
    for item in items:
        parsed = TemporalModeFormalizer(Morphology()).formalize(
            result(item), resolver=resolve
        )
        assert parsed.assertions[0].temporal_mode is None
    assert calls == 0


def test_logically_scoped_occurrence_is_not_temporal_state_evidence() -> None:
    item = occurrence()
    source = result(item)
    scoped = PerceptionResult(
        source.source_text,
        assertions=source.assertions,
        proposition_roots=(
            PropositionRootCandidate(
                "F1",
                PropositionExprCandidate(
                    PropositionOperator.POSSIBLE,
                    members=(PropositionExprCandidate.ref_expr("A1"),),
                ),
            ),
        ),
    )
    parsed = TemporalModeFormalizer(Morphology()).formalize(
        scoped,
        resolver=lambda *_args: pytest.fail("scoped occurrence must not be probed"),
    )
    assert parsed.assertions[0].temporal_mode is None


def test_existing_transition_is_preserved_and_contract_is_bidirectional() -> None:
    item = occurrence(
        mode=TemporalMode.TRANSITION,
        transition=TransitionOperator.CONTINUE,
    )
    parsed = TemporalModeFormalizer(Morphology()).formalize(result(item))
    assert parsed.assertions[0] == item
    with pytest.raises(ValueError, match="requires transition_operator"):
        occurrence(mode=TemporalMode.TRANSITION)


def test_alternative_temporal_readings_must_agree() -> None:
    alternative = occurrence(mode=TemporalMode.STATE)
    base = occurrence(alternatives=(alternative,))
    with pytest.raises(TemporalModeFormalizationError, match="alternatives disagree"):
        TemporalModeFormalizer(Morphology()).formalize(
            result(base),
            resolver=lambda *_args: TemporalModeProbeDecision.PROCESS,
        )


def test_temporal_mode_probe_is_nonthinking_fixed_choice_and_uid_free() -> None:
    class Backend:
        def __init__(self) -> None:
            self.calls = []

        def generate(self, prompt, *, system="", override=None, role="generic"):
            self.calls.append((role, prompt, dict(override or {})))
            return LLMResponse("PROCESS", {})

    backend = Backend()
    parser = AdaptivePerceptionParser(
        backend,
        AdaptiveSettings(
            morphology_backend="none",
            prompt_dir=Path(__file__).resolve().parents[1]
            / "prompts"
            / "perception",
            generation=LLMRoleSettings(max_new_tokens=8),
            retry_attempts=0,
        ),
        morphology=Morphology(),
    )
    decision = parser._resolve_temporal_mode_candidate(
        "Сервер работал два часа.",
        occurrence(),
        PredicateTemporalProfile(("impf",), ("past",), ("indc",), ("VERB",)),
    )
    assert decision is TemporalModeProbeDecision.PROCESS
    assert len(backend.calls) == 1
    role, prompt, override = backend.calls[0]
    assert role == "semantic_temporal_mode"
    assert override["enable_thinking"] is False
    assert "CHOICES:\nSTATE\nEVENT\nPROCESS\nAMBIGUOUS" in prompt
    assert "UID" not in prompt.upper()


def _environment():
    core = AHCore(uid_generator=SequentialUidGenerator())
    user = core.add_entity(Domain.P, {"name": Property("name", "user", "str")})
    agent = core.add_entity(Domain.P, {"name": Property("name", "agent", "str")})
    context = InteractionContext(user_ref=core.ref(user.uid), self_ref=core.ref(agent.uid))
    service = IntegrationService(core, IntegrationConfig(0.4, 0.3, 0.2))
    return core, context, service


def test_same_frame_with_distinct_temporal_modes_keeps_distinct_canonical_n(tmp_path) -> None:
    core, context, service = _environment()
    state = occurrence(role=None, mode=TemporalMode.STATE)
    event = occurrence(local_id="A2", role=None, mode=TemporalMode.EVENT)
    commit = service.integrate_external(
        PerceptionResult("Сервер работал.", assertions=(state, event)), context
    )
    assert len(commit.assertions) == 2
    assert commit.assertions[0].ref != commit.assertions[1].ref
    assert {
        core.store.get_hypernode(item.ref.uid).meta.get("temporal_mode")
        for item in commit.assertions
    } == {"STATE", "EVENT"}

    path = tmp_path / "temporal-mode.json"
    persistence = JsonPersistence(path, PersistenceSettings(enabled=True))
    persistence.save(core, context=context)
    loaded = persistence.load(uid_generator=SequentialUidGenerator()).core
    assert {
        node.meta.get("temporal_mode")
        for node in loaded.store.find_hypernodes_by_template(
            loaded.store.get_hypernode(commit.assertions[0].ref.uid).template.uid
        )
    } == {"STATE", "EVENT"}


def test_semantic_oracle_checks_mode_and_transition_wrapper() -> None:
    core, context, service = _environment()
    item = occurrence(
        role=None,
        mode=TemporalMode.TRANSITION,
        transition=TransitionOperator.STOP,
    )
    source = PerceptionResult("Сервер перестал работать.", assertions=(item,))
    commit = service.integrate_external(source, context)
    record = {
        "status": "OK",
        "perception_result": _jsonable(source),
        "integration_commit": _jsonable(commit),
        "queries": [],
    }
    oracle = SemanticOracleCase(
        1,
        source.source_text,
        "EXACT",
        {
            "perception": {
                "assertions": [
                    {
                        "key": "a1",
                        "predicate": "работал",
                        "status": "ASSERTED",
                        "negated": False,
                        "temporal_mode": "TRANSITION",
                        "transition_operator": "STOP",
                        "roles": {"SUBJECT": "сервер"},
                    }
                ],
                "queries": [],
                "relations": [],
                "conditionals": [],
            },
            "integration": {"must_succeed": True},
        },
    )
    snapshot = canonical_ah_snapshot(SimpleNamespace(core=core))
    verdict = evaluate_semantic_case(record, oracle, snapshot, {})
    assert verdict.status == "PASS", verdict.failures
