from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

import pytest

from ah.agent import InteractionContext
from ah.config import InferenceSettings, LLMRoleSettings, PersistenceSettings
from ah.core import AHCore, JsonPersistence, SequentialUidGenerator
from ah.inference import FormulaGoal, GoalSpec, InferenceEngine, InferenceQuery, LogicalStatus
from ah.integration import IntegrationConfig, IntegrationService
from ah.model import ActantRole, BoundVar, Domain, FunctionSymbol, Hypernode, Property, Ref, VariableSort
from ah.perception import (
    ActantCandidate,
    AssertionCandidate,
    AssertionStatus,
    EvidenceSpan,
    PerceptionResult,
    PredicateCandidate,
    TemplateCandidate,
    TemporalScopeCandidate,
    TemporalScopeFormalizationError,
    TemporalScopeFormalizer,
    TemporalScopeKind,
    TemporalScopeProbeDecision,
)
from ah.perception.morphology import MorphInfo
from ah.perception.adaptive_parser import AdaptivePerceptionParser, AdaptiveSettings
from ah.llm import LLMResponse
from ah.temporal import TemporalKind, TemporalPrecision, TemporalValue, ensure_time_entity


ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "data" / "acceptance_semantic_composition" / "cases.txt"
ORACLE = ROOT / "data" / "acceptance_semantic_composition" / "oracle.json"
ANCHOR = datetime(2026, 9, 11, 12, 0, tzinfo=timezone.utc)


class Morphology:
    name = "never-test"

    def __init__(self, readings=None):
        self.readings = {
            key.casefold(): tuple(value) for key, value in (readings or {}).items()
        }

    def analyze_all(self, word: str):
        return self.readings.get(word.casefold(), ())

    def analyze(self, word: str):
        values = self.analyze_all(word)
        return values[0] if values else None


def morph(lemma: str, pos: str, *grammemes: str) -> MorphInfo:
    return MorphInfo(lemma, pos, grammemes=frozenset(grammemes), score=1.0)


def occurrence(
    *,
    source: str = "Лев никогда не проверял мотор.",
    status: AssertionStatus = AssertionStatus.ASSERTED,
    quoted: bool = False,
    temporal_scope: TemporalScopeCandidate | None = None,
) -> PerceptionResult:
    cue_start = source.casefold().find("никогда")
    cue = ActantCandidate(
        ActantRole.TIME,
        mention="никогда",
        normalized_hint="никогда",
        evidence=EvidenceSpan("никогда", cue_start, cue_start + 7),
    )
    roles = (ActantRole.SUBJECT, ActantRole.OBJECT, ActantRole.TIME)
    return PerceptionResult(
        source,
        assertions=(
            AssertionCandidate(
                "A1",
                PredicateCandidate(
                    "проверял",
                    "проверять",
                    template_candidate=TemplateCandidate(roles),
                ),
                (
                    ActantCandidate(ActantRole.SUBJECT, mention="Лев", normalized_hint="лев"),
                    ActantCandidate(ActantRole.OBJECT, mention="мотор", normalized_hint="мотор"),
                    cue,
                ),
                negated=True,
                status=status,
                quoted=quoted,
                temporal_scope=temporal_scope,
            ),
        ),
    )


def env():
    core = AHCore(uid_generator=SequentialUidGenerator())
    user = core.add_entity(Domain.P, {"name": Property("name", "user", "str")})
    agent = core.add_entity(Domain.P, {"name": Property("name", "agent", "str")})
    context = InteractionContext(user_ref=core.ref(user.uid), self_ref=core.ref(agent.uid))
    service = IntegrationService(core, IntegrationConfig(0.4, 0.3, 0.2))
    engine = InferenceEngine(
        core,
        InferenceSettings(max_depth=12, max_expanded_states=512),
        schema_registry=service.schema_registry,
    )
    return core, context, service, engine


def render(core: AHCore, operand) -> str:
    if isinstance(operand, BoundVar):
        return f"${operand.local_id}:{operand.sort.value}"
    assert isinstance(operand, Ref)
    obj = core.store.get_element_any_domain(operand.uid)
    if isinstance(obj, FunctionSymbol):
        return f"{obj.function_id}(" + ",".join(render(core, item) for item in obj.operands) + ")"
    if isinstance(obj, Hypernode):
        template = core.store.get_template(obj.template.uid)
        symbol = core.store.get_symbol(template.predicate.uid)
        predicate = sorted(symbol.forms, key=lambda item: (len(item), item))[0]
        return f"{predicate}(" + ",".join(render(core, obj.actants[role]) for role in template.roles) + ")"
    return operand.uid


