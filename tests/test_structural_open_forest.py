"""Real source-selection path; scripted answers do not test model quality."""
import re
from copy import deepcopy
import pytest
from tools.formalizer_v7_native_binding import ChatBackend,execute_native
from tools.formalizer_v7_extended_binding import Session
from ah.formalizer import v7_pipeline
from ah.formalizer.relation_composition import RELATIONS
from ah.formalizer.structural_forest import current_domains,live
from ah.formalizer.structural_tasks import licensed


def native(tmp_path,monkeypatch,choices,answer=None,text=None):
    captured=[];prompts=[]
    def generate(self,prompt,**kw):
        prompts.append(prompt)
        slot=re.search(r'Decision slot: (\S+)',prompt).group(1)
        from ah.formalizer.composition_session import _current
        runtime=_current.get()
        if slot!='structural_relation' or (runtime and getattr(runtime,'structural_child_edge',None)):
            return answer(slot,prompt) if answer else '?'
        labels=re.findall(r'^(\d+)\. (.*)$',prompt,re.M)
        selected=[n for n,label in labels if any(label.startswith(RELATIONS[c]) for c in choices)]
        return ','.join(selected) if selected else '0'
    original=v7_pipeline.build_plan
    def capture(state,*a,**kw):
        captured.append(state)
        return original(state,*a,**kw)
    monkeypatch.setattr(ChatBackend,'generate',generate)
    monkeypatch.setattr(v7_pipeline,'build_plan',capture)
    text=text or 'Иван пришёл или Мария спит.'
    payload={'raw_input':{'text':text,'source_id':'forest-test','revision':1,
        'range':[0,len(text)],'language':'ru','request_kind':'ASSERTION','batch_kind':'MESSAGE'}}
    session=Session([payload],tmp_path/'journal.log');session.observer_contract='v7-observer-1'
    result=execute_native(session,payload,{'provider':'lmstudio','model':'scripted',
                                         'structure_mode':'region_probes'})
    assert captured,result
    return captured[-1],result,prompts


@pytest.mark.parametrize('choices',[('AND','OR'),('LEXICAL','FORALL'),tuple(RELATIONS)])
def test_native_retains_each_member_without_scalar_license_or_write(tmp_path,monkeypatch,choices):
    state,result,prompts=native(tmp_path,monkeypatch,choices)
    domains=current_domains(state)
    assert len(domains)==1,[(r.get('kind'),r.get('reason')) for r in state.syntax_trace]
    row=domains[0]
    assert {h['candidate']['relation'] for h in row['hypotheses']}==set(choices)
    assert len({h['hypothesis_ref'] for h in row['hypotheses']})==len(choices)
    assert row['relation_menu_complete']
    assert not any(row[k] for k in ('producer_complete','frontier_complete',
                                   'propagation_complete','structure_complete','write_eligible'))
    assert not result['assertions']['ah'],result
    assert all(h['obligations'] and h['status']=='OPEN' for h in row['hypotheses'])
    for h in row['hypotheses']:
        proof={'decision_ref':row['membership']['decision_ref'],
               'domain_ref':row['membership']['domain_ref'],
               'candidate_id':h['candidate']['candidate_id']}
        assert not licensed(state,proof,slot='structural_relation')
    assert not any(r.get('slot')=='structural_relation' and r.get('selected')
                   for r in state.syntax_trace if r.get('kind')=='STRUCTURAL_TASK')
    assert all(re.search(r'Decision slot: (\S+)',p).group(1) in
               {'structural_relation','structural_operand_1_start','structural_introducer_start','structural_group_start',
                'nominal_coordination_discovery'} for p in prompts)


def test_receipt_rejects_mutation_revision_and_page_retirement(tmp_path,monkeypatch):
    state,_,_=native(tmp_path,monkeypatch,('AND','OR'))
    row=current_domains(state)[0]
    modified=deepcopy(row);modified['hypotheses'].pop()
    assert not live(state,modified)
    state.interpretation_version+=1
    assert not current_domains(state)
    state.interpretation_version-=1
    domain=next(r for r in state.syntax_trace if r.get('kind')=='TASK_DOMAIN'
                and r['task_ref']==row['membership']['domain_ref'])
    state.syntax_trace.append({'kind':'COMPOSITION_PROBE_SUPERSEDED',
                              'previous_decision_ref':domain['page_refs'][0]})
    assert not current_domains(state)


