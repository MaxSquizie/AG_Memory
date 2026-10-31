"""Native multiple-relation producer, with isolated scripted partition answers."""
import re
from copy import deepcopy
from types import SimpleNamespace
import pytest
from test_structural_open_forest import native
from ah.formalizer.structural_shells import live,evidence_state
from ah.formalizer.structural_conditions import applicable,branch,origin,resolve
from ah.formalizer.structural_tasks import licensed,licensed_in_scope


def boundaries(slot,prompt):
    if 'Optional search:' in prompt:return '0'
    if slot=='structural_partition' or slot=='relation_marker_role':return '1'
    labels=re.findall(r'^(\d+)\. (.*)$',prompt,re.M)
    desired={'structural_operand_1_start':'Start at «Иван»',
             'structural_operand_1_end':'End after «пришёл»',
             'structural_operand_2_start':'Start at «Мария»',
             'structural_operand_2_end':'End after «спит»'}.get(slot)
    if desired:
        return next((n for n,label in labels if label.startswith(desired)),'0')
    return '?'


def shells(state):return [r for r in state.syntax_trace if r.get('kind')=='STRUCTURAL_CONDITIONAL_SHELL']


def runtime_for(monkeypatch,state,shell):
    from ah.formalizer import composition_session
    basis=origin(state,resolve(state,shell['condition']).forest['membership']['domain_ref'])
    ctx=deepcopy(basis['context'])
    from ah.formalizer.composition_dispatcher import Dispatcher
    runtime=SimpleNamespace(dispatcher=Dispatcher(state,1000),area_inputs=(None,None,ctx['request']),
        tasks=SimpleNamespace(feedback=ctx['parent_feedback']),
        morphology_scope=ctx['morphology_scope'],domain_feedback=ctx['domain_feedback'],
        input_signature=lambda:basis['input_scope'],context_signature=lambda:ctx['memory_context'])
    monkeypatch.setattr(composition_session,'current',lambda _:runtime)
    cfg={'_task_constraints':ctx['constraints'],'_task_constraints_text':ctx['constraints_text'],
         '_ownership_feedback':ctx['ownership_feedback']}
    return runtime,cfg


def test_native_produces_both_shells_without_children_or_global_proofs(tmp_path,monkeypatch):
    state,result,prompts=native(tmp_path,monkeypatch,('AND','OR'),boundaries)
    rows=shells(state)
    assert len(rows)==2
    assert {r['status'] for r in rows}=={'SHELL_PRODUCED'},[(r['status'],r['evidence']['diagnostics']) for r in rows]
    assert all(live(state,r) for r in rows)
    assert sum(len(r['children']) for r in rows)==4
    assert len({c['child_ref'] for r in rows for c in r['children']})==4
    assert not result['assertions']['ah']
    assert not any('Decision slot: predicate_' in p for p in prompts)
    for row in rows:
        assert all(not row[k] for k in ('producer_complete','structure_complete','write_eligible'))
        assert all(c['status']=='UNEXPANDED' for c in row['children'])
        assert not licensed(state,row['partition_proof'])
        local=evidence_state(state,row)
        assert not licensed(local,row['partition_proof'])
        assert not licensed_in_scope(local,row['partition_proof'])
        assert all(r.get('branch_condition')==row['condition'] for r in row['evidence']['trace']
                   if r.get('kind') in {'TASK_DOMAIN','STRUCTURAL_TASK'})
        assert not set(row['evidence']['decisions']).intersection(state.decisions)


def test_membership_and_partition_revocation_invalidate_shell(tmp_path,monkeypatch):
    state,_,_=native(tmp_path,monkeypatch,('AND','OR'),boundaries)
    rows=shells(state);assert all(live(state,r) for r in rows)
    selected=rows[0]
    state.syntax_trace.append({'kind':'DEPENDENCY_REJECTED','decision_ref':selected['partition_proof']['decision_ref']})
    assert not live(state,selected)
    assert live(state,rows[1])
    state.syntax_trace.append({'kind':'DEPENDENCY_REJECTED',
        'decision_ref':resolve(state,selected['condition']).forest['membership']['decision_ref']})
    assert not any(live(state,r) for r in rows)


