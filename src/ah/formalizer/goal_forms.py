"""Typed formula algebra and independently checked compositional premises.

Certificates name existing proof records, never new truth grounds. Universal
restrictions require a proof of the whole quantified formula; enumerating the
currently stored entities does not establish a closed domain.
"""
from copy import deepcopy

from .canonical_ledger import digest, region
from .temporal_license import forall_inst_license, normalize

COMMUTATIVE = {'AND', 'OR', 'XOR'}
BINDERS = {'FORALL', 'EXISTS', 'AT_LEAST_N', 'EXACTLY_N', 'AT_MOST_N'}


def spend(budget):
    budget[0] -= 1
    if budget[0] < 0:
        raise ValueError('COMPUTATION_LIMIT')


def formula(ledger, uid, budget, *, specs=None, seen=frozenset()):
    spend(budget)
    if not isinstance(uid, str):
        return deepcopy(uid)
    nodes = ledger.data['nodes'] if specs is None else specs
    n = nodes.get(uid)
    if n is None:
        return uid
    if uid in seen or len(seen) >= 32:
        raise ValueError('GOAL_FORM_MISMATCH')
    if n.get('semantic_status') == 'UNLINKED':
        raise ValueError('OPEN_LEXICAL_INFERENCE_FORBIDDEN')
    seen = seen | {uid}
    def child(v):
        return formula(ledger, v, budget, specs=nodes, seen=seen)
    if n.get('function_id'):
        return {'function_id': n['function_id'], 'operands': [child(v) for v in n['operands']]}
    return {'template_ref': n['template_ref'], 'actants': {r: child(v) for r,v in n['actants'].items()}}


def from_pattern(p):
    from ah.model import Ref, BoundVar, TimeLiteral, CountLiteral
    from .native_queries import Pattern
    if isinstance(p, Ref): return p.uid
    if isinstance(p, BoundVar): return {'bound_var': p.local_id, 'sort': p.sort.value}
    if isinstance(p, TimeLiteral): return {'time_literal': list(p.bounds)}
    if isinstance(p, CountLiteral): return {'count_literal': p.value}
    if not isinstance(p, Pattern) or p.lexical_anchor or p.occurrence_ref is not None:
        raise ValueError('GOAL_FORM_MISMATCH')
    if p.operator:
        return {'function_id': p.operator, 'operands': [from_pattern(m) for m in p.members]}
    return {'template_ref': p.template_ref, 'actants': {r.value: from_pattern(v) for r,v in p.actants}}


def substitute(value, bindings):
    if not isinstance(value, dict): return deepcopy(value)
    if 'bound_var' in value: return deepcopy(bindings.get(value['bound_var'], value))
    local = bindings
    ops = value.get('operands', ())
    if value.get('function_id') in BINDERS and ops and isinstance(ops[0], dict) and 'bound_var' in ops[0]:
        local = {k:v for k,v in bindings.items() if k != ops[0]['bound_var']}
    return {k: [substitute(x, local) for x in v] if isinstance(v, list)
            else substitute(v, local) for k,v in value.items()}


def canonical(value, env=None):
    env = {} if env is None else env
    if isinstance(value, list): return [canonical(v, env) for v in value]
    if not isinstance(value, dict): return value
    if 'bound_var' in value:
        return {'bound_var': env.get(value['bound_var'], ('free', value['bound_var'])), 'sort': value.get('sort','ENTITY')}
    ops = value.get('operands')
    if ops is not None:
        local = dict(env)
        if value.get('function_id') in BINDERS and ops and isinstance(ops[0],dict) and 'bound_var' in ops[0]:
            local[ops[0]['bound_var']] = len(env)
        children = [canonical(v, local) for v in ops]
        if value['function_id'] in COMMUTATIVE: children.sort(key=digest)
        return {'function_id': value['function_id'], 'operands': children}
    return {k: canonical(v,env) for k,v in value.items()}


def equivalent(a, b):
    return canonical(a) == canonical(b)


