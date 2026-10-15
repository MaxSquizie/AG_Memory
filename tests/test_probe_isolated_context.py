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
    session=CompositionSession(SimpleNamespace(evidence=[],frames=[],syntax_trace=[],diagnostics=[]),SimpleNamespace(entries=lambda name:[]),reader)
    text=session.memory('structural_relation',[{},{}],(0,1),{'max_candidates':16,'context_chars':2048})
    assert ('PROVED' in text)==proved
    assert 'UNKNOWN' not in text
    assert bool(text)==proved


def test_child_question_does_not_reassign_removed_outer_words(tmp_path,monkeypatch):
    result,script=run(tmp_path,monkeypatch,'Иван не пришёл.',
        unary('NOT','не','не')+relation('LEXICAL'))
    child=[p for slot,p in script.calls if slot=='structural_relation'][1]
    target=child.split('Context span: ',1)[1].split('\nSurrounding source',1)[0]
    assert 'не' not in target and 'Иван' in target and 'пришёл' in target
    assert 'Context span: '+target in child
    assert 'Surrounding source' in child and 'Иван не пришёл' in child
    assert 'do not assign surrounding words to it again' in child
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
    assert 'Proposed split' in p and 'outer relation words: «Неверно что»' in p
    assert 'punctuation outside parts: «, .»' in p
    assert 'answer 0 if' in p and 'Every remaining token belongs' not in p
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


def test_reserved_content_and_feedback_are_scoped_to_their_region(tmp_path,monkeypatch):
    from test_structural_relation_tasks import content_steps
    steps=content_steps('сказала','Иван','вошёл','Мария')
    first=steps[:5]+[('structural_partition','0'),('structural_revision','REVISE')]
    result,script=run(tmp_path,monkeypatch,'Мария сказала: «Иван вошёл».',
        first+steps+relation('LEXICAL'))
    questions=[p for slot,p in script.calls if slot=='structural_relation']
    assert 'Earlier attempt:' in questions[1]
    parent,body=questions[2:]
    assert 'content slot of this predicate is supplied separately' in parent
    assert 'Context span: Мария сказала\n' in parent
    assert 'Earlier attempt:' not in parent and 'Earlier attempt:' not in body
    assert 'supplied separately' not in body
    assert 'Surrounding source' in parent and 'Surrounding source' in body
    assert 'Resolve ONLY the target area «Мария сказала»' in parent
    assert 'Resolve ONLY the target area «Иван вошёл»' in body
    partition=next(p for slot,p in script.calls if slot=='structural_partition')
    assert 'parent intentionally has an open content slot' in partition
    assert 'parent clause with a content slot: «Мария сказала»' in partition
    assert result['assertions']['ah'][0]['predicate']=='SAY'


def test_repeated_failed_assignment_stops_without_another_revision_probe(tmp_path,monkeypatch):
    first=binary('AND',('Иван','пришёл'),('Мария','спит'))[:5]+[('structural_partition','0')]
    result,script=run(tmp_path,monkeypatch,'Иван пришёл и Мария спит.',
        first+[('structural_revision','REVISE')]+first)
    assert not result['assertions']['ah']
    assert 'STRUCTURAL_REVISION_NO_PROGRESS' in result['diagnostics']['codes']
    assert sum(slot=='structural_revision' for slot,_ in script.calls)==1


def test_changed_partial_grammar_state_is_progress_even_with_same_outer_choice(monkeypatch):
    from ah.formalizer import component_refinement,relation_composition,structural_tasks
    from ah.formalizer.state import Diagnostic
    state=SimpleNamespace(syntax_trace=[],diagnostics=[],decisions={},component_probe_records={})
    state.diag=lambda code,detail:state.diagnostics.append(Diagnostic(code,detail))
    region=SimpleNamespace(region_id='region:test',source_range=(0,1))
    release=SimpleNamespace(entries=lambda name:[{'max_depth':10,'composition':{'structural_tasks':'CLOSED_RELATIONS_V1'}}])
    calls=[];revisions=[]
    def compose(*args):
        calls.append(True)
        state.syntax_trace.append({'kind':'STRUCTURAL_TASK','region_ref':region.region_id,
            'slot':'structural_relation','selected':'LEXICAL','status':'SELECTED','reason':'ONE_SELECTED',
            'alternatives':[{'candidate_id':'LEXICAL','label':'One predication'}]})
        # Same outer type, different retained grammar domain on the second attempt.
        role='OBJECT' if len(calls)==1 else 'LOCATION'
        return [SimpleNamespace(frame_id='partial',semantic={'structural_unresolved':True,
            'proposed_roles':{'word':role}})]
    def revise(*args):
        revisions.append(True);return {'candidate_id':'REVISE'},{}
    monkeypatch.setattr(relation_composition,'compose',compose)
    monkeypatch.setattr(structural_tasks,'choose',revise)
    component_refinement._compose_area(state,release,None,region,[],{'refinement':{'max_depth':4}})
    assert len(calls)==3 and len(revisions)==2
    assert state.diagnostics[-1].code=='STRUCTURAL_REVISION_NO_PROGRESS'


