"""Bounded on-demand compiler over typed canonical propositions and support IDs."""
from __future__ import annotations
from itertools import islice, product
from uuid import uuid4
from .canonical_ledger import digest
from .goal_executor import GoalRequest
from .goal_channel import execute
from .store_interface import StoreOp

MAX_PATH_COMBINATIONS=64


def _options(ledger,node_id):
    live=ledger.paths()
    for sid,s in sorted(ledger.data['supports'].items()):
        if sid not in live or s['conclusion_ref']!=node_id: continue
        dated=[aid for aid,a in sorted(ledger.data['assertions'].items()) if a['support_record_id']==sid and ledger.evidence_live({'record_id':aid})]
        for aid in dated or [None]: yield sid,aid


def prove_node(store,node_id,*,point=None,window=None):
    ledger=store.ledger
    if ledger.query_proposition(node_id,point=point,window=window)['answer']=='YES': return
    spec=ledger.data['nodes'].get(node_id,{})
    if spec.get('semantic_status')=='UNLINKED': return
    remaining=MAX_PATH_COMBINATIONS
    for rid,root in sorted(ledger.data['nodes'].items()):
        if root.get('function_id')!='OR' or node_id not in root.get('operands',()): continue
        not_nodes=[]
        for other in root['operands']:
            if other==node_id: continue
            options=[(sid,aid) for nid,n in sorted(ledger.data['nodes'].items()) if n.get('function_id')=='NOT' and n.get('operands')==[other] for sid,aid in _options(ledger,nid)]
            not_nodes.append(options)
        for combo in islice(product(list(_options(ledger,rid)),*not_nodes),remaining):
            remaining-=1
            supports=tuple(p for p,a in combo); assertions=tuple(a for p,a in combo if a is not None)
            execute(store,GoalRequest('goal:'+uuid4().hex,'OR_ELIMINATION',supports,spec['content_key'],temporal_premise_assertion_refs=assertions,conclusion_ref=node_id,request_window=window or ((point,point) if point is not None else None)))
            ledger=store.ledger
            if ledger.query_proposition(node_id,point=point,window=window)['answer']=='YES': return
            if remaining<=0: return ('COMPUTATION_LIMIT',)


def prove_instances(store,template_uid,known_roles,*,point=None,window=None):
    """Instantiate only consequents selected by this template/argument goal."""
    ledger=store.ledger; remaining=MAX_PATH_COMBINATIONS
    for rid,root in sorted(ledger.data['nodes'].items()):
        if root.get('function_id')!='FORALL' or len(root.get('operands',()))!=2: continue
        body=ledger.data['nodes'].get(root['operands'][1],{})
        if body.get('function_id')!='IMPLIES' or len(body.get('operands',()))!=2: continue
        ant=ledger.data['nodes'].get(body['operands'][0],{}); con=ledger.data['nodes'].get(body['operands'][1],{})
        if con.get('template_ref')!=template_uid or con.get('semantic_status')=='UNLINKED': continue
        variable=root['operands'][0].get('bound_var') if isinstance(root['operands'][0],dict) else None
        if variable is None: continue
        for actual in store._store.find_hypernodes_by_template(ant.get('template_ref','')):
            premise=ledger.data['nodes'].get(actual.uid,{})
            if not premise: continue
            substitution={}
            def unify(pattern,value):
                if isinstance(pattern,dict) and 'bound_var' in pattern:
                    if pattern['bound_var']!=variable: return False
                    if variable in substitution: return substitution[variable]==value
                    substitution[variable]=value; return True
                if isinstance(pattern,dict): return isinstance(value,dict) and set(pattern)==set(value) and all(unify(pattern[k],value[k]) for k in pattern)
                return pattern==value
            if not unify(ant.get('proposition',{}),premise.get('proposition',{})): continue
            def replace(value):
                if isinstance(value,dict) and 'bound_var' in value: return substitution.get(value['bound_var'])
                if isinstance(value,dict): return {k:replace(v) for k,v in value.items()}
                return value
            proposition=replace(con.get('proposition',{})); roles=proposition.get('actants',{})
            if any(v is None for v in roles.values()) or any(roles.get(k)!=v for k,v in known_roles.items()): continue
            signature=digest(proposition)
            target=next((uid for uid,n in ledger.data['nodes'].items() if n.get('content_key')==signature and n.get('temporal_mode')=='STATE'),None)
            spec={**con,'uid':'@conclusion','actants':roles,'proposition':proposition,'content_key':signature,'identity_key':[signature]}
            spec.pop('op_id',None); spec.pop('source_tag',None)
            ops=() if target else (StoreOp('ENSURE_NODE',spec),)
            for combo in islice(product(list(_options(ledger,rid)),list(_options(ledger,actual.uid))),remaining):
                remaining-=1
                outcome=execute(store,GoalRequest('goal:'+uuid4().hex,'FORALL_INST',tuple(p for p,a in combo),signature,temporal_premise_assertion_refs=tuple(a for p,a in combo if a is not None),conclusion_ref=target,conclusion_ops=ops,request_window=window or ((point,point) if point is not None else None)))
                ledger=store.ledger
                if outcome['outcome'] in {'APPLIED','APPLIED_NOOP'} and ledger.query(outcome['conclusion_ref'],point=point,window=window)['answer']=='YES': break
                if remaining<=0: return ('COMPUTATION_LIMIT',)
