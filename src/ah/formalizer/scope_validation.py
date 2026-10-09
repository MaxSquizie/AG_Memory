"""Close the binder environment at the final factual write boundary.

Structural bodies may contain variables. The supported root, rather than each
individual N/G record, owns their scope, so validation follows typed content
edges from factual roots and never grants truth to a structural operand.
"""
from .goal_forms import BINDERS


def validate_asserted_scopes(ledger):
    nodes=ledger.data['nodes'];budget=[100000]
    def walk(value,bound,ancestors):
        budget[0]-=1
        if budget[0]<0:raise ValueError('COMPUTATION_LIMIT')
        if isinstance(value,dict):
            if 'bound_var' in value:
                if value['bound_var'] not in bound:raise ValueError('SCOPE_NOT_COVERED: free variable')
            return
        if not isinstance(value,str) or value not in nodes:return
        if value in ancestors:raise ValueError('SCOPE_NOT_COVERED: cyclic proposition')
        node=nodes[value];ancestors=ancestors|{value}
        op=node.get('function_id');members=node.get('operands',())
        if op in BINDERS:
            arity=3 if op in {'AT_LEAST_N','EXACTLY_N','AT_MOST_N'} else 2
            if len(members)!=arity or not isinstance(members[0],dict) or 'bound_var' not in members[0]:
                raise ValueError('SCOPE_NOT_COVERED: malformed binder')
            var=members[0]['bound_var']
            if var in bound:raise ValueError('SCOPE_NOT_COVERED: multiple active binders')
            if not isinstance(members[1],str) or members[1] not in nodes:
                raise ValueError('SCOPE_NOT_COVERED: untyped quantified body')
            walk(members[1],bound|{var},ancestors)
            for child in members[2:]:walk(child,bound,ancestors)
            return
        for child in members:walk(child,bound,ancestors)
        for child in node.get('actants',{}).values():walk(child,bound,ancestors)
    paths=ledger.paths()
    for sid in sorted(paths):
        walk(ledger.data['supports'][sid]['conclusion_ref'],frozenset(),frozenset())
