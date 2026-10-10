import pytest

from ah.formalizer.pipeline import t0
from ah.formalizer.syntax_rules import enumerate_matches, SearchLimit, _junction


def rule(rid='r'):
    return {'rule_id': rid, 'priority': 0, 'stage': 'T2',
            'input_feature_pattern': {'captures': {'x': {'surface': ['x']}}, 'window': 'SENTENCE'},
            'output_kind': 'CANDIDATE_GRAPH', 'constraints': [], 'min_evidence': 1}


def state(text, regional=True):
    st = t0(text)
    st.observation = {'syntax_budget_scope': 'SOURCE_WINDOW_V1' if regional else 'OBSERVATION'}
    return st


def test_document_windows_do_not_spend_one_anothers_limits():
    policy = {'max_rule_steps': 8, 'max_rule_matches': 1, 'max_source_tokens': 8}
    found = enumerate_matches(state('x. x.'), [rule()], 'T2', policy, None)
    assert [m.window for m in found] == [(0, 2), (2, 4)]
    with pytest.raises(SearchLimit):
        enumerate_matches(state('x. x.', False), [rule()], 'T2', policy, None)


def test_rules_share_one_window_budget_and_incomplete_search_still_fails_closed():
    st = state('x.')
    with pytest.raises(SearchLimit):
        enumerate_matches(st, [rule('a'), rule('b')], 'T2',
                          {'max_rule_steps': 12, 'max_rule_matches': 20, 'max_source_tokens': 8}, None)
    assert st.syntax_trace[-1]['window'] == [0, 2]
    assert st.syntax_trace[-1]['window_step'] == 13
    assert st.syntax_trace[-1]['budget_scope'] == 'SOURCE_WINDOW_V1'


@pytest.mark.parametrize('kind, values, result', [
    ('AND', [None, False], False), ('OR', [None, True], True),
    ('AND', [True, None], None), ('OR', [False, None], None),
    ('AND', [True, True], True), ('OR', [False, False], False)])
def test_short_circuit_retains_three_valued_semantics(kind, values, result):
    assert _junction(iter(values), kind) is result


@pytest.mark.parametrize('kind, decisive', [('AND', False), ('OR', True)])
def test_short_circuit_does_not_evaluate_irrelevant_tail(kind, decisive):
    def terms():
        yield decisive
        pytest.fail('decisive term must stop the evaluation')
    assert _junction(terms(), kind) is decisive


def test_domain_pruning_never_removes_a_true_binding():
    from itertools import product
    from ah.formalizer.syntax_rules import _possible_ast, evaluate_ast
    from tools.formalizer_v7_syntax_fixture import _complete_window
    st = t0('x y.')
    variants = [(i,None) for i in range(3)]
    expressions = [_complete_window(['a','b']),
        {'op':'NOT', 'arg':{'op':'span_relation','left':'a','right':'b','relation':'OVERLAPS'}},
        {'op':'feature_eq','field':'a.POS','value':'NOUN'},
        {'op':'OR', 'args':[{'op':'feature_eq','field':'a.surface','value':'x'},
                           {'op':'feature_eq','field':'b.surface','value':'y'}]}]
    for left in ([variants[0]], variants[:2], variants):
        for right in ([variants[1]], variants):
            domains = {'a':left,'b':right}
            for expression in expressions:
                possible = _possible_ast(expression, domains, st, None, (0,3), lambda:None)
                actual = {evaluate_ast(expression,dict(zip(domains, pair)),st,None,(0,3),lambda:None)
                          for pair in product(left,right)}
                assert actual <= possible


def test_feature_trace_batch_is_lossless():
    from ah.formalizer.state import MorphVariant
    st=state('x.')
    st.evidence[0].variants=(MorphVariant(lemma='x',pos='NOUN'),MorphVariant(lemma='x',pos='VERB'))
    enumerate_matches(st,[rule()],'T2',{'max_rule_steps':100,'max_rule_matches':10,'max_source_tokens':8},None)
    batches=[row for row in st.syntax_trace if row['event']=='FEATURE_CHECK_BATCH']
    assert len(batches)==1
    checks=[dict(zip(batches[0]['columns'],row)) for row in batches[0]['checks']]
    assert [(r['token_ref'],r['variant_index'],r['result']) for r in checks] == [
        ('tok:0:1',0,True),('tok:0:1',1,True),('tok:1:2',0,False)]
    assert [r['step'] for r in checks]==sorted({r['step'] for r in checks})