def test_condition_cannot_escape_branch_or_change_context(tmp_path,monkeypatch):
    state,_,_=native(tmp_path,monkeypatch,('AND','OR'),boundaries)
    first,second=shells(state);local=evidence_state(state,first)
    runtime,cfg=runtime_for(monkeypatch,local,first)
    forest=resolve(local,first['condition']).forest;hyp=next(h for h in forest['hypotheses'] if h['hypothesis_ref']==first['hypothesis_ref'])
    assert applicable(local,forest,cfg)
    # observe is irrelevant to this standalone consumer check.
    monkeypatch.setattr('ah.formalizer.dispatch_evidence.observe',lambda *a,**kw:None)
    with branch(local,forest,hyp,cfg):
        assert licensed_in_scope(local,first['partition_proof'])
        assert not licensed(local,first['partition_proof'])
        assert not licensed_in_scope(evidence_state(state,second),second['partition_proof'])
    assert not licensed_in_scope(local,first['partition_proof'])
    runtime.tasks.feedback={'contract':'different parent','context':'different context'}
    assert not applicable(local,forest,cfg)
    with pytest.raises(ValueError,match='INAPPLICABLE'):
        with branch(local,forest,hyp,cfg):pass


def test_unknown_and_unconnected_relation_keep_open_members(tmp_path,monkeypatch):
    state,result,_=native(tmp_path,monkeypatch,('AND','OR','FORALL'))
    rows=shells(state)
    assert len(rows)==2 and all(r['status']=='OPEN' and not r['children'] for r in rows)
    forest=resolve(state,rows[0]['condition']).forest
    assert {h['candidate']['relation'] for h in forest['hypotheses']}=={'AND','OR','FORALL'}
    assert not result['assertions']['ah']


@pytest.mark.parametrize('change',['parent','morphology','domain','source','version'])
def test_original_execution_basis_is_required(tmp_path,monkeypatch,change):
    state,_,_=native(tmp_path,monkeypatch,('AND','OR'),boundaries)
    row=shells(state)[0];runtime,cfg=runtime_for(monkeypatch,state,row)
    forest=resolve(state,row['condition']).forest
    assert applicable(state,forest,cfg)
    if change=='parent':runtime.input_signature=lambda:'different-slot'
    if change=='morphology':runtime.morphology_scope={'different':'reading'}
    if change=='domain':runtime.domain_feedback='different domain'
    if change=='source':state.text+=' Changed'
    if change=='version':state.context_version+=1
    assert not applicable(state,forest,cfg)


def test_budget_stop_keeps_each_hypothesis_open(tmp_path,monkeypatch):
    from ah.formalizer.partition_domain import PartitionDomain
    from ah.formalizer.composition_session import current
    original=PartitionDomain.resolve
    def stopped(self,*a,**kw):
        current(self.state).dispatcher.limit=0
        return original(self,*a,**kw)
    monkeypatch.setattr(PartitionDomain,'resolve',stopped)
    state,result,_=native(tmp_path,monkeypatch,('AND','OR'),boundaries)
    rows=shells(state)
    assert len(rows)==2 and all(r['status']=='OPEN' for r in rows)
    assert all(any(d['code']=='COMPOSITION_DISPATCH_INCOMPLETE' for d in r['evidence']['diagnostics']) for r in rows)
    assert not result['assertions']['ah']


def test_menu_order_preserves_shell_contents(tmp_path,monkeypatch):
    from ah.formalizer import relation_composition
    first=tmp_path/'first';first.mkdir();second=tmp_path/'second';second.mkdir()
    state,_,_=native(first,monkeypatch,('AND','OR'),boundaries)
    def projection(state):
        return {r['relation']:[(c['token_refs'],c['input_slot']) for c in r['children']] for r in shells(state)}
    expected=projection(state)
    monkeypatch.setattr(relation_composition,'RELATIONS',dict(reversed(list(relation_composition.RELATIONS.items()))))
    state,result,_=native(second,monkeypatch,('AND','OR'),boundaries)
    assert projection(state)==expected
    assert all(live(state,r) for r in shells(state))
    assert not result['assertions']['ah']