def test_a1_acceptance_oracle_is_aligned_before_production() -> None:
    lines = tuple(line.strip() for line in CASES.read_text(encoding="utf-8").splitlines() if line.strip())
    oracle = json.loads(ORACLE.read_text(encoding="utf-8"))
    assert oracle["roadmap_step"] == "A1_TEMPORAL_NEVER"
    assert oracle["case_count"] == len(lines) == len(oracle["cases"]) == 20
    assert tuple(item["text"] for item in oracle["cases"]) == lines
    assert {item["decision"] for item in oracle["cases"]} == {"NEVER", "PLAIN_NEGATION", "AMBIGUOUS"}
    assert {item["scope"] for item in oracle["cases"]} >= {"ASSERTED", "QUOTED", "POSSIBLE", "REQUIRED"}


def test_structural_candidate_uses_one_bounded_semantic_decision() -> None:
    source = occurrence()
    formalizer = TemporalScopeFormalizer(
        Morphology({"никогда": (morph("никогда", "ADVB"),)})
    )
    calls = []

    def resolve(text, assertion, candidates):
        calls.append((text, assertion.local_id, candidates))
        return TemporalScopeProbeDecision.NEVER

    parsed = formalizer.formalize(source, resolver=resolve)
    item = parsed.assertions[0]
    assert len(calls) == 1
    assert item.negated is False
    assert item.temporal_scope is not None
    assert item.temporal_scope.kind is TemporalScopeKind.NEVER
    assert item.temporal_scope.anchor == "RELEVANT_PAST"
    assert len([actant for actant in item.actants if actant.role is ActantRole.TIME]) == 1
    assert item.actants[-1].entity_ref == item.temporal_scope.variable_ref


def test_plain_negation_is_not_rewritten_and_ambiguity_fails_closed() -> None:
    source = occurrence()
    formalizer = TemporalScopeFormalizer(
        Morphology({"никогда": (morph("никогда", "ADVB"),)})
    )
    plain = formalizer.formalize(
        source, resolver=lambda *_args: TemporalScopeProbeDecision.PLAIN_NEGATION
    )
    assert plain.assertions[0].temporal_scope is None
    assert plain.assertions[0].negated is True
    with pytest.raises(TemporalScopeFormalizationError, match="ambiguous"):
        formalizer.formalize(
            source, resolver=lambda *_args: TemporalScopeProbeDecision.AMBIGUOUS
        )


def test_temporal_scope_probe_is_nonthinking_fixed_choice_and_uid_free() -> None:
    class Backend:
        def __init__(self) -> None:
            self.calls = []

        def generate(self, prompt, *, system="", override=None, role="generic"):
            self.calls.append((role, prompt, dict(override or {})))
            return LLMResponse("NEVER", {})

    backend = Backend()
    parser = AdaptivePerceptionParser(
        backend,
        AdaptiveSettings(
            morphology_backend="none",
            prompt_dir=ROOT / "prompts" / "perception",
            generation=LLMRoleSettings(max_new_tokens=8),
            retry_attempts=0,
        ),
        morphology=Morphology(),
    )
    decision = parser._resolve_temporal_scope_candidate(
        "Лев никогда не проверял мотор.",
        occurrence().assertions[0],
        (EvidenceSpan("никогда", 4, 11),),
    )
    assert decision is TemporalScopeProbeDecision.NEVER
    assert len(backend.calls) == 1
    role, prompt, override = backend.calls[0]
    assert role == "semantic_temporal_scope"
    assert override["enable_thinking"] is False
    assert "CHOICES:\nNEVER\nPLAIN_NEGATION\nAMBIGUOUS" in prompt
    assert "UID" not in prompt.upper()


def test_explicit_temporal_scope_is_idempotent_and_alternatives_must_agree() -> None:
    explicit = TemporalScopeCandidate(
        TemporalScopeKind.NEVER,
        variable_ref="TIME:A1",
        anchor="RELEVANT_PAST",
    )
    source = occurrence(temporal_scope=explicit)
    parsed = TemporalScopeFormalizer(Morphology()).formalize(
        source, resolver=lambda *_args: pytest.fail("typed scope must not be probed")
    )
    assert parsed.assertions[0].temporal_scope == explicit

    item = source.assertions[0]
    mismatch = occurrence().assertions[0]
    inconsistent = PerceptionResult(
        source.source_text,
        assertions=(AssertionCandidate(
            item.local_id,
            item.predicate,
            item.actants,
            alternatives=(mismatch,),
            negated=item.negated,
            temporal_scope=item.temporal_scope,
        ),),
    )
    with pytest.raises(TemporalScopeFormalizationError, match="alternatives disagree"):
        TemporalScopeFormalizer(Morphology()).formalize(inconsistent)


