"""Native confirmation evidence; scripted answers are not model-quality evidence."""
from copy import deepcopy
import pytest
from test_structural_open_forest import native
from test_structural_conditional_shells import boundaries,shells
from ah.formalizer.structural_shells import evidence_state
from ah.formalizer.partition_exclusions import live,find,failure_live
from ah.formalizer.canonical_ledger import digest


def reject(slot,prompt):return '0' if slot=='structural_partition' else boundaries(slot,prompt)


def negative(state):
    shell=next(s for s in shells(state) if s['relation']=='AND')
    local=evidence_state(state,shell)
    receipt=next(r for r in shell['evidence']['trace'] if r.get('kind')=='STRUCTURAL_PARTITION_EXCLUSION')
    return local,receipt


def test_native_rejection_excludes_only_one_combination(tmp_path,monkeypatch):
    from ah.formalizer.structural_conditions import active
    def selective(slot,prompt):
        from ah.formalizer.composition_session import _current
        if slot=='structural_partition':return '0' if active(_current.get().state).candidate['relation']=='AND' else '1'
        return boundaries(slot,prompt)
    state,result,_=native(tmp_path,monkeypatch,('AND','OR'),selective)
    local,receipt=negative(state);assert live(local,receipt)
    rows=shells(state)
    assert next(s for s in rows if s['relation']=='AND')['children']==[]
    assert len(next(s for s in rows if s['relation']=='OR')['children'])==2
    root=next(j for j in next(iter(state.observation['structural_frontiers'].values()))['jobs'] if j['depth']==1)
    assert root['excluded_combination_refs']==[receipt['candidate']['combination_ref']]
    assert all(not s['producer_complete'] for s in rows)
    assert not result['assertions']['ah']


@pytest.mark.parametrize('change',['page','domain','fingerprint','payload','scope','source','condition','prerequisite','premise_retire'])
def test_negative_evidence_requires_live_exact_basis(tmp_path,monkeypatch,change):
    state,_,_=native(tmp_path,monkeypatch,('AND','OR'),reject)
    local,receipt=negative(state);receipt=deepcopy(receipt)
    assert live(local,receipt)
    page=receipt['pages'][0]['decision_ref']
    domain=next(r for r in local.syntax_trace if r.get('kind')=='TASK_DOMAIN' and r.get('task_ref')==receipt['domain_ref'])
    if change in {'page','domain'}:
        local.syntax_trace.append({'kind':'DEPENDENCY_REJECTED','decision_ref':page if change=='page' else receipt['domain_ref']})
    elif change=='fingerprint':local.decisions[page].selector_outcome='INSUFFICIENT_CONTEXT'
    elif change=='payload':receipt['candidate']['offered_payload']['operands'].reverse()
    elif change=='scope':domain['selection_purpose']='SELECT_ALTERNATIVE'
    elif change=='source':local.text+=' изменено'
    elif change=='condition':
        ref=receipt['candidate']['condition']['condition_ref']
        node=local.observation['structural_condition_registry'][ref]
        local.syntax_trace.append({'kind':'DEPENDENCY_REJECTED','decision_ref':node['forest']['membership']['decision_ref']})
    elif change=='premise_retire':
        assert domain['prerequisites']
        local.syntax_trace.append({'kind':'DEPENDENCY_REJECTED','decision_ref':domain['prerequisites'][0]['proof']['decision_ref']})
    else:domain['prerequisites']=[{'slot':'structural_relation','value':{},'proof':{}}]
    receipt['exclusion_ref']='partition-exclusion:'+digest({k:v for k,v in receipt.items() if k!='exclusion_ref'})
    assert not live(local,receipt)
    if change!='payload':assert find(local,receipt['candidate']) is None


@pytest.mark.parametrize('reply',['?','blocked'])
def test_unknown_and_resource_stop_never_exclude(tmp_path,monkeypatch,reply):
    def answer(slot,prompt):
        if slot=='structural_partition':return '?'
        return boundaries(slot,prompt)
    if reply=='blocked':
        from ah.formalizer import relation_composition
        original=relation_composition.choose
        def choose(state,*args,**kw):
            if args[4]=='structural_partition':
                state.budget.llm_limit=state.budget.llm_calls
            return original(state,*args,**kw)
        monkeypatch.setattr(relation_composition,'choose',choose)
    state,result,_=native(tmp_path,monkeypatch,('AND','OR'),answer)
    assert not any(r.get('kind')=='STRUCTURAL_PARTITION_EXCLUSION' for s in shells(state) for r in s['evidence']['trace'])
    assert not result['assertions']['ah']