def test_other_area_or_slot_cannot_supply_membership(tmp_path,monkeypatch):
    from types import SimpleNamespace
    from ah.formalizer.structural_forest import retain
    from ah.formalizer.partial_readings import SupportedDomain
    from ah.formalizer.canonical_ledger import digest
    state,_,_=native(tmp_path,monkeypatch,('AND','OR'))
    row=current_domains(state)[0];membership=row['membership']
    domain=SupportedDomain(tuple(membership['alternatives']),membership['decision_ref'],membership['domain_ref'])
    region=SimpleNamespace(region_id='another-area',source_range=row['source_range'])
    tokens=[e for e in state.evidence if e.token_id in row['token_refs']]
    with pytest.raises(ValueError,match='ADDRESS_MISMATCH'):retain(state,region,tokens,None,{},domain)
    forged=deepcopy(row);forged['hypotheses'].pop()
    forged['receipt_digest']=digest({k:v for k,v in forged.items() if k!='receipt_digest'})
    assert not live(state,forged)
    receipt=next(r for r in state.syntax_trace if r.get('kind')=='TASK_DOMAIN'
                 and r['task_ref']==membership['domain_ref'])
    receipt['slot']='structural_owner'
    assert not live(state,row)


def test_parent_feedback_has_separate_address(tmp_path,monkeypatch):
    from types import SimpleNamespace
    from ah.formalizer import composition_session
    from ah.formalizer.structural_forest import retain
    from ah.formalizer.partial_readings import SupportedDomain
    state,_,_=native(tmp_path,monkeypatch,('AND','OR'))
    row=current_domains(state)[0];membership=row['membership']
    domain=SupportedDomain(tuple(membership['alternatives']),membership['decision_ref'],membership['domain_ref'])
    region=SimpleNamespace(region_id=row['region_ref'],source_range=row['source_range'])
    tokens=[e for e in state.evidence if e.token_id in row['token_refs']]
    from ah.formalizer.composition_dispatcher import Dispatcher
    runtime=SimpleNamespace(dispatcher=Dispatcher(state,1000),tasks=SimpleNamespace(feedback={'contract':'PROPOSITION'}),
        morphology_scope=None,domain_feedback=None,context_signature=lambda:None,
        input_signature=lambda:row['input_scope'])
    monkeypatch.setattr(composition_session,'current',lambda _:runtime)
    first=retain(state,region,tokens,None,{},domain)
    runtime.tasks.feedback={'contract':'EVENT_DESCRIPTION'}
    second=retain(state,region,tokens,None,{},domain)
    assert first['forest_ref']!=second['forest_ref']
    assert first['hypotheses'][0]['hypothesis_ref']!=second['hypotheses'][0]['hypothesis_ref']
    assert first['context']['parent_feedback']=={'contract':'PROPOSITION'}


def test_producer_order_does_not_change_hypothesis_addresses(tmp_path,monkeypatch):
    from ah.formalizer import relation_composition
    first_dir=tmp_path/'first';first_dir.mkdir()
    second_dir=tmp_path/'second';second_dir.mkdir()
    state,_,_=native(first_dir,monkeypatch,('AND','OR'))
    first=current_domains(state)[0]
    monkeypatch.setattr(relation_composition,'RELATIONS',dict(reversed(list(RELATIONS.items()))))
    state,result,_=native(second_dir,monkeypatch,('AND','OR'))
    second=current_domains(state)[0]
    assert first['forest_ref']==second['forest_ref']
    assert [h['hypothesis_ref'] for h in first['hypotheses']]==[h['hypothesis_ref'] for h in second['hypotheses']]
    assert not result['assertions']['ah']
