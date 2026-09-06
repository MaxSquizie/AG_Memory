"""Semantic boundary regressions; fixtures supply only the bounded role extraction seam."""
from dataclasses import replace
import types

import pytest

from ah.model import ActantRole
from ah.perception.adaptive_parser import AdaptiveParseError
from ah.perception.contracts import (
    ActantCandidate, AssertionStatus, EvidenceSpan,
    ActantCompositionCandidate, CompositionMemberCandidate, CompositionOperator,
)
from ah.perception.linguistic_candidates import LinguisticCandidateBuilder
from test_ellipsis_recovery_0257 import morphology, parser, source_assertion

TEXT = 'Иван купил книгу, а Мария — журнал, Пётр — журнал.'


def setup(text=TEXT):
    p = parser(morphology())
    p._candidate_graph = LinguisticCandidateBuilder(p.morphology).build(text)
    p._active_implicit_clause_id = None
    p._runtime_blocked_token_indices = set()
    tokens = p._source_tokens(text)
    source = source_assertion(text)
    spans = {'A1': p._resolve_span(text, tokens, 2, 2)}
    return p, tokens, source, spans


def filler(text, mention, role, start=0):
    offset = text.index(mention, start)
    return ActantCandidate(role, mention=mention, normalized_hint=mention,
                           evidence=EvidenceSpan(mention, offset, offset + len(mention)))


def extract_targets(p, text, *, fail=None):
    def extract(self, *args, **kwargs):
        if fail:
            raise fail
        clause = next(c for c in self._candidate_graph.clauses
                      if c.clause_id == self._active_implicit_clause_id)
        subject = 'Мария' if 'Мария' in clause.span.text else 'Пётр'
        return ((filler(text, subject, ActantRole.SUBJECT),
                 filler(text, 'журнал', ActantRole.OBJECT, clause.span.evidence.start)), ())
    p._extract_actants = types.MethodType(extract, p)


@pytest.mark.parametrize('source_id', ['A1', 'A3', 'A10', 'custom'])
@pytest.mark.parametrize('reverse', [False, True])
def test_recovery_allocates_unique_ids_and_keeps_source_order_independent(source_id, reverse):
    p, tokens, source, spans = setup()
    source = replace(source, local_id=source_id)
    spans = {source_id: spans['A1']}
    extract_targets(p, TEXT)
    # An unrelated existing local id occupies the naive len(out)+1 slot.
    other = replace(source, local_id='A4' if source_id != 'A4' else 'A5')
    inputs = [other, source] if reverse else [source, other]
    out, result_spans = p._recover_ellipsis_assertions(TEXT, tokens, inputs, spans)
    assert len({a.local_id for a in out}) == len(out) == 4
    assert len(result_spans) == 3
    assert [a.actants[0].mention for a in out[-2:]] == ['Мария', 'Пётр']


@pytest.mark.parametrize('status', list(AssertionStatus))
@pytest.mark.parametrize('negated', [False, True])
@pytest.mark.parametrize('quoted', [False, True])
def test_chain_preserves_polarity_status_quote_and_target_provenance(status, negated, quoted):
    p, tokens, source, spans = setup()
    source = replace(source, status=status, negated=negated, quoted=quoted)
    extract_targets(p, TEXT)
    out, new_spans = p._recover_ellipsis_assertions(TEXT, tokens, [source], spans)
    assert len(out) == 3
    assert out[0] is source
    for result in out[1:]:
        assert (result.status, result.negated, result.quoted) == (status, negated, quoted)
        assert result.predicate is source.predicate
        span = new_spans[result.local_id]
        assert span is not None, 'scope compilation needs the recovered clause location'
        assert span.evidence == result.evidence
        assert TEXT[span.evidence.start:span.evidence.end] == span.text
    assert len(spans) == 1, 'input provenance map must not be mutated'


