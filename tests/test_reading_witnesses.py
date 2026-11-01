"""Strict P01 proof contracts; real task/domain selection, scripted model only."""
from copy import deepcopy
from dataclasses import replace
import pytest
from ah.formalizer import reading_witnesses as rw
from ah.formalizer.morphology_domain import clean,strict_use
from ah.formalizer.composition_dispatcher import canonical
from ah.formalizer.composition_session import session
from ah.formalizer.structural_tasks import choose,choose_domain
from test_composition_dispatcher import setup_morphology,First


def prepared(domain=False):
    state,release,region,cfg=setup_morphology('Книга лежит.')
    token=next(t for t in state.evidence if t.span=='Книга')
    original=rw.source_snapshot(state,source_revision=1,resource_version=release.sha256,original_evidence=state.evidence)
    reading=clean(token.variants[0]);use={'kind':'PREDICATE_ARGUMENT','role':'SUBJECT','predicate_ref':'p'}
    with session(state,release) as runtime:
        with runtime.area(region,state.evidence,None):
            where=rw.address(state,source_revision=1,region_ref=region.region_id,
                occurrence_refs=region.token_refs,input_scope=runtime.input_signature(),resource_version=release.sha256)
            binding={'token_ref':token.token_id,'source_range':[token.start,token.end],
                     'reading':canonical(reading),'use':use,'address':canonical(where)}
            options=[{'candidate_id':'a','label':'Whole noun reading in the subject role',
                      'token_ref':token.token_id,'reading':reading,'reading_uses':[binding]},
                     {'candidate_id':'b','label':'A second admitted interpretation',
                      'token_ref':token.token_id,'reading':reading,'reading_uses':[binding]}]
            if domain:
                selected=choose_domain(state,release,First('1,2'),region,cfg,'predicate_argument_reading',options,'Which whole reading fits this occurrence?')
                assert selected is not None
                payload=selected.values[0];proof=None;record=selected.record()
            else:
                selected=choose(state,release,First('1'),region,cfg,'predicate_argument_reading',options,'Which whole reading fits this occurrence?')
                assert selected is not None
                payload,proof=selected;record=None
    w=rw.witness(where,'SELECTED_DOMAIN' if domain else 'DERIVED',token.token_id,(token.start,token.end),
        reading,use,rule='SELECTED_READING_USE_V1',payload=payload,proof=proof,domain=record,
        basis=rw.selection_basis(state,record or proof))
    return state,token,original,w


def test_real_selection_validates_outside_session_and_cannot_mutate_witness():
    state,token,original,w=prepared()
    assert strict_use(state,w,expected_address=w.address).supported
    value=rw.json.loads(w.payload_json);value['reading_uses'].clear()
    assert strict_use(state,w,expected_address=w.address).supported
    assert not rw.json.loads(w.payload_json)['reading_uses']==[]


@pytest.mark.parametrize('change,reason',[
    ({'token_ref':'other'},'OCCURRENCE_OUTSIDE_SCOPE'),
    ({'source_range':(1,5)},'OCCURRENCE_RANGE_MISMATCH'),
    ({'reading_json':rw.freeze({'pos':'VERB'})},'PAYLOAD_DOES_NOT_LICENSE_USE'),
    ({'use_json':rw.freeze({'kind':'PREDICATE_ARGUMENT','role':'OBJECT'})},'PAYLOAD_DOES_NOT_LICENSE_USE'),
    ({'payload_json':rw.freeze({'candidate_id':'foreign'})},'SELECTED_PAYLOAD_MISMATCH'),
])
def test_wrong_address_payload_or_whole_use_is_conflict(change,reason):
    state,_,_,w=prepared();r=rw.validate(state,replace(w,**change),expected_address=w.address)
    assert (r.status,r.reason)==('CONFLICT',reason)


@pytest.mark.parametrize('field,value',[('source_revision',2),('interpretation_version',99),('resource_version','changed'),('source_uid','other')])
def test_changed_source_or_resource_is_stale(field,value):
    state,_,_,w=prepared()
    assert rw.validate(state,w,expected_address=replace(w.address,**{field:value})).status=='STALE'


def test_synthetic_selected_decision_does_not_supply_missing_proof():
    state,_,_,w=prepared();state.syntax_trace=[]
    # Previously captured evidence disappearing is stale. A bare synthetic
    # decision which never had a task basis is unknown.
    assert rw.validate(state,w,expected_address=w.address).status=='STALE'
    assert rw.validate(state,replace(w,basis_json='null'),expected_address=w.address).status=='UNKNOWN'


