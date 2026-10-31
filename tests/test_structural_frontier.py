"""Actual native probes build three structural levels; no semantic oracle claim."""
import re
import pytest
from test_structural_open_forest import native
from ah.formalizer.composition_session import _current
from ah.formalizer.structural_conditions import resolve,historical

TEXT='Иван спит и Мария читает и Пётр пишет и Анна ждёт и Олег едет и Ирина звонит и Павел уходит и Вера гуляет'


def answer(slot,prompt):
    runtime=_current.get();tokens=runtime.area_inputs[1]
    labels=re.findall(r'^(\d+)\. (.*)$',prompt,re.M)
    if slot=='structural_relation':
        return next((n for n,label in labels if 'Conjunction:' in label),'0')
    if 'Optional search:' in prompt:return '0'
    if slot in {'structural_partition','relation_marker_role'}:return '1'
    connectors=[i for i,t in enumerate(tokens) if t.span=='и']
    if not connectors:return '?'
    mid=connectors[len(connectors)//2]
    edges={'structural_operand_1_start':tokens[0],'structural_operand_1_end':tokens[mid-1],
           'structural_operand_2_start':tokens[mid+1],'structural_operand_2_end':tokens[-1]}
    token=edges.get(slot)
    if token:
        prefix='Start at' if slot.endswith('start') else 'End after'
        return next((n for n,label in labels if label.startswith(prefix+' «'+token.span+'» @'+str(token.start if slot.endswith('start') else token.end))),'0')
    return '?'


def test_native_breadth_three_and_frontier_four(tmp_path,monkeypatch):
    state,result,_=native(tmp_path,monkeypatch,('AND','OR'),answer,text=TEXT)
    events=[r for r in state.syntax_trace if r.get('kind')=='STRUCTURAL_FRONTIER_EVENT']
    started=[r['depth'] for r in events if r['event']=='started']
    assert started==sorted(started) and set(started)=={1,2,3},started
    snapshots=state.observation['structural_frontiers'];assert len(snapshots)==1
    snapshot=next(iter(snapshots.values()))
    assert any(j['depth']==4 and j['status']=='QUEUED' for j in snapshot['jobs']),snapshot
    assert not any(j['depth']==4 and j['status']!='QUEUED' for j in snapshot['jobs'])
    assert all(j['status']=='PRODUCED' for j in snapshot['jobs'] if j['depth']<=3),snapshot
    assert not result['assertions']['ah']
    registry=state.observation['structural_condition_registry']
    assert any(n['parent_condition_ref'] for n in registry.values())
    for ref in registry:
        assert historical(state,{'condition_ref':ref})
    print('TRACE levels',started,'frontier',sum(j['depth']==4 for j in snapshot['jobs']))

SHORT='Иван спит и Мария читает и Пётр пишет и Анна ждёт'


def short_answer(slot,prompt):
    if slot=='structural_relation' and not any(t.span=='и' for t in _current.get().area_inputs[1]):
        labels=re.findall(r'^(\d+)\. (.*)$',prompt,re.M)
        return next((n for n,label in labels if 'One lexical predication' in label),'0')
    return answer(slot,prompt)


def intercept(monkeypatch,hook):
    from ah.formalizer import structural_frontier
    original=structural_frontier.start
    def start(runtime,*args):
        result=original(runtime,*args)
        driver=next(iter(runtime.structural_frontiers.values()))
        hook(driver)
        return result
    monkeypatch.setattr(structural_frontier,'start',start)


def test_repeat_and_local_then_root_fingerprint_revocation(tmp_path,monkeypatch):
    checked=[]
    def check(driver):
        # The injected fingerprint fault creates a real negative observation;
        # restoring it can replay the enclosing dispatcher. Inject only once.
        if checked:return
        checked.append(True)
        calls=driver.state.budget.llm_calls
        first=driver.snapshot();assert driver.run()==first
        assert driver.state.budget.llm_calls==calls
        # Local partition retirement affects its descendants, not the other branch.
        root=next(j for j in driver.jobs.values() if j['depth']==1)
        first_shell,other=root['results']
        driver.state.syntax_trace.append({'kind':'DEPENDENCY_REJECTED',
            'decision_ref':first_shell['partition_proof']['decision_ref']})
        snap=driver.run()
        assert all(j['status']=='STALE' for j in snap['jobs'] if j['parent_shell_ref']==first_shell['shell_ref'])
        assert all(j['status']!='STALE' for j in snap['jobs'] if j['parent_shell_ref']==other['shell_ref'])
        # Change the page fingerprint without emitting a retirement event.
        domain=next(r for r in driver.state.syntax_trace if r.get('kind')=='TASK_DOMAIN'
                    and r.get('task_ref')==root['forest']['membership']['domain_ref'])
        decision=driver.state.decisions[domain['page_refs'][0]]
        previous=(decision.selected,decision.selector_outcome)
        decision.selected=();decision.selector_outcome='INSUFFICIENT_CONTEXT'
        assert all(j['status']=='STALE' for j in driver.run()['jobs'])
        assert driver.state.budget.llm_calls==calls
        # End the injected fault before the enclosing dispatcher validates its own read.
        decision.selected,decision.selector_outcome=previous
    intercept(monkeypatch,check)
    state,result,_=native(tmp_path,monkeypatch,('AND','OR'),short_answer,text=SHORT)
    assert not result['assertions']['ah']


@pytest.mark.parametrize('mode',['dispatcher','search'])
def test_resource_resume_keeps_prefix_and_budget(tmp_path,monkeypatch,mode):
    from ah.formalizer import structural_frontier
    original=structural_frontier.start;captured=[];cut=[];old_limit=[];prefix_calls=[]
    def stop_once(slot,prompt):
        runtime=_current.get()
        prefix_calls.append(str(prompt))
        if slot=='structural_operand_1_start' and getattr(runtime,'structural_child_edge',None) and not cut:
            cut.append(str(prompt))
            if mode=='dispatcher':runtime.dispatcher.limit=runtime.dispatcher.spent
            else:
                policy=runtime.release.entries('ProposalPolicy')[0]
                old_limit.append(policy['max_rule_steps'])
                policy['max_rule_steps']=runtime.state.budget.task_candidates_examined
        return short_answer(slot,prompt)
    def start(runtime,*args):
        original(runtime,*args);driver=next(iter(runtime.structural_frontiers.values()))
        stopped=driver.snapshot();calls=runtime.state.budget.llm_calls
        assert any(j['status']=='PENDING_RESOURCE' for j in stopped['jobs'])
        assert driver.run()==stopped and runtime.state.budget.llm_calls==calls
        completed={j['job_ref']:j['result_refs'] for j in stopped['jobs'] if j['status']=='PRODUCED'}
        runtime.dispatcher.limit+=10000
        if old_limit:runtime.release.entries('ProposalPolicy')[0]['max_rule_steps']=old_limit[0]
        resumed=driver.run()
        assert not any(j['status'] in {'PENDING_RESOURCE','QUEUED'} for j in resumed['jobs'] if j['depth']<=3),resumed
        assert all(next(j for j in resumed['jobs'] if j['job_ref']==ref)['result_refs']==refs for ref,refs in completed.items())
        assert runtime.state.budget.llm_calls>=calls
        captured.extend([stopped,resumed]);return resumed
    monkeypatch.setattr(structural_frontier,'start',start)
    state,result,_=native(tmp_path,monkeypatch,('AND','OR'),stop_once,text=SHORT)
    assert cut and len(captured)==2 and not result['assertions']['ah']
    assert prefix_calls.count(cut[0])==1
    print('RESOURCE frontier',[(j['depth'],j['status']) for j in captured[0]['jobs']],
          'RESUMED',[(j['depth'],j['status']) for j in captured[1]['jobs']])


def test_multiple_child_and_reverse_sibling_order(tmp_path,monkeypatch):
    from ah.formalizer import structural_frontier
    def multiple(slot,prompt):
        rt=_current.get()
        if slot=='structural_relation' and rt.area_inputs[1][0].span=='Иван' and any(t.span=='и' for t in rt.area_inputs[1]):
            labels=re.findall(r'^(\d+)\. (.*)$',prompt,re.M)
            return ','.join(n for n,label in labels if 'Conjunction:' in label or 'Inclusive alternative' in label)
        return short_answer(slot,prompt)
    def projection(state):
        snapshot=next(iter(state.observation['structural_frontiers'].values()))
        return {(j['job_ref'],j['depth'],j['status']) for j in snapshot['jobs']}
    first=tmp_path/'first';first.mkdir();second=tmp_path/'second';second.mkdir()
    state,_,_=native(first,monkeypatch,('AND','OR'),multiple,text=SHORT)
    expected=projection(state)
    nodes=state.observation['structural_condition_registry']
    assert any(n['parent_condition_ref'] and len(n['forest']['hypotheses'])>1 for n in nodes.values())
    assert any(n['parent_condition_ref'] and len(n['forest']['hypotheses'])==1 for n in nodes.values())
    old=structural_frontier.order
    monkeypatch.setattr(structural_frontier,'order',lambda jobs:sorted(list(jobs),key=lambda j:(j['depth'],tuple(-ord(c) for c in j['job_ref']))))
    state,result,_=native(second,monkeypatch,('AND','OR'),multiple,text=SHORT)
    assert projection(state)==expected
    assert not result['assertions']['ah']


def test_unknown_sibling_does_not_block_available_next_level(tmp_path,monkeypatch):
    def unknown(slot,prompt):
        rt=_current.get()
        if slot=='structural_relation' and rt.area_inputs[1][0].span=='Иван':return '?'
        return short_answer(slot,prompt)
    state,result,_=native(tmp_path,monkeypatch,('AND','OR'),unknown,text=SHORT)
    jobs=next(iter(state.observation['structural_frontiers'].values()))['jobs']
    assert any(j['depth']==2 and j['status']=='PENDING_EVIDENCE' for j in jobs)
    assert any(j['depth']==3 for j in jobs)
    assert not result['assertions']['ah']


def test_unforkable_reader_keeps_capability_obligation(tmp_path,monkeypatch):
    from ah.formalizer.attention_context import AttentionContextReader
    monkeypatch.setattr(AttentionContextReader,'fork',None)
    state,result,_=native(tmp_path,monkeypatch,('AND','OR'),short_answer,text=SHORT)
    jobs=next(iter(state.observation['structural_frontiers'].values()))['jobs']
    assert len(jobs)==1 and jobs[0]['status']=='PENDING_CAPABILITY'
    assert not result['assertions']['ah']


def test_retirement_after_enqueue_prevents_child_start(tmp_path,monkeypatch):
    from ah.formalizer.structural_frontier import StructuralFrontier
    original=StructuralFrontier.enqueue_children;retired=[]
    def enqueue(self,job,shell):
        original(self,job,shell)
        if job['depth']==1 and not retired:
            retired.extend(c['child_ref'] for c in shell['children'])
            self.state.syntax_trace.append({'kind':'DEPENDENCY_REJECTED',
                'decision_ref':shell['partition_proof']['decision_ref']})
    monkeypatch.setattr(StructuralFrontier,'enqueue_children',enqueue)
    state,result,_=native(tmp_path,monkeypatch,('AND','OR'),short_answer,text=SHORT)
    started={r['job_ref'] for r in state.syntax_trace if r.get('kind')=='STRUCTURAL_FRONTIER_EVENT' and r['event']=='started'}
    assert retired and not started.intersection(retired)
    assert not result['assertions']['ah']


def test_changed_parent_context_retires_checkpoint_without_probes(tmp_path,monkeypatch):
    from test_structural_conditional_shells import boundaries
    def check(driver):
        calls=driver.state.budget.llm_calls
        previous=driver.runtime.domain_feedback
        driver.runtime.domain_feedback='new parent constraint'
        assert all(j['status']=='STALE' for j in driver.run()['jobs'])
        assert driver.state.budget.llm_calls==calls
        driver.runtime.domain_feedback=previous
    intercept(monkeypatch,check)
    state,result,_=native(tmp_path,monkeypatch,('AND','OR'),boundaries)
    assert not result['assertions']['ah']


@pytest.mark.parametrize('addressed',[False,True])
def test_child_execution_inherits_applicable_context(tmp_path,monkeypatch,addressed):
    from ah.formalizer import relation_composition
    from test_structural_conditional_shells import boundaries
    original=relation_composition.select_relation
    seen=[]
    feedback={'contract':'preserve assigned roles','context':'prior established evidence'}
    if addressed:feedback['target_child']='another-child'
    def select(state,*args):
        runtime=_current.get()
        if not getattr(runtime,'structural_child_edge',None):
            runtime.morphology_scope='morphology:verified-parent-occurrences'
            runtime.domain_feedback='Retain established occurrence assignments'
            runtime.tasks.feedback=feedback.copy()
        else:
            assert runtime.morphology_scope=='morphology:verified-parent-occurrences'
            assert runtime.domain_feedback=='Retain established occurrence assignments'
            assert runtime.tasks.feedback==(None if addressed else feedback)
            assert len(runtime.area_inputs[1])==2
            assert runtime.area_inputs[2].surrounding_relations
            seen.append(runtime.input_question('structural_relation'))
        return original(state,*args)
    monkeypatch.setattr(relation_composition,'select_relation',select)
    state,result,prompts=native(tmp_path,monkeypatch,('AND','OR'),boundaries)
    assert len(seen)==4
    assert all('Retain established occurrence assignments' in p for p in seen)
    child_prompts=[p for p in prompts if 'Already handled outside the target:' in p]
    assert child_prompts and all('Retain established occurrence assignments' in p for p in child_prompts)
    assert not result['assertions']['ah']
