"""Closed source choices over the real GUI/oracle route, not a graph stub."""
import json
import re
from collections import deque

import pytest

from tools.formalizer_v7_native_binding import ChatBackend,execute_native
from tools.formalizer_v7_extended_binding import Session


class Script:
    def __init__(self,steps,default='1'):
        # Legacy scenarios declared CONTENT's owner after its boundaries.
        # The addressed protocol now selects that same owner first. Reorder
        # only the declared task, preserving every answer and semantic oracle.
        steps=list(steps)
        for i,(slot,value) in enumerate(steps):
            if slot!='structural_relation' or value!='CONTENT':continue
            for j in range(i+1,len(steps)):
                if steps[j][0]=='structural_relation':break
                if steps[j][0]=='structural_owner':
                    steps.insert(i+1,steps.pop(j));break
        self.steps=deque(steps);self.default=default;self.calls=[];self.errors=[];self.selected_slot=None

    def generate(self,prompt,**kwargs):
        slot=re.search(r'Decision slot: (\S+)',prompt).group(1)
        self.calls.append((slot,prompt))
        if 'Optional search:' in prompt and (not self.steps or self.steps[0][0]!=slot):return '0'
        if slot==self.selected_slot and (not self.steps or self.steps[0][0]!=slot):return '0'
        if not slot.startswith('structural_') and (not self.steps or self.steps[0][0]!=slot):return self.default
        if not self.steps:
            self.errors.append('Unexpected '+slot);return '?'
        expected,value=self.steps[0]
        if slot!=expected:
            self.errors.append('Expected '+expected+', got '+slot);return '?'
        if 'Optional search:' in prompt and value in {'DONE','NONE','KEEP_ALL','No further'}:
            self.steps.popleft();return '0'
        if value in {'?','0','ONE_SELECTED'}:
            self.steps.popleft();return value
        mapping={cid:str(n) for n,cid in enumerate(getattr(prompt,'selection_audit',{}).get('candidates',()),1)}
        labels=dict(re.findall(r'^(\d+)\. (.*)$',prompt,re.M))
        # A real HTTP peer receives only model text, never the audit IDs.
        # These aliases express this test's scripted choices using that text.
        if not mapping:
            from ah.formalizer.relation_composition import RELATIONS
            if value in RELATIONS:value=RELATIONS[value]
            elif value=='INDEPENDENT':value='No agreement governor:'
            elif value=='RELATION_ONLY':value='Relation wording «'
            elif value=='PARTITION' and len(labels)==1:
                value=next(iter(labels.values()))
            elif slot=='structural_content_role' and ':' in value:
                role,attitude=value.split(':',1)
                value=next((label for label in labels.values()
                    if label.startswith(role+' of ') and 'attitude='+attitude in label),value)
        number=mapping.get(value) or next((n for n,label in labels.items()
            if label.startswith(value) or label.startswith('An additional relation INSIDE the target words: '+value)),None)
        if number:
            self.steps.popleft();self.selected_slot=slot;return number
        return '0' if slot.startswith('structural_') else self.default


def run(tmp_path,monkeypatch,text,steps,kind='ASSERTION',default='1',observer_contract='v7-observer-1',raw_extra=None):
    script=Script(steps,default)
    monkeypatch.setattr(ChatBackend,'generate',lambda self,prompt,**kw:script.generate(prompt,**kw))
    payload={'raw_input':{'text':text,'source_id':'structural-task-test','revision':1,
        'range':[0,len(text)],'language':'ru','request_kind':kind,'batch_kind':'MESSAGE',**(raw_extra or {})}}
    session=Session([payload],tmp_path/'journal.log');session.observer_contract=observer_contract
    result=execute_native(session,payload,
        {'provider':'lmstudio','model':'scripted-source-selection','structure_mode':'region_probes'})
    assert not script.errors,script.errors
    assert not script.steps,list(script.steps)
    return result,script


def relation(kind):return [('structural_relation',kind)]


def bounds(slot,first,last):
    return [(slot+'_start','Start at «'+first+'»'),(slot+'_end','End after «'+last+'»')]


def binary(kind,left,right):
    return relation(kind)+bounds('structural_operand_1',*left)+bounds('structural_operand_2',*right)+[
        ('structural_partition','PARTITION')]+relation('LEXICAL')+relation('LEXICAL')


