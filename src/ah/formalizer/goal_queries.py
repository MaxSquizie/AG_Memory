"""Indexed, bounded ordinary rule compiler with concrete premise certificates."""
from itertools import islice, product
from uuid import uuid4

from .canonical_ledger import digest
from .goal_executor import GoalRequest
from .goal_channel import execute
from .goal_forms import (formula, canonical, equivalent, unify, substitute,
                         indexed_matches, spend, BINDERS)
from .native_records import record_index
from .store_interface import StoreOp

MAX_PATH_COMBINATIONS = 64


def _options(store, node_id, budget):
    ledger=store.ledger; index=record_index(store._core,ledger); live=ledger.paths()
    for sid in sorted(index['supports'].get(node_id,())):
        spend(budget)
        if sid not in live: continue
        aids=index['assertions'].get(sid,())
        if not aids:
            yield sid,None
        else:
            for aid in sorted(aids):
                spend(budget)
                if ledger.evidence_live({'record_id':aid}): yield sid,aid
    # Having dated assertions which are all retracted is NOT an undated path.


def _values(store, form, names, budget):
    """Overapproximate from typed leaves; final certificates prove full scope."""
    result={name:set() for name in names}; ledger=store.ledger
    def walk(p,active):
        if not isinstance(p,dict): return
        if 'template_ref' in p:
            for node in store._store.find_hypernodes_by_template(p['template_ref']):
                spend(budget); spec=ledger.data['nodes'].get(node.uid,{})
                actual=spec.get('actants',{})
                for role,v in p['actants'].items():
                    if isinstance(v,dict) and v.get('bound_var') in active:
                        uid=actual.get(role)
                        if isinstance(uid,str) and store._store.has_uid(uid):
                            sort=v.get('sort','ENTITY')
                            if sort=='ENTITY' and store._store.kind_of(uid).value!='M': continue
                            result[v['bound_var']].add(uid)
                            if len(result[v['bound_var']])>1024: raise ValueError('COMPUTATION_LIMIT')
        ops=p.get('operands',())
        if p.get('function_id') in BINDERS and ops and isinstance(ops[0],dict): active=active-{ops[0].get('bound_var')}
        for v in ops: walk(v,active)
        for v in p.get('actants',{}).values(): walk(v,active)
    walk(form,set(names))
    return result


def _instantiate(store, source_ref, bindings, budget):
    """Close a typed consequent graph; the writer assigns new root IDs."""
    ledger=store.ledger; ops=[]; emitted={}; cache={}
    def build(uid,local,root=False):
        spend(budget)
        if not isinstance(uid,str):
            return substitute(uid,local),digest(substitute(uid,local))
        if uid not in ledger.data['nodes']: return uid,digest(uid)
        key=(uid,digest(local),root)
        if key in cache: return cache[key]
        source=ledger.data['nodes'][uid]
        if source.get('semantic_status')=='UNLINKED': raise ValueError('OPEN_LEXICAL_INFERENCE_FORBIDDEN')
        if source.get('function_id'):
            fid=source['function_id']; local=dict(local)
            if fid in BINDERS and source['operands'] and isinstance(source['operands'][0],dict):
                local.pop(source['operands'][0].get('bound_var'),None)
            children=[build(v,local) for v in source['operands']]
            if fid in {'AND','OR','XOR'}: children.sort(key=lambda x:str(x[0]))
            operands=[u for u,c in children]
            ck=children[0][1] if fid=='NOT' else digest([fid,[c for u,c in children]])
            node_id='G:'+digest([fid,operands])
            payload={'uid':node_id,'function_id':fid,'operands':operands,'content_key':ck,
                     'polarity':source.get('polarity',True),'origin_ref':uid}
            op_type='ENSURE_FUNCTION'
        else:
            roles={r:build(v,local)[0] for r,v in source['actants'].items()}
            proposition={**source['proposition'],'actants':roles}; ck=digest(proposition)
            if roles==source['actants']:
                node_id=uid
            else:
                node_id='@conclusion' if root and source.get('temporal_mode')!='STATE' else 'N:'+digest([ck])
            payload={k:v for k,v in source.items() if k not in {'op_id','source_tag','source_ref'}}
            payload.update(uid=node_id,actants=roles,proposition=proposition,content_key=ck,
                           identity_key=[ck],origin_ref=uid)
            op_type='ENSURE_NODE'
        if node_id not in ledger.data['nodes'] and node_id not in emitted:
            emitted[node_id]=payload; ops.append(StoreOp(op_type,payload))
            if op_type=='ENSURE_FUNCTION':
                for position,child in enumerate(payload['operands']):
                    if not isinstance(child,str) or child not in ledger.data['nodes'] and child not in emitted: continue
                    ops.append(StoreOp('MATERIALIZE_USAGE_LINK',{'link_id':'usage:'+digest([child,node_id,position,'OPERATOR']),
                               'node_ref':child,'parent_ref':node_id,'position':position,'kind':'OPERATOR'}))
        cache[key]=(node_id,ck)
        return node_id,ck
    target,signature=build(source_ref,bindings,True)
    return target,signature,tuple(ops)