def test_retired_selection_invalidates_parent_and_identity_child():
    state,_,_,w=prepared()
    child=replace(w,rule='IDENTITY_FROM_PARENT_V1',parent_refs=(w.ref,))
    assert rw.validate(state,child,expected_address=w.address,parents=[w]).supported
    assert rw.validate(state,child,expected_address=w.address).status=='UNKNOWN'
    key=rw.json.loads(w.proof_json)['decision_ref'];state.syntax_trace.append({'kind':'DEPENDENCY_REJECTED','decision_ref':key})
    assert rw.validate(state,child,expected_address=w.address,parents=[w]).status=='STALE'


def test_original_uses_frozen_source_not_mutable_overlay_or_recovery():
    state,token,original,w=prepared()
    original_w=replace(w,kind='ORIGINAL',rule='SOURCE_DICTIONARY_V1',use_json=rw.freeze({'kind':'AVAILABLE_READING'}))
    assert rw.validate(state,original_w,expected_address=w.address,original=original).supported
    token.variants=()
    assert rw.validate(state,original_w,expected_address=w.address,original=original).supported
    forged=rw.json.loads(original_w.reading_json);forged['origin']='RECOVERED'
    assert rw.validate(state,replace(original_w,reading_json=rw.freeze(forged)),expected_address=w.address,original=original).status=='CONFLICT'
    assert rw.validate(state,original_w,expected_address=w.address).status=='UNKNOWN'
    assert rw.validate(state,replace(original_w,use_json=w.use_json),expected_address=w.address,original=original).status=='CONFLICT'


def test_domain_membership_does_not_become_scalar_selection():
    state,_,_,w=prepared(domain=True)
    result=rw.validate(state,w,expected_address=w.address)
    assert result.supported and result.reason=='DOMAIN_MEMBER_ONLY'
    assert rw.validate(state,replace(w,kind='DERIVED'),expected_address=w.address).status=='UNKNOWN'
    key=rw.json.loads(w.domain_json)['decision_ref'];state.syntax_trace.append({'kind':'DEPENDENCY_REJECTED','decision_ref':key})
    assert rw.validate(state,w,expected_address=w.address).status=='STALE'


def test_unconditional_validator_rejects_conditional_without_using_ambient_state():
    state,_,_,w=prepared();a=replace(w.address,condition_json=rw.freeze({'condition_ref':'missing'}))
    conditional=replace(w,address=a)
    assert rw.validate(state,conditional,expected_address=a).reason=='CONDITIONAL_WITNESS_AT_PUBLIC_BOUNDARY'
    assert rw.historical(state,conditional,expected_address=a).status=='STALE'


def test_unknown_transform_cannot_fall_back_to_legacy(monkeypatch):
    state,_,_,w=prepared()
    monkeypatch.setattr('ah.formalizer.morphology_domain.function_use',lambda *a:pytest.fail('legacy fallback'))
    assert strict_use(state,replace(w,rule='MISSING_ADAPTER'),expected_address=w.address).status=='UNKNOWN'


def test_changed_parent_scope_is_not_transported_implicitly():
    state,_,_,w=prepared()
    assert rw.validate(state,w,expected_address=replace(w.address,input_scope='other')).status=='CONFLICT'


def test_deep_parent_chain_uses_bounded_python_stack():
    state,_,_,w=prepared();parents=[w]
    for _ in range(1100):
        w=replace(w,rule='IDENTITY_FROM_PARENT_V1',parent_refs=(w.ref,));parents.append(w)
    assert rw.validate(state,w,expected_address=w.address,parents=parents[:-1]).supported


def test_real_conditional_original_is_historical_only(tmp_path,monkeypatch):
    from test_structural_open_forest import native
    from test_structural_conditional_shells import boundaries,shells
    state,_,_=native(tmp_path,monkeypatch,('AND','OR'),boundaries)
    shell=shells(state)[0];token=next(t for t in state.evidence if any(v.origin=='DICTIONARY' for v in t.variants))
    original=rw.source_snapshot(state,source_revision=1,resource_version='explicit-test-release',original_evidence=state.evidence)
    a=rw.address(state,source_revision=1,region_ref='historical-test',occurrence_refs=[token.token_id],
        input_scope='historical-test',resource_version='explicit-test-release',condition=shell['condition'])
    reading=next(v for v in token.variants if v.origin=='DICTIONARY')
    w=rw.witness(a,'ORIGINAL',token.token_id,(token.start,token.end),clean(reading),
        {'kind':'AVAILABLE_READING'},rule='SOURCE_DICTIONARY_V1')
    assert rw.historical(state,w,expected_address=a,original=original).supported
    assert not rw.validate(state,w,expected_address=a,original=original).supported
    from ah.formalizer.structural_conditions import resolve
    key=resolve(state,shell['condition']).forest['membership']['decision_ref']
    state.syntax_trace.append({'kind':'DEPENDENCY_REJECTED','decision_ref':key})
    assert rw.historical(state,w,expected_address=a,original=original).status=='STALE'