def test_same_candidate_replay_and_revocation(tmp_path,monkeypatch):
    from ah.formalizer import relation_composition
    original=relation_composition.confirm_partition;seen=[]
    def confirm(state,*args,**kw):
        result=original(state,*args,**kw)
        if args[5]=='AND' and not seen:
            receipt=next(r for r in reversed(state.syntax_trace) if r.get('kind')=='STRUCTURAL_PARTITION_EXCLUSION')
            calls=state.budget.llm_calls
            assert original(state,*args,**kw) is None
            assert state.budget.llm_calls==calls
            state.syntax_trace.append({'kind':'DEPENDENCY_REJECTED','decision_ref':receipt['domain_ref']})
            assert not live(state,receipt)
            assert find(state,receipt['candidate']) is None
            seen.append(receipt['candidate']['combination_ref'])
        return result
    monkeypatch.setattr(relation_composition,'confirm_partition',confirm)
    state,result,_=native(tmp_path,monkeypatch,('AND','OR'),reject)
    assert seen and not result['assertions']['ah']


def test_combination_identity_independent_of_confirmation(tmp_path,monkeypatch):
    a=tmp_path/'a';a.mkdir();b=tmp_path/'b';b.mkdir()
    rejected,_,_=native(a,monkeypatch,('AND','OR'),reject)
    _,receipt=negative(rejected)
    accepted,_,_=native(b,monkeypatch,('AND','OR'),boundaries)
    shell=next(s for s in shells(accepted) if s['relation']=='AND')
    assert shell['combination_ref']==receipt['candidate']['combination_ref']


def test_diagnostic_without_negative_receipt_cannot_exclude(tmp_path,monkeypatch):
    state,_,_=native(tmp_path,monkeypatch,('AND','OR'),reject)
    local,receipt=negative(state)
    failure=next(r for r in local.syntax_trace if r.get('category')=='PARTITION_REJECTED')
    assert failure_live(local,failure)
    fake=deepcopy(failure);fake['witness'].pop('exclusion_ref')
    assert not failure_live(local,fake)
    local.syntax_trace.append({'kind':'DEPENDENCY_REJECTED','decision_ref':receipt['domain_ref']})
    assert not failure_live(local,failure)


def test_rejection_read_invalidates_partition_cache(tmp_path,monkeypatch):
    from ah.formalizer import relation_composition
    from ah.formalizer.composition_session import current
    from ah.formalizer.partition_domain import PartitionDomain
    original=relation_composition.confirm_partition;seen=[]
    def confirm(state,*args,**kw):
        result=original(state,*args,**kw)
        if args[5]=='AND' and not seen:
            failure=next(r for r in reversed(state.syntax_trace) if r.get('category')=='PARTITION_REJECTED')
            release,selector,region,tokens,cfg,kind,groups,proof=args
            domain=PartitionDomain(state,release,selector,region,tokens,{**cfg,'_partition_rejections':[failure]},kind,proof)
            runtime=current(state);calls=[]
            def compute():
                domain.refresh_rejections();calls.append(True);return bool(domain.rejected)
            assert runtime.dispatcher.run('g4-cache-check',[],compute,kind='PARTITION')
            assert runtime.dispatcher.run('g4-cache-check',[],compute,kind='PARTITION')
            assert len(calls)==1
            receipt=next(r for r in reversed(state.syntax_trace) if r.get('kind')=='STRUCTURAL_PARTITION_EXCLUSION')
            state.syntax_trace.append({'kind':'DEPENDENCY_REJECTED','decision_ref':receipt['domain_ref']})
            assert not runtime.dispatcher.run('g4-cache-check',[],compute,kind='PARTITION')
            assert len(calls)==2
            seen.append(True)
        return result
    monkeypatch.setattr(relation_composition,'confirm_partition',confirm)
    native(tmp_path,monkeypatch,('AND','OR'),reject)
    assert seen