def test_inner_relation_stays_reachable_with_separate_outer_context(tmp_path,monkeypatch):
    result,script=run(tmp_path,monkeypatch,'Возможно, Иван не пришёл.',
        unary('POSSIBLE','Возможно','Возможно')+[
            ('structural_governor','INDEPENDENT')]+unary('NOT','не','не')+relation('LEXICAL'))
    questions=[p for slot,p in script.calls if slot=='structural_relation']
    inner=questions[1]
    assert 'Context span: Иван не пришёл' in inner
    assert 'Surrounding source (reference only): Возможно, Иван не пришёл.' in inner
    assert 'Resolve ONLY the target area «Иван не пришёл»' in inner
    assert {'NOT','POSSIBLE','CONTENT','FORALL'}<=set(inner.selection_audit['candidates'])
    tree=result['assertions']['ah'][0]
    assert tree['operator']=='POSSIBLE' and tree['operands'][0]['operator']=='NOT'
    tasks=[r for r in result['runtime']['ir']['syntax_trace'] if r.get('slot')=='structural_relation']
    assert all(r['context_policy']=='TARGET_WITH_CONTEXT' and r['target_token_refs'] for r in tasks)


def test_grammatical_reading_still_has_surrounding_context():
    from ah.formalizer.component_source import probe_context
    parent=SimpleNamespace(region_id='sentence',parent_ref=None,kind='SENTENCE',source_range=(0,15))
    child=SimpleNamespace(region_id='child',parent_ref='sentence',grounds=('MORPHOLOGICAL_REFINEMENT',))
    state=SimpleNamespace(text='Иван не пришёл.',region_forest=SimpleNamespace(regions=[parent,child]))
    local='Иван    пришёл'
    context,question=probe_context(state,child,{'context_chars':2048},local)
    assert 'Surrounding source (reference only): Иван не пришёл.' in context
    assert local in question
    target,question=probe_context(state,child,{'context_chars':2048},local,include_surrounding=False)
    assert target==local and question==''


def test_dependency_question_explains_roles_without_python_context_dump(tmp_path,monkeypatch):
    from test_structural_relation_tasks import Script
    from tools.formalizer_v7_native_binding import ChatBackend,execute_native
    from tools.formalizer_v7_extended_binding import Session
    script=Script(relation('LEXICAL'))
    monkeypatch.setattr(ChatBackend,'generate',lambda self,prompt,**kw:script.generate(prompt,**kw))
    text='Вчера марии Пётр передал книгу.'
    payload={'raw_input':{'text':text,'source_id':'recipient-context','revision':1,
        'range':[0,len(text)],'language':'ru','request_kind':'ASSERTION','batch_kind':'MESSAGE',
        'source_timestamp':'2026-10-09T12:00:00+00:00'}}
    result=execute_native(Session([payload],tmp_path/'journal'),payload,
        {'provider':'lmstudio','model':'scripted-recipient','structure_mode':'region_probes'})
    assert not script.steps and not script.errors
    p=next(p for slot,p in script.calls if slot=='nominal_dependency' and 'attachment of «марии»' in p)
    assert 'recipient or addressee of the action' in p
    assert '«Пётр» is grammatical subject of the predicate «передал»' in p
    assert "'dependent':" not in p and 'APPOSITION' not in p
    assert result['assertions']['ah'][0]['roles']['RECIPIENT']=={'entity':'maria'}


def test_conditional_function_question_names_keep_set_and_outer_contract(tmp_path,monkeypatch):
    from test_structural_relation_tasks import bounds
    steps=relation('IMPLIES')+bounds('structural_operand_1','Если','пришёл')+bounds('structural_operand_2','то','спит')+[
        ('structural_function_owner','Outer relation owns «Если»'),
        ('structural_function_owner','Outer relation owns «то»'),
        ('structural_partition','PARTITION')]+relation('LEXICAL')+relation('LEXICAL')
    result,script=run(tmp_path,monkeypatch,'Если Иван пришёл, то Мария спит.',steps)
    p=next(p for slot,p in script.calls if slot=='structural_function_owner')
    assert 'Keep all listed words inside their parts: «Если» @0, «то» @18' in p
    assert 'Words introducing the condition or consequence' in p
    assert result['assertions']['ah'][0]['operator']=='IMPLIES'


def test_gui_explains_which_words_reached_the_structure_question():
    from test_formalization_readable import sample,visible
    from ah.gui.formalization_inspection import Inspection
    from ah.gui.formalization_readable import ReadableInspection
    data=sample();data['state']['syntax_trace']=[{'kind':'STRUCTURAL_TASK','slot':'structural_relation',
        'source_range':[0,26],'context_policy':'TARGET_WITH_CONTEXT','target_token_refs':['student','read']}]
    inspection=Inspection(data);reader=ReadableInspection(inspection)
    explanation=visible(reader.explain(inspection.by_ref['trace:0']))
    assert 'Текст этой структурной задачи: «студент читает»' in explanation
    assert 'Окружение доступно для понимания смысла и грамматики' in reader.report([])