def unify(a, b, variables, budget, bindings=None):
    """Only declared outer variables bind; nested binders remain scoped."""
    result = {} if bindings is None else dict(bindings)
    def match(x,y,alpha):
        spend(budget)
        if isinstance(x,dict) and 'bound_var' in x:
            name = x['bound_var']
            if name in alpha:
                return isinstance(y,dict) and y.get('bound_var') == alpha[name] and y.get('sort','ENTITY') == x.get('sort','ENTITY')
            if name in variables:
                if not isinstance(y,str): return False
                return result.setdefault(name,y) == y
            return x == y
        if not isinstance(x,dict): return x == y
        if not isinstance(y,dict) or set(x) != set(y): return False
        if 'operands' in x:
            if x['function_id'] != y['function_id'] or len(x['operands']) != len(y['operands']): return False
            xx,yy = list(x['operands']),list(y['operands']); local = dict(alpha)
            if x['function_id'] in BINDERS:
                if not xx or not isinstance(xx[0],dict) or not isinstance(yy[0],dict): return False
                if 'bound_var' not in xx[0] or 'bound_var' not in yy[0] or xx[0].get('sort','ENTITY') != yy[0].get('sort','ENTITY'): return False
                local[xx[0]['bound_var']] = yy[0]['bound_var']; xx,yy = xx[1:],yy[1:]
            if x['function_id'] in COMMUTATIVE:
                def pair(left,right):
                    spend(budget)
                    if not left: return True
                    for i,v in enumerate(right):
                        old = dict(result)
                        if match(left[0],v,local) and pair(left[1:],right[:i]+right[i+1:]): return True
                        result.clear(); result.update(old)
                    return False
                return pair(xx,yy)
            return all(match(v,w,local) for v,w in zip(xx,yy))
        return all(match(x[k],y[k],alpha) for k in x)
    return result if match(a,b,{}) else None


def indexed_matches(core, ledger, form, budget, variables=()):
    """Template seeds and reverse G indexes, never a global node scan."""
    if not isinstance(form,dict): return ()
    def candidates(p):
        if 'template_ref' in p:
            result=[]
            for n in core.store.find_hypernodes_by_template(p['template_ref']):
                spend(budget); result.append(n.uid)
            return result
        child=next((v for v in p.get('operands',()) if isinstance(v,dict) and ('template_ref' in v or 'function_id' in v)),None)
        if child is None: return []
        result=set()
        for uid in candidates(child):
            for parent in core.store.function_parents(uid):
                spend(budget)
                if ledger.data['nodes'].get(parent.uid,{}).get('function_id')==p.get('function_id'): result.add(parent.uid)
        return sorted(result)
    ids=candidates(form)
    result = []
    for uid in ids:
        spend(budget)
        if uid not in ledger.data['nodes']: continue
        try: actual = formula(ledger,uid,budget)
        except ValueError as exc:
            if str(exc) == 'OPEN_LEXICAL_INFERENCE_FORBIDDEN': continue
            raise
        env = unify(form,actual,variables,budget)
        if env is not None: result.append((uid,env))
        if len(result) > 1024: raise ValueError('COMPUTATION_LIMIT')
    return tuple(result)


def check_proof(ledger, expected, proof, windows, evidence, budget, core=None):
    """Verify full antecedent against named live supports inside commit lock."""
    spend(budget)
    if not isinstance(proof,dict): raise ValueError('GOAL_FORM_MISMATCH')
    kind = proof.get('kind')
    if kind == 'SUPPORT':
        sid = proof.get('support_id'); support = ledger.data['supports'].get(sid)
        if not support or not equivalent(expected,formula(ledger,support['conclusion_ref'],budget)):
            raise ValueError('GOAL_FORM_MISMATCH')
        witness = evidence.get(sid,{}).get('witness_ref')
        return {sid}, windows.get(sid,region()), witness
    fid = expected.get('function_id') if isinstance(expected,dict) else None
    ops = expected.get('operands',()) if isinstance(expected,dict) else ()
    if kind == 'AND' and fid == 'AND' and len(proof.get('children',())) == len(ops):
        rows = [check_proof(ledger,x,y,windows,evidence,budget,core) for x,y in zip(ops,proof['children'])]
        supports = set().union(*(s for s,r,w in rows)); common = rows[0][1] if rows else None
        witness = rows[0][2] if rows else None
        for s,r,w in rows[1:]:
            if witness and witness == w and common == r: continue
            lic = forall_inst_license(common,r)
            if lic.status != 'LICENSED': raise ValueError('GOAL_LICENSE_FAILED')
            common = normalize(lic.derived_region); witness = None
        if common is None: raise ValueError('GOAL_FORM_MISMATCH')
        return supports,common,witness
    if kind == 'OR' and fid == 'OR' and type(proof.get('position')) is int and 0 <= proof['position'] < len(ops):
        return check_proof(ledger,ops[proof['position']],proof.get('child'),windows,evidence,budget,core)
    if kind == 'EXISTS' and fid == 'EXISTS' and len(ops)==2 and isinstance(ops[0],dict) and isinstance(proof.get('value'),str):
        if core is not None:
            kinds={'ENTITY':{'M'},'VALUE':{'M'},'PROPOSITION':{'N','G'},'EVENT':{'N','G'},'UNKNOWN':{'M','N','G','K'}}
            if not core.store.has_uid(proof['value']) or core.store.kind_of(proof['value']).value not in kinds.get(ops[0].get('sort','ENTITY'),set()):
                raise ValueError('GOAL_FORM_MISMATCH')
        return check_proof(ledger,substitute(ops[1],{ops[0]['bound_var']:proof['value']}),proof.get('child'),windows,evidence,budget,core)
    raise ValueError('GOAL_FORM_MISMATCH')