def unary(kind,first,last):
    return relation(kind)+bounds('structural_introducer',first,last)+[('structural_partition','PARTITION')]


def atom(predicate,person):return {'predicate':predicate,'roles':{'AGENT':{'entity':person}}}


@pytest.mark.parametrize('text,operator,left,right',[
    ('Если Иван пришёл, то Мария спит.','IMPLIES',('Иван','пришёл'),('Мария','спит')),
    ('Мария спит только если Иван пришёл.','IMPLIES',('Мария','спит'),('Иван','пришёл')),
    ('Если бы Иван пришёл, Мария бы спала.','COUNTERFACTUAL',('Иван','пришёл'),('Мария','спала')),
    ('Иван пришёл или Мария спит.','OR',('Иван','пришёл'),('Мария','спит')),
    ('Либо Иван пришёл, либо Мария спит.','XOR',('Иван','пришёл'),('Мария','спит')),
    ('Иван пришёл и Мария спит.','AND',('Иван','пришёл'),('Мария','спит')),
])
def test_binary_relation_uses_shared_source_slots(tmp_path,monkeypatch,text,operator,left,right):
    steps=binary(operator,left,right)
    if operator=='COUNTERFACTUAL':steps.insert(5,('structural_function_owner','Outer relation owns «бы»'))
    result,_=run(tmp_path,monkeypatch,text,steps)
    expected=[atom('SLEEP','maria'),atom('ARRIVE','ivan')] if left[0]=='Мария' else [atom('ARRIVE','ivan'),atom('SLEEP','maria')]
    facts=[{'operator':operator,'operands':expected}]
    if operator=='AND':facts+=expected  # ordinary AND elimination is licensed
    assert result['assertions']['ah']==facts
    assert result['diagnostics']['codes']==[]


@pytest.mark.parametrize('text,operator,first,last',[
    ('Неверно, что Иван пришёл.','NOT','Неверно','что'),
    ('Вполне вероятно, что Иван пришёл.','POSSIBLE','Вполне','что'),
    ('Иван не пришёл.','NOT','не','не'),
])
def test_unlisted_unary_phrases_reach_same_compiler(tmp_path,monkeypatch,text,operator,first,last):
    steps=unary(operator,first,last)+relation('LEXICAL')
    result,_=run(tmp_path,monkeypatch,text,steps)
    assert result['assertions']['ah']==[{'operator':operator,'operands':[atom('ARRIVE','ivan')]}]
    assert result['diagnostics']['codes']==[]


@pytest.mark.parametrize('verb',['сказал','сообщил','предположил'])
def test_proposition_owner_does_not_require_a_lemma_whitelist(tmp_path,monkeypatch,verb):
    text='Иван '+verb+', что Пётр пришёл.'
    steps=relation('CONTENT')+bounds('structural_content','Пётр','пришёл')+bounds('structural_parent','Иван',verb)+[
        ('structural_owner','Content belongs to predicate «'+verb+'»'),('structural_partition','PARTITION'),
        ('structural_content_role','OBJECT:'+('HYPOTHETICAL' if verb=='предположил' else 'QUOTED'))]+relation('LEXICAL')+relation('LEXICAL')
    result,_=run(tmp_path,monkeypatch,text,steps)
    facts=result['assertions']['ah']
    assert len(facts)==1 and facts[0].get('predicate')!='ARRIVE'
    assert atom('ARRIVE','petr') in facts[0]['roles'].values()
    assert result['diagnostics']['codes']==[]


def content_steps(owner,first,last,parent_first='Иван',attitude='QUOTED'):
    return relation('CONTENT')+bounds('structural_content',first,last)+bounds('structural_parent',parent_first,owner)+[
        ('structural_owner','Content belongs to predicate «'+owner+'»'),('structural_partition','PARTITION'),
        ('structural_content_role','OBJECT:'+attitude)]+relation('LEXICAL')


