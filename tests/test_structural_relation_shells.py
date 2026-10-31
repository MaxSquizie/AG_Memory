"""Conditional simple-relation adapters on native producers, scripted replies."""
import re
from copy import deepcopy
import pytest
from test_structural_open_forest import native
from ah.formalizer.structural_relations import CONTRACTS
from ah.formalizer.structural_shells import live
from ah.formalizer.canonical_ledger import digest


CASES=[
    ('XOR','Иван пришёл либо Мария спит',[('Иван','пришёл'),('Мария','спит')],None),
    ('IMPLIES','Если Иван пришёл то Мария спит',[('Иван','пришёл'),('Мария','спит')],None),
    ('COUNTERFACTUAL','Если бы Иван пришёл то Мария спит',[('Иван','пришёл'),('Мария','спит')],None),
    ('BEFORE','Иван пришёл прежде чем Мария спит',[('Иван','пришёл'),('Мария','спит')],None),
    ('AFTER','Иван пришёл после того как Мария спит',[('Иван','пришёл'),('Мария','спит')],None),
    ('DURING','Иван пришёл пока Мария спит',[('Иван','пришёл'),('Мария','спит')],None),
    ('IF_ELSE','Если Иван пришёл то Мария спит иначе Пётр читает',
     [('Иван','пришёл'),('Мария','спит'),('Пётр','читает')],None),
    ('NOT','Неверно что Иван пришёл',[('Иван','пришёл')],('Неверно','что')),
    ('QUERY','Верно ли что Иван пришёл?',[('Иван','пришёл')],('Верно','что')),
    ('GROUP','(Иван пришёл)',[('Иван','пришёл')],None),
]


@pytest.mark.parametrize('kind,text,parts,introducer',CASES)
def test_conditional_shell_has_typed_children(tmp_path,monkeypatch,kind,text,parts,introducer):
    def answer(slot,prompt):
        labels=re.findall(r'^(\d+)\. (.*)$',prompt,re.M)
        if 'Optional search:' in prompt:return '0'
        if slot in {'structural_partition','relation_marker_role'}:return '1'
        desired={}
        for i,(first,last) in enumerate(parts,1):
            desired['structural_operand_'+str(i)+'_start']='Start at «'+first+'»'
            desired['structural_operand_'+str(i)+'_end']='End after «'+last+'»'
        if introducer:
            desired.update(structural_introducer_start='Start at «'+introducer[0]+'»',
                           structural_introducer_end='End after «'+introducer[1]+'»')
        if kind=='GROUP':
            desired.update(structural_group_start='Start at «Иван»',structural_group_end='End after «пришёл»')
        return next((n for n,label in labels if slot in desired and label.startswith(desired[slot])),'?')
    state,result,_=native(tmp_path,monkeypatch,(kind,'LEXICAL'),answer,text=text)
    rows=[r for r in state.syntax_trace if r.get('kind')=='STRUCTURAL_CONDITIONAL_SHELL' and r['relation']==kind]
    assert rows and live(state,rows[0]),[(r['status'],r['evidence']['diagnostics']) for r in rows]
    shell=rows[0];assert len(shell['children'])==len(parts)
    assert CONTRACTS[kind].accepts(len(parts))
    for child in shell['children']:
        slot=child['input_slot']
        if kind=='GROUP':assert slot['inside_attitude'] and slot['surrounding_relations']==[]
        else:assert slot['surrounding_relations']==[kind]
    forged=deepcopy(shell);forged['children'].append(deepcopy(forged['children'][0]))
    forged['receipt_digest']=digest({k:v for k,v in forged.items() if k!='receipt_digest'})
    assert not live(state,forged)
    assert not result['assertions']['ah']
    state.syntax_trace.append({'kind':'DEPENDENCY_REJECTED','decision_ref':shell['partition_proof']['decision_ref']})
    assert not live(state,shell)
