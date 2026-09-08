"""Real morphology and recovery -> canonical integration -> formal proof gates."""
from dataclasses import replace

import pytest

from ah.agent import InteractionContext
from ah.config import InferenceSettings
from ah.core import AHCore, SequentialUidGenerator
from ah.inference import FormulaGoal, InferenceEngine, LogicalStatus
from ah.integration import IntegrationService, IntegrationConfig
from ah.model import ActantRole, Domain, Property
from ah.perception.contracts import (
    AssertionCandidate, AssertionStatus, PerceptionResult, PredicateCandidate, TemplateCandidate,
)
from ah.perception.linguistic_candidates import EllipsisKind, LinguisticCandidateBuilder
from ah.perception.morphology import Pymorphy3Morphology
from test_ellipsis_invariants_02513 import filler, setup, extract_targets, TEXT
from test_ellipsis_recovery_0257 import parser


@pytest.fixture(scope='module')
def morph():
    return Pymorphy3Morphology()


@pytest.mark.parametrize('dash', ['—', '–', '-'])
@pytest.mark.parametrize('middle', ['Мария', 'а Мария'])
@pytest.mark.parametrize('tail', ['а Пётр — нет', 'и Пётр тоже'])
def test_real_morphology_chained_peer_ownership(morph, dash, middle, tail):
    text = f'Иван купил книгу, {middle} {dash} журнал, {tail}.'
    graph = LinguisticCandidateBuilder(morph).build(text)
    assert len(graph.clauses) == 3
    first, second, third = graph.clauses
    assert second.ellipsis_kind is EllipsisKind.FRAME
    assert second.ellipsis_source_clause_id == first.clause_id
    expected = EllipsisKind.PROPOSITION_NEGATION if 'нет' in tail else EllipsisKind.PROPOSITION_CONFIRMATION
    assert third.ellipsis_kind is expected
    assert third.ellipsis_source_clause_id == second.clause_id
    assert not second.predicate_heads and not third.predicate_heads
    assert [head.token_index for head in graph.predicates] == [2]


@pytest.mark.parametrize('coordinator', ['и', 'или'])
@pytest.mark.parametrize('dash', ['—', '–', '-'])
def test_real_morphology_does_not_split_coordinated_rejection_subject(morph, coordinator, dash):
    graph = LinguisticCandidateBuilder(morph).build(
        f'Иван купил книгу, а Мария {coordinator} Пётр {dash} нет.')
    assert len(graph.clauses) == 2
    assert graph.clauses[1].ellipsis_kind is EllipsisKind.PROPOSITION_NEGATION
    assert f'Мария {coordinator} Пётр' in graph.clauses[1].span.text


@pytest.mark.parametrize('text', [
    'Иван купил книгу, журнал и газету.',
    'Иван купил книгу и журнал.',
    'Иван купил книгу и журнал, а Мария продала газету и открытку.',
    'Иван купил книгу и журнал, Пётр продал газету.',
    'Иван купил книгу. Мария — врач.',
    'Иван купил книгу; Мария — врач.',
    'Иван купил книгу, а Мария — врач.',
    'Иван купил книгу, а Мария прочитала журнал.',
])
def test_real_morphology_preserves_nonellipsis_boundaries(morph, text):
    clauses = LinguisticCandidateBuilder(morph).build(text).clauses
    if "— врач" in text:
        # The dash shell is both a grammatically valid nominal predication and a
        # possible discourse ellipsis.  Keep both readings until complete slot
        # alignment; the parser preserves the nominal reading for this sentence.
        assert clauses[-1].ellipsis_kind is EllipsisKind.FRAME
        assert clauses[-1].implicit_copula
        assert all(c.ellipsis_kind is None for c in clauses[:-1])
    else:
        assert all(c.ellipsis_kind is None for c in clauses)


def runtime():
    core = AHCore(uid_generator=SequentialUidGenerator())
    agent = core.add_entity(Domain.P, {'name': Property('name', 'Агент', 'str')})
    user = core.add_entity(Domain.P, {'name': Property('name', 'Пользователь', 'str')})
    context = InteractionContext(self_ref=core.ref(agent.uid), user_ref=core.ref(user.uid))
    return core, context, IntegrationService(core, IntegrationConfig(initial_hypernode_weight=0.4, experience_hypernode_weight=0.3, follow_link_weight=0.2))


def with_template(source):
    return replace(source, predicate=replace(source.predicate,
        template_candidate=TemplateCandidate(tuple(a.role for a in source.actants))))


