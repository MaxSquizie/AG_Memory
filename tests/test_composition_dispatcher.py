"""Dependency changes, real morphology and final materialization contracts."""
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace

import pytest

from ah.formalizer.pipeline import t0,MorphProvider,t1
from ah.formalizer.composition_dispatcher import Dispatcher,DispatchBlocked
from ah.formalizer.composition_tree import InputSlot


def test_transitive_invalidation_retains_independent_branch_and_pending_result():
    state=t0('source');d=Dispatcher(state);calls=[];inputs={'form':'nom'}
    def run(key,value,fn):
        return d.run(key,value,lambda:calls.append(key) or fn(),kind=key)
    def morphology():return run('morph',inputs['form'],lambda:inputs['form'])
    def grammar():return run('grammar',None,morphology)
    def other():return run('unresolved',None,lambda:None)
    def parent():return run('parent',None,lambda:(grammar(),other()))
    assert parent()==('nom',None)
    assert parent()==('nom',None) and calls==['parent','grammar','morph','unresolved']
    inputs['form']='dat';assert morphology()=='dat'
    assert not d.valid('grammar') and not d.valid('parent') and d.valid('unresolved')
    assert parent()==('dat',None)
    assert calls.count('unresolved')==1 and calls.count('grammar')==2


def test_version_change_mid_computation_cannot_publish_mixed_dependencies():
    d=Dispatcher(t0('source'));value=['old'];calls=[]
    def child():return d.run('m',value[0],lambda:value[0],kind='MORPHOLOGY')
    def parent():
        old=child();calls.append(old)
        if old=='old':
            value[0]='new';child()
        return old
    # Both reads must not hide an earlier consumption of the older version.
    result=d.run('p',None,parent,kind='COMPOSITION')
    assert result=='new' and calls==['old','new']


def test_cycle_and_budget_block_without_a_cached_result():
    d=Dispatcher(t0('source'))
    with pytest.raises(DispatchBlocked,match='CYCLE'):
        d.run('a',None,lambda:d.run('a',None,lambda:1,kind='MORPHOLOGY'),kind='COMPOSITION')
    assert not d.valid('a')
    d=Dispatcher(t0('source'),limit=1)
    with pytest.raises(DispatchBlocked,match='INCOMPLETE'):
        d.run('a',None,lambda:d.run('b',None,lambda:1,kind='MORPHOLOGY'),kind='COMPOSITION')
    assert not d.valid('a')


def test_resolved_probe_rechecks_changed_parent_and_retains_exact_attempt():
    from ah.formalizer.component_probe import _probe
    from ah.formalizer.composition_session import session
    class Release:
        sha256='test'
        def entries(self,kind):return [{'composition':{'max_candidates':8,'context_chars':1000}}] if kind=='ProposalPolicy' else []
    class Selector:
        selection_reply_format='SELECT_LABELS_V1'
        def __init__(self):self.prompts=[]
        def select(self,p):self.prompts.append(p);return str(len(self.prompts))
    state=t0('source');state.budget.llm_limit=10;selector=Selector()
    options=[{'candidate_id':'a','label':'nominative'},{'candidate_id':'b','label':'dative'}]
    with session(state,Release()) as runtime:
        def probe():return _probe(state,selector,Release(),'same-key','test',options,'source',(0,6))
        assert probe()==probe()=='a' and len(selector.prompts)==1
        runtime.tasks.feedback={'parent_ref':'p','contract':'dative argument','context':'A new governor requires dative.'}
        assert probe()==probe()=='b' and len(selector.prompts)==2
        assert 'A new governor requires dative' in selector.prompts[-1]
    assert state.component_probe_records['same-key']['attempts'][0]['decision']['selected']==('a',)


def setup_morphology(text):
    from tools.formalizer_v7_native_binding import fixture
    from tools.formalizer_component_fixture import with_full_composition
    from ah.core import AHCore
    from ah.formalizer.regions import build_regions
    core=AHCore();release,_=fixture(core,'known');release=with_full_composition(release,core=core)
    state=t0(text)
    from ah.formalizer.native_frontend import run_srl
    run_srl(state,release,MorphProvider())
    t1(state,morph=MorphProvider(),preserve_variants=True,shared_form_expansion=False)
    state.budget.llm_limit=100
    state.region_forest=build_regions(text,state.evidence,'dispatcher-test')
    region=next(r for r in state.region_forest.regions if r.kind=='SENTENCE')
    from ah.formalizer.component_policy import policy
    return state,release,region,policy(release)


