"""Obligation scheduling and view identity; native proofs exercise consumers."""
from copy import deepcopy
from types import SimpleNamespace
import sys
from ah.formalizer import validation_graph as graph


def test_iterative_deep_dag_and_cycle(monkeypatch):
    state=SimpleNamespace();depths=[]
    def expand(item):
        kind,state,number,options=item
        frame=sys._getframe();depth=0
        while frame:depth+=1;frame=frame.f_back
        depths.append(depth)
        if number:
            if not (yield graph.request('CONDITION',state,number-1)):return False
            if not (yield graph.request('CONDITION',state,number-1)):return False
        return True
    monkeypatch.setattr(graph,'expand',expand)
    with graph.scope() as engine:assert graph.validate('CONDITION',state,2000)
    assert max(depths)-min(depths)<=1
    assert engine.stats['obligations']==2001 and engine.stats['cache_hits']==2000
    def cycle(item):return (yield graph.request('CONDITION',item[1],item[2]))
    monkeypatch.setattr(graph,'expand',cycle)
    assert not graph.validate('CONDITION',state,1)


def test_view_identity_preserves_both_task_lookup_orders_and_retirement():
    state=SimpleNamespace(decisions={},component_probe_records={},syntax_trace=[])
    a={'kind':'STRUCTURAL_TASK','decision_ref':'D','selected':None,'alternatives':[]}
    b={'kind':'STRUCTURAL_TASK','decision_ref':'D','selected':'PARTITION','alternatives':[]}
    def packet(rows):return {'decisions':{},'probes':{},'trace':rows}
    with graph.scope() as engine:
        first=engine.overlay(state,packet([a,b]));second=engine.overlay(state,packet([b,a]))
        assert first is not second
        changed=deepcopy(a);changed['alternatives']=()
        assert engine.overlay(state,packet([changed,b])) is not first
        assert engine.overlay(state,packet(deepcopy([a,b]))) is first
        revoked=engine.overlay(first,packet([{'kind':'DEPENDENCY_REJECTED','decision_ref':'ancestor'}]))
        assert revoked is not first
        assert engine.overlay(revoked,packet([a,b])) is revoked


def test_native_proof_cache_separates_permission_expected_payload_and_visiting(tmp_path,monkeypatch):
    from test_structural_open_forest import native
    from test_structural_conditional_shells import boundaries,shells
    from ah.formalizer.structural_shells import evidence_state
    from ah.formalizer.structural_tasks import _licensed
    state,_,_=native(tmp_path,monkeypatch,('AND','OR'),boundaries)
    shell=shells(state)[0];local=evidence_state(state,shell);proof=shell['partition_proof']
    with graph.scope():
        assert _licensed(local,proof,_branch=shell['condition'])
        operands=[c['token_refs'] for c in shell['children']]
        assert _licensed(local,proof,_branch=shell['condition'],operands=operands)
        assert not _licensed(local,proof,_branch=shell['condition'],operands=tuple(operands))
        assert not _licensed(local,proof,_branch=shell['condition'],combination_ref='wrong')
        assert not _licensed(local,proof)
        assert not _licensed(local,proof,_branch=shell['condition'],_visiting={proof['decision_ref']})
        assert _licensed(local,proof,_branch=shell['condition'],_visiting={'unrelated'})


def test_malformed_shell_fails_closed(tmp_path,monkeypatch):
    from test_structural_open_forest import native
    from test_structural_conditional_shells import boundaries,shells
    from ah.formalizer.structural_shells import live
    from ah.formalizer.canonical_ledger import digest
    state,_,_=native(tmp_path,monkeypatch,('AND','OR'),boundaries)
    shell=deepcopy(shells(state)[0]);shell.pop('status')
    shell['receipt_digest']=digest({k:v for k,v in shell.items() if k!='receipt_digest'})
    assert not live(state,shell)


