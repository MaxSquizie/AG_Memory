"""P04: the observed predicate and its replay have the same contract."""
import json
from types import SimpleNamespace
import pytest
from ah.formalizer import dispatch_evidence as evidence
from ah.formalizer.composition_dispatcher import Dispatcher
from ah.formalizer.composition_session import session
from ah.formalizer.producer_reads import capture
from test_reading_witnesses import prepared


def test_unconditional_proof_replay_is_not_a_missing_condition():
    state,_,_,w=prepared()
    value={'proof':json.loads(w.proof_json),'condition':None,'expected_payload':{}}
    assert evidence.valid(state,'CONDITIONAL_PROOF',value)
    state.syntax_trace.append({'kind':'DEPENDENCY_REJECTED','decision_ref':value['proof']['decision_ref']})
    assert not evidence.valid(state,'CONDITIONAL_PROOF',value)


@pytest.mark.parametrize('kind',['REFINEMENT_HOST','NOMINAL_HOST'])
def test_negative_owner_read_rechecks_after_repair_without_explicit_invalidation(kind):
    from ah.formalizer.refinement_host_proof import capture as owner,live
    from ah.formalizer.component_constraints import host_live
    from ah.formalizer.function_inventory import source_basis
    from ah.formalizer.dispatch_history import valid as historical
    state,_,_,w=prepared();proof=json.loads(w.proof_json);key=proof['decision_ref']
    key=next(k for k in state.decisions if not k.startswith('task-domain:'))
    value=owner(state,key,proof['candidate_id'])
    if kind=='NOMINAL_HOST':
        value={**value,'source_basis':source_basis(state),'selected':proof['candidate_id']};live=host_live
    decision=state.decisions.pop(key)
    with session(state,SimpleNamespace(entries=lambda kind:[])) as runtime:
        d=runtime.dispatcher
        assert d.run('owner',None,lambda:live(state,value),kind='COMPOSITION') is False
        assert d.valid('owner') and historical(state,'owner',1)
        d.run('sibling',None,lambda:7,kind='COMPOSITION')
        state.decisions[key]=decision
        assert not d.valid('owner') and not historical(state,'owner',1)
        assert d.valid('sibling') and historical(state,'sibling',1)
        assert d.run('owner',None,lambda:live(state,value),kind='COMPOSITION') is True
        assert d.valid('owner') and historical(state,'owner',2)


def test_selected_task_prerequisites_are_traversed_even_if_domain_differs():
    state,_,_,w=prepared();proof=json.loads(w.proof_json)
    row=next(r for r in state.syntax_trace if r.get('kind')=='STRUCTURAL_TASK' and r.get('decision_ref')==proof['decision_ref'])
    row['prerequisites']=[{'proof':{'decision_ref':'task-only-parent','candidate_id':'a'}}]
    assert 'task-only-parent' in evidence.evidence_probe_refs(state,'PROOF',{'proof':proof})
    # A malformed cyclic ancestry must terminate without dropping the parent.
    row['prerequisites'].append({'proof':proof})
    assert 'task-only-parent' in evidence.evidence_probe_refs(state,'PROOF',{'proof':proof})


def test_discard_refinement_premise_from_frozen_cached_capture_keeps_sibling():
    from ah.formalizer.refinement_host_proof import capture as owner
    state,_,_,w=prepared();proof=json.loads(w.proof_json);key=proof['decision_ref']
    owner_key=next(k for k in state.decisions if not k.startswith('task-domain:'))
    value=owner(state,owner_key,proof['candidate_id'],[proof])
    d=Dispatcher(state)
    # Capture actual obligations; no need to forge a second selection just to
    # test extraction independently of liveness.
    with capture(d) as reads:
        reads.observe('REFINEMENT_HOST',value,False)
        reads.observe('NOMINAL_HOST',{'decision_ref':'sibling'},False)
        d.discard_reads(['probe:'+key],'REVISED_PREMISE')
    assert [r['kind'] for r in reads.snapshot()['external']]==['NOMINAL_HOST']


