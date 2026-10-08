"""Production goal channel: decision-first recovery and one serialized DB-N."""
from dataclasses import asdict
from .canonical_ledger import CanonicalLedger,digest,region,region_data
from .temporal_license import or_elimination_license,forall_inst_license,undated,LicenseResult
from .store_interface import StoreOp


def _spec(ledger,ref):
    return ledger.data['nodes'].get(ref,{})


def _licensed(rule,W,V,a,b,evidence):
    x=next((e for e in evidence if e['support_record_id']==a),{})
    y=next((e for e in evidence if e['support_record_id']==b),{})
    if x.get('witness_ref') and x['witness_ref']==y.get('witness_ref') and digest(x['region'])==digest(y['region']):
        return LicenseResult('LICENSED',W)
    return or_elimination_license(W,V) if rule=='OR_ELIMINATION' else forall_inst_license(W,V)


def validate_goal(ledger,req):
    if req.rule_id not in {'OR_ELIMINATION','FORALL_INST'}: return 'GOAL_RULE_UNKNOWN',None,None
    if not req.premise_support_ids: return 'GOAL_NO_PREMISES',None,None
    paths=ledger.paths()
    if any(p not in paths for p in req.premise_support_ids): return 'GOAL_PREMISES_STALE',None,None
    supports=[ledger.data['supports'][p] for p in req.premise_support_ids]
    nodes=[_spec(ledger,s['conclusion_ref']) for s in supports]
    evidence=[]
    for aid in req.temporal_premise_assertion_refs:
        a=ledger.data['assertions'].get(aid)
        if not a or not ledger.evidence_live({'record_id':aid}) or a['support_record_id'] not in req.premise_support_ids:
            return 'GOAL_LICENSE_FAILED',None,None
        evidence.append(a)
    # Dated paths cannot be made undated merely by omitting their evidence IDs.
    selected={a['support_record_id'] for a in evidence}
    if any(any(a['support_record_id']==p and ledger.evidence_live({'record_id':aid}) for aid,a in ledger.data['assertions'].items()) and p not in selected for p in req.premise_support_ids):
        return 'GOAL_LICENSE_FAILED',None,None
    if len({a['support_record_id'] for a in evidence}) != len(evidence):
        return 'GOAL_LICENSE_FAILED',None,None
    windows={a['support_record_id']:region(a['region']) for a in evidence}
    roots=[i for i,n in enumerate(nodes) if n.get('function_id')==('OR' if req.rule_id=='OR_ELIMINATION' else 'FORALL' if req.rule_id=='FORALL_INST' else 'IMPLIES')]
    if len(roots)!=1: return 'GOAL_FORM_MISMATCH',None,None
    root_idx=roots[0]; root=nodes[root_idx]; root_support=supports[root_idx]
    target=req.conclusion_ref or ledger.data.get('signature_index',{}).get(req.conclusion_signature)
    if req.conclusion_ops and target is None: target='@conclusion'
    ops=tuple(req.conclusion_ops)
    target_spec=_spec(ledger,target)
    if ops:
        choices=[op.payload for op in ops if op.op_type=='ENSURE_NODE' and op.payload.get('uid')==target]
        if len(choices)!=1 or target_spec or len(ops)!=1: return 'GOAL_FORM_MISMATCH',None,None
        target_spec=choices[0]
    if not target or not target_spec or target_spec.get('semantic_status')=='UNLINKED': return 'GOAL_FORM_MISMATCH',None,None
    if req.conclusion_signature not in {target,digest(target_spec.get('proposition',{})),target_spec.get('content_key')}:
        return 'GOAL_FORM_MISMATCH',None,None
    W=windows.get(root_support['record_id'],undated())
    if req.rule_id=='OR_ELIMINATION':
        operands=root.get('operands',())
        remaining=[r for r in operands if r!=target]
        if target not in operands or len(supports)!=len(remaining)+1: return 'OR_ELIMINATION_INCOMPLETE',None,None
        nots=[(supports[i],n) for i,n in enumerate(nodes) if i!=root_idx]
        for other in remaining:
            found=[(s,n) for s,n in nots if n.get('function_id')=='NOT' and n.get('operands')==[other]]
            if len(found)!=1: return 'OR_ELIMINATION_INCOMPLETE',None,None
            s,n=found[0]
            lic=_licensed(req.rule_id,W,windows.get(s['record_id'],undated()),root_support['record_id'],s['record_id'],evidence)
            if lic.status!='LICENSED': return 'GOAL_LICENSE_FAILED',None,None
        return None,target,W
    if len(supports)!=2: return 'GOAL_FORM_MISMATCH',None,None
    other_idx=1-root_idx; premise=nodes[other_idx]
    body=root
    if req.rule_id=='FORALL_INST':
        operands=root.get('operands',())
        if len(operands)!=2 or not isinstance(operands[0],dict) or 'bound_var' not in operands[0]: return 'GOAL_FORM_MISMATCH',None,None
        body=_spec(ledger,operands[1])
        if body.get('function_id')!='IMPLIES': return 'GOAL_FORM_MISMATCH',None,None
    body_ops=body.get('operands',())
    if len(body_ops)!=2: return 'GOAL_FORM_MISMATCH',None,None
    antecedent=_spec(ledger,body_ops[0]); consequent=_spec(ledger,body_ops[1])
    if req.rule_id=='MODUS_PONENS':
        if supports[other_idx]['conclusion_ref']!=body_ops[0] or target!=body_ops[1]: return 'GOAL_FORM_MISMATCH',None,None
    else:
        pattern=antecedent.get('proposition',{}); actual=premise.get('proposition',{})
        expected=consequent.get('proposition',{}); result=target_spec.get('proposition',{})
        substitution={}
        def unify(a,b):
            if isinstance(a,dict) and set(a)>={'bound_var'}:
                if a['bound_var']!=root['operands'][0]['bound_var']: return False
                key=str(a['bound_var'])
                if key in substitution: return substitution[key]==b
                substitution[key]=b; return True
            if isinstance(a,dict): return isinstance(b,dict) and set(a)==set(b) and all(unify(a[k],b[k]) for k in a)
            if isinstance(a,list): return isinstance(b,list) and len(a)==len(b) and all(unify(x,y) for x,y in zip(a,b))
            return a==b
        if not pattern or not expected or not unify(pattern,actual) or not unify(expected,result): return 'GOAL_FORM_MISMATCH',None,None
    lic=_licensed(req.rule_id,W,windows.get(supports[other_idx]['record_id'],undated()),root_support['record_id'],supports[other_idx]['record_id'],evidence)
    return (None,target,lic.derived_region) if lic.status=='LICENSED' else ('GOAL_LICENSE_FAILED',None,None)