class Search:
    def __init__(self,store,budget=None,point=None,window=None):
        self.store=store; self.budget=budget if budget is not None else [4096]
        self.point=point; self.window=window; self.attempts=0

    def _run(self,rule,root_option,proof,support_options,source_ref,bindings=None,target=None,conclusion_path=()):
        self.attempts+=1; spend(self.budget)
        if self.attempts>MAX_PATH_COMBINATIONS: raise ValueError('COMPUTATION_LIMIT')
        if target is None:
            target,signature,ops=_instantiate(self.store,source_ref,bindings or {},self.budget)
        else:
            spec=self.store.ledger.data['nodes'][target]; signature=spec['content_key']; ops=()
        selected=[root_option,*support_options]
        supports=tuple(sorted({sid for sid,aid in selected}))
        assertions=tuple(sorted({aid for sid,aid in selected if aid is not None}))
        result=execute(self.store,GoalRequest('goal:'+uuid4().hex,rule,supports,signature,
            temporal_premise_assertion_refs=assertions,conclusion_ref=target,
            conclusion_ops=ops,instantiation=tuple(sorted((bindings or {}).items())),antecedent_proof=proof,
            rule_root_support_id=root_option[0],conclusion_path=conclusion_path,instantiation_depth=len(bindings or {}) if rule=='FORALL_INST' else None,request_window=self.window or ((self.point,self.point) if self.point is not None else None)))
        return result

    def _rules(self,form):
        # Symbolic heads have the same typed shape. Free variables of each
        # stored head are matched later, rather than globally scanning rules.
        seeds=set()
        def seed(p):
            if not isinstance(p,dict): return
            if 'template_ref' in p:
                for n in self.store._store.find_hypernodes_by_template(p['template_ref']):
                    spend(self.budget); seeds.add(n.uid)
            for x in p.get('operands',()): seed(x)
            for x in p.get('actants',{}).values(): seed(x)
        seed(form)
        visited=set(); frontier=sorted(seeds); roots=[]
        while frontier:
            uid=frontier.pop(); spend(self.budget)
            if uid in visited: continue
            visited.add(uid)
            for parent in self.store._store.function_parents(uid):
                spend(self.budget); spec=self.store.ledger.data['nodes'].get(parent.uid,{})
                fid=spec.get('function_id'); args=spec.get('operands',())
                if fid=='IMPLIES' and len(args)==2 and args[1]==uid:
                    roots.append((parent.uid,(),parent.uid))
                    queue=[(parent.uid,())]
                    while queue:
                        body,variables=queue.pop()
                        for universal in self.store._store.function_parents(body):
                            spend(self.budget); n=self.store.ledger.data['nodes'].get(universal.uid,{})
                            if n.get('function_id')=='FORALL' and len(n['operands'])==2 and n['operands'][1]==body:
                                var=n['operands'][0]
                                if not isinstance(var,dict) or 'bound_var' not in var: continue
                                name=var['bound_var']
                                if name in variables: continue
                                names=(name,*variables); roots.append((universal.uid,names,parent.uid)); queue.append((universal.uid,names))
                                if len(names)>32: raise ValueError('COMPUTATION_LIMIT')
                # Walk typed content ancestors to reach composite consequents;
                # do not climb through a rule's antecedent to unrelated heads.
                elif fid!='IMPLIES':
                    if fid=='FORALL' and len(args)==2 and args[1]==uid and isinstance(args[0],dict) and 'bound_var' in args[0]:
                        variables=[args[0]['bound_var']]; body=uid
                        n=self.store.ledger.data['nodes'].get(body,{})
                        if n.get('function_id')!='IMPLIES': roots.append((parent.uid,tuple(variables),body))
                        while n.get('function_id')=='FORALL' and len(n.get('operands',()))==2 and isinstance(n['operands'][0],dict):
                            name=n['operands'][0].get('bound_var')
                            if name is None or name in variables: break
                            variables.append(name); body=n['operands'][1]; n=self.store.ledger.data['nodes'].get(body,{})
                            if len(variables)>32: raise ValueError('COMPUTATION_LIMIT')
                            if n.get('function_id')!='IMPLIES': roots.append((parent.uid,tuple(variables),body))
                    if parent.uid not in visited: frontier.append(parent.uid)
        return tuple(dict.fromkeys(roots))

    def certificates(self,expected,seen=frozenset(),depth=0):
        spend(self.budget)
        if depth>32: raise ValueError('COMPUTATION_LIMIT')
        key=digest(canonical(expected)); local=seen|{key}
        matches=indexed_matches(self.store._core,self.store.ledger,expected,self.budget)
        yielded=set()
        for uid,env in matches:
            for sid,aid in _options(self.store,uid,self.budget):
                yielded.add((sid,aid)); yield {'kind':'SUPPORT','support_id':sid},((sid,aid),)
        if key not in seen:
            for uid,env in matches: self.prove_node(uid,seen,depth+1)
            self.derive(expected,local,depth+1)
            for uid,env in indexed_matches(self.store._core,self.store.ledger,expected,self.budget):
                for sid,aid in _options(self.store,uid,self.budget):
                    if (sid,aid) not in yielded: yield {'kind':'SUPPORT','support_id':sid},((sid,aid),)
        if not isinstance(expected,dict): return
        fid=expected.get('function_id'); members=expected.get('operands',())
        if fid=='AND':
            groups=[list(islice(self.certificates(m,local,depth+1),65)) for m in members]
            for combo in islice(product(*groups),65):
                spend(self.budget)
                rows=tuple(x for p,rows in combo for x in rows)
                # One certificate cannot select two different assertion IDs of
                # the same support: those are different realizations/paths.
                if any(len({a for s,a in rows if s==sid})>1 for sid,a in rows): continue
                yield {'kind':'AND','children':[p for p,rows in combo]},rows
        elif fid=='OR':
            for i,m in enumerate(members):
                for proof,rows in self.certificates(m,local,depth+1): yield {'kind':'OR','position':i,'child':proof},rows
        elif fid=='EXISTS' and len(members)==2 and isinstance(members[0],dict):
            var=members[0]['bound_var']; choices=_values(self.store,members[1],(var,),self.budget)[var]
            for value in sorted(choices):
                for proof,rows in self.certificates(substitute(members[1],{var:value}),local,depth+1):
                    yield {'kind':'EXISTS','value':value,'child':proof},rows

    def derive(self,expected,seen=frozenset(),depth=0,constraints=None):
        spend(self.budget)
        if depth>32: raise ValueError('COMPUTATION_LIMIT')
        for root_id,variables,body_id in self._rules(expected):
            root_options=list(_options(self.store,root_id,self.budget))
            if not root_options: continue
            body=self.store.ledger.data['nodes'][body_id]
            if body.get('function_id')=='IMPLIES': ante,con=body['operands']
            else: ante=None; con=body_id
            for head,path in self._heads(con):
                found=self._derive_head(expected,root_id,variables,ante,head,path,seen,depth,constraints)
                if found is not None: return found
        return None

    def _heads(self,uid,path=()):
        spend(self.budget)
        yield uid,path
        node=self.store.ledger.data['nodes'].get(uid,{})
        if node.get('function_id')=='AND':
            for i,child in enumerate(node['operands']):
                yield from self._heads(child,(*path,i))

    def _derive_head(self,expected,root_id,variables,ante,con,path,seen,depth,constraints):
        root_options=list(_options(self.store,root_id,self.budget))
        con_form=formula(self.store.ledger,con,self.budget)
        if constraints is None:
            bound=unify(con_form,expected,set(variables),self.budget)
            if bound is None: return None
        else:
            if con_form.get('template_ref')!=constraints[0]: return None
            bound={}; compatible=True
            for role,value in constraints[1].items():
                item=con_form['actants'].get(role)
                if isinstance(item,dict) and item.get('bound_var') in variables:
                    old=bound.setdefault(item['bound_var'],value)
                    if old!=value: compatible=False; break
                elif item!=value: compatible=False; break
            if not compatible: return None
        ante_form=formula(self.store.ledger,ante,self.budget) if ante else {}
        missing=set(variables)-set(bound)
        values=_values(self.store,substitute(ante_form,bound),missing,self.budget) if missing else {}
        for combo in product(*(sorted(values[v]) for v in sorted(missing))):
            spend(self.budget); bindings={**bound,**dict(zip(sorted(missing),combo))}
            concrete=substitute(ante_form,bindings)
            certificates=self.certificates(concrete,seen,depth+1) if ante else [(None,())]
            for proof,rows in islice(certificates,65):
                for option in root_options:
                    result=self._run('FORALL_INST' if variables else 'MODUS_PONENS',option,proof,rows,con,bindings,conclusion_path=path)
                    if result['outcome'] in {'APPLIED','APPLIED_NOOP'}:
                        yield_ref=result['conclusion_ref']
                        if self.store.ledger.query(yield_ref,point=self.point,window=self.window)['answer']=='YES': return yield_ref
        return None

    def prove_node(self,node_id,seen=frozenset(),depth=0):
        spend(self.budget); ledger=self.store.ledger
        if ledger.query_proposition(node_id,point=self.point,window=self.window)['answer']=='YES': return node_id
        spec=ledger.data['nodes'].get(node_id,{})
        if not spec or spec.get('semantic_status')=='UNLINKED': return None
        form=formula(ledger,node_id,self.budget); key=digest(canonical(form))
        if key in seen and depth>1: return None
        local=seen|{key}
        for parent in self.store._store.function_parents(node_id):
            spend(self.budget); root=self.store.ledger.data['nodes'].get(parent.uid,{})
            if root.get('function_id')!='OR': continue
            groups=[list(_options(self.store,parent.uid,self.budget))]
            for other in root['operands']:
                if other==node_id: continue
                negatives=[]
                for neg in self.store._store.function_parents(other):
                    spend(self.budget); n=self.store.ledger.data['nodes'].get(neg.uid,{})
                    if n.get('function_id')=='NOT' and n.get('operands')==[other]:
                        self.prove_node(neg.uid,local,depth+1)
                        negatives.extend(_options(self.store,neg.uid,self.budget))
                groups.append(negatives)
            for combo in islice(product(*groups),65):
                result=self._run('OR_ELIMINATION',combo[0],None,combo[1:],node_id,target=node_id)
                if result['outcome'] in {'APPLIED','APPLIED_NOOP'} and self.store.ledger.query_proposition(node_id,point=self.point,window=self.window)['answer']=='YES': return result['conclusion_ref']
        return self.derive(form,local,depth+1)


