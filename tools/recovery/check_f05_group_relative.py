"""Scripted native group-description projection with original membership proof."""
from pathlib import Path
from tempfile import TemporaryDirectory
from pytest import MonkeyPatch
from test_structural_relation_tasks import run,relation,bounds

def group():
    return [('nominal_coordination_discovery','Another flat group')]+bounds('nominal_coordination_members','Иван','Иван')+[
        ('nominal_coordination_members_continue','Another piece starts at «Мария»'),
        ('nominal_coordination_members_piece_end','End after «Мария»'),('nominal_coordination_members_continue','0'),
        ('nominal_coordination_marking','This group has explicit')]+bounds('nominal_coordination_markers','и','и')+[
        ('nominal_coordination_markers_continue','0'),('nominal_coordination_discovery','0')]
for text,marker,last,role in [
    ('Иван и Мария которые прочитали книгу спят.','которые','книгу','SUBJECT'),
    ('Иван и Мария которых Пётр видел спят.','которых','видел','OBJECT')]:
    steps=relation('NOMINAL_DESCRIPTION')+bounds('structural_description',marker,last)+[
        ('structural_description_binding','An explicit relative expression'),('structural_description_marker','«'+marker+'»')]+relation('LEXICAL')+group()+[
        ('nominal_attachment','WHOLE established group'),('relative_argument_role',role)]+relation('LEXICAL')
    with TemporaryDirectory() as tmp,MonkeyPatch.context() as patch:
        from ah.formalizer import v7_pipeline
        original=v7_pipeline.build_plan;captured=[];plan_inputs=[]
        def capture(state,*args,**kwargs):
            result=original(state,*args,**kwargs);captured.append(state);plan_inputs.append((args,kwargs));return result
        patch.setattr(v7_pipeline,'build_plan',capture)
        result,script=run(Path(tmp),patch,text,steps)
        print(result['diagnostics'],result['assertions']['ah'])
    
        assert not result['diagnostics']['codes'],result['diagnostics']
        facts=result['assertions']['ah']
        assert len(facts)==1 and facts[0]['predicate']=='SLEEP',facts
        assert {m['entity'] for m in facts[0]['roles']['AGENT']['group']}=={'ivan','maria'},facts
        frames=result['runtime']['ir']['frames']
        projected=[f for f in frames if f['semantic'].get('refinement_binding',{}).get('host_member_refs')]
        assert projected,frames
        assert all(f['semantic']['refinement_binding']['host_role']==role for f in projected)
        parents=[f for f in frames if f['semantic'].get('nominal_args')]
        for child in projected:
            members=child['semantic']['refinement_binding']['host_member_refs']
            assert any(all(child['semantic']['morph_bindings'][t]==parent['semantic']['morph_bindings'].get(t) for t in members) for parent in parents)
        import json
        def dictionaries(value):
            if isinstance(value,dict):
                yield value
                for v in value.values():yield from dictionaries(v)
            elif isinstance(value,list):
                for v in value:yield from dictionaries(v)
        records=[json.loads(line) for line in (Path(tmp)/'journal.log').read_text().splitlines()]
        links=[v for r in records for v in dictionaries(r) if v.get('kind')=='NOMINAL' and 'host_ref' in v]
        assert links and all(v['host_ref'].startswith('K:') and v['host_role']==role for v in links),links
        assert all(f['semantic']['nominal_groups'][0]['marker_refs'] for f in projected)
        from ah.formalizer.component_constraints import frame_hosts_live
        from ah.formalizer.component_probe_replay import supersede
        from copy import deepcopy
        state=captured[-1]
        child=next(f for f in state.frames if f.semantic.get('refinement_binding',{}).get('host_member_refs'))
        assert frame_hosts_live(state,child)
        changed=deepcopy(child);changed.semantic['refinement_binding'].pop('function_proofs')
        assert not frame_hosts_live(state,changed)
        changed=deepcopy(child);changed.semantic['refinement_binding']['host_role']='UNRELATED'
        assert not frame_hosts_live(state,changed)
        parent=next(f for f in state.frames if any(a.get('host_selection_required') for a in f.semantic.get('nominal_args',())))
        owner_proof=parent.semantic['nominal_args'][0]['host_selection_proof']
        assert child.semantic['refinement_owner_required']
        assert frame_hosts_live(state,parent)
        lost=deepcopy(child);lost.semantic.pop('refinement_owner_proofs')
        assert not frame_hosts_live(state,lost)
        changed=deepcopy(parent);changed.semantic['nominal_args'][0]['host_token_ref']='different occurrence'
        assert not frame_hosts_live(state,changed)
        # Use the runtime evidence adapter to check the exact captured selection.
        from ah.formalizer.dispatch_evidence import valid
        assert valid(state,'REFINEMENT_HOST',owner_proof)
        changed_state=deepcopy(state)
        supersede(changed_state,owner_proof['decision_ref'],'owner replacement')
        assert not frame_hosts_live(changed_state,parent) and not frame_hosts_live(changed_state,child)
        assert not valid(changed_state,'REFINEMENT_HOST',owner_proof)
        changed_boundary=deepcopy(state)
        assert owner_proof['premises']
        supersede(changed_boundary,owner_proof['premises'][0]['decision_ref'],'boundary replacement')
        assert not frame_hosts_live(changed_boundary,parent) and not frame_hosts_live(changed_boundary,child)
        args,kwargs=plan_inputs[-1]
        _,_,diagnostics,_=original(changed_state,*args,**kwargs)
        assert any(d.startswith('NOMINAL_HOST_PROOF_RETIRED:') for d in diagnostics),diagnostics
        proof=child.semantic['refinement_binding']['function_proofs'][0]
        supersede(state,proof['decision_ref'],'replacement')
        assert not frame_hosts_live(state,child)
print('PASS: group relative subject/object roles, source morphology unchanged, nominal K link retained in native write')