def test_content_introducer_inside_provisional_body(tmp_path,monkeypatch):
    steps=relation('CONTENT')+bounds('structural_content','что','пришла')+bounds('structural_parent','Иван','сказал')+[
        ('structural_owner','Content belongs to predicate «сказал»'),
        ('structural_function_owner','Outer relation owns «что»'),
        ('structural_partition','PARTITION'),('structural_content_role','OBJECT:QUOTED')]+relation('LEXICAL')
    steps+=relation('NOT')+bounds('structural_introducer','не','не')+[('structural_partition','PARTITION')]+relation('LEXICAL')
    result,script=run(tmp_path,monkeypatch,'Иван сказал что Мария не пришла.',steps)
    assert not result['diagnostics']['codes']
    assert result['assertions']['ah']==[{'predicate':'SAY','roles':{'AGENT':{'entity':'ivan'},
        'CONTENT':{'operator':'NOT','operands':[atom('ARRIVE','maria')]}}}]
    question=next(p for s,p in script.calls if s=='structural_function_owner')
    options=re.findall(r'^\d+\. (.*)$',question,re.M)
    assert any('«что»' in o for o in options) and any('«не»' in o for o in options)
    assert not any(o.startswith('Outer relation owns «сказал»') for o in options)


@pytest.mark.parametrize('quoted',[False,True])
def test_recursive_propositions_and_quotes(tmp_path,monkeypatch,quoted):
    from ah.formalizer import component_probe
    probe=component_probe._probe;sealed=[]
    def checked(state,selector,release,key,slot,*args,**kwargs):
        if slot=='predicate_value':
            assert state.structural_closed
            sealed.append(key)
        return probe(state,selector,release,key,slot,*args,**kwargs)
    monkeypatch.setattr(component_probe,'_probe',checked)
    text='Иван сказал'+(': «' if quoted else ', что ')+'Пётр думал, что Мария пришла'+('».' if quoted else '.')
    steps=content_steps('сказал','Пётр','пришла')+content_steps('думал','Мария','пришла','Пётр','EMBEDDED')+relation('LEXICAL')
    result,script=run(tmp_path,monkeypatch,text,steps)
    assert result['diagnostics']['codes']==[]
    assert result['assertions']['ah']==[{'predicate':'SAY','roles':{'AGENT':{'entity':'ivan'},
        'CONTENT':{'predicate':'THINK','roles':{'AGENT':{'entity':'petr'},'CONTENT':atom('ARRIVE','maria')}}}}]

    assert len(sealed)==3
    partitions=[v for row in result['runtime']['ir']['syntax_trace']
        if row.get('kind')=='STRUCTURAL_TASK' and row.get('slot')=='structural_partition'
        for v in row.get('alternatives',()) if v.get('relation')=='CONTENT']
    assert partitions  # A page and its domain may both expose the same payload.
    assert all(p['owner_ref'] in p['operands'][0] and p['owner_proof']['decision_ref'] for p in partitions)
    assert len({p['owner_ref'] for p in partitions})==2
    assert all('selected content fills the slot of predicate' in p['label'] for p in partitions)
    calls=[s for s,p in script.calls]
    assert max(i for i,s in enumerate(calls) if s.startswith('structural_'))<calls.index('predicate_value')
    prompt=next(p for s,p in script.calls if s=='speech_act')
    assert text in prompt and 'separately parsed' in prompt


def test_inner_content_can_be_separated_before_its_ancestor(tmp_path,monkeypatch):
    text='Иван сказал, что Пётр думал, что Мария пришла.'
    # The first split leaves THINK's content open inside the still nested parent.
    steps=content_steps('думал','Мария','пришла',attitude='EMBEDDED')[:-1]
    steps.insert(6,('structural_function_owner','KEEP_ALL'))
    steps+=content_steps('сказал','Пётр','думал')+relation('LEXICAL')+relation('LEXICAL')
    result,script=run(tmp_path,monkeypatch,text,steps)
    assert result['diagnostics']['codes']==[]
    assert result['assertions']['ah']==[{'predicate':'SAY','roles':{'AGENT':{'entity':'ivan'},
        'CONTENT':{'predicate':'THINK','roles':{'AGENT':{'entity':'petr'},'CONTENT':atom('ARRIVE','maria')}}}}]
    prompts=[p for s,p in script.calls if s=='structural_relation']
    assert 'Only «думал»' in prompts[1] and 'Only «сказал»' not in prompts[1]
    assert 'Only «сказал»' in prompts[2] and 'Only «думал»' not in prompts[2]
    assert 'Only «думал»' in prompts[3] and 'Only «сказал»' not in prompts[3]


