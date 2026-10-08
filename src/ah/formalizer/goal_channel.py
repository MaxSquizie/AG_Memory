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


def validate_goal(ledger,req,core=None):
    from .native_records import record_index
    index=record_index(core,ledger) if core is not None else None
    if req.rule_id not in {'OR_ELIMINATION','FORALL_INST','MODUS_PONENS'}: return 'GOAL_RULE_UNKNOWN',None,None
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
    if any((bool(index['assertions'].get(p)) if index else any(a['support_record_id']==p for a in ledger.data['assertions'].values())) and p not in selected for p in req.premise_support_ids):
        return 'GOAL_LICENSE_FAILED',None,None
    if len({a['support_record_id'] for a in evidence}) != len(evidence):
        return 'GOAL_LICENSE_FAILED',None,None
    windows={a['support_record_id']:region(a['region']) for a in evidence}
    function = {'OR_ELIMINATION':'OR','FORALL_INST':'FORALL','MODUS_PONENS':'IMPLIES'}[req.rule_id]
    roots=[i for i,n in enumerate(nodes) if n.get('function_id')==function and (req.rule_root_support_id is None or supports[i]['record_id']==req.rule_root_support_id)]
    if len(roots)!=1: return 'GOAL_FORM_MISMATCH',None,None
    root_idx=roots[0]; root=nodes[root_idx]; root_support=supports[root_idx]
    target=req.conclusion_ref or ledger.data.get('signature_index',{}).get(req.conclusion_signature)
    if req.conclusion_ops and target is None: target='@conclusion'
    ops=tuple(req.conclusion_ops)
    target_spec=_spec(ledger,target)
    if ops:
        choices=[op.payload for op in ops if op.op_type in {'ENSURE_NODE','ENSURE_FUNCTION'} and op.payload.get('uid')==target]
        if len(choices)!=1 or target_spec or any(op.op_type not in {'ENSURE_NODE','ENSURE_FUNCTION','MATERIALIZE_USAGE_LINK'} for op in ops): return 'GOAL_FORM_MISMATCH',None,None
        target_spec=choices[0]
    if not target or not target_spec or target_spec.get('semantic_status')=='UNLINKED': return 'GOAL_FORM_MISMATCH',None,None
    from .goal_forms import formula, canonical
    typed_specs={**ledger.data['nodes'],**{op.payload['uid']:op.payload for op in ops if op.op_type in {'ENSURE_NODE','ENSURE_FUNCTION'}}}
    try: typed_signature=digest(canonical(formula(ledger,target,[8192],specs=typed_specs)))
    except (ValueError,KeyError,TypeError): return 'GOAL_FORM_MISMATCH',None,None
    accepted_signatures={target,target_spec.get('content_key'),typed_signature}
    if target_spec.get('proposition'): accepted_signatures.add(digest(target_spec['proposition']))
    if req.conclusion_signature not in accepted_signatures: return 'GOAL_FORM_MISMATCH',None,None
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
    from .goal_forms import formula, substitute, equivalent, check_proof
    budget=[8192]
    try:
        root_formula=formula(ledger,root_support['conclusion_ref'],budget)
        variables={}; body=root_formula
        if req.rule_id=='FORALL_INST':
            if req.instantiation_depth is not None and (type(req.instantiation_depth) is not int or not 1<=req.instantiation_depth<=32):
                return 'GOAL_FORM_MISMATCH',None,None
            while body.get('function_id')=='FORALL' and (req.instantiation_depth is None or len(variables)<req.instantiation_depth):
                operands=body.get('operands',())
                if len(operands)!=2 or not isinstance(operands[0],dict) or 'bound_var' not in operands[0]:
                    return 'GOAL_FORM_MISMATCH',None,None
                name=operands[0]['bound_var']
                if name in variables: return 'GOAL_FORM_MISMATCH',None,None
                variables[name]=operands[0]; body=operands[1]
        if req.rule_id=='FORALL_INST' and req.instantiation_depth is not None and len(variables)!=req.instantiation_depth:
            return 'GOAL_FORM_MISMATCH',None,None
        conditional=body.get('function_id')=='IMPLIES' and len(body.get('operands',()))==2
        if req.rule_id=='MODUS_PONENS' and not conditional: return 'GOAL_FORM_MISMATCH',None,None
        bindings=dict(req.instantiation or {})
        # Legacy atomic requests can infer their single outer binding, but the
        # same full formula checker validates them, not a weaker special case.
        if req.antecedent_proof is None and conditional:
            if len(supports)!=2: return 'GOAL_FORM_MISMATCH',None,None
            other_idx=1-root_idx
            from .goal_forms import unify
            bindings=unify(body['operands'][0],formula(ledger,supports[other_idx]['conclusion_ref'],budget),set(variables),budget,bindings)
            if bindings is None: return 'GOAL_FORM_MISMATCH',None,None
            proof={'kind':'SUPPORT','support_id':supports[other_idx]['record_id']}
        else: proof=req.antecedent_proof
        if set(bindings)!=set(variables) or any(not isinstance(v,str) for v in bindings.values()):
            return 'GOAL_FORM_MISMATCH',None,None
        if core is not None:
            kinds={'ENTITY':{'M'},'VALUE':{'M'},'PROPOSITION':{'N','G'},'EVENT':{'N','G'},'UNKNOWN':{'M','N','G','K'}}
            if any(not core.store.has_uid(v) or core.store.kind_of(v).value not in kinds.get(variables[k].get('sort','ENTITY'),set()) for k,v in bindings.items()):
                return 'GOAL_FORM_MISMATCH',None,None
        expected=substitute(body['operands'][1] if conditional else body,bindings)
        for position in req.conclusion_path:
            if expected.get('function_id')!='AND' or type(position) is not int or not 0<=position<len(expected.get('operands',())):
                return 'GOAL_FORM_MISMATCH',None,None
            expected=expected['operands'][position]
        specs={**ledger.data['nodes'],**{op.payload['uid']:op.payload for op in ops if op.op_type in {'ENSURE_NODE','ENSURE_FUNCTION'}}}
        if not equivalent(expected,formula(ledger,target,budget,specs=specs)):
            return 'GOAL_FORM_MISMATCH',None,None
        # A plan can close this exact formula and its structural links only;
        # auxiliary assertions, entities, unrelated nodes or forged metadata
        # never enter through the goal channel.
        reachable=set()
        def visit(uid):
            if not isinstance(uid,str) or uid in reachable or uid not in specs: return
            reachable.add(uid); n=specs[uid]
            for v in n.get('operands',()) if n.get('function_id') else n.get('actants',{}).values(): visit(v)
        visit(target)
        available=set(ledger.data['nodes']); planned=set()
        for op in ops:
            p=op.payload
            if op.op_type in {'ENSURE_NODE','ENSURE_FUNCTION'}:
                if p['uid'] in planned or core is not None and core.store.has_uid(p['uid']):
                    return 'GOAL_FORM_MISMATCH',None,None
                values=p.get('operands',()) if op.op_type=='ENSURE_FUNCTION' else p.get('actants',{}).values()
                if any(isinstance(v,str) and v not in available and (core is None or not core.store.has_uid(v)) for v in values):
                    return 'GOAL_FORM_MISMATCH',None,None
                planned.add(p['uid']); available.add(p['uid'])
            if op.op_type=='MATERIALIZE_USAGE_LINK':
                parent=specs.get(p.get('parent_ref'),{})
                if p.get('kind')!='OPERATOR' or p.get('parent_ref') not in available or p.get('node_ref') not in available or p.get('parent_ref') not in reachable or p.get('node_ref') not in reachable:
                    return 'GOAL_FORM_MISMATCH',None,None
                position=p.get('position')
                if type(position) is not int or position<0 or position>=len(parent.get('operands',())) or parent['operands'][position]!=p['node_ref']:
                    return 'GOAL_FORM_MISMATCH',None,None
                if p.get('link_id')!='usage:'+digest([p['node_ref'],p['parent_ref'],position,'OPERATOR']):
                    return 'GOAL_FORM_MISMATCH',None,None
            elif p['uid'] not in reachable or p['uid'] in ledger.data['nodes']:
                return 'GOAL_FORM_MISMATCH',None,None
            elif op.op_type=='ENSURE_NODE':
                origin=_spec(ledger,p.get('origin_ref'))
                prototypes=[origin] if origin else [_spec(ledger,supports[root_idx]['conclusion_ref'])]
                if not origin:
                    source=root
                    while source.get('function_id')=='FORALL': source=_spec(ledger,source['operands'][1])
                    prototypes=[_spec(ledger,source.get('operands',[None,None])[1])]
                prototypes=[n for n in prototypes if n.get('template_ref')==p.get('template_ref') and n.get('semantic_status')!='UNLINKED']
                if not any(n.get('temporal_mode')==p.get('temporal_mode') and n.get('proposition',{}).get('predicate')==p.get('proposition',{}).get('predicate') for n in prototypes):
                    return 'GOAL_FORM_MISMATCH',None,None
                if p.get('semantic_status')!='KNOWN' or p.get('proposition',{}).get('actants')!=p.get('actants') or p.get('content_key')!=digest(p['proposition']) or p.get('polarity') is not True:
                    return 'GOAL_FORM_MISMATCH',None,None
            elif op.op_type=='ENSURE_FUNCTION':
                children=p['operands']; fid=p['function_id']
                keys=[specs[v]['content_key'] if isinstance(v,str) and v in specs else digest(v) for v in children]
                ck=keys[0] if fid=='NOT' else digest([fid,keys])
                polarity=not specs[children[0]].get('polarity',True) if fid=='NOT' else True
                if p.get('content_key')!=ck or p.get('polarity')!=polarity:
                    return 'GOAL_FORM_MISMATCH',None,None
        required_links={(p['uid'],i,v) for op in ops if op.op_type=='ENSURE_FUNCTION' for p in [op.payload] for i,v in enumerate(p['operands']) if isinstance(v,str) and v in specs}
        provided_links={(op.payload['parent_ref'],op.payload['position'],op.payload['node_ref']) for op in ops if op.op_type=='MATERIALIZE_USAGE_LINK'}
        if required_links!=provided_links: return 'GOAL_FORM_MISMATCH',None,None
        if conditional:
            used,V,witness=check_proof(ledger,substitute(body['operands'][0],bindings),proof,windows,{a['support_record_id']:a for a in evidence},budget,core)
        else:
            if proof is not None: return 'GOAL_FORM_MISMATCH',None,None
            used,V,witness=set(),W,None
        if used|{root_support['record_id']}!=set(req.premise_support_ids):
            return 'GOAL_FORM_MISMATCH',None,None
        a=next((a for a in evidence if a['support_record_id']==root_support['record_id']),{})
        if not conditional or witness and witness==a.get('witness_ref') and W==V:
            lic=LicenseResult('LICENSED',W)
        else:
            lic=forall_inst_license(W,V)
        return (None,target,lic.derived_region) if lic.status=='LICENSED' else ('GOAL_LICENSE_FAILED',None,None)
    except (ValueError,KeyError,TypeError) as exc:
        return str(exc) if str(exc) in {'GOAL_LICENSE_FAILED','GOAL_PREMISES_STALE','COMPUTATION_LIMIT'} else 'GOAL_FORM_MISMATCH',None,None


