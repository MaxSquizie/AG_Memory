"""Native conditional source execution and explicit child suspension (scripted)."""
import re
from copy import deepcopy
from types import SimpleNamespace as NS
import pytest
from test_structural_open_forest import native
from test_structural_conditional_shells import boundaries


def lexical_answer(slot,prompt):
    labels=re.findall(r'^(\d+)\. (.*)$',prompt,re.M)
    if slot=='structural_relation':return next((n for n,label in labels if 'One lexical predication' in label),'0')
    if slot in {'nominal_coordination_discovery','nominal_function','temporal_function'}:return '0'
    if slot=='predicate_function':return next((n for n,label in labels if '«пришёл»' in label or '«спит»' in label),'0')
    if slot=='predicate_argument_role':return next((n for n,label in labels if 'core subject' in label),'0')
    if slot=='predicate_argument_reading':return next((n for n,label in labels if 'nominative' in label),'0')
    return boundaries(slot,prompt)


def test_native_open_root_retains_real_grammar_leaves_privately(tmp_path,monkeypatch):
    state,result,_=native(tmp_path,monkeypatch,('AND','OR'),lexical_answer)
    rows=list(state.observation['structural_lexical_results'].values())
    assert len(rows)==4
    assert len({r['condition']['condition_ref'] for r in rows})==4
    for row in rows:
        assert row['status']=='PENDING_VALIDATION'
        assert not row['producer_complete'] and not row['structure_complete'] and not row['write_eligible']
        grammar,component=row['sources']
        assert grammar['source']=='GRAMMAR' and grammar['frames'] and grammar['execution_complete']
        assert grammar['bundles'] and grammar['obligations']
        assert component['frames'] and component['bundles'] and not component['producer_complete']
        assert not component['diagnostics']
        assert all(not f['semantic'].get('component_scope_tree') for f in component['frames'])
        assert all(f['frame_id'] not in {f.frame_id for f in state.frames} for f in grammar['frames'])
        assert set(row['evidence']['decisions'])-set(state.decisions)  # private answers exist
    assert not result['assertions']['ah']


def test_native_infinitive_suspends_before_child_execution(tmp_path,monkeypatch):
    def answer(slot,prompt):
        labels=re.findall(r'^(\d+)\. (.*)$',prompt,re.M)
        if 'Optional search:' in prompt:return '0'
        desired={'infinitive_head':'Dependent infinitive starts at «читать»',
                 'infinitive_content_end':'End after «читать»'}.get(slot)
        if desired:return next((n for n,label in labels if label.startswith(desired)),'0')
        return '?'
    state,result,_=native(tmp_path,monkeypatch,('LEXICAL','FORALL'),answer,text='Иван хочет читать')
    row=next(iter(state.observation['structural_lexical_results'].values()))
    source=next(s for s in row['sources'] if s['source']=='COMPONENT')
    demands=[o for o in source['obligations'] if o['kind']=='LEXICAL_CHILD_DEMAND']
    assert len(demands)==1,source
    demand=demands[0]
    assert demand['status']=='PENDING_SCHEDULER' and demand['condition']==row['condition']
    assert demand['input_slot']['pending_proposition_roles']
    assert not source['execution_complete'] and not source['frames']
    assert not any(r.get('region_ref')==demand['region_ref'] and r.get('slot')=='structural_relation'
                   for r in row['evidence']['trace'])
    assert not result['assertions']['ah']


def test_child_interception_precedes_morphology_or_dispatch_and_restores_scope(monkeypatch):
    from ah.formalizer.lexical_demands import capture,ChildDemand,intercept
    from ah.formalizer.component_refinement import compose_area
    from ah.formalizer import morphology_domain
    state=NS();region=NS(region_id='child',source_range=(0,1))
    from dataclasses import make_dataclass
    tokens=[make_dataclass("Token",[("token_id",str)])("t")]
    monkeypatch.setattr(morphology_domain,'project',lambda *a:pytest.fail('child computation escaped'))
    with capture(state,{'parent':'test'}):
        with pytest.raises(ChildDemand) as exc:
            compose_area(state,None,None,region,tokens,{},request=None)
    assert exc.value.obligation['child_key']
    # Outside the guard the interception itself is a no-op.
    intercept(state,region,tokens,{},0,None,None,None)


