"""Concrete scope fixtures cannot silently replace a runtime operation."""
import pytest
from tools.formalizer_v7_extended_binding import Session
from tools.formalizer_v7_scope_binding import scope_action
from tools.formalizer_v7_query_binding import query_action
from ah.formalizer.goal_forms import substitute


OPEN={'predicate':'OPEN:переадресовать','roles':{'AGENT':{'entity':'courier'},'THEME':{'entity':'letter'}}}


def session(tmp_path,p):
    return Session([p],tmp_path/'journal.log')


@pytest.mark.parametrize('change,answer',[
    ('none','YES'),('absolute_query_token_position','YES'),('verb','UNKNOWN'),
    ('role','UNKNOWN'),('scope','UNKNOWN'),('source_scope','UNKNOWN'),
    ('dead_proof','UNKNOWN'),('surface_as_agent','UNKNOWN')])
def test_open_attestation_preserves_exact_scope_and_excitation(tmp_path,change,answer):
    p={'activated_source':'O1','asserted_open_formula':OPEN,'change':change,
       'fixture_identity_bindings':{'query:courier':'courier','query:letter':'letter'}}
    s=session(tmp_path,p);actual=scope_action(s,'exact_attestation_query',p)
    assert actual['answer']['status']==answer
    assert actual['query']=={'new_derived_supports':0,'new_markers':0}
    if change=='absolute_query_token_position':
        assert actual['query_token_start']>len('Курьер ')
        assert any('shifted raw query span' in api for api in s.api)


@pytest.mark.parametrize('mutation',['free_variable','double_binder','capture_after_substitution',
                                    'string_restriction','three_slot_FORALL','quantifier_scope_first_wins'])
def test_malformed_scopes_fail_before_factual_commit(tmp_path,mutation):
    p={'mutation':mutation};actual=scope_action(session(tmp_path,p),'validate_scope',p)
    assert actual['scope']['valid'] is False
    assert actual['store']['new_asserted_fact_count']==0


def test_substitution_renames_inner_binder_without_capturing_free_replacement():
    inner={'function_id':'EXISTS','operands':[{'bound_var':2,'sort':'ENTITY'},
           {'template_ref':'KNOW','actants':{'SUBJECT':{'bound_var':1,'sort':'ENTITY'},'OBJECT':{'bound_var':2,'sort':'ENTITY'}}}]}
    actual=substitute(inner,{1:{'bound_var':2,'sort':'ENTITY'}})
    renamed=actual['operands'][0]['bound_var']
    assert renamed!=2
    assert actual['operands'][1]['actants']['SUBJECT']['bound_var']==2
    assert actual['operands'][1]['actants']['OBJECT']['bound_var']==renamed
    assert inner['operands'][0]['bound_var']==2


@pytest.mark.parametrize('change',['restriction','count_variable','nested_scope','time_window','source_scope','dead_support'])
def test_certificate_mutations_reach_actual_count_validator(tmp_path,change):
    p={'change':change,'signature_version':'native-query-pattern-v1'}
    actual=query_action(session(tmp_path,p),'validate_formula_certificate',p)
    assert actual['certificate']['valid'] is False
    assert actual['answer']['exact_count'] is None


def test_alpha_renaming_changes_scoped_variable_not_count_gap(tmp_path):
    p={'renaming':{'x':'y'},'capture_safe':True,'signature_version':'native-query-pattern-v1'}
    actual=query_action(session(tmp_path,p),'validate_formula_certificate',p)
    assert actual['signature']['alpha_equal'] is True
    assert actual['certificate']['valid'] is True


def test_runtime_cartesian_budget_observer_delegates_proofs(tmp_path):
    p={'required_combinations':6,'limit':1024,'enumeration_exhausted':True}
    actual=query_action(session(tmp_path,p),'compound_binding_budget',p)
    assert actual['query']=={'search_complete':True,'combinations_visited':6,
                            'domain_certificate_inferred_from_enumeration':False}


@pytest.mark.parametrize('scope',['AND','OR','NOT','EXISTS','FORALL','IMPLIES','QUOTED'])
@pytest.mark.parametrize('proven',[False,True])
def test_binding_candidates_are_structural_until_whole_scope_is_proven(tmp_path,scope,proven):
    p={'scope':scope,'runtime_variable':'q','mode':'WH','candidate_bindings':['ivan','petr'],
       'atomic_body_match_entities':['ivan','petr'],
       'whole_pattern_proof_entities':['ivan'] if proven else [],
       'quoted_content_independent_assertion':False}
    s=session(tmp_path,p);actual=query_action(s,'compound_binding_query',p)
    assert actual['answer']['binding_entities']==(['ivan'] if proven else [])
    assert actual['query']['new_root_supports']==0
    assert actual['query']['variable_has_ah_uid'] is False
    if scope=='QUOTED':
        # A result proves the complete report while its quoted content stays
        # structural. No ReportBridgingRule or independent assertion is used.
        arrive=s.templates[('ARRIVE',('AGENT',))]['uid']
        assert all(s.store.ledger.data['nodes'][uid].get('template_ref')!=arrive
                   for uid in s.store.ledger.f_visible())
    if not proven:
        assert all(s.store.ledger.data['nodes'][uid].get('template_ref')!=s.templates[('STUDENT',('THEME',))]['uid']
                   for uid in s.store.ledger.f_visible())