def test_reading_query_includes_parent_proof_of_transformation():
    state,token,_,w=prepared();proof=json.loads(w.proof_json)
    state.syntax_trace.append({'kind':'MORPHOLOGY_PROPOSAL','token_ref':token.token_id,
        'reading':{},'input_token':{'readings':[]},'source_proofs':[proof]})
    assert proof['decision_ref'] in evidence.evidence_probe_refs(state,'READING_QUERY',
        {'token_ref':token.token_id,'scope':None,'reading':None})


def test_inventory_unit_missing_then_completed_then_changed():
    from ah.formalizer.function_inventory import unit_live,unit_hash,source_basis
    from ah.formalizer.dispatch_history import valid as historical
    state,_,_,_=prepared()
    unit={'kind':'TEMPORAL_FUNCTION','unit_ref':'u','inventory_ref':'i','token_refs':[]}
    state.syntax_trace.append(unit)
    with session(state,SimpleNamespace(entries=lambda kind:[])) as runtime:
        d=runtime.dispatcher
        assert d.run('unit',None,lambda:unit_live(state,unit),kind='COMPOSITION') is False
        assert historical(state,'unit',1)
        state.syntax_trace.append({'kind':'FUNCTION_INVENTORY','inventory_ref':'i',
            'inventory_complete':True,'multiplicity':'COMPATIBLE_FUNCTIONS',
            'completion_scope':'DECLARED_FUNCTION_INVENTORY','interpretation_complete':False,
            'source_basis':source_basis(state),'unit_hashes':{'u':unit_hash(unit)},'proofs':[]})
        assert not d.valid('unit') and not historical(state,'unit',1)
        assert d.run('unit',None,lambda:unit_live(state,unit),kind='COMPOSITION') is True
        assert historical(state,'unit',2)
        # Frozen unit differs from the current trace even though inventory id
        # and the completion record remain present.
        unit['token_refs']=['changed']
        assert not d.valid('unit') and not historical(state,'unit',2)


def test_direct_query_empty_then_populated_is_one_final_addressed_obligation():
    from ah.formalizer.reading_producers import query_snapshot
    from ah.formalizer.dispatch_history import valid as historical
    state,token,_,_=prepared();d=Dispatcher(state)
    address={'token_ref':token.token_id,'scope':None,'reading':None}
    calls=[]
    def query():
        value={**address,'signature':query_snapshot(state,token.token_id,None)}
        d.observe('READING_QUERY',value)
        return value
    def compute():
        calls.append(1);query()
        state.syntax_trace.append({'kind':'MORPHOLOGY_PROPOSAL','token_ref':token.token_id,
            'reading':{},'input_token':{'readings':[]}})
        return query()['signature']
    with capture(d) as reads:
        result=d.run('source',None,compute,kind='COMPOSITION')
    assert len(calls)==1 and len(reads.snapshot()['external'])==1
    assert d.run('source',None,compute,kind='COMPOSITION')==result and len(calls)==1
    assert historical(state,'source',1)
    state.syntax_trace.append({'kind':'MORPHOLOGY_PROPOSAL','token_ref':'sibling',
        'reading':{},'input_token':{'readings':[]}})
    assert d.valid('source') and historical(state,'source',1)
    state.syntax_trace.append({'kind':'MORPHOLOGY_PROPOSAL','token_ref':token.token_id,
        'reading':{'pos':'NOUN'},'input_token':{'readings':[]}})
    assert not d.valid('source') and not historical(state,'source',1)


def test_direct_query_addresses_and_exact_witness_assessments_do_not_merge():
    state,_,_,_=prepared();d=Dispatcher(state)
    with capture(d) as reads:
        for tid,signature in [('a','empty'),('b','empty'),('a','filled')]:
            d.observe('READING_QUERY',{'token_ref':tid,'scope':None,'signature':signature})
        for result in [False,True]:d.observe('PROOF',{'proof':{},'expected_payload':{}},result)
    rows=reads.snapshot()['external']
    assert len(rows)==4
    assert {r['value']['signature'] for r in rows if r['kind']=='READING_QUERY'}=={'empty','filled'}
    assert {r['expected'] for r in rows if r['kind']=='PROOF'}=={True,False}