def test_boundary_page_revocation_invalidates_only_its_shell(tmp_path,monkeypatch):
    state,_,_=native(tmp_path,monkeypatch,('AND','OR'),boundaries)
    first,second=shells(state)
    boundary=next(r for r in first['dependencies'] if r['slot']=='structural_operand_1_start')
    state.syntax_trace.append({'kind':'COMPOSITION_PROBE_SUPERSEDED','previous_decision_ref':boundary['page_refs'][0]})
    assert not live(state,first) and live(state,second)


def test_rejected_partition_and_pending_sibling_do_not_publish(tmp_path,monkeypatch):
    def reject(slot,prompt):
        return '0' if slot=='structural_partition' else boundaries(slot,prompt)
    state,result,_=native(tmp_path,monkeypatch,('AND','OR'),reject)
    rows=shells(state)
    assert all(r['status']=='OPEN' for r in rows)
    assert all(any(r.get('category')=='PARTITION_REJECTED' for r in shell['evidence']['trace']) for shell in rows)
    assert not result['assertions']['ah']


def test_context_mutation_during_probe_cannot_become_unconditional(tmp_path,monkeypatch):
    from ah.formalizer.composition_session import _current
    changed=[]
    def mutate(slot,prompt):
        if not changed and slot=='structural_operand_1_start':
            _current.get().domain_feedback='changed during provider call';changed.append(True)
        return boundaries(slot,prompt)
    state,result,_=native(tmp_path,monkeypatch,('AND','OR'),mutate)
    first,second=shells(state)
    assert first['status']=='OPEN' and second['status']=='SHELL_PRODUCED'
    assert any(d['code']=='STRUCTURAL_CONDITION_INPUT_CHANGED' for d in first['evidence']['diagnostics'])
    assert not result['assertions']['ah']


def test_actual_shell_execution_order_is_independent(tmp_path,monkeypatch):
    from ah.formalizer import structural_shells
    first=tmp_path/'first';first.mkdir();second=tmp_path/'second';second.mkdir()
    state,_,_=native(first,monkeypatch,('AND','OR'),boundaries)
    rows=shells(state);assert [r['relation'] for r in rows]==['AND','OR']
    def projection(rows):
        return {r['relation']:[(c['token_refs'],c['input_slot'],c['inherited_context']) for c in r['children']] for r in rows}
    expected=projection(rows)
    monkeypatch.setattr(structural_shells,'execution_order',lambda f:reversed(f['hypotheses']))
    state,result,_=native(second,monkeypatch,('AND','OR'),boundaries)
    rows=shells(state);assert [r['relation'] for r in rows]==['OR','AND']
    assert projection(rows)==expected and all(live(state,r) for r in rows)
    assert not result['assertions']['ah']


def test_child_slot_must_follow_parent_even_with_recomputed_checksum(tmp_path,monkeypatch):
    from ah.formalizer.canonical_ledger import digest
    state,_,_=native(tmp_path,monkeypatch,('AND','OR'),boundaries)
    row=deepcopy(shells(state)[0]);row['children'][0]['input_slot']['inside_attitude']=True
    row['receipt_digest']=digest({k:v for k,v in row.items() if k!='receipt_digest'})
    assert not live(state,row)


def test_reconstructed_evidence_cannot_reuse_outer_validation_memo(tmp_path,monkeypatch):
    from ah.formalizer.canonical_ledger import digest
    state,_,_=native(tmp_path,monkeypatch,('AND','OR'),boundaries)
    row=deepcopy(shells(state)[0]);condition=resolve(state,row['condition'])
    row['evidence']['trace'].append({'kind':'DEPENDENCY_REJECTED',
        'decision_ref':condition.forest['membership']['decision_ref']})
    row['receipt_digest']=digest({k:v for k,v in row.items() if k!='receipt_digest'})
    assert not live(state,row)