def test_different_partition_with_shared_boundary_is_not_excluded(tmp_path,monkeypatch):
    from ah.formalizer import relation_composition
    from test_structural_frontier import SHORT,short_answer
    original=relation_composition.confirm_partition;checked=[];answers=[]
    def answer(slot,prompt):
        if slot=='structural_partition':
            answers.append(True);return '0' if len(answers)==1 else '1'
        return short_answer(slot,prompt)
    def confirm(state,*args,**kw):
        result=original(state,*args,**kw)
        if args[5]=='AND' and not checked:
            receipt=next(r for r in reversed(state.syntax_trace) if r.get('kind')=='STRUCTURAL_PARTITION_EXCLUSION')
            values=list(args);tokens=values[3]
            split=next(i for i,t in enumerate(tokens) if t.span=='и')
            other=[tokens[:split],tokens[split+1:]]
            assert other[0][0].token_id==values[6][0][0].token_id
            assert [[t.token_id for t in g] for g in other]!=receipt['candidate']['proposal']['operands']
            values[6]=other
            # Fresh ownership for the new split; the former combination alone is excluded.
            fresh={**kw,'marker_roles':{}}
            accepted=original(state,*values,**fresh)
            assert accepted and live(state,receipt)
            row=next(r for r in reversed(state.syntax_trace) if r.get('kind')=='STRUCTURAL_PARTITION_CANDIDATE')
            assert row['combination_ref']!=receipt['candidate']['combination_ref']
            checked.append(True)
        return result
    monkeypatch.setattr(relation_composition,'confirm_partition',confirm)
    _,result,_=native(tmp_path,monkeypatch,('AND','OR'),answer,text=SHORT)
    assert checked and not result['assertions']['ah']


def test_positive_shell_binds_combination_address(tmp_path,monkeypatch):
    from ah.formalizer.structural_shells import live as shell_live
    state,_,_=native(tmp_path,monkeypatch,('AND','OR'),boundaries)
    row=deepcopy(shells(state)[0]);assert shell_live(state,row)
    row['combination_ref']='different-combination'
    row['receipt_digest']=digest({k:v for k,v in row.items() if k!='receipt_digest'})
    assert not shell_live(state,row)


def test_revision_history_does_not_reassert_retired_rejection(tmp_path,monkeypatch):
    from ah.formalizer import relation_composition
    import json
    original=relation_composition.confirm_partition;carried=[]
    def confirm(state,*args,**kw):
        cfg=args[4]
        if cfg.get('_partition_rejections'):
            carried.append(cfg)
            assert not any(f['category']=='PARTITION_REJECTED' for f in json.loads(cfg['_task_constraints'])['failures'])
            assert 'explicitly rejected' not in cfg['_task_constraints_text']
            assert 'does not exclude any partition' in cfg['_task_constraints_text']
        return original(state,*args,**kw)
    def answer(slot,prompt):
        if slot=='structural_revision':return '1'
        return reject(slot,prompt)
    monkeypatch.setattr(relation_composition,'confirm_partition',confirm)
    _,result,prompts=native(tmp_path,monkeypatch,('AND',),answer)
    assert carried
    later=[p for p in prompts if 'Earlier attempt:' in p]
    assert later and all('explicitly rejected' not in p.split('Earlier attempt:',1)[1].split('Question about',1)[0] for p in later if 'Decision slot: structural_relation' in p)
    assert not result['assertions']['ah']


def test_reversed_execution_preserves_excluded_combination_set(tmp_path,monkeypatch):
    from ah.formalizer import structural_shells
    def collect(path):
        path.mkdir()
        state,_,_=native(path,monkeypatch,('AND','OR'),reject)
        snapshot=next(iter(state.observation['structural_frontiers'].values()))
        return {ref for job in snapshot['jobs'] for ref in job['excluded_combination_refs']}
    forward=collect(tmp_path/'forward')
    monkeypatch.setattr(structural_shells,'execution_order',lambda forest:reversed(forest['hypotheses']))
    assert forward==collect(tmp_path/'reverse') and len(forward)==2