def test_nested_same_modal_relation_stays_selectable(tmp_path,monkeypatch):
    steps=unary('POSSIBLE','Возможно',',')+[('structural_governor','INDEPENDENT')]
    steps+=unary('POSSIBLE','может','может')+[('structural_governor','Agreement/controller anchor «может»')]+relation('LEXICAL')
    result,script=run(tmp_path,monkeypatch,'Возможно, Иван может прийти.',steps)
    assert result['diagnostics']['codes']==[]
    assert result['assertions']['ah']==[{'operator':'POSSIBLE','operands':[
        {'operator':'POSSIBLE','operands':[atom('ARRIVE','ivan')]}]}]
    prompts=[p for s,p in script.calls if s=='structural_relation']
    assert 'An additional relation INSIDE the target words: Possibility' in prompts[1]


def test_infinitive_producer_remains_available_inside_reported_content(tmp_path,monkeypatch):
    steps=content_steps('сказал','Мария','книгу')+relation('LEXICAL')+[
        ('component_attachment','Infinitive area «читать книгу»')]+relation('LEXICAL')+[
        ('component_attachment','«читать» fills OBJECT')]+relation('LEXICAL')
    result,script=run(tmp_path,monkeypatch,'Иван сказал: «Мария хочет читать книгу».',steps)
    assert result['diagnostics']['codes']==[]
    assert result['assertions']['ah']==[{'predicate':'SAY','roles':{'AGENT':{'entity':'ivan'},
        'CONTENT':{'predicate':'WANT','roles':{'EXPERIENCER':{'entity':'maria'},'CONTENT':{
            'predicate':'READ','roles':{'AGENT':{'entity':'maria'},'THEME':{'entity':'book'}}}}}}}]
    assert any('what the parent predicate is about' in p for s,p in script.calls if s=='component_attachment')


def test_modal_control_inside_modal(tmp_path,monkeypatch):
    steps=unary('POSSIBLE','может','может')+[('structural_governor','Agreement/controller anchor «может»')]+content_steps(
        'хотеть','читать','книгу',attitude='HYPOTHETICAL')+[
        ('structural_control','Same')]+relation('LEXICAL')
    result,_=run(tmp_path,monkeypatch,'Иван может хотеть читать книгу.',steps)
    assert result['diagnostics']['codes']==[]
    assert len(result['assertions']['ah'])==1
    assert result['assertions']['ah'][0]['operator']=='POSSIBLE'


def test_relative_clause_is_quantifier_restriction(tmp_path,monkeypatch):
    text='Каждый студент, который прочитал книгу, может сдать экзамен.'
    steps=relation('FORALL')+bounds('structural_quantifier','Каждый','Каждый')+[
        ('structural_partition','PARTITION'),('structural_binder_head','Bind the nominal «студент»')]+unary('POSSIBLE','может','может')+[
        ('structural_governor','Agreement/controller anchor «может»')]+relation('NOMINAL_DESCRIPTION')+bounds('structural_description','который','книгу')+[
        ('structural_description_binding','An explicit relative expression'),('structural_description_marker','«который»')]+relation('LEXICAL')+relation('LEXICAL')
    result,_=run(tmp_path,monkeypatch,text,steps)
    assert result['diagnostics']['codes']==[]
    assert len(result['assertions']['ah'])==1 and result['assertions']['ah'][0]['operator']=='FORALL'
    frames=result['runtime']['ir']['frames']
    restrictions=[f for f in frames if f['semantic'].get('quantifier_restriction')]
    assert len(restrictions)==1 and restrictions[0]['semantic'].get('quantifier_description_refs')
    assert result['assertions']['ah'][0]['operands'][1]['operands'][0]['operator']=='AND'


@pytest.mark.parametrize('text,kind,left,right',[
    ('Иван пришёл прежде, чем Мария уснула.','BEFORE',('Иван','пришёл'),('Мария','уснула')),
    ('Мария спит после прихода Ивана.','AFTER',('Мария','спит'),('прихода','Ивана')),
])
def test_temporal_relations_accept_finite_and_nominal_children(tmp_path,monkeypatch,text,kind,left,right):
    steps=binary(kind,left,right)
    if right[0]=='прихода':steps[-1:]=[('structural_event_head','Nominal event head «прихода»')]
    result,_=run(tmp_path,monkeypatch,text,steps)
    assert result['diagnostics']['codes']==[]
    assert result['assertions']['ah'] and result['assertions']['ah'][0]['operator']==kind