class First:
    selection_reply_format='SELECT_LABELS_V1'
    def __init__(self,answer='1'):self.prompts=[];self.answer=answer
    def select(self,p):self.prompts.append(p);return self.answer


def test_oov_parent_case_change_reopens_domain_without_mutating_source():
    from ah.formalizer.composition_session import session
    from ah.formalizer.composition_morphology import prepare
    state,release,region,cfg=setup_morphology('Иван передал книгу флырке.')
    original=deepcopy(state.evidence);selector=First()
    head=next(t for t in state.evidence if t.span=='флырке')
    with session(state,release,selector=selector) as runtime:
        def resolve(cases):
            slot=InputSlot(head_ref=head.token_id,allowed_cases=frozenset(cases))
            with runtime.area(region,state.evidence,slot):
                return prepare(runtime,region,state.evidence,slot,cfg)
        resolve({'dat'});n=len(selector.prompts)
        resolve({'dat'});assert len(selector.prompts)==n
        resolve({'acc'});assert len(selector.prompts)>n
        assert 'accusative' in selector.prompts[-1]
        assert any(r.get('kind')=='DISPATCH_INVALIDATED' and r['task_kind']=='MORPHOLOGY' for r in state.syntax_trace)
    assert state.evidence==original


def test_agreement_repair_is_scoped_and_retracted_when_head_leaves_area():
    from ah.formalizer.composition_session import session
    from ah.formalizer.composition_morphology import prepare
    state,release,region,cfg=setup_morphology('Красивый книга.')
    original=deepcopy(state.evidence);selector=First('2')
    with session(state,release,selector=selector) as runtime:
        with runtime.area(region,state.evidence,None):
            repaired=prepare(runtime,region,state.evidence,None,cfg)
        assert any(t.lexical_recovery for t in repaired)
        alone=[state.evidence[0]]
        local=replace(region,token_refs=(alone[0].token_id,),source_range=(alone[0].start,alone[0].end))
        with runtime.area(local,alone,None):fresh=prepare(runtime,local,alone,None,cfg)
        assert not fresh[0].lexical_recovery and fresh[0].variants==original[0].variants
    assert state.evidence==original and len(selector.prompts)==1


def test_query_child_receives_handled_outer_relation(tmp_path,monkeypatch):
    from test_structural_relation_tasks import run,unary,relation
    result,script=run(tmp_path,monkeypatch,'Верно ли, что иван вошёл?',
        unary('QUERY','Верно','что')+relation('LEXICAL'),kind='QUERY')
    p=[p for slot,p in script.calls if slot=='structural_relation'][-1]
    assert 'Already handled outside the target: A question' in p
    assert 'target words themselves express it' in p
    assert not result['assertions']['ah']
    assert result['generation']['observed_candidate_patterns'][0]['predicate']=='ENTER'


@pytest.mark.parametrize('producer',['phrase','reference','dependency'])
def test_nominal_producers_recheck_parent_requirements_through_common_cache(producer):
    from ah.formalizer.composition_session import session
    from ah.formalizer.component_nominal_questions import choose
    from ah.formalizer.nominal_reference_groups import project
    state,release,region,cfg=setup_morphology('Море волнует.' if producer=='dependency' else 'Эта книга.')
    selector=First()
    with session(state,release,selector=selector) as runtime:
        def run(slot):
            with runtime.area(region,state.evidence,slot):
                if producer=='phrase':
                    return choose(state,release,selector,region,'same-phrase',[
                        {'candidate_id':'a','label':'First attachment'},
                        {'candidate_id':'b','label':'Second attachment'}],'Which attachment fits?')
                if producer=='dependency':
                    from ah.formalizer.component_dependency_reduction import reduce
                    predicate=state.evidence[1]
                    roles=[{'role_id':'SUBJECT','allowed_cases':['nom']},
                           {'role_id':'OBJECT','allowed_cases':['acc']}]
                    result=reduce(state,release,selector,region,state.evidence,predicate,predicate.variants[0],
                        roles,[state.evidence[0]],{},cfg)
                    return tuple(r[0] for r in result['roots'].values())
                return bool(project(state,release,selector,region,state.evidence,cfg)[1])
        before=run(InputSlot());assert before
        assert run(InputSlot())==before and len(selector.prompts)==1
        selector.answer='2'
        after=run(InputSlot(constraint_signature='new-parent',surrounding_relations=('QUERY',)))
        assert after!=before and len(selector.prompts)==2
        assert 'Already handled outside the target' in selector.prompts[-1]
        assert run(InputSlot(constraint_signature='new-parent',surrounding_relations=('QUERY',)))==after
        assert len(selector.prompts)==2


