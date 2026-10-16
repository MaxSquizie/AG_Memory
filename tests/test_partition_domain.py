"""Conditional ownership propagation, with real frontend/dispatcher/commit gates.

Scripted replies verify the contour, not the accuracy of a local LLM.
"""
import pytest
from test_structural_relation_tasks import run,relation,bounds,unary,binary,atom,content_steps


def trace(result):return result['runtime']['ir']['syntax_trace']


def test_query_repair_keeps_question_status_and_records_dispatch_dependency(tmp_path,monkeypatch):
    steps=relation('QUERY')+bounds('structural_introducer','что','вошёл')+[
        ('relation_marker_role','«Пётр»')]+bounds('structural_introducer','Верно','что')+[
        ('structural_partition','PARTITION')]+relation('LEXICAL')
    result,script=run(tmp_path,monkeypatch,'Верно ли, что Пётр вошёл?',steps,kind='QUERY')
    assert result['diagnostics']['codes']==['SPEECH_ACT_QUERY']
    assert not result['assertions']['ah'] and not result['assertions']['journal']
    assert result['generation']['observed_candidate_patterns'][0]==atom('ENTER','petr')
    rows=trace(result)
    conflict=next(r for r in rows if r.get('kind')=='STRUCTURAL_PARTITION_COVERAGE')
    assert conflict['status']=='REPAIRED' and conflict['replacement_decision_ref']
    changed=[r for r in rows if r.get('kind')=='DISPATCH_INVALIDATED' and r.get('task_kind')=='PARTITION']
    assert len(changed)==1
    key=changed[0]['task_ref']
    assert any(d.get('task_ref')==key and d.get('revision')==2 for r in rows
               if r.get('kind')=='DISPATCH_COMPLETED' for d in r.get('dependencies',()))
    assert not any(s=='structural_revision' for s,_ in script.calls)


@pytest.mark.parametrize('marker,kind',[('Каждый','FORALL'),('Некоторый','EXISTS')])
def test_quantifier_repair_preserves_restriction_and_whole_body(tmp_path,monkeypatch,marker,kind):
    steps=relation(kind)+bounds('structural_quantifier',marker,'студент')+[
        ('relation_marker_role','RELATION_ONLY'),('relation_marker_role','«студент»')]
    steps+=bounds('structural_quantifier',marker,marker)+[
        ('structural_partition','PARTITION'),('structural_binder_head','Bind the nominal «студент»')]+relation('LEXICAL')
    result,_=run(tmp_path,monkeypatch,marker+' студент читает книгу.',steps)
    assert result['diagnostics']['codes']==[]
    assert len(result['assertions']['ah'])==1
    formula=result['assertions']['ah'][0]
    assert formula['operator']==kind
    body=next(p for p in formula['operands'][1]['operands'] if p.get('predicate')=='READ')
    assert body['predicate']=='READ' and body['roles']['AGENT']=={'bound_var':'x'}


def test_binary_repair_does_not_choose_a_side_for_the_missing_participant(tmp_path,monkeypatch):
    steps=relation('AND')+bounds('structural_operand_1','пришёл','пришёл')+bounds('structural_operand_2','Мария','спит')+[
        ('relation_marker_role','«Иван»')]
    steps+=bounds('structural_operand_1','Иван','пришёл')+bounds('structural_operand_2','Мария','спит')+[
        ('structural_partition','PARTITION')]+relation('LEXICAL')+relation('LEXICAL')
    result,script=run(tmp_path,monkeypatch,'Иван пришёл и Мария спит.',steps)
    assert result['diagnostics']['codes']==[]
    assert result['assertions']['ah'][0]=={'operator':'AND','operands':[atom('ARRIVE','ivan'),atom('SLEEP','maria')]}
    second=[p for s,p in script.calls if s=='structural_operand_1_start'][1]
    assert 'Start at «Мария»' in second and 'Start at «Иван»' in second