def test_identity_never_promotes_domain_membership_to_selected_use():
    state,_,_,w=prepared(domain=True)
    child=replace(w,kind='DERIVED',rule='IDENTITY_FROM_PARENT_V1',parent_refs=(w.ref,))
    result=rw.validate(state,child,expected_address=w.address,parents=[w])
    assert result.supported and result.permission=='DOMAIN_MEMBERSHIP' and not result.selected_use


@pytest.mark.parametrize('domain',[False,True])
@pytest.mark.parametrize('field,value',[
    ('token_refs',['foreign']),('source_range',[100,200]),
    ('branch_condition',{'condition_ref':'missing'}),
    ('execution_basis',{'input_scope':'foreign'}),
])
def test_task_domain_mutation_revokes_witness(domain,field,value):
    state,_,_,w=prepared(domain)
    proof=rw.json.loads(w.domain_json if domain else w.proof_json)
    record=next(r for r in state.syntax_trace if r.get('kind')=='TASK_DOMAIN' and r['task_ref']==proof['domain_ref'])
    record[field]=value
    assert rw.validate(state,w,expected_address=w.address).status=='STALE'
    # Recapturing the changed task cannot legitimize a self-declared use address.
    forged=replace(w,basis_json=rw.freeze(rw.selection_basis(state,proof)))
    assert not rw.validate(state,forged,expected_address=w.address).supported


@pytest.mark.parametrize('as_domain',[False,True])
def test_real_conditional_selection_has_no_public_or_sibling_permission(as_domain):
    from ah.formalizer.relation_composition import select_relation
    from ah.formalizer.structural_forest import retain
    from ah.formalizer.structural_conditions import branch
    state,release,region,cfg=setup_morphology('Книга лежит.')
    token=state.evidence[0];reading=clean(token.variants[0]);use={'kind':'EXACT_TEST_USE'}
    with session(state,release) as runtime:
        with runtime.area(region,state.evidence,None):
            domain=select_relation(state,release,First('6,7'),region,state.evidence,cfg,None)
            forest=retain(state,region,state.evidence,None,cfg,domain)
            records=[]
            for hyp in forest['hypotheses']:
                with branch(state,forest,hyp,cfg) as condition:
                    a=rw.address(state,source_revision=1,region_ref=region.region_id,
                        occurrence_refs=region.token_refs,input_scope=runtime.input_signature(),
                        resource_version=release.sha256,condition=condition.record())
                    binding={'token_ref':token.token_id,'source_range':[token.start,token.end],
                             'reading':canonical(reading),'use':use,'address':canonical(a)}
                    options=[{'candidate_id':c,'label':label,'token_ref':token.token_id,
                              'reading':reading,'reading_uses':[binding]} for c,label in [('a','First whole reading'),('b','Second whole reading')]]
                    if as_domain:
                        result=choose_domain(state,release,First('1,2'),region,cfg,'predicate_argument_reading',options,'Which whole reading fits?')
                        payload=result.values[0];proof=None;record=result.record()
                    else:
                        payload,proof=choose(state,release,First('1'),region,cfg,'predicate_argument_reading',options,'Which whole reading fits?');record=None
                    w=rw.witness(a,'SELECTED_DOMAIN' if as_domain else 'DERIVED',token.token_id,
                        (token.start,token.end),reading,use,rule='SELECTED_READING_USE_V1',payload=payload,
                        proof=proof,domain=record,basis=rw.selection_basis(state,record or proof))
                    records.append(w)
    first,second=records
    assert rw.historical(state,first,expected_address=first.address).supported
    assert not rw.validate(state,first,expected_address=first.address).supported
    assert rw.historical(state,first,expected_address=second.address).status=='CONFLICT'
    moved=replace(first,address=second.address)
    assert not rw.historical(state,moved,expected_address=second.address).supported


@pytest.mark.parametrize('where',['page_condition','page_basis','raw_condition'])
@pytest.mark.parametrize('domain',[False,True])
def test_page_context_cannot_be_laundered_by_recapture(where,domain):
    state,_,_,w=prepared(domain)
    proof=rw.json.loads(w.domain_json if domain else w.proof_json)
    d=next(r for r in state.syntax_trace if r.get('kind')=='TASK_DOMAIN' and r['task_ref']==proof['domain_ref'])
    key=d['page_refs'][0]
    if where=='raw_condition':state.component_probe_records[key]['branch_condition']={'condition_ref':'missing'}
    else:
        p=next(r for r in state.syntax_trace if r.get('kind')=='STRUCTURAL_TASK' and r.get('decision_ref')==key)
        p['branch_condition' if where=='page_condition' else 'execution_basis']={'condition_ref':'missing'} if where=='page_condition' else {'input_scope':'other'}
    assert rw.validate(state,w,expected_address=w.address).status=='STALE'
    recaptured=replace(w,basis_json=rw.freeze(rw.selection_basis(state,proof)))
    assert rw.validate(state,recaptured,expected_address=w.address).status=='CONFLICT'
