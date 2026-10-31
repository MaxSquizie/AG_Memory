"""Semantic evaluator contracts with scripted evidence validity, not model quality."""
from dataclasses import asdict
from types import SimpleNamespace as NS
import pytest
from ah.formalizer.pipeline import t0
from ah.formalizer.bundle_constraints import inspect,signature,required_inventory_refs
from ah.formalizer.dispatch_evidence import valid,evidence_probe_refs
from ah.formalizer.function_inventory import unit_hash
from test_f05_shared_predicate_constraints import frame


def role(state,**kw):
    row=dict(kind='ESTABLISHED_PREDICATE_ROLE',region_ref='r',task_scope='scope',
             predicate_ref='p',token_ref='a',role='SUBJECT',proof={'candidate_id':'SUBJECT'})
    row.update(kw);state.syntax_trace.append(row);return row


@pytest.fixture
def state(monkeypatch):
    monkeypatch.setattr('ah.formalizer.structural_tasks._licensed',
        lambda state,proof,**kw: proof.get('candidate_id')==kw.get('candidate_id'))
    monkeypatch.setattr('ah.formalizer.partial_readings.valid_domain',lambda *a:True)
    monkeypatch.setattr('ah.formalizer.function_inventory.live',lambda state,row,**kw:not row.get('retired'))
    return t0('source')


def check(state,frames,**kw):return inspect(state,'r','scope',['a','p'],frames,**kw)


def test_roles_distinguish_known_missing_and_invalid_proof(state):
    row=role(state)
    assert check(state,[frame('f','a')])['status']=='REQUIREMENTS_SATISFIED'
    assert check(state,[frame('f','a','OBJECT')])['status']=='CONTRACT_CONFLICT'
    assert check(state,[frame('f','b')])['status']=='OPEN_REQUIREMENTS'
    row['role']='OBJECT'
    assert check(state,[frame('f','a','OBJECT')])['status']=='STALE_EVIDENCE'


def test_negative_role_does_not_forbid_context_and_reading_is_independent(state):
    row=role(state,role='NO_DIRECT_ROLE',proof={'candidate_id':'NO_DIRECT_ROLE'})
    f=frame('f','a');f.semantic['proposed_roles']={}
    assert check(state,[f])['status']=='REQUIREMENTS_SATISFIED'
    assert check(state,[frame('f','a')])['status']=='CONTRACT_CONFLICT'
    row['reading']={'pos':'NOUN'}
    assert check(state,[frame('f','b')])['status']=='OPEN_REQUIREMENTS'
    result=check(state,[f])
    assert any(r['kind']=='READING_PROVENANCE_UNKNOWN' for r in result['unknowns'])


def domain(state,readings):
    state.syntax_trace.append(dict(kind='PARTIAL_READING_DOMAIN',region_ref='r',task_scope='scope',
        domain_ref='d',predicate_ref='p',token_ref='a',role='SUBJECT',alternatives=[
            dict(predicate_ref='p',token_ref='a',role='SUBJECT',reading=r) for r in readings]))


def test_whole_alternatives_cannot_mix_features_or_invent_specificity(state):
    domain(state,[{'pos':'NOUN','cases':['nom'],'number':'sing'},
                  {'pos':'NOUN','cases':['dat'],'number':'plur'}])
    for reading,status in [({'pos':'NOUN','cases':['nom'],'number':'plur'},'CONTRACT_CONFLICT'),
        ({'pos':'NOUN','cases':['nom']},'OPEN_REQUIREMENTS'),
        ({'pos':'NOUN','cases':['nom'],'number':'sing'},'REQUIREMENTS_SATISFIED')]:
        assert check(state,[frame('f','a',reading=reading)])['status']==status
    state.syntax_trace.clear();domain(state,[{'pos':'NOUN'}])
    assert check(state,[frame('f','a')])['status']=='OPEN_REQUIREMENTS'


def inventory(state,kind='REFERENCE'):
    unit=dict(kind='NOMINAL_FUNCTION',inventory_ref='inv',unit_ref='unit',function=kind,
              head_ref='a',function_refs=['q'],identity_constraint='IDENTIFY',external_case='nom')
    inv=dict(kind='FUNCTION_INVENTORY',inventory_ref='inv',inventory_kind='NOMINAL',
             region_ref='r',task_scope='scope',branch_condition=None,inventory_tokens=['a','p'],
             unit_hashes={'unit':unit_hash(unit)})
    state.syntax_trace.extend([unit,inv]);return unit,inv


@pytest.mark.parametrize('kind',['REFERENCE','QUANTITY'])
def test_nominal_exact_occurrence_missing_conflict_and_stale(state,kind):
    unit,inv=inventory(state,kind);f=frame('f','a')
    def project(refs,value):
        if kind=='REFERENCE':return {'reference_constraint':dict(head_ref='a',function_refs=refs,identity_constraint=value)}
        return dict(head_ref='a',quantity_token_refs=refs,external_cases=[value])
    good='IDENTIFY' if kind=='REFERENCE' else 'nom'
    key='lexical_units' if kind=='REFERENCE' else 'qualitative_groups'
    vals=[project(['q'],good),project(['other'],'different')]
    f.semantic[key]=dict(enumerate(vals)) if kind=='REFERENCE' else vals
    assert check(state,[f])['status']=='REQUIREMENTS_SATISFIED'
    bad=[project(['q'],'different')]
    f.semantic[key]=dict(enumerate(bad)) if kind=='REFERENCE' else bad
    assert check(state,[f])['status']=='CONTRACT_CONFLICT'
    f.semantic[key]={} if kind=='REFERENCE' else []
    assert check(state,[f])['status']=='OPEN_REQUIREMENTS'
    inv['retired']=True
    assert check(state,[f])['status']=='STALE_EVIDENCE'