def test_all_observer_kinds_are_registered():
    import ast
    from pathlib import Path
    found=set()
    for path in Path('src/ah/formalizer').glob('*.py'):
        for node in ast.walk(ast.parse(path.read_text())):
            if not isinstance(node,ast.Call):continue
            if isinstance(node.func,ast.Name) and node.func.id=='observe' and len(node.args)>1:
                kind=node.args[1]
            elif isinstance(node.func,ast.Attribute) and node.func.attr=='observe' and node.args:
                kind=node.args[0]
            else:continue
            if isinstance(kind,ast.Constant) and isinstance(kind.value,str):found.add(kind.value)
    assert found==evidence.KINDS
    with pytest.raises(ValueError,match='KIND_UNKNOWN'):
        evidence.evidence_probe_refs(None,'unregistered',{})


def test_recovery_wording_observes_absence_revocation_and_region_isolation(monkeypatch):
    from test_derived_reading_liveness import setup
    from ah.formalizer import composition_session
    from ah.formalizer.recovery_constraints import wording
    from ah.formalizer.dispatch_history import valid as historical
    state,token,_=setup('recovered');d=Dispatcher(state)
    monkeypatch.setattr(composition_session,'current',lambda s:SimpleNamespace(dispatcher=d,
        release=SimpleNamespace(sha256=state.resource_snapshot.get('snapshot_id'))))
    def read():return wording(state,[token.token_id])
    assert d.run('wording',None,read,kind='TEST')==[]
    token.lexical_recovery={'decision_ref':'d','surface':'example'}
    assert not d.valid('wording') and not historical(state,'wording',1)
    result=d.run('wording',None,read,kind='TEST')
    assert len(result)==1 and 'explicitly selected' in result[0]
    assert d.run('wording',None,read,kind='TEST')==result
    assert historical(state,'wording',2)
    d.run('sibling-wording',None,lambda:wording(state,['q']),kind='TEST')
    state.decisions['d'].outcome='UNRESOLVED'
    assert not d.valid('wording') and not historical(state,'wording',2)
    assert d.valid('sibling-wording')
    assert d.run('wording',None,read,kind='TEST')==[]
    state.decisions['d'].outcome=None
    assert not d.valid('wording') and len(d.run('wording',None,read,kind='TEST'))==1


def test_provider_ancestry_is_iterative_and_survives_retired_receipt_for_discard():
    from ah.formalizer.evidence_ancestry import provider_refs
    state,_,_,_=prepared()
    # Deep hard/soft receipt ancestry is a scheduler graph, not linguistic data.
    for i in range(1100):
        state.syntax_trace.append({'kind':'DISPATCH_COMPLETED','task_ref':'provider:'+str(i),'revision':1,
            'dependencies':[{'task_ref':'provider:'+str(i-1),'revision':1}] if i else [],
            'evidence_reads':[{'kind':'NOMINAL_HOST','value':{'decision_ref':'root-probe'},'expected':False}] if not i else []})
    assert provider_refs(state,'provider:1099',1)=={'root-probe'}
    state.syntax_trace.append({'kind':'DISPATCH_INVALIDATED','task_ref':'provider:0'})
    assert provider_refs(state,'provider:1099',1)=={'root-probe'}


def test_recovery_discard_uses_exact_selector_and_preserves_previous_snapshot():
    from copy import deepcopy
    from test_derived_reading_liveness import setup
    from ah.formalizer.recovery_constraints import inspect,signature
    state,token,_=setup('recovered');d=Dispatcher(state)
    a={'decision_ref':'d','surface':'example'};b={'decision_ref':'other','surface':'different'}
    original=next(r for r in state.syntax_trace if r.get('kind')=='AGREEMENT_RECOVERY')
    other=json.loads(json.dumps(original).replace('"d"','"other"'))
    other['lexical_recovery']=b;state.syntax_trace.append(other)
    token.lexical_recovery=a
    value={'token_refs':['t'],'condition':None,'signature':signature(inspect(state,['t']))}
    assert 'other' not in evidence.evidence_probe_refs(state,'RECOVERY_QUERY',value)
    with capture(d) as reads:
        d.observe('RECOVERY_QUERY',value)
        d.discard_reads(['probe:other'],'UNRELATED_DECLARATION')
        assert len(reads.snapshot()['external'])==1
        token.lexical_recovery=b
        assert not evidence.valid(state,'RECOVERY_QUERY',value)
        # Current selector now reads B; the consumed snapshot still remembers A.
        d.discard_reads(['probe:d'],'REPLACED_DECLARATION')
        assert reads.snapshot()['external']==[]