@pytest.mark.parametrize('problem', ['missing', 'future', 'ambiguous_clause', 'alternatives', 'empty_parse', 'missing_source_id'])
def test_unresolved_antecedent_cannot_be_replaced_by_arbitrary_frame(problem):
    p, tokens, source, spans = setup()
    extract_targets(p, TEXT)
    if problem == 'empty_parse':
        inputs, spans = [], {}
    elif problem == 'missing_source_id':
        clauses = p._candidate_graph.clauses
        p._candidate_graph = replace(p._candidate_graph, clauses=(clauses[0], replace(clauses[1], ellipsis_source_clause_id=None), clauses[2]))
        inputs = [source]
    elif problem == 'missing':
        inputs, spans = [source], {}
    elif problem == 'future':
        # The only available frame occurs after the target clause.
        last = p._candidate_graph.clauses[-1]
        spans = {'A1': p._resolve_span(TEXT, tokens, last.span.start_index, last.span.end_index)}
        inputs = [source]
    elif problem == 'ambiguous_clause':
        inputs = [source, replace(source, local_id='A2')]
        spans['A2'] = spans['A1']
    else:
        inputs = [replace(source, alternatives=(source, replace(source, negated=True)))]
    with pytest.raises(AdaptiveParseError, match='ellipsis'):
        p._recover_ellipsis_assertions(TEXT, tokens, inputs, spans)


@pytest.mark.parametrize('problem', ['empty', 'duplicate_role', 'foreign_role', 'outside', 'no_evidence', 'fabricated_evidence'])
def test_invalid_target_is_not_silently_dropped_or_overwritten(problem):
    p, tokens, source, spans = setup()
    target = filler(TEXT, 'Мария', ActantRole.SUBJECT)
    targets = {
        'empty': (),
        'duplicate_role': (replace(target, evidence=None), replace(target, mention='Пётр', evidence=None)),
        'foreign_role': (replace(target, role=ActantRole.TOOL, evidence=None),),
        'outside': (source.actants[0],),
        'fabricated_evidence': (replace(target, evidence=replace(target.evidence, text='invented')),),
        'no_evidence': (replace(target, evidence=None),),
    }[problem]
    p._extract_actants = lambda *args, **kwargs: (targets, ())
    with pytest.raises(AdaptiveParseError, match='ellipsis'):
        p._recover_ellipsis_assertions(TEXT, tokens, [source], spans)


def test_role_extraction_exception_restores_runtime_state():
    p, tokens, source, spans = setup()
    p._active_implicit_clause_id = 'previous'
    p._runtime_blocked_token_indices = {99}
    extract_targets(p, TEXT, fail=RuntimeError('probe failed'))
    with pytest.raises(RuntimeError, match='probe failed'):
        p._recover_ellipsis_assertions(TEXT, tokens, [source], spans)
    assert p._active_implicit_clause_id == 'previous'
    assert p._runtime_blocked_token_indices == {99}
    assert list(spans) == ['A1']


def test_coordinated_target_is_preserved_as_one_composition():
    text = 'Иван купил книгу, а Мария и Пётр — нет.'
    p, tokens, source, spans = setup(text)
    group = ActantCandidate(ActantRole.SUBJECT,
        composition=ActantCompositionCandidate(CompositionOperator.AND, (
            CompositionMemberCandidate('Мария'), CompositionMemberCandidate('Пётр'))),
        evidence=EvidenceSpan('Мария и Пётр', text.index('Мария'), text.index('Пётр')+4))
    p._extract_actants = lambda *args, **kwargs: ((group,), ())
    out, _ = p._recover_ellipsis_assertions(text, tokens, [source], spans)
    assert out[-1].actants == (group, source.actants[1])
    assert out[-1].negated is True


def test_negated_antecedent_rejection_does_not_report_partial_success():
    text = 'Иван купил книгу, а Мария — нет.'
    p, tokens, source, spans = setup(text)
    p._extract_actants = lambda *args, **kwargs: ((filler(text, 'Мария', ActantRole.SUBJECT),), ())
    with pytest.raises(AdaptiveParseError, match='ellipsis'):
        p._recover_ellipsis_assertions(text, tokens, [replace(source, negated=True)], spans)