def test_dispatcher_explanation_is_human_readable():
    from test_formalization_readable import sample,visible
    from ah.gui.formalization_inspection import Inspection
    from ah.gui.formalization_readable import ReadableInspection
    data=sample();data['state']['syntax_trace']=[
        {'kind':'DISPATCH_COMPLETED','task_ref':'morph-hash','task_kind':'MORPHOLOGY','revision':2,'token_refs':['student']},
        {'kind':'DISPATCH_INVALIDATED','task_ref':'opaque-hash','task_kind':'COMPOSITION',
         'reason':'INPUT_CHANGED','changed_task_ref':'morph-hash'},
        {'kind':'DISPATCH_COMPLETED','task_ref':'opaque-hash','task_kind':'COMPOSITION','revision':3,
         'dependencies':[{'task_ref':'morph-hash','revision':2}]}]
    view=Inspection(data);reader=ReadableInspection(view)
    text=visible(reader.explain(view.by_ref['trace:1']))
    assert 'Изменились входы задачи' in text and 'больше не разрешает завершить разбор' in text
    assert 'студент' in text and 'morph-hash' not in text
    text=reader.explain(view.by_ref['trace:2'])
    assert 'review:trace%3A0' in text and 'Использованный результат' in text


def test_oscillating_dependencies_stop_without_guessing():
    d=Dispatcher(t0('source'));value=[False]
    def child():return d.run('m',value[0],lambda:value[0],kind='MORPHOLOGY')
    def parent():
        old=child();value[0]=not value[0];child();return old
    with pytest.raises(DispatchBlocked,match='NO_PROGRESS'):
        d.run('p',None,parent,kind='COMPOSITION')
    assert not d.valid('p') and d.spent<20


def test_new_context_reopens_child_and_probe_but_unchanged_unknown_is_cached(monkeypatch):
    from ah.formalizer.composition_session import session
    from ah.formalizer.component_probe import _probe
    monkeypatch.setattr('ah.formalizer.context_proofs.compile_goals',lambda *args:[])
    class Release:
        sha256='test-context'
        def entries(self,kind):return [{'composition':{'max_candidates':8,'context_chars':1000}}] if kind=='ProposalPolicy' else []
    class Reader:
        def read(self,state,request):return {'rows':[{'label':str(state.context_facts)}]}
    state=t0('source');state.budget.llm_limit=10;state.context_facts=('before',)
    selector=First('?')
    with session(state,Release(),Reader()) as runtime:
        def compute():
            _probe(state,selector,Release(),'key','test',[
                {'candidate_id':'a','label':'first'},{'candidate_id':'b','label':'second'}],'source',(0,6))
            return []
        runtime.child('c',compute);runtime.child('c',compute)
        assert len(selector.prompts)==1
        state.context_facts=('after',)
        runtime.child('c',compute)
        assert len(selector.prompts)==2 and 'after' in selector.prompts[-1]
        assert runtime.dispatcher.nodes['child:c']['revision']==2
        assert any(runtime.dispatcher.nodes[k]['kind']=='GOAL_CONTEXT'
                   for k in runtime.dispatcher.nodes['child:c']['reads'])