def test_multiple_conflicts_shrink_one_domain_without_reclassifying_relation(tmp_path,monkeypatch):
    steps=relation('NOT')+bounds('structural_introducer','Иван','прочитал')+[
        ('relation_marker_role','«Иван»')]+bounds('structural_introducer','не','прочитал')+[
        ('relation_marker_role','«прочитал»')]+bounds('structural_introducer','не','не')+[
        ('structural_partition','PARTITION')]+relation('LEXICAL')
    result,script=run(tmp_path,monkeypatch,'Иван не прочитал книгу.',steps)
    assert result['diagnostics']['codes']==[]
    assert result['assertions']['ah'][0]['operator']=='NOT'
    assert result['assertions']['ah'][0]['operands'][0]['predicate']=='READ'
    restricted=[r for r in trace(result) if r.get('kind')=='STRUCTURAL_BOUNDARY_DOMAIN' and r.get('status')=='RESTRICTED']
    assert [len(r['required_content_refs']) for r in restricted]==[1,2]
    assert len([p for s,p in script.calls if s=='structural_relation'])==2  # NOT, then lexical child


@pytest.mark.parametrize('answer',['?','ONE_SELECTED'])
def test_unknown_or_malformed_marker_reply_creates_no_constraint_or_retry(tmp_path,monkeypatch,answer):
    steps=relation('NOT')+bounds('structural_introducer','не','прочитал')+[('relation_marker_role',answer)]
    result,script=run(tmp_path,monkeypatch,'Иван не прочитал книгу.',steps)
    assert not result['assertions']['journal']
    assert not any(r.get('kind')=='STRUCTURAL_BOUNDARY_DOMAIN' and r.get('required_content_refs') for r in trace(result))
    assert len([s for s,_ in script.calls if s=='structural_introducer_start'])==1


def test_constraint_does_not_leak_into_a_nested_modal_with_lexical_wording(tmp_path,monkeypatch):
    steps=relation('NOT')+bounds('structural_introducer','Неверно','предположить')+[
        ('relation_marker_role','«предположить»')]+bounds('structural_introducer','Неверно','что')+[
        ('structural_partition','PARTITION')]+relation('POSSIBLE')+bounds('structural_introducer','можно',':')+[
        ('relation_marker_role','RELATION_ONLY'),('relation_marker_role','RELATION_ONLY'),
        ('structural_partition','PARTITION')]+relation('LEXICAL')
    result,script=run(tmp_path,monkeypatch,'Неверно, что можно предположить: Иван пришёл.',steps)
    assert result['diagnostics']['codes']==[]
    assert result['assertions']['ah']==[{'operator':'NOT','operands':[{'operator':'POSSIBLE','operands':[atom('ARRIVE','ivan')]}]}]
    child=[p for s,p in script.calls if s=='structural_introducer_start'][-1]
    assert 'local ownership check' not in child


def test_exhausted_boundary_does_not_reclassify_the_relation_without_evidence(tmp_path,monkeypatch):
    steps=relation('NOT')+bounds('structural_introducer','Можно',':')+[
        ('relation_marker_role','«предположить»'),('structural_introducer_start','0')]
    result,script=run(tmp_path,monkeypatch,'Можно предположить: Иван пришёл.',steps)
    assert not result['assertions']['ah'] and not result['assertions']['journal']
    assert len([s for s,p in script.calls if s=='structural_relation'])==1
    assert not any(s=='structural_revision' for s,p in script.calls)


def test_gui_explains_conditional_constraint_and_repaired_conflict():
    from test_formalization_readable import sample
    from ah.gui.formalization_inspection import Inspection
    from ah.gui.formalization_readable import ReadableInspection
    data=sample();data['state']['syntax_trace']=[
        {'kind':'STRUCTURAL_BOUNDARY_DOMAIN','relation':'NOT','status':'RESTRICTED',
         'required_content_refs':['read'],'constraint_proofs':[{'decision_ref':'gap'}]},
        {'kind':'STRUCTURAL_PARTITION_COVERAGE','relation':'NOT','uncovered_token_refs':['read'],
         'status':'REPAIRED','replacement_decision_ref':'gap'}]
    idx=Inspection(data);reader=ReadableInspection(idx)
    html=reader.explain(idx.by_ref['trace:0'])
    assert '«читает» должны остаться в содержании' in html
    assert 'не переносится в другую область или связь' in html
    assert 'Почему слово должно остаться' in html and 'required_content_refs' not in html
    assert 'противоречие прежнего разбиения устранено' in reader.explain(idx.by_ref['trace:1'])


