"""Bounded shared-scope prefixes, preserving already selected local nesting."""
from itertools import product


def inventory(selected, by_id):
    modifiers=[];chains=[]
    for i,root in enumerate(selected):
        # Shared-event DAGs need subgroup scope enumeration before lifting
        # through a separate inter-clause conjunction. Never inspect just
        # the lexical carrier and silently discard its sibling branches.
        if root.semantic.get('component_scope_tree',{}).get('operator'):
            raise ValueError('COMPONENT_COORDINATION_SCOPE_INCOMPLETE')
        frame=root;chain=[];seen=set()
        while frame.frame_id.startswith('component-modifier:'):
            if frame.frame_id in seen: raise ValueError('COMPONENT_NOMINAL_CYCLE')
            seen.add(frame.frame_id)
            args=frame.semantic.get('proposition_args',{})
            if len(args)!=1: raise ValueError('COMPONENT_COORDINATION_SCOPE_INCOMPLETE')
            role,child=next(iter(args.items()))
            if child.get('frame_ref') not in by_id: raise ValueError('COMPONENT_COORDINATION_SCOPE_INCOMPLETE')
            chain.append(len(modifiers));modifiers.append((i,frame,role,child))
            frame=by_id[child['frame_ref']]
        chains.append(chain)
    return modifiers,chains


def orders(chains,limit):
    # Each lifted prefix keeps its ancestor relation: inner wrapper first in
    # construction order. Do not enumerate arbitrary factorial permutations
    # and discard almost all of them afterwards.
    result=[]
    def interleave(sequences,prefix):
        if not any(sequences):
            result.append(tuple(prefix))
            if len(result)>limit: raise OverflowError
            return
        for i,seq in enumerate(sequences):
            if seq:
                next_sequences=list(sequences);next_sequences[i]=seq[1:]
                interleave(next_sequences,[*prefix,seq[0]])
    if 1+sum(map(len,chains))>limit: raise OverflowError
    for lengths in product(*(range(len(chain)+1) for chain in chains)):
        interleave([tuple(reversed(chain[:n])) for chain,n in zip(chains,lengths)],[])
    return sorted(result,key=lambda order:(len(order),order))


def scope_label(order,modifiers):
    def name(m):
        i,frame,_,_=modifiers[m]
        return 'M'+str(m+1)+' «'+frame.anchor_span+' '+', '.join(frame.arguments)+'» (from clause '+str(i+1)+')'
    rows=[]
    for m,(i,frame,role,child) in enumerate(modifiers):
        target='both clauses' if m in order else 'only clause '+str(i+1)
        rows.append(name(m)+' applies to '+target)
    if len(order)>1:
        rows.append('shared nesting, inner to outer: '+' then '.join('M'+str(m+1) for m in order))
    return '; '.join(rows) or 'AND joins the listed clauses without an additional shared modifier'
