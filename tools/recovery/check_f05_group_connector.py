"""Explicit connector descriptions keep a whole group and source membership."""
from pathlib import Path
from tempfile import TemporaryDirectory
from copy import deepcopy
import json
from pytest import MonkeyPatch
from test_structural_relation_tasks import run,relation,bounds

def group():
    return [('nominal_coordination_discovery','Another flat group')]+bounds('nominal_coordination_members','Иван','Иван')+[
        ('nominal_coordination_members_continue','Another piece starts at «Мария»'),
        ('nominal_coordination_members_piece_end','End after «Мария»'),('nominal_coordination_members_continue','0'),
        ('nominal_coordination_marking','This group has explicit')]+bounds('nominal_coordination_markers','и','и')+[
        ('nominal_coordination_markers_continue','0'),('nominal_coordination_discovery','0')]

def dictionaries(value):
    if isinstance(value,dict):
        yield value
        for v in value.values():yield from dictionaries(v)
    elif isinstance(value,list):
        for v in value:yield from dictionaries(v)

for connector,verb in [('из-за','ушёл'),('возле','уснул')]:
    text=f'Иван и Мария {connector} которых Пётр {verb} спят.'
    steps=relation('NOMINAL_DESCRIPTION')+bounds('structural_description',connector,verb)+[
        ('structural_description_binding','An explicit connector'),('structural_description_marker','«'+connector+'»'),
        ('structural_description_link_continue','Another piece starts at «которых»'),
        ('structural_description_link_piece_end','End after «которых»'),('structural_description_link_continue','0')]+relation('LEXICAL')+group()+[
        ('nominal_attachment','WHOLE established group')]+relation('LEXICAL')
    if connector=='возле':steps.append(('structural_marker_reading','pos: preposition'))
    with TemporaryDirectory() as tmp,MonkeyPatch.context() as patch:
        from ah.formalizer import v7_pipeline
        original=v7_pipeline.build_plan;captured=[]
        def capture(state,*args,**kwargs):
            result=original(state,*args,**kwargs);captured.append((state,args,kwargs));return result
        patch.setattr(v7_pipeline,'build_plan',capture)
        result,script=run(Path(tmp),patch,text,steps)
        assert not result['diagnostics']['codes'],result['diagnostics']
        facts=result['assertions']['ah']
        assert len(facts)==1 and facts[0]['predicate']=='SLEEP',facts
        assert {m['entity'] for m in facts[0]['roles']['AGENT']['group']}=={'ivan','maria'}
        state,args,kwargs=captured[-1]
        frame=next(f for f in state.frames if f.semantic.get('refinement_binding',{}).get('kind')=='RELATIVE')
        binding=frame.semantic['refinement_binding'];members=binding['host_member_refs']
        assert len(members)==2 and set(frame.argument_token_refs)==set(members)
        assert binding['host_token_ref'] not in frame.semantic['morph_bindings']
        assert frame.semantic['nominal_groups'][0]['source_evidence']
        unit=frame.semantic['lexical_units'][frame.predicate_token_ref]
        assert unit['surface']==connector+' которых'
        assert len(unit['anchor_refs'])==2
        assert len(frame.semantic['proposition_args'])==1
        assert next(iter(frame.semantic['proposition_args'].values()))['attitude']=='UNKNOWN'
        rows=[json.loads(line) for line in (Path(tmp)/'journal.log').read_text().splitlines()]
        links=[v for row in rows for v in dictionaries(row) if v.get('kind')=='NOMINAL' and 'host_ref' in v]
        assert links and all(v['host_ref'].startswith('K:') for v in links),links
        from ah.formalizer.component_probe_replay import supersede
        from ah.formalizer.component_constraints import frame_hosts_live
        connector_proof=frame.semantic.get('relative_connector_reading')
        if connector_proof:
            revised=deepcopy(state)
            supersede(revised,connector_proof['proof']['decision_ref'],'connector revised')
            assert not frame_hosts_live(revised,frame)
            corrupted=deepcopy(frame)
            corrupted.semantic['morph_bindings'][connector_proof['marker_ref']]['pos']='ADVB'
            assert not frame_hosts_live(state,corrupted)
        changed=deepcopy(state)
        supersede(changed,frame.semantic['refinement_owner_proofs'][0]['decision_ref'],'owner revised')
        assert not frame_hosts_live(changed,frame)
        _,_,diagnostics,_=original(changed,*args,**kwargs)
        assert any(d.startswith('NOMINAL_HOST_PROOF_RETIRED:') for d in diagnostics),diagnostics
        print('PASS:',text,'group host, source connector, nested UNKNOWN content, K usage link, late revocation')