def root_id(ledger,req):
    function={'OR_ELIMINATION':'OR','FORALL_INST':'FORALL','MODUS_PONENS':'IMPLIES'}[req.rule_id]
    return next((ledger.data['supports'][p]['conclusion_ref'] for p in req.premise_support_ids if ledger.data['nodes'].get(ledger.data['supports'][p]['conclusion_ref'],{}).get('function_id')==function),None)


def execute(store,req,interleave=None):
    payload=asdict(req)
    payload['conclusion_ops']=[asdict(o) for o in req.conclusion_ops]
    # Preserve hashes of pre-extension requests already in durable journals.
    # New certificate fields are included only when the request uses them.
    for field in ('instantiation','antecedent_proof','rule_root_support_id','instantiation_depth','conclusion_path'):
        if not payload.get(field): payload.pop(field,None)
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
        reason,target,W=validate_goal(ledger,req,store._core)
        legacy_key=key
        if not reason:
            from .goal_forms import formula,canonical,equivalent
            specs={**ledger.data['nodes'],**{op.payload['uid']:op.payload for op in req.conclusion_ops if op.op_type in {'ENSURE_NODE','ENSURE_FUNCTION'}}}
            expected=formula(ledger,target,[8192],specs=specs)
            # Conflict content_key deliberately aliases P and NOT(P). It is
            # therefore not a sufficient identity for a derived proof path.
            typed_signature=digest(canonical(expected))
            key=digest([req.rule_id,sorted(req.premise_support_ids),typed_signature,sorted(req.temporal_premise_assertion_refs)])
        existing=ledger.data['goal_paths'].get(key)
        if existing is None and not reason:
            old=ledger.data['goal_paths'].get(legacy_key)
            if old and equivalent(expected,formula(ledger,old['conclusion_ref'],[8192])):
                existing=old
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
            # Resolve placeholders in dependency order. The complete typed
            # closure stays in this one store transaction with its decision.
            resolved={}; rewritten=[]; positions={}
            def ref(v):
                if isinstance(v,str): return resolved.get(v,v)
                if isinstance(v,list): return [ref(x) for x in v]
                if isinstance(v,dict): return {k:ref(x) for k,x in v.items()}
                return v
            for op in ops:
                p=dict(op.payload); old=p.get('uid')
                if op.op_type=='ENSURE_NODE':
                    p['actants']=ref(p['actants']); p['proposition']={**p['proposition'],'actants':p['actants']}
                    p['content_key']=digest(p['proposition'])
                    candidates=(n.uid for n in store._store.find_hypernodes_by_template(p['template_ref']))
                    shared=next((uid for uid in candidates if p.get('temporal_mode')=='STATE' and ledger.data['nodes'].get(uid,{}).get('content_key')==p['content_key']),None)
                    if shared: resolved[old]=shared; continue
                    if old=='@conclusion':
                        from uuid import uuid4
                        resolved[old]='N:goal:'+uuid4().hex
                    p['uid']=resolved.get(old,old); p['identity_key']=[p['content_key'],sid] if old=='@conclusion' else [p['content_key']]
                elif op.op_type=='ENSURE_FUNCTION':
                    indexed=list(enumerate(ref(p['operands'])))
                    if p['function_id'] in {'AND','OR','XOR'}: indexed.sort(key=lambda pair:str(pair[1]))
                    positions[old]={original:current for current,(original,value) in enumerate(indexed)}
                    p['operands']=[value for original,value in indexed]
                    resolved[old]='G:'+digest([p['function_id'],p['operands']]); p['uid']=resolved[old]
                    child_specs={**ledger.data['nodes'],**{o.payload['uid']:o.payload for o in rewritten if o.op_type in {'ENSURE_NODE','ENSURE_FUNCTION'}}}
                    keys=[child_specs[v]['content_key'] if isinstance(v,str) and v in child_specs else digest(v) for v in p['operands']]
                    p['content_key']=keys[0] if p['function_id']=='NOT' else digest([p['function_id'],keys])
                else:
                    old_parent=p['parent_ref']; old_position=p['position']
                    p['node_ref']=ref(p['node_ref']); p['parent_ref']=ref(p['parent_ref'])
                    parent=next((o.payload for o in rewritten if o.op_type=='ENSURE_FUNCTION' and o.payload['uid']==p['parent_ref']),ledger.data['nodes'].get(p['parent_ref'],{}))
                    p['position']=positions.get(old_parent,{}).get(old_position,old_position)
                    p['link_id']='usage:'+digest([p['node_ref'],p['parent_ref'],p['position'],'OPERATOR'])
                    if p['link_id'] in ledger.data['usage_links']: continue
                if old in resolved and resolved[old] in ledger.data['nodes']: continue
                rewritten.append(StoreOp(op.op_type,p))
            target=ref(target); ops=rewritten
            formula_ref=target
            target_spec=ledger.data['nodes'].get(target,{})
            if not ops and target_spec.get('template_ref') and target_spec.get('temporal_mode')!='STATE':
                from uuid import uuid4
                target='N:goal:'+uuid4().hex
                spec={**target_spec,'uid':target,'formula_ref':formula_ref,'identity_key':[target_spec['content_key'],sid]}
                spec.pop('op_id',None); spec.pop('source_tag',None)
                ops=[StoreOp('ENSURE_NODE',spec)]
            support={'record_id':sid,'conclusion_ref':target,'kind':'DERIVED','rule_id':req.rule_id,'premise_support_refs':sorted(req.premise_support_ids),'temporal_assertion_refs':sorted(req.temporal_premise_assertion_refs),'goal_run_id':req.goal_run_id,'formula_ref':formula_ref,'conclusion_path':list(req.conclusion_path)}
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