def prove_node(store,node_id,*,point=None,window=None,budget=None):
    try: Search(store,budget,point,window).prove_node(node_id)
    except ValueError as exc:
        if str(exc)=='COMPUTATION_LIMIT': return ('COMPUTATION_LIMIT',)
        if str(exc)!='OPEN_LEXICAL_INFERENCE_FORBIDDEN': raise


def prove_instances(store,template_uid,known_roles,*,point=None,window=None,budget=None):
    try:
        search=Search(store,budget,point,window)
        seed={'template_ref':template_uid,'actants':known_roles}
        search.derive(seed,constraints=(template_uid,known_roles))
    except ValueError as exc:
        if str(exc)=='COMPUTATION_LIMIT': return ('COMPUTATION_LIMIT',)
        if str(exc)!='OPEN_LEXICAL_INFERENCE_FORBIDDEN': raise


def prove_pattern(store,pattern,*,point=None,window=None,budget=None):
    from .goal_forms import from_pattern
    try:
        expected=from_pattern(pattern); search=Search(store,budget,point,window)
        for uid,env in indexed_matches(store._core,store.ledger,expected,search.budget):
            found=search.prove_node(uid)
            if found and store.ledger.query(found,point=point,window=window)['answer']=='YES': return found
        return search.derive(expected)
    except ValueError as exc:
        if str(exc) in {'GOAL_FORM_MISMATCH','OPEN_LEXICAL_INFERENCE_FORBIDDEN'}: return None
        raise