def test_original_discard_includes_publication_acquired_after_capture():
    from test_derived_reading_liveness import setup
    from ah.formalizer.composition_morphology import publish_recoveries
    from ah.formalizer.morphology_domain import clean
    from ah.formalizer.state import FrameCandidate
    state,token,reading=setup('recovered');d=Dispatcher(state)
    value={'token_ref':'t','reading':clean(token.variants[0])}
    with capture(d) as reads:
        d.observe('MORPHOLOGY_ORIGINAL',value)
        assert reads.snapshot()['external'][0]['probe_refs']==[]
        frame=FrameCandidate('f','FLAT','example',(),semantic={'morph_bindings':{'t':reading}})
        publish_recoveries(state,[frame])
        assert evidence.valid(state,'MORPHOLOGY_ORIGINAL',value)
        d.discard_reads(['probe:d'],'REVISED_PUBLICATION')
        assert reads.snapshot()['external']==[]


def test_repeated_exact_observation_retains_both_ancestry_snapshots():
    state,_,_,w=prepared();d=Dispatcher(state);proof=json.loads(w.proof_json)
    task=next(r for r in state.syntax_trace if r.get('kind')=='STRUCTURAL_TASK' and r.get('decision_ref')==proof['decision_ref'])
    value={'proof':proof,'expected_payload':{}}
    with capture(d) as reads:
        task['prerequisites']=[{'proof':{'decision_ref':'old','candidate_id':'a'}}]
        d.observe('PROOF',value,False)
        task['prerequisites']=[{'proof':{'decision_ref':'new','candidate_id':'a'}}]
        d.observe('PROOF',value,False)
        assert {'old','new'}<=set(reads.snapshot()['external'][0]['probe_refs'])
        task['prerequisites']=[]
        d.discard_reads(['probe:old'],'REPAIRED_OLD_PREMISE')
        assert reads.snapshot()['external']==[]


def test_import_discard_keeps_frozen_ancestry_inside_provider_completion():
    from ah.formalizer.evidence_ancestry import provider_refs
    state,_,_,w=prepared();d=Dispatcher(state);proof=json.loads(w.proof_json)
    task=next(r for r in state.syntax_trace if r.get('kind')=='STRUCTURAL_TASK' and r.get('decision_ref')==proof['decision_ref'])
    task['prerequisites']=[{'proof':{'decision_ref':'old-provider-premise','candidate_id':'a'}}]
    saved=evidence.read_record(state,'PROOF',{'proof':proof,'expected_payload':{}},False)
    state.syntax_trace.append({'kind':'DISPATCH_COMPLETED','task_ref':'parent','revision':1,
        'dependencies':[],'evidence_reads':[saved]})
    task['prerequisites']=[{'proof':{'decision_ref':'new-provider-premise','candidate_id':'a'}}]
    assert {'old-provider-premise','new-provider-premise'}<=provider_refs(state,'parent',1)
    imported={'kind':'MORPHOLOGY_FUNCTION_IMPORT','parent_task':'parent','parent_revision':1}
    with capture(d) as reads:
        d.observe('MORPHOLOGY_PROVENANCE',{'row':imported},False)
        d.observe('NOMINAL_HOST',{'decision_ref':'sibling'},False)
        d.discard_reads(['probe:old-provider-premise'],'REPAIRED_PROVIDER')
        assert [r['kind'] for r in reads.snapshot()['external']]==['NOMINAL_HOST']
