from copy import deepcopy

import pytest

from ah.formalizer.composition_contracts import lexical_violations
from ah.formalizer.state import FrameCandidate


def frame(name, **semantic):
    return FrameCandidate(name, 'FLAT', name, (name,), predicate_token_ref=name, semantic=semantic)


def modifier(child):
    return frame('modifier', component_questions=[{'kind': 'MODIFIER_SCOPE', 'content_asserted': False}],
                 proposition_args={'OBJECT': {'frame_ref': child.frame_id, 'attitude': 'UNKNOWN'}})


def test_lexical_modifier_passes_without_asserting_or_rewriting_its_content():
    host = frame('host')
    frames = [host, modifier(host)]
    before = deepcopy(frames)
    assert lexical_violations(frames, ['host', 'modifier']) == []
    assert frames == before


@pytest.mark.parametrize('nested', ['clause', 'operator', 'nominal_clause'])
def test_modifier_preserves_genuine_structural_conflict(nested):
    clause = frame('clause')
    host = frame('host')
    outer = modifier(host)
    if nested == 'clause':
        host.semantic['proposition_args'] = {'OBJECT': {'frame_ref': 'clause'}}
    elif nested == 'operator':
        host.semantic['component_scope_tree'] = {'operator': 'NOT', 'operands': [{'frame_ref': 'host'}]}
    else:
        host.semantic['nominal_args'] = [{'frame_ref': 'clause'}]
    frames = [clause, host, outer]
    assert lexical_violations(frames, ['clause', 'host', 'modifier'], boundaries=[outer])


def test_attitude_reading_keeps_its_propositional_boundary():
    host = frame('host')
    outer = modifier(host)
    outer.semantic['proposition_args']['OBJECT']['attitude'] = 'REPORTED'
    assert lexical_violations([outer, host], ['modifier', 'host'])


def test_missing_modifier_host_cannot_pass_as_a_closed_lexical_expression():
    outer = modifier(frame('missing'))
    assert lexical_violations([outer], ['modifier']) == [
        {'owner_ref': 'modifier', 'missing_frame_ref': 'missing'}
    ]