def test_temporal_never_materializes_explicit_time_scope_without_query_writes(tmp_path: Path) -> None:
    core, context, service, engine = env()
    typed = TemporalScopeFormalizer(Morphology()).formalize(
        occurrence(
            temporal_scope=TemporalScopeCandidate(
                TemporalScopeKind.NEVER,
                variable_ref="TIME:A1",
                anchor="RELEVANT_PAST",
            )
        )
    )
    before = len(core.store.all_elements())
    commit = service.integrate_external(typed, context, source_timestamp=ANCHOR)
    assert len(commit.temporal_scopes) == 1
    integrated = commit.temporal_scopes[0]
    assert render(core, integrated.ref).startswith("NOT(EXISTS($0:TIME,AND(")
    assert "RELEVANT_PAST($0:TIME," in render(core, integrated.ref)
    assert "проверял(" in render(core, integrated.ref)
    body = core.store.get_element_any_domain(integrated.member_refs[0].uid)
    assert isinstance(body, Hypernode)
    assert body.meta["semantic_scope"] == "TEMPORAL_NEVER"
    assert body.meta["occurrence_count"] == 0

    persisted = tmp_path / "never.json"
    persistence = JsonPersistence(persisted, PersistenceSettings(enabled=True))
    persistence.save(core)
    loaded = persistence.load().core
    assert render(loaded, loaded.ref(integrated.ref.uid)) == render(core, integrated.ref)

    count_before_query = len(core.store.all_elements())
    outcome = engine.solve(InferenceQuery(GoalSpec(FormulaGoal(integrated.ref))))
    assert outcome.status is LogicalStatus.PROVED
    assert outcome.proof_support[0].rule_id == "NOT_ASSERTED"
    assert len(core.store.all_elements()) == count_before_query
    assert before < count_before_query


def test_absence_does_not_prove_never_but_asserted_never_refutes_matching_exists() -> None:
    core, context, service, engine = env()
    typed = TemporalScopeFormalizer(Morphology()).formalize(
        occurrence(
            temporal_scope=TemporalScopeCandidate(
                TemporalScopeKind.NEVER,
                variable_ref="TIME:A1",
                anchor="RELEVANT_PAST",
            )
        )
    )
    commit = service.integrate_external(typed, context, source_timestamp=ANCHOR)
    never_ref = commit.temporal_scopes[0].ref
    never_obj = core.store.get_element_any_domain(never_ref.uid)
    assert isinstance(never_obj, FunctionSymbol) and never_obj.function_id == "NOT"
    exists_ref = never_obj.operands[0]
    assert isinstance(exists_ref, Ref)

    asserted = engine.solve(InferenceQuery(GoalSpec(FormulaGoal(exists_ref))))
    assert asserted.status is LogicalStatus.DISPROVED
    assert asserted.proof_support[0].rule_id == "NOT_ASSERTED"

    empty_core, _empty_context, _empty_service, empty_engine = env()
    subject = empty_core.add_entity(Domain.C, {"name": Property("name", "Лев", "str")})
    obj = empty_core.add_entity(Domain.C, {"name": Property("name", "мотор", "str")})
    symbol = empty_core.ensure_abstract_symbol("проверять")
    template = empty_core.add_template(
        Domain.C,
        empty_core.ref(symbol.uid),
        (ActantRole.SUBJECT, ActantRole.OBJECT, ActantRole.TIME),
    )
    variable = BoundVar(0, VariableSort.TIME)
    pattern, _ = empty_core.add_hypernode(
        Domain.C,
        empty_core.ref(template.uid),
        {
            ActantRole.SUBJECT: empty_core.ref(subject.uid),
            ActantRole.OBJECT: empty_core.ref(obj.uid),
            ActantRole.TIME: variable,
        },
        0.4,
        meta={"semantic_scope": "TEMPORAL_NEVER"},
        count_occurrence=False,
    )
    anchor, _ = ensure_time_entity(
        empty_core,
        TemporalValue(
            TemporalKind.POINT,
            ANCHOR.isoformat(),
            None,
            TemporalPrecision.SECOND,
        ),
    )
    past, _ = empty_core.ensure_function(
        Domain.C, "RELEVANT_PAST", (variable, anchor)
    )
    body, _ = empty_core.ensure_function(
        Domain.C,
        "AND",
        (empty_core.ref(pattern.uid), empty_core.ref(past.uid)),
    )
    exists, _ = empty_core.ensure_function(
        Domain.C, "EXISTS", (variable, empty_core.ref(body.uid))
    )
    before_query = len(empty_core.store.all_elements())
    absent = empty_engine.solve(
        InferenceQuery(GoalSpec(FormulaGoal(empty_core.ref(exists.uid))))
    )
    assert absent.status is LogicalStatus.UNKNOWN
    assert len(empty_core.store.all_elements()) == before_query

    future, _ = ensure_time_entity(
        empty_core,
        TemporalValue(
            TemporalKind.POINT,
            "2026-09-12T12:00:00+00:00",
            None,
            TemporalPrecision.SECOND,
        ),
    )
    empty_core.add_hypernode(
        Domain.C,
        empty_core.ref(template.uid),
        {
            ActantRole.SUBJECT: empty_core.ref(subject.uid),
            ActantRole.OBJECT: empty_core.ref(obj.uid),
            ActantRole.TIME: future,
        },
        0.4,
    )
    assert empty_engine.solve(
        InferenceQuery(GoalSpec(FormulaGoal(empty_core.ref(exists.uid))))
    ).status is LogicalStatus.UNKNOWN

    past_time, _ = ensure_time_entity(
        empty_core,
        TemporalValue(
            TemporalKind.POINT,
            "2026-09-10T12:00:00+00:00",
            None,
            TemporalPrecision.SECOND,
        ),
    )
    ground, _ = empty_core.add_hypernode(
        Domain.C,
        empty_core.ref(template.uid),
        {
            ActantRole.SUBJECT: empty_core.ref(subject.uid),
            ActantRole.OBJECT: empty_core.ref(obj.uid),
            ActantRole.TIME: past_time,
        },
        0.4,
    )
    before_proof = len(empty_core.store.all_elements())
    witnessed = empty_engine.solve(
        InferenceQuery(GoalSpec(FormulaGoal(empty_core.ref(exists.uid))))
    )
    assert witnessed.status is LogicalStatus.PROVED
    assert witnessed.proof_support[0].rule_id == "EXISTS_WITNESS"
    assert empty_core.ref(ground.uid) in witnessed.premise_refs
    assert past_time in witnessed.premise_refs
    assert anchor in witnessed.premise_refs
    assert len(empty_core.store.all_elements()) == before_proof


