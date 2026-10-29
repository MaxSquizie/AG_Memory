"""Grammar constraints supplied to the shared domain engine."""
from collections import defaultdict
from itertools import combinations
from .composition_domains import DomainNetwork


def compatible(left_id, left, right_id, right, shared_slot=False):
    if left['kind']==right['kind']=='ROOT' and left['role']==right['role']:
        if not shared_slot:return False
    if shared_slot:
        # Selected predicate-slot coordination is one argument, not two
        # competing ROOT roles. Each member keeps its own dependent domain.
        if left['kind']!=right['kind'] or left.get('role')!=right.get('role'):return False
        if left['kind']!='ROOT':return False
        from .component_nominal_groups import compatible_cases
        if not compatible_cases([left['morph'],right['morph']]):return False
    if left.get('host_ref')==right_id and right.get('host_ref')==left_id:
        return False
    for dependent,host,host_id in ((left,right,right_id),(right,left,left_id)):
        if dependent.get('host_ref')==host_id:
            # Domains were proposed before the host reading was selected. A
            # noun homonym cannot remain a nominal host after choosing ADJF.
            if host.get('morph',{}).get('pos') not in {'NOUN','NPRO'}:return False
            if 'host_morph' in dependent:
                field='head_morph' if dependent.get('host_layer')=='HEAD' else 'morph'
                if host.get(field)!=dependent['host_morph']:return False
    return True


def network(pool, nominal_groups=()):
    result=DomainNetwork(pool);edges=set();roles=defaultdict(set)
    for tid,choices in pool.items():
        for option in choices.values():
            if option['kind']=='ROOT':roles[option['role']].add(tid)
            if option.get('host_ref') in pool:
                edges.add(tuple(sorted((tid,option['host_ref']))))
    for variables in roles.values():edges.update(combinations(sorted(variables),2))
    shared={tuple(sorted(pair)) for g in nominal_groups for pair in combinations(g["member_refs"],2)}
    edges.update(shared)
    for a,b in sorted(edges):
        result.connect(a,b,lambda left,right,a=a,b=b:compatible(a,left,b,right,(a,b) in shared),
                       'NOMINAL_ROLE_AGREEMENT_AND_PARENT')
    return result


def propagate(graph, fixed, alternatives=None):
    for tid,option in fixed.items():
        from .component_dependency_domains import key
        if not graph.restrict(tid,[key(v) for v in (alternatives or {}).get(tid,[option])],'FIXED_SOURCE_DEPENDENCY'):return False
    while graph.propagate():
        changed=False
        # Longer cycles are a global tree invariant, separate from pairwise
        # compatibility. Only established edges can exclude such a candidate.
        for tid,choices in graph.domains.items():
            allowed=[]
            for cid,option in choices.items():
                cursor=option.get('host_ref');seen={tid}
                while cursor is not None and cursor not in seen:
                    seen.add(cursor);cursor=fixed.get(cursor,{}).get('host_ref')
                if cursor is None:allowed.append(cid)
            if len(allowed)!=len(choices):
                changed=True
                if not graph.restrict(tid,allowed,'ACYCLIC_NOMINAL_PARENT'):return False
        if not changed:return True
    return False
