"""Native n-ary groups and scoped children; replies are scripted, not live LLM."""
import re
import json
import pytest
from test_structural_relation_tasks import run,relation,bounds,atom
from test_structural_open_forest import native
from ah.formalizer.composition_session import _current
from ah.formalizer.structural_shells import live


def normalized(value):
    # AH canonicalizes commutative operands and assertion order. Keep the full
    # hierarchy and multiplicity: sorting must not flatten or deduplicate.
    if isinstance(value,list):return sorted((normalized(v) for v in value),key=lambda v:json.dumps(v,sort_keys=True))
    if isinstance(value,dict):return {k:normalized(v) for k,v in value.items()}
    return value


@pytest.mark.parametrize('kind,link',[('AND','и'),('OR','или'),('XOR','либо')])
def test_three_direct_parts_reach_native_write(tmp_path,monkeypatch,kind,link):
    text=f'Иван пришёл {link} Мария спит {link} Пётр пришёл'
    steps=relation(kind)
    for index,edge in enumerate([('Иван','пришёл'),('Мария','спит'),('Пётр','пришёл')],1):
        if index<3:steps+=bounds('structural_operand_'+str(index),*edge)
        else:steps += [('structural_group_next','Another direct part begins at «'+edge[0]+'»'),
                       ('structural_operand_'+str(index)+'_end','End after «'+edge[1]+'»')]
    steps += [('structural_partition','PARTITION')]+relation('LEXICAL')*3
    result,_=run(tmp_path,monkeypatch,text,steps)
    children=[atom('ARRIVE','ivan'),atom('SLEEP','maria'),atom('ARRIVE','petr')]
    assert normalized(result['assertions']['ah'])==normalized(
        [{'operator':kind,'operands':children}]+(children if kind=='AND' else []))
    assert not result['diagnostics']['codes']


def test_direct_part_keeps_different_nested_relation(tmp_path,monkeypatch):
    # Script explicitly chooses AND(A, OR(B,C)); adjacency alone decides neither
    # this grouping nor its competing reading OR(AND(A,B),C).
    text='Иван пришёл и Мария спит или Пётр пришёл'
    steps=relation('AND')+bounds('structural_operand_1','Иван','пришёл')
    steps+=bounds('structural_operand_2','Мария','пришёл')+[('structural_partition','PARTITION')]
    steps+=relation('LEXICAL')+relation('OR')+bounds('structural_operand_1','Мария','спит')
    steps+=bounds('structural_operand_2','Пётр','пришёл')+[('structural_partition','PARTITION')]
    steps+=relation('LEXICAL')*2
    result,_=run(tmp_path,monkeypatch,text,steps)
    root=next(f for f in result['assertions']['ah'] if f.get('operator')=='AND')
    assert normalized(root)==normalized({'operator':'AND','operands':[atom('ARRIVE','ivan'),
        {'operator':'OR','operands':[atom('SLEEP','maria'),atom('ARRIVE','petr')]}]})
    assert not any(f.get('predicate') in {'SLEEP'} or f==atom('ARRIVE','petr') for f in result['assertions']['ah'])
    assert not result['diagnostics']['codes']


def test_shared_wording_supplies_all_three_alternatives(tmp_path,monkeypatch):
    steps=relation('OR')
    for index,edge in enumerate([('Иван','Иван'),('Мария','Мария'),('Пётр','придёт')],1):
        if index<3:steps+=bounds('structural_operand_'+str(index),*edge)
        else:steps += [('structural_group_next','Another direct part begins at «'+edge[0]+'»'),
                       ('structural_operand_'+str(index)+'_end','End after «'+edge[1]+'»')]
    steps += [('structural_shared_material','Some wording')]+bounds('structural_shared_source','придёт','придёт')
    steps += [('structural_partition','PARTITION')]+relation('LEXICAL')*3
    result,_=run(tmp_path,monkeypatch,'Иван или Мария или Пётр придёт',steps)
    assert normalized(result['assertions']['ah'])==normalized([{'operator':'OR','operands':[
        atom('ARRIVE',name) for name in ('ivan','maria','petr')]}])
    assert not result['diagnostics']['codes']


def direct_answer(slot,prompt):
    labels=re.findall(r'^(\d+)\. (.*)$',prompt,re.M)
    if slot=='structural_group_next':
        return next((n for n,label in labels if label.startswith('Another direct part begins at «Пётр»')),'0')
    if 'Optional search:' in prompt:return '0'
    if slot=='structural_relation':
        return next((n for n,label in labels if 'One lexical predication' in label),'0')
    if slot in {'structural_partition','relation_marker_role'}:return '1'
    tokens=_current.get().area_inputs[1]
    # Positions are declared test replies, never production boundary rules.
    indices={'structural_operand_1_start':0,'structural_operand_1_end':1,
             'structural_operand_2_start':3,'structural_operand_2_end':4,
             'structural_operand_3_start':6,'structural_operand_3_end':7}
    if slot in indices:
        token=tokens[indices[slot]];start=slot.endswith('start')
        prefix=('Start at' if start else 'End after')+' «'+token.span+'» @'+str(token.start if start else token.end)
        return next((n for n,label in labels if label.startswith(prefix)),'0')
    return '?'