@pytest.mark.parametrize('dash', ['—', '–', '-'])
def test_conditional_recovered_consequent_is_canonical_operand_not_world_premise(morph, dash):
    text = f'Если Иван купил книгу, а Мария {dash} журнал.'
    p = parser(morph)
    p._candidate_graph = LinguisticCandidateBuilder(morph).build(text)
    p._active_implicit_clause_id = None
    p._runtime_blocked_token_indices = set()
    tokens = p._source_tokens(text)
    source = AssertionCandidate('A1', PredicateCandidate('купил', normalized_hint='купить'), (
        filler(text, 'Иван', ActantRole.SUBJECT), filler(text, 'книгу', ActantRole.OBJECT)))
    source = with_template(source)
    span = p._resolve_span(text, tokens, 3, 3)
    p._extract_actants = lambda *args, **kwargs: ((
        filler(text, 'Мария', ActantRole.SUBJECT), filler(text, 'журнал', ActantRole.OBJECT)), ())
    out, spans = p._recover_ellipsis_assertions(text, tokens, [source], {'A1': span})
    conditions = p._derive_conditionals(out, spans)
    assert len(conditions) == 1
    assert conditions[0].antecedent_refs == ('A1',)
    assert conditions[0].consequent_refs == (out[-1].local_id,)
    out = p._mark_conditional_statuses(out, conditions)
    assert all(a.status is AssertionStatus.CONDITIONAL for a in out)
    core, context, service = runtime()
    commit = service.integrate_external(PerceptionResult(
        source_text=text, assertions=tuple(out), conditionals=conditions), context)
    assert not commit.assertions
    assert len(commit.conditionals) == 1
    conditional = commit.conditionals[0]
    for ref in conditional.member_refs:
        node = core.store.get_hypernode(ref.uid)
        assert node.meta['semantic_scope'] == 'CONDITIONAL'
        assert node.meta['occurrence_count'] == 0
        outcome = InferenceEngine(core, InferenceSettings()).solve(FormulaGoal(ref))
        assert outcome.status is not LogicalStatus.PROVED


@pytest.mark.parametrize('status', [AssertionStatus.ASSERTED, AssertionStatus.EMBEDDED,
    AssertionStatus.HYPOTHETICAL, AssertionStatus.MODAL])
@pytest.mark.parametrize('quoted', [False, True])
def test_recovered_facts_keep_canonical_scope_and_proof_eligibility(status, quoted):
    p, tokens, source, spans = setup()
    source = with_template(replace(source, status=status, quoted=quoted))
    extract_targets(p, TEXT)
    out, _ = p._recover_ellipsis_assertions(TEXT, tokens, [source], spans)
    core, context, service = runtime()
    commit = service.integrate_external(PerceptionResult(source_text=TEXT, assertions=tuple(out)), context)
    assert len(commit.assertions) == 3
    for assertion in commit.assertions:
        node = core.store.get_hypernode(assertion.ref.uid)
        factual = status is AssertionStatus.ASSERTED and not quoted
        assert bool(node.meta.get('semantic_scope')) is not factual
        outcome = InferenceEngine(core, InferenceSettings()).solve(FormulaGoal(assertion.ref))
        assert (outcome.status is LogicalStatus.PROVED) is factual


def test_recovered_role_substitutions_persist_in_canonical_graph():
    p, tokens, source, spans = setup()
    source = with_template(source)
    extract_targets(p, TEXT)
    out, _ = p._recover_ellipsis_assertions(TEXT, tokens, [source], spans)
    core, context, service = runtime()
    commit = service.integrate_external(PerceptionResult(source_text=TEXT, assertions=tuple(out)), context)
    nodes = [core.store.get_hypernode(a.ref.uid) for a in commit.assertions]
    assert len({n.template for n in nodes}) == 1
    assert len({n.actants[ActantRole.SUBJECT] for n in nodes}) == 3
    assert nodes[0].actants[ActantRole.OBJECT] != nodes[1].actants[ActantRole.OBJECT]
    assert nodes[1].actants[ActantRole.OBJECT] == nodes[2].actants[ActantRole.OBJECT]

# Manual structural expectations for failures in the user's 20260907_000020 run.
# This is a candidate-graph regression, not a replacement semantic acceptance score.
@pytest.mark.parametrize('case_index,modes', [
    (2, (None, 'FRAME')), (8, (None, 'FRAME')),
    (21, (None, 'FRAME')), (22, (None, 'FRAME')),
    (23, (None, 'PROPOSITION_NEGATION')),
    (24, (None, 'FRAME', 'FRAME', 'FRAME')),
    (25, (None, 'FRAME', None)),
    (26, (None, 'FRAME', 'FRAME')),
    (27, (None, 'FRAME', 'FRAME', 'FRAME')),
    (28, (None, 'FRAME', 'FRAME')),
    (29, (None, 'FRAME', 'FRAME')),
    (30, (None, 'FRAME', 'FRAME')),
    (31, (None, 'FRAME', 'FRAME')),
    (32, (None, 'FRAME', 'FRAME')),
    (33, (None, 'FRAME', None)),
    (34, (None, None, 'FRAME')),
    (77, (None, 'FRAME', None)),
    (78, (None, None, 'FRAME')),
    (79, (None, 'FRAME', None, 'FRAME')),
    (80, (None, 'FRAME', None, 'FRAME')),
    (81, (None, 'FRAME', None)),
    (82, (None, 'FRAME', None)),
    (83, (None, 'FRAME', 'FRAME')),
    (84, (None, 'FRAME', None)),
    (85, (None, None)),
])
def test_live_acceptance_failure_clause_regression(morph, case_index, modes):
    import json
    from pathlib import Path
    oracle = json.loads((Path(__file__).resolve().parents[1] /
        'data/acceptance_ellipsis/oracle.json').read_text(encoding='utf-8'))
    text = oracle['cases'][case_index - 1]['text']
    graph = LinguisticCandidateBuilder(morph).build(text)
    assert tuple(c.ellipsis_kind.value if c.ellipsis_kind else None
                 for c in graph.clauses) == modes
    for index, clause in enumerate(graph.clauses):
        if modes[index] is not None:
            assert not clause.predicate_heads
            # A grammatically valid dash predication is retained as a
            # provisional competing reading until slot alignment.
            if clause.implicit_copula:
                assert clause.ellipsis_kind is EllipsisKind.FRAME
            assert clause.ellipsis_source_clause_id == graph.clauses[index - 1].clause_id