def test_real_agreement_repair_reaches_native_memory(tmp_path,monkeypatch):
    from test_structural_relation_tasks import run,relation
    result,_=run(tmp_path,monkeypatch,'Иван читает красивый книгу.',[
        ('lexical_recovery','Explicit inflection correction «красивый» → «красивую»')]+relation('LEXICAL'))
    assert result['assertions']['ah']
    token=next(t for t in result['runtime']['ir']['evidence'] if t['span']=='красивый')
    assert token['lexical_recovery']['surface']=='красивую'
    assert not result['diagnostics']['codes']


def test_changed_reading_reprojects_grammar_even_with_existing_source_candidate():
    from test_formalizer_v7_syntax_fixture import released,grammar
    from tools.formalizer_v7_test_support import role
    from ah.formalizer.composition_session import session
    from ah.formalizer.regions import build_regions
    release=released([('MOVE','перенести','VERB',[role('SUBJECT'),role('OBJECT',('acc',))])])
    state=grammar('Курьер перенёс книгу.',release,MorphProvider())
    state.region_forest=build_regions(state.text,state.evidence,'grammar-revision')
    region=next(r for r in state.region_forest.regions if r.kind=='SENTENCE')
    with session(state,release) as runtime:
        before=runtime.sources.reuse(region,state.evidence,None,None,None)
        assert before
        book=next(t for t in state.evidence if t.span=='книгу')
        # Controlled producer input: a different whole reading of the object.
        tokens=[replace(t,variants=tuple(replace(v,number='plur') for v in t.variants))
                if t.token_id==book.token_id else t for t in state.evidence]
        after=runtime.sources.reuse(region,tokens,None,None,None)
        assert after and all(f.semantic['morph_bindings'][book.token_id]['number']=='plur' for f in after)
        assert any(n['kind']=='GRAMMAR' and n['revision']==2 for n in runtime.dispatcher.nodes.values())
        assert len(state._grammar_chart.items)>1
    assert book.variants[0].number=='sing'


def test_goal_compilation_reads_current_owned_morphology(monkeypatch):
    from ah.formalizer.composition_session import session
    from ah.formalizer.state import MorphVariant
    from ah.formalizer.regions import TextRegion
    state=t0('x y');state.evidence=[];seen=[]
    monkeypatch.setattr('ah.formalizer.context_proofs.compile_goals',
        lambda release,evidence,*args:seen.append([(t.token_id,t.variants[0].lemma) for t in evidence]) or [])
    release=SimpleNamespace(entries=lambda kind:[])
    reader=SimpleNamespace(read=lambda state,req:{'rows':[]})
    owned=SimpleNamespace(token_id='y',start=2,end=3,variants=(MorphVariant('new','NOUN'),))
    region=TextRegion('r','CLAUSE',(0,3),('y',),None)
    with session(state,release,reader) as runtime:
        with runtime.area(region,[owned],None):
            runtime.memory('morph',[{},{}],(0,3),{'max_candidates':8,'context_chars':100})
    assert seen==[[('y','new')]]


def test_parent_feedback_does_not_reask_unchanged_descendant():
    from ah.formalizer.composition_session import session
    from ah.formalizer.component_probe import _probe
    class Release:
        sha256='scoped-feedback'
        def entries(self,kind):return [{'composition':{'max_candidates':8,'context_chars':1000}}] if kind=='ProposalPolicy' else []
    state=t0('source');state.budget.llm_limit=10;selector=First();calls=[]
    with session(state,Release()) as runtime:
        def inner():
            calls.append('inner')
            _probe(state,selector,Release(),'inner-probe','test',[{'candidate_id':'a','label':'reading'}],'source',(0,6))
            return [SimpleNamespace(frame_id='f',semantic={})]
        def outer():return runtime.child('inner',inner)
        runtime.child('outer',outer)
        runtime.tasks.feedback={'target_child':'outer','parent_ref':'p','contract':'new outer role','context':'Different parent constraint.'}
        runtime.child('outer',outer)
        assert calls==['inner'] and len(selector.prompts)==1
        assert runtime.dispatcher.nodes['child:outer']['revision']==2
        assert runtime.dispatcher.nodes['child:inner']['revision']==1