def root_id(ledger,req):
    function='OR' if req.rule_id=='OR_ELIMINATION' else 'FORALL'
    return next((ledger.data['supports'][p]['conclusion_ref'] for p in req.premise_support_ids if ledger.data['nodes'].get(ledger.data['supports'][p]['conclusion_ref'],{}).get('function_id')==function),None)


def execute(store,req,interleave=None):
    payload=asdict(req)
    payload['conclusion_ops']=[asdict(o) for o in req.conclusion_ops]
    if req.temporal is not None: payload['temporal']=[region_data(region(r)) for r in req.temporal]
    with store._journal.atomic():
        old_pending=next((r['payload'] for r in store._journal.scan_unprocessed(0) if r['payload'].get('kind')=='GOAL_PENDING' and r['payload'].get('goal_run_id')==req.goal_run_id),None)
        if old_pending and digest(old_pending['request']) != digest(payload): raise ValueError('INTEGRITY_ERROR: goal run input changed')
        if old_pending is None:
            store._journal.append('goal',{'kind':'GOAL_PENDING','goal_run_id':req.goal_run_id,'request':payload},run_id=req.goal_run_id)
    if interleave: interleave()
    with store._journal.atomic(),store._store._lock:
        store._refresh()
        decision=decision_for(store,req.goal_run_id)
        if decision is not None:
            if decision['request_hash']!=digest(payload): raise ValueError('INTEGRITY_ERROR: goal run input changed')
            verify_applied(store,decision)
            finish(store,decision)
            return dict(decision)
        draft=store._draft(); ledger=CanonicalLedger(draft.store._state.formalizer_state); before=ledger.copy()
        key=digest([req.rule_id,sorted(req.premise_support_ids),req.conclusion_signature,sorted(req.temporal_premise_assertion_refs)])
        reason,target,W=validate_goal(ledger,req)
        existing=ledger.data['goal_paths'].get(key)
        if reason:
            outcome='ABORTED'; events=[]
        elif existing:
            sid=existing['support_record_id']
            if sid not in ledger.paths(): reason='GOAL_PREMISES_STALE'; outcome='ABORTED'
            else: outcome='APPLIED_NOOP'; target=existing['conclusion_ref']
            events=[]
        else:
            sid='derived:'+digest([key])
            ops=list(req.conclusion_ops)
            if target=='@conclusion':
                from uuid import uuid4
                spec=dict(ops[0].payload)
                shared=next((uid for uid,n in ledger.data['nodes'].items() if spec.get('temporal_mode')=='STATE' and n.get('content_key')==spec.get('content_key')),None)
                target=shared or 'N:goal:'+uuid4().hex
                if shared: ops=[]
                else: ops=[StoreOp('ENSURE_NODE',{**spec,'uid':target})]
            formula_ref=target
            target_spec=ledger.data['nodes'].get(target,{})
            if not ops and target_spec.get('template_ref') and target_spec.get('temporal_mode')!='STATE':
                from uuid import uuid4
                target='N:goal:'+uuid4().hex
                spec={**target_spec,'uid':target,'formula_ref':formula_ref,'identity_key':[target_spec['content_key'],sid]}
                spec.pop('op_id',None); spec.pop('source_tag',None)
                ops=[StoreOp('ENSURE_NODE',spec)]
            support={'record_id':sid,'conclusion_ref':target,'kind':'DERIVED','rule_id':req.rule_id,'premise_support_refs':sorted(req.premise_support_ids),'temporal_assertion_refs':sorted(req.temporal_premise_assertion_refs),'goal_run_id':req.goal_run_id,'formula_ref':formula_ref}
            ops.append(StoreOp('ADD_DERIVED_SUPPORT',support))
            if W.kind!='UNDATED':
                ops.append(StoreOp('ADD_TIME_ASSERTION',{'assertion_id':'assertion:'+digest([sid,region_data(W)]),'target_ref':target,'support_record_id':sid,'region':region_data(W),'anchor':None,'witness_ref':next((ledger.data['assertions'][aid].get('witness_ref') for aid in req.temporal_premise_assertion_refs if digest(ledger.data['assertions'][aid]['region'])==digest(region_data(W))),None),'provenance':{'source':{'kind':'GOAL_RUN','goal_run_id':req.goal_run_id},'support':{'kind':'DERIVED','rule_id':req.rule_id,'premise_support_refs':sorted(req.premise_support_ids)}}}))
            _,events=store._apply(draft,ops)
            ledger.data['goal_paths'][key]={'support_record_id':sid,'conclusion_ref':target}
            outcome='APPLIED'
        decision={'goal_run_id':req.goal_run_id,'outcome':outcome,'request_hash':digest(payload)}
        if reason: decision['reason']=reason
        if target and not reason: decision['conclusion_ref']=target
        decision['created']=outcome=='APPLIED'
        if outcome=='APPLIED':
            decision['support_record_id']=sid
            decision['assertion_refs']=[aid for aid,a in ledger.data['assertions'].items() if a['support_record_id']==sid]
        if outcome=='APPLIED':
            ledger.data['goal_decisions'][req.goal_run_id]=decision
            ledger.refresh(before,req.goal_run_id,store.read_global_head()+1,events)
            store._write_unit(draft,tx_ref=req.goal_run_id,extra={'kind':'GOAL_DECISION',**decision})
        else:
            # DB-N: the common journal lock covers reads, outcome and fsync.
            # No AH/store mutation for NOOP or ABORTED.
            store._journal.append('goal',{'kind':'GOAL_DECISION',**decision},run_id=req.goal_run_id)
        finish(store,decision)
        return dict(decision)


