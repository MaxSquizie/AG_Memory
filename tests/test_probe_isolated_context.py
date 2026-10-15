"""Isolated calls carry their task; audit addressing never becomes model text."""
import json
from copy import deepcopy
from types import SimpleNamespace

import pytest

from ah.formalizer.selection_labels import build_label_selection_prompt
from ah.formalizer.selection_protocol import DecisionSchema,Relation
from ah.formalizer.provider_adapter import ProviderAdapter,IntegrityError
from ah.formalizer.provider_call_log import ProviderCallLog
from ah.formalizer.selection_prompt import SelectionPrompt
from test_structural_relation_tasks import run,relation,unary,binary


def prompt(ids=('internal:a','internal:b')):
    schema=DecisionSchema('resource-hash',{
        cid:Relation(cid,label,0,(),label) for cid,label in zip(ids,('first meaning','second meaning'))})
    return 'A local question.\n'+build_label_selection_prompt(slot_id='test',frame_id='internal-frame',
        context_span='Исходный текст.',mentions={},schema=schema,candidates=ids)


def test_model_text_and_addressing_survive_prefix_copy_and_wal_replay():
    p=deepcopy(prompt())
    assert isinstance(p,SelectionPrompt)
    assert 'internal' not in p and 'resource-hash' not in p
    assert json.loads(json.dumps({'content':p}))['content']==str(p)
    log=ProviderCallLog();sent=[]
    adapter=ProviderAdapter('test',frozenset({'select'}),lambda p:sent.append(str(p)) or '2',log=log)
    assert adapter.select(p,'r',ordinal=1)=='2'
    record=log.lookup('r',1)
    assert record['prompt']==str(p)
    assert record['selection_audit']['candidates']==['internal:a','internal:b']
    assert adapter.select(p,'r',ordinal=1)=='2' and len(sent)==1
    different=prompt(('different:a','different:b'))
    assert str(different)==str(p)
    with pytest.raises(IntegrityError,match='REPLAY_MISMATCH'):
        adapter.select(different,'r',ordinal=1)


def test_audit_map_cannot_change_during_journal_reload():
    class Journal:
        def __init__(self):self.records=[]
        def scan_unprocessed(self,n):return self.records
    journal=Journal()
    base={'kind':'prov_call','id':'x','state':'PENDING','selection_audit':{'candidates':['a']}}
    journal.records=[{'payload':base},{'payload':{**base,'state':'RECEIVED','selection_audit':{'candidates':['b']}}}]
    with pytest.raises(ValueError,match='identity changed'):ProviderCallLog(journal)


@pytest.mark.parametrize('proved',[False,True])
def test_unknown_lookup_is_not_a_syntax_hint_but_proof_is_retained(monkeypatch,proved):
    from ah.formalizer.composition_session import CompositionSession
    from ah.formalizer import context_proofs
    monkeypatch.setattr(context_proofs,'compile_goals',lambda *args:[])
    item={'status':'PROVED' if proved else 'UNKNOWN','goal':{'template_ref':'known-template'}}
    if proved:item['proof']={'conclusion':{'template_ref':'known-template'},'premise_support_refs':['support'],'derivations':[]}
    reader=SimpleNamespace(read=lambda *args:{'rows':[],'proof_results':[item]})
    session=CompositionSession(SimpleNamespace(evidence=[],frames=[]),SimpleNamespace(entries=lambda name:[]),reader)
    text=session.memory('structural_relation',[{},{}],(0,1),{'max_candidates':16,'context_chars':2048})
    assert ('PROVED' in text)==proved
    assert 'UNKNOWN' not in text
    assert bool(text)==proved


def test_child_question_does_not_reassign_removed_outer_words(tmp_path,monkeypatch):
    result,script=run(tmp_path,monkeypatch,'Иван не пришёл.',
        unary('NOT','не','не')+relation('LEXICAL'))
    child=[p for slot,p in script.calls if slot=='structural_relation'][1]
    target=child.split('Resolve ONLY the target area «',1)[1].split('»',1)[0]
    assert 'не' not in target and 'Иван' in target and 'пришёл' in target
    assert 'Context span: Иван не пришёл.' in child
    assert result['assertions']['ah'][0]['operator']=='NOT'
    decisions=result['runtime']['ir']['decisions']
    decisions=decisions.values() if isinstance(decisions,dict) else decisions
    assert any(h['kind']=='SELECTION_LABEL_MAP' for d in decisions for h in d.get('history',()))


def test_function_question_contains_current_parts_without_previous_calls(tmp_path,monkeypatch):
    steps=binary('COUNTERFACTUAL',('Иван','пришёл'),('Мария','спала'))
    steps.insert(5,('structural_function_owner','Outer relation owns «бы»'))
    _,script=run(tmp_path,monkeypatch,'Если бы Иван пришёл, Мария бы спала.',steps)
    p=next(p for slot,p in script.calls if slot=='structural_function_owner')
    assert 'Current parts: 1: «Иван пришёл»; 2: «Мария бы спала»' in p


def test_partition_is_a_proposal_not_a_declared_fact(tmp_path,monkeypatch):
    _,script=run(tmp_path,monkeypatch,'Неверно, что Иван пришёл.',
        unary('NOT','Неверно','что')+relation('LEXICAL'))
    p=next(p for slot,p in script.calls if slot=='structural_partition')
    assert 'proposed content parts' in p and 'proposed linking words' in p
    assert 'Answer 0 if' in p and 'Every remaining token belongs' not in p
    assert 'UNKNOWN' not in p and 'fixture:T:' not in p


def test_readable_choices_use_separate_audit_after_serialization():
    from test_formalization_readable import sample
    from ah.gui.formalization_inspection import Inspection
    from ah.gui.formalization_readable import ReadableInspection
    from ah.formalizer.state import Decision
    from ah.formalizer.selection_prompt import record_prompt
    from dataclasses import asdict
    d=Decision('test','x',('internal:a','internal:b'))
    record_prompt(d,prompt())
    reader=ReadableInspection(Inspection(sample()))
    rows=reader.choices(json.loads(json.dumps(asdict(d))))
    assert rows[0][1]=='first meaning' and rows[1][1]=='second meaning'