def test_conditional_inventory_is_valid_only_with_explicit_condition(tmp_path,monkeypatch):
    from ah.formalizer.structural_shells import evidence_state
    from ah.formalizer.function_inventory import live
    from ah.formalizer.dispatch_evidence import valid
    state,_,_=native(tmp_path,monkeypatch,('AND','OR'),lexical_answer)
    rows=list(state.observation['structural_lexical_results'].values())
    row=rows[0];local=evidence_state(state,row)
    receipt=next(r for r in row['evidence']['trace'] if r.get('kind')=='FUNCTION_INVENTORY')
    assert not live(local,receipt)
    assert live(local,receipt,condition=row['condition'])
    assert not live(local,receipt,condition=rows[1]['condition'])
    dependency={'inventory_ref':receipt['inventory_ref'],'condition':row['condition']}
    assert valid(local,'INVENTORY',dependency)
    from ah.formalizer.dispatch_evidence import evidence_probe_refs
    assert receipt['completion_proof']['decision_ref'] in evidence_probe_refs(local,'INVENTORY',dependency)
    empty=deepcopy(receipt);empty['proofs']=[]
    assert not live(local,empty)
    assert live(local,empty,condition=row['condition'])
    local.syntax_trace.append({'kind':'DEPENDENCY_REJECTED',
        'decision_ref':receipt['completion_proof']['decision_ref']})
    assert not valid(local,'INVENTORY',dependency)
    from ah.formalizer.structural_conditions import resolve
    local.syntax_trace.append({'kind':'DEPENDENCY_REJECTED',
        'decision_ref':resolve(local,row['condition']).forest['membership']['decision_ref']})
    assert not live(local,empty,condition=row['condition'])


def test_lexical_dispatch_stop_is_resumable_resource_state(tmp_path,monkeypatch):
    from ah.formalizer import lexical_component,structural_frontier
    from ah.formalizer.composition_dispatcher import DispatchBlocked
    original=lexical_component.produce;stopped=[];resumed=[]
    start=structural_frontier.start
    def blocked(*a,**k):
        if not stopped:
            stopped.append(True);raise DispatchBlocked('COMPOSITION_DISPATCH_INCOMPLETE')
        return original(*a,**k)
    def run(runtime,*args):
        start(runtime,*args)
        driver=next(iter(runtime.structural_frontiers.values()))
        waiting=[j for j in driver.jobs.values() if j['status']=='PENDING_RESOURCE']
        assert len(waiting)==1
        runtime.dispatcher.limit+=100
        result=driver.run()
        assert waiting[0]['status']=='PENDING_EVIDENCE'
        sources=waiting[0]['lexical_results'][0]['sources']
        assert all(s['execution_complete'] for s in sources)
        assert not any(o['kind']=='RESOURCE_PENDING' for s in sources for o in s['obligations'])
        resumed.append(True)
        return result
    monkeypatch.setattr(lexical_component,'produce',blocked)
    monkeypatch.setattr(structural_frontier,'start',run)
    state,result,_=native(tmp_path,monkeypatch,('AND','OR'),lexical_answer)
    assert resumed and not result['assertions']['ah']


def test_native_authorized_window_reaches_actual_lexical_frames(tmp_path,monkeypatch):
    from test_structural_windows import answer as window_answer,TEXT
    def answer(slot,prompt):
        if slot.startswith('structural_') or slot=='relation_marker_role':return window_answer(slot,prompt)
        return lexical_answer(slot,prompt)
    state,result,_=native(tmp_path,monkeypatch,('NOT','LEXICAL'),answer,text=TEXT)
    snapshot=next(iter(state.observation['structural_frontiers'].values()))
    deepest=max(snapshot['jobs'],key=lambda j:j['depth'])
    assert deepest['depth']==5 and snapshot['windows']
    row=state.observation['structural_lexical_results'][deepest['lexical_result_refs'][0]]
    assert all(s['frames'] for s in row['sources'])
    assert not row['write_eligible'] and not result['assertions']['ah']