def decision_for(store,run_id):
    for r in store._journal.scan_unprocessed(0):
        p=r['payload']; d=p.get('extra') if p.get('kind')=='canonical_unit' else p
        if d and d.get('kind')=='GOAL_DECISION' and d.get('goal_run_id')==run_id:
            return {k:v for k,v in d.items() if k!='kind'}
    return None


def verify_applied(store,decision):
    if decision['outcome']!='APPLIED': return
    ledger=store.ledger; sid=decision['support_record_id']
    if sid not in ledger.data['supports'] or ledger.data['supports'][sid]['conclusion_ref']!=decision['conclusion_ref']:
        raise ValueError('INTEGRITY_ERROR: goal decision without support')
    if any(aid not in ledger.data['assertions'] or ledger.data['assertions'][aid]['support_record_id']!=sid for aid in decision['assertion_refs']):
        raise ValueError('INTEGRITY_ERROR: goal support/assertion pair incomplete')


def finish(store,decision):
    rid=decision['goal_run_id']
    if not any(r['payload'].get('kind')=='GOAL_TERMINAL' and r['payload'].get('goal_run_id')==rid for r in store._journal.scan_unprocessed(0)):
        store._journal.append('goal',{'kind':'GOAL_TERMINAL',**decision},run_id=rid)


def recover(store):
    from .goal_executor import GoalRequest
    for r in store._journal.scan_unprocessed(0):
        p=r['payload']
        if p.get('kind')!='GOAL_PENDING': continue
        request=dict(p['request'])
        if request.get('temporal') is not None: request['temporal']=tuple(region(x) for x in request['temporal'])
        request['conclusion_ops']=tuple(StoreOp(**o) for o in request.get('conclusion_ops',()))
        execute(store,GoalRequest(**request))