def test_oov_role_is_explicitly_licensed(tmp_path,monkeypatch):
    steps=[('structural_oov_function','noun:')]+relation('LEXICAL')
    result,_=run(tmp_path,monkeypatch,'Флырка пришла.',steps)
    assert result['diagnostics']['codes']==['OOV_KEEP_AS_IS']
    assert result['assertions']['ah'] and result['assertions']['ah'][0]['predicate']=='ARRIVE'


def test_quantified_modal_has_indivisible_coordinated_body(tmp_path,monkeypatch):
    text='Каждый студент может читать книгу и спать.'
    steps=relation('FORALL')+bounds('structural_quantifier','Каждый','Каждый')+[
        ('structural_partition','PARTITION'),('structural_binder_head','Bind the nominal «студент»')]+unary('POSSIBLE','может','может')+[
        ('structural_governor','Agreement/controller anchor «может»')]+binary('AND',('студент','книгу'),('спать','спать'))+[
        ('implicit_argument','Same bound variable')]
    result,_=run(tmp_path,monkeypatch,text,steps)
    assert result['diagnostics']['codes']==[]
    assert len(result['assertions']['ah'])==1
    formula=result['assertions']['ah'][0]
    assert formula['operator']=='FORALL'
    body=formula['operands'][1]['operands'][1]
    assert body['operator']=='POSSIBLE' and body['operands'][0]['operator']=='AND'
    assert all(atom['roles']['AGENT']=={'bound_var':'x'} for atom in body['operands'][0]['operands'])


def test_nested_modals_share_adjectival_agreement_governor(tmp_path,monkeypatch):
    steps=unary('NECESSARY','должен','должен')+[
        ('structural_governor','Agreement/controller anchor «должен»')]+unary('POSSIBLE','мочь','мочь')+relation('LEXICAL')
    result,_=run(tmp_path,monkeypatch,'Иван должен мочь читать книгу.',steps)
    assert result['diagnostics']['codes']==[]
    facts=result['assertions']['ah']
    assert len(facts)==1 and facts[0]['operator']=='NECESSARY'
    assert facts[0]['operands'][0]['operator']=='POSSIBLE'


def test_arithmetic_quantifier_remains_deferred(tmp_path,monkeypatch):
    result,_=run(tmp_path,monkeypatch,'Два студента читают книгу.',
        relation('EXISTS')+bounds('structural_quantifier','Два','Два'))
    assert result['assertions']['ah']==[]
    assert 'ARITHMETIC_QUANTIFIER_DEFERRED' in result['diagnostics']['codes']


def test_unlisted_owner_after_content_uses_same_contract(tmp_path,monkeypatch):
    steps=relation('CONTENT')+bounds('structural_content','Пётр','пришёл')+bounds('structural_parent','сообщил','Иван')+[
        ('structural_owner','Content belongs to predicate «сообщил»'),('structural_partition','PARTITION'),
        ('structural_content_role','OBJECT:QUOTED')]+relation('LEXICAL')+relation('LEXICAL')
    result,_=run(tmp_path,monkeypatch,'Пётр пришёл, как сообщил Иван.',steps)
    assert result['diagnostics']['codes']==[]
    assert len(result['assertions']['ah'])==1 and result['assertions']['ah'][0]['predicate']!='ARRIVE'


def test_all_producers_remain_reachable_for_complete_grammar(tmp_path,monkeypatch):
    result,script=run(tmp_path,monkeypatch,'Иван пришёл.',relation('LEXICAL'))
    traces=result['runtime']['ir']['syntax_trace']
    both=[r for r in traces if r.get('kind')=='COMPOSITION_PRODUCERS']
    assert both and all(x['frames'] for x in both[-1]['sources'])
    assert not any(slot=='child_slot' for slot,_ in script.calls)
    equal=[r for r in traces if r.get('kind')=='COMPOSITION_EQUIVALENT_SOURCES']
    assert equal and {s['source'] for s in equal[-1]['sources']}=={'GRAMMAR','COMPONENT'}
    assert result['assertions']['ah']==[atom('ARRIVE','ivan')]