def test_public_domain_and_forest_reads_track_changes_and_discard_exact_refs(tmp_path,monkeypatch):
    from test_structural_open_forest import native
    from test_structural_conditional_shells import boundaries
    from ah.formalizer import composition_session
    from ah.formalizer.composition_dispatcher import Dispatcher
    from ah.formalizer.partial_readings import valid_domain
    from ah.formalizer.structural_forest import live
    state,_,_=native(tmp_path,monkeypatch,('AND','OR'),boundaries)
    forest=next(r for r in state.syntax_trace if r.get('kind')=='STRUCTURAL_OPEN_DOMAIN')
    domain=next(r for r in state.syntax_trace if r.get('kind')=='TASK_DOMAIN' and r.get('task_ref')==forest['membership']['domain_ref'])
    page=domain['page_refs'][0];runtime=SimpleNamespace(dispatcher=Dispatcher(state,1000))
    monkeypatch.setattr(composition_session,'current',lambda s:runtime if s is state else None)
    for index,check in enumerate((lambda:valid_domain(state,forest['membership']),lambda:live(state,forest))):
        calls=[]
        def compute():calls.append(True);return check()
        key='read-check:'+str(index)
        assert runtime.dispatcher.run(key,[],compute,kind='PARTITION')
        assert runtime.dispatcher.run(key,[],compute,kind='PARTITION') and len(calls)==1
        decision=state.decisions[page];previous=decision.selector_outcome
        decision.selector_outcome='INSUFFICIENT_CONTEXT'
        assert not runtime.dispatcher.run(key,[],compute,kind='PARTITION') and len(calls)==2
        decision.selector_outcome=previous
        assert runtime.dispatcher.run(key,[],compute,kind='PARTITION') and len(calls)==3
    def replace():
        assert valid_domain(state,forest['membership']) and live(state,forest)
        assert not valid_domain(state,{'decision_ref':'unrelated','domain_ref':'unrelated'})
        runtime.dispatcher.discard_reads({'probe:'+page},'TEST_REPLACEMENT')
        return True
    assert runtime.dispatcher.run('replace-check',[],replace,kind='PARTITION')
    reads=runtime.dispatcher.nodes['replace-check']['evidence_reads'].values()
    assert len(list(reads))==1
    assert next(iter(reads))['value']['domain_ref']=='unrelated'



def test_discard_refs_include_registry_membership_and_shell_boundaries():
    from ah.formalizer.dispatch_evidence import evidence_probe_refs
    def domain(ref,page):return {'kind':'TASK_DOMAIN','task_ref':ref,'page_refs':[page]}
    condition={'condition_ref':'C'}
    state=SimpleNamespace(syntax_trace=[],observation={
        'structural_condition_registry':{'C':{'forest':{'membership':{'decision_ref':'MD','domain_ref':'MD'}},'parent_shell_ref':'S'}},
        'structural_condition_evidence':{'C':{'trace':[domain('MD','old-membership'),domain('MD','membership')]}},
        'structural_shell_registry':{'S':{'partition_proof':{'decision_ref':'PD','domain_ref':'PD'},
            'dependencies':[{'task_ref':'boundary'}],
            'evidence':{'trace':[domain('boundary','old-boundary'),domain('boundary','boundary-page')]}}}})
    value={'proof':{'decision_ref':'P','domain_ref':'P'},'condition':condition}
    refs=evidence_probe_refs(state,'CONDITIONAL_PROOF',value)
    assert {'membership','boundary-page'}<=refs
    assert not {'old-membership','old-boundary'}&refs
    state.syntax_trace.append(domain('boundary','authoritative-page'))
    refs=evidence_probe_refs(state,'CONDITIONAL_PROOF',value)
    assert 'authoritative-page' in refs and 'boundary-page' not in refs


def test_native_membership_partition_condition_cycle_is_rejected(tmp_path,monkeypatch):
    from test_structural_open_forest import native
    from test_structural_conditional_shells import boundaries,shells
    from ah.formalizer.structural_shells import evidence_state,live
    from ah.formalizer.structural_conditions import resolve
    state,_,_=native(tmp_path,monkeypatch,('AND','OR'),boundaries)
    shell=shells(state)[0];local=evidence_state(state,shell)
    assert live(local,shell)
    proof=shell['partition_proof']
    row=next(r for r in local.syntax_trace if r.get('kind')=='STRUCTURAL_TASK' and r.get('decision_ref')==proof['decision_ref'])
    value=next(v for v in row['alternatives'] if v['candidate_id']==proof['candidate_id'])
    membership=resolve(local,shell['condition']).forest['membership']['domain_ref']
    domain=next(r for r in reversed(local.syntax_trace) if r.get('kind')=='TASK_DOMAIN' and r.get('task_ref')==membership)
    domain['prerequisites']=[{'slot':'structural_partition','value':value,'proof':proof}]
    assert not live(local,shell)