def test_pending_partition_is_cached_but_parent_feedback_reopens_it():
    from test_composition_dispatcher import setup_morphology,First
    from ah.formalizer.composition_session import session
    from ah.formalizer.partition_domain import PartitionDomain,PartitionProposal
    from ah.formalizer.structural_tasks import choose
    state,release,region,cfg=setup_morphology('Иван пришёл.')
    selector=First('?')
    proof={'decision_ref':'outer','candidate_id':'NOT'}
    def propose(domain):
        selected=choose(state,release,selector,region,cfg,'test_partition_input',
            [{'candidate_id':'keep','label':'Keep the clause'}],'Keep this clause as content?')
        return PartitionProposal([list(state.evidence)]) if selected else None
    with session(state,release,selector=selector) as runtime,runtime.area(region,state.evidence,None):
        def resolve():return PartitionDomain(state,release,selector,region,state.evidence,cfg,'NOT',proof).resolve(propose)
        assert resolve() is None
        reads={'probes':set(),'blocked':False};runtime.tasks.reads.append(reads)
        try:assert resolve() is None
        finally:runtime.tasks.reads.pop()
        assert len(selector.prompts)==1 and len(reads['probes'])==1
        runtime.tasks.feedback={'contract':'Propositional argument','context':'The surrounding predicate supplies this slot.'}
        selector.answer='1'
        assert resolve() is not None
        assert len(selector.prompts)==3  # changed local task, then partition check
        assert 'The surrounding predicate supplies this slot.' in selector.prompts[1]


def test_same_source_in_distinct_typed_slots_keeps_independent_partition_tasks():
    from test_composition_dispatcher import setup_morphology,First
    from ah.formalizer.composition_session import session
    from ah.formalizer.composition_tree import InputSlot
    from ah.formalizer.partition_domain import PartitionDomain,PartitionProposal
    state,release,region,cfg=setup_morphology('Иван пришёл.')
    selector=First();proof={'decision_ref':'outer','candidate_id':'NOT'}
    with session(state,release,selector=selector) as runtime:
        for request in (InputSlot(),InputSlot(inside_attitude=True)):
            with runtime.area(region,state.evidence,request):
                domain=PartitionDomain(state,release,selector,region,state.evidence,cfg,'NOT',proof)
                assert domain.resolve(lambda d:PartitionProposal([list(state.evidence)]))
        nodes=[key for key,value in runtime.dispatcher.nodes.items() if value['kind']=='PARTITION']
        assert len(nodes)==2 and all(runtime.dispatcher.valid(key) for key in nodes)


@pytest.mark.parametrize('contiguous',[False,True])
def test_lookahead_keeps_exactly_the_completable_two_part_boundaries(monkeypatch,contiguous):
    # Exhaustive five-token topology: content before AND after the first part.
    # CONTENT compacts the remaining parent; binary operands cannot cross it.
    from types import SimpleNamespace
    from ah.formalizer.partition_domain import PartitionDomain,ContentRequired
    from ah.formalizer import structural_tasks
    tokens=[SimpleNamespace(token_id=str(i),span=str(i),start=i,end=i+1) for i in range(5)]
    state=SimpleNamespace(syntax_trace=[],diag=lambda *args:None)
    region=SimpleNamespace(region_id='topology',source_range=(0,5))
    domain=PartitionDomain(state,None,None,region,tokens,{},'CONTENT',{})
    domain.constraints=[ContentRequired(('0','4'),'test')]
    wanted=[]
    def choose(*args,empty=None):
        if not wanted:return (empty,{}) if empty is not None else None
        options=list(args[-2]);candidate=wanted.pop(0)
        found=next((v for v in options if v['candidate_id']==candidate),None)
        if found:return found,{}
        state.syntax_trace.append({'status':'PENDING'})
    monkeypatch.setattr(structural_tasks,'choose',choose)
    intervals=[tuple(range(a,b+1)) for a in range(5) for b in range(a,5)]
    expected=set()
    for first in intervals:
        rest=[i for i in range(5) if i not in first]
        seconds=intervals if contiguous else [tuple(rest[a:b+1]) for a in range(len(rest)) for b in range(a,len(rest))]
        if any(not set(first)&set(second) and {0,4}<=set(first)|set(second) for second in seconds):
            expected.add(first)
    actual=set()
    for part in intervals:
        wanted[:]=['start:'+str(part[0]),'end:'+str(part[-1])]
        chosen=domain.span(tokens,'test','Select content.',remaining_parts=1,remaining_contiguous=contiguous)
        if chosen:actual.add(tuple(int(t.token_id) for t in chosen[0]))
    assert actual==expected