def test_missing_relevant_past_anchor_fails_before_canonical_mutation() -> None:
    core, context, service, _engine = env()
    typed = TemporalScopeFormalizer(Morphology()).formalize(
        occurrence(
            temporal_scope=TemporalScopeCandidate(
                TemporalScopeKind.NEVER,
                variable_ref="TIME:A1",
                anchor="RELEVANT_PAST",
            )
        )
    )
    before = len(core.store.all_elements())
    with pytest.raises(Exception, match="relevant-past anchor"):
        service.integrate_external(typed, context)
    assert len(core.store.all_elements()) == before


@pytest.mark.parametrize(
    ("status", "quoted"),
    ((AssertionStatus.EMBEDDED, False), (AssertionStatus.MODAL, False), (AssertionStatus.ASSERTED, True)),
)
def test_temporal_never_nested_scope_never_becomes_ordinary_fact(status, quoted) -> None:
    source = occurrence(status=status, quoted=quoted)
    parsed = TemporalScopeFormalizer(
        Morphology({"никогда": (morph("никогда", "ADVB"),)})
    ).formalize(source, resolver=lambda *_args: TemporalScopeProbeDecision.NEVER)
    item = parsed.assertions[0]
    assert item.temporal_scope is not None
    assert item.negated is False
    assert item.status is status
    assert item.quoted is quoted
    core, context, service, engine = env()
    commit = service.integrate_external(parsed, context, source_timestamp=ANCHOR)
    assert len(commit.temporal_scopes) == 1
    scoped = commit.temporal_scopes[0]
    body = core.store.get_hypernode(scoped.member_refs[0].uid)
    assert body.meta["semantic_scope"] == "TEMPORAL_NEVER"
    assert body.meta["source_scope"] in {"EMBEDDED", "MODAL", "QUOTED"}
    assert body.meta["occurrence_count"] == 0
    outcome = engine.solve(InferenceQuery(GoalSpec(FormulaGoal(scoped.ref))))
    assert outcome.status is LogicalStatus.UNKNOWN


def test_acceptance_sentences_are_not_a_production_dictionary() -> None:
    algorithm = "\n".join(
        path.read_text(encoding="utf-8")
        for base in (ROOT / "src" / "ah" / "perception", ROOT / "src" / "ah" / "integration")
        for path in base.rglob("*.py")
    ).casefold()
    for line in CASES.read_text(encoding="utf-8").splitlines():
        if line.strip():
            assert line.strip().casefold() not in algorithm