def test_unimplemented_partition_does_not_reinterpret_the_source(tmp_path,monkeypatch):
    steps=binary('OR',('Иван','пришёл'),('Мария','спит'))[:5]+[('structural_partition','0')]
    result,script=run(tmp_path,monkeypatch,'Иван пришёл при условии, что Мария спит.',steps)
    assert result['assertions']['ah']==[]
    assert not any(slot=='structural_revision' for slot,_ in script.calls)
    assert result['diagnostics']['codes']


def test_description_can_precede_its_nominal_host(tmp_path,monkeypatch):
    steps=relation('NOMINAL_DESCRIPTION')+bounds('structural_description','Прочитавший','книгу')+[
        ('structural_description_binding','The nominal host fills')]+relation('LEXICAL')+[
        ('structural_description_role','SUBJECT')]+relation('LEXICAL')
    result,_=run(tmp_path,monkeypatch,'Прочитавший книгу студент спит.',steps)
    assert result['diagnostics']['codes']==[]
    traces=result['runtime']['ir']['syntax_trace']
    refinements=[r for r in traces if r.get('kind')=='NOMINAL_REFINEMENT']
    assert refinements
    assert len(result['assertions']['ah'])==1 and result['assertions']['ah'][0]['predicate']=='SLEEP'


def test_oov_verb_keeps_surface_instead_of_guessing_known_sense(tmp_path,monkeypatch):
    steps=[('structural_oov_function','finite verb:')]+relation('LEXICAL')
    result,_=run(tmp_path,monkeypatch,'Иван флыркает.',steps)
    assert result['diagnostics']['codes']==['OOV_KEEP_AS_IS']
    assert len(result['assertions']['ah'])==1
    assert 'флыркает' in result['assertions']['ah'][0]['predicate']


@pytest.mark.parametrize('answer',['?','0','ONE_SELECTED'])
def test_unresolved_outer_task_never_asserts_a_child(tmp_path,monkeypatch,answer):
    result,_=run(tmp_path,monkeypatch,'Иван сообщил, что Пётр пришёл.',relation(answer))
    assert result['assertions']['ah']==[]
    assert 'STRUCTURAL_TASK_UNRESOLVED' in result['diagnostics']['codes']


def test_parenthesized_relation_reaches_child_tasks(tmp_path,monkeypatch):
    steps=relation('GROUP')+bounds('structural_group','Иван','спит')+[
        ('structural_partition','PARTITION')]+binary('OR',('Иван','пришёл'),('Мария','спит'))
    result,_=run(tmp_path,monkeypatch,'(Иван пришёл или Мария спит).',steps)
    assert result['diagnostics']['codes']==[]
    assert result['assertions']['ah']==[{'operator':'OR','operands':[atom('ARRIVE','ivan'),atom('SLEEP','maria')]}]


def test_confirmed_child_does_not_escape_unresolved_sibling(tmp_path,monkeypatch):
    steps=binary('IMPLIES',('Иван','пришёл'),('Мария','спит'))
    steps[-1]=('structural_relation','?')
    steps.append(('structural_relation','?'))  # one retry with new parent context
    result,_=run(tmp_path,monkeypatch,'Если Иван пришёл, то Мария спит.',steps)
    assert result['assertions']['ah']==[]


def test_query_wrapper_preserves_question_scope(tmp_path,monkeypatch):
    result,_=run(tmp_path,monkeypatch,'Верно ли, что Иван пришёл?',
        unary('QUERY','Верно','что')+relation('LEXICAL'),kind='QUERY')
    assert result['assertions']['ah']==[]
    assert 'STRUCTURE_NOT_COVERED' not in result['diagnostics']['codes']


@pytest.mark.parametrize('marker,operator',[('Каждый','FORALL'),('Любой','FORALL'),('Некоторый','EXISTS')])
def test_nonnumeric_binders_without_keyword_admission(tmp_path,monkeypatch,marker,operator):
    steps=relation(operator)+bounds('structural_quantifier',marker,marker)+[
        ('structural_partition','PARTITION'),('structural_binder_head','Bind the nominal «студент»')]+relation('LEXICAL')
    result,_=run(tmp_path,monkeypatch,marker+' студент читает книгу.',steps)
    assert result['assertions']['ah'] and result['assertions']['ah'][0]['operator']==operator
    assert result['diagnostics']['codes']==[]