def test_late_requirements_invalidate_empty_cache_only_at_own_address(state):
    f=frame('f','a');result=check(state,[f],nominal=False)
    payload=dict(region_ref='r',task_scope='scope',token_refs=['a','p'],frames=[asdict(f)],
                 condition=None,nominal=False,signature=signature(result))
    role(state,task_scope='other',role='OBJECT',proof={'candidate_id':'OBJECT'})
    assert valid(state,'BUNDLE_CONSTRAINTS',payload)
    role(state,role='OBJECT',proof={'candidate_id':'OBJECT'})
    assert not valid(state,'BUNDLE_CONSTRAINTS',payload)


def test_inventory_selection_keeps_explicit_subsets_and_excludes_other_scopes(state):
    unit,inv=inventory(state);f=frame('f','a')
    inv['task_scope']='other'
    assert not required_inventory_refs(state,'r','scope',['a','p'],[f])
    f.semantic['function_inventory_refs']=['inv']
    assert required_inventory_refs(state,'r','scope',['a','p'],[f])=={'inv'}
    inv['superseded']=True
    assert required_inventory_refs(state,'r','scope',['a','p'],[f])=={'inv'}


@pytest.mark.parametrize('kind,word',[('REFERENCE','Он'),('QUANTITY','Многие')])
def test_native_conditional_nonempty_nominal_inventory(tmp_path,monkeypatch,kind,word):
    import re
    from test_structural_open_forest import native
    from test_structural_lexical import lexical_answer
    from ah.formalizer.structural_shells import evidence_state
    from ah.formalizer.function_inventory import live
    def answer(slot,prompt):
        labels=re.findall(r'^(\d+)\. (.*)$',prompt,re.M)
        target=None
        if slot=='nominal_function':
            if kind+': «'+word+'»' in prompt:return '0'
            target='An expression points' if kind=='REFERENCE' else 'An expression says how many'
        elif slot=='nominal_function_source_start':target='Start at «'+word+'»'
        elif slot=='nominal_function_source_end':target='End after «'+word+'»'
        elif slot=='nominal_function_head':target='Nominal head «'+word+'»'
        elif slot=='nominal_identity_function':target='Identify the nominal'
        elif slot=='nominal_external_case':target='Nominative case'
        elif slot=='predicate_function':target='Predicate occurrence «пришли»'
        if target:return next((n for n,label in labels if label.startswith(target)),'?')
        return lexical_answer(slot,prompt)
    state,result,prompts=native(tmp_path,monkeypatch,('LEXICAL','FORALL'),answer,text=word+' пришли.')
    rows=list(state.observation['structural_lexical_results'].values())
    assert rows
    units=[]
    for row in rows:
        local=evidence_state(state,row)
        for inv in local.syntax_trace:
            if inv.get('kind')!='FUNCTION_INVENTORY' or not inv.get('unit_hashes'):continue
            assert live(local,inv,condition=row['condition'])
            units.extend(u for u in local.syntax_trace if u.get('kind')=='NOMINAL_FUNCTION'
                         and u.get('inventory_ref')==inv['inventory_ref'] and u.get('function')==kind)
    assert units,[(re.search(r'Decision slot: (\S+)',p).group(1),p[-500:]) for p in prompts]
    assert not result['assertions']['ah']


def test_union_unknown_bundle_cannot_make_other_source_the_only_answer(monkeypatch):
    from ah.formalizer.composition_source_union import merge
    state=t0('source');region=NS(region_id='r',source_range=(0,6))
    grammar=frame('grammar','a');component=frame('component','a')
    def checked(state,region,tokens,frames,**kwargs):
        status='OPEN_REQUIREMENTS' if frames[0].frame_id=='component' else 'REQUIREMENTS_SATISFIED'
        return dict(status=status,conflicts=[],unknowns=[],stale=[])
    monkeypatch.setattr('ah.formalizer.component_constraints.inspect_bundle',checked)
    result=merge(state,None,None,region,[],{},[grammar],[component],0)
    assert len(result)==2 and all(f.semantic.get('structural_unresolved') for f in result)
    assert all(not f.semantic.get('structural_rejection') for f in result)
    assert any(d.code=='COMPOSITION_CONSTRAINT_UNRESOLVED' for d in state.diagnostics)


def test_empty_bundle_read_keeps_condition_dependency(state):
    state.observation['structural_condition_registry']={'branch':{
        'forest':{'membership':{'decision_ref':'membership','domain_ref':'domain'}}}}
    refs=evidence_probe_refs(state,'BUNDLE_CONSTRAINTS',dict(region_ref='r',task_scope='scope',
        token_refs=[],frames=[],nominal=False,condition={'condition_ref':'branch'}))
    assert {'membership','domain'}<=refs


def test_submission_contract_does_not_turn_missing_projection_into_language_conflict(state):
    _,inv=inventory(state);f=frame('f','a')
    assert check(state,[f])['status']=='OPEN_REQUIREMENTS'
    checked=check(state,[f],require_nominal_projection=True)
    assert checked['status']=='INVALID_PRODUCER_OUTPUT' and not checked['conflicts']
    assert checked['invalid_outputs']
    inv['retired']=True
    assert check(state,[f],require_nominal_projection=True)['status']=='STALE_EVIDENCE'