@pytest.mark.parametrize('retired_slot',['structural_group_next','structural_operand_1_continue','structural_operand_2_continue'])
def test_siblings_share_depth_and_completion_revocation_retires_shell(tmp_path,monkeypatch,retired_slot):
    state,result,_=native(tmp_path,monkeypatch,('AND','OR'),direct_answer,
                         text='Иван пришёл и Мария спит и Пётр пришёл')
    rows=[r for r in state.syntax_trace if r.get('kind')=='STRUCTURAL_CONDITIONAL_SHELL']
    assert len(rows)==2 and all(live(state,r) and len(r['children'])==3 for r in rows)
    snapshot=next(iter(state.observation['structural_frontiers'].values()))
    assert sorted(j['depth'] for j in snapshot['jobs'])==[1,2,2,2,2,2,2]
    assert not result['assertions']['ah']
    completed=next(r for r in rows[0]['evidence']['trace'] if r.get('kind')=='STRUCTURAL_TASK'
               and r.get('slot')==retired_slot and r.get('selected')=='DONE')
    state.syntax_trace.append({'kind':'DEPENDENCY_REJECTED','decision_ref':completed['decision_ref']})
    assert not live(state,rows[0]) and live(state,rows[1])


def test_group_projection_binds_each_part_and_completion(tmp_path,monkeypatch):
    from copy import deepcopy
    from ah.formalizer import direct_partitions
    original=direct_partitions.valid;checked=[]
    def inspect(state,grouping,kind,groups,markers,shared):
        result=original(state,grouping,kind,groups,markers,shared)
        if result:
            assert not original(state,None,kind,groups,markers,shared)
            moved=list(groups);moved[0],moved[1]=moved[1],moved[0]
            assert not original(state,grouping,kind,moved,markers,shared)
            forged=deepcopy(grouping)
            forged['raw_groups'][0],forged['raw_groups'][1]=forged['raw_groups'][1],forged['raw_groups'][0]
            assert not original(state,forged,kind,moved,markers,shared)
            checked.append(True)
        return result
    monkeypatch.setattr(direct_partitions,'valid',inspect)
    test_three_direct_parts_reach_native_write(tmp_path,monkeypatch,'AND','и')
    assert checked


def test_source_supported_boundary_repair_recollects_group(tmp_path,monkeypatch):
    steps=relation('AND')+bounds('structural_operand_1','Иван','Мария')
    steps += [('structural_operand_2_start','0'),
              ('structural_ownership_revision','Reconsider a direct content part')]
    steps += bounds('structural_operand_1','Иван','пришёл')+bounds('structural_operand_2','Мария','спит')
    steps += [('structural_partition','PARTITION')]+relation('LEXICAL')*2
    result,script=run(tmp_path,monkeypatch,'Иван пришёл и Мария спит',steps)
    assert not result['diagnostics']['codes']
    assert any(slot=='structural_ownership_revision' for slot,_ in script.calls)
    root=next(f for f in result['assertions']['ah'] if f.get('operator')=='AND')
    assert normalized(root)==normalized({'operator':'AND','operands':[atom('ARRIVE','ivan'),atom('SLEEP','maria')]})


@pytest.mark.parametrize('reply',['?','MULTIPLE'])
def test_unresolved_next_does_not_finish_group(tmp_path,monkeypatch,reply):
    def answer(slot,prompt):
        if slot=='structural_group_next':
            if reply!='MULTIPLE':return reply
            return ','.join(n for n,label in re.findall(r'^(\d+)\. (.*)$',prompt,re.M)
                            if '«Пётр»' in label or '«пришёл»' in label) or '0'
        return direct_answer(slot,prompt)
    state,result,prompts=native(tmp_path,monkeypatch,('AND','OR'),answer,
                               text='Иван пришёл и Мария спит и Пётр пришёл')
    assert not any('Decision slot: structural_operand_3_end' in p for p in prompts)
    assert not any('Decision slot: structural_operand_count' in p for p in prompts)
    assert not result['assertions']['ah']
    rows=[r for r in state.syntax_trace if r.get('kind')=='STRUCTURAL_CONDITIONAL_SHELL']
    assert rows and all(r['status']=='OPEN' and not r['children'] for r in rows)
    if reply=='MULTIPLE':
        assert all(any(r.get('reason')=='MULTIPLE_ADMISSIBLE' and len(r['alternatives'])==2
                       for r in shell['evidence']['trace']) for shell in rows)


def test_rejected_next_endpoint_cannot_switch_start_or_finish(tmp_path,monkeypatch):
    def answer(slot,prompt):
        if slot=='structural_operand_3_end':return '0'
        return direct_answer(slot,prompt)
    state,result,prompts=native(tmp_path,monkeypatch,('AND','OR'),answer,
                               text='Иван пришёл и Мария спит и Пётр пришёл')
    assert any('Decision slot: structural_operand_3_end' in p for p in prompts)
    assert not any('Decision slot: structural_operand_3_start' in p for p in prompts)
    assert not result['assertions']['ah']
    rows=[r for r in state.syntax_trace if r.get('kind')=='STRUCTURAL_CONDITIONAL_SHELL']
    assert rows and all(r['status']=='OPEN' for r in rows)
