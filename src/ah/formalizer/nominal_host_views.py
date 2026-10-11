"""Render established subtrees as attachment candidates without changing identity."""


def candidates(state,frame,units,hosts,head):
    evidence={e.token_id:e for e in state.evidence}
    roots=set(frame.argument_token_refs)
    roots.update(d['head_ref'] for d in frame.semantic.get('nominal_dependencies',()))
    roots.update(e.token_id for u in units for e,v in u['entities'])
    children={};owned={t:{t} for t in roots}
    owned['EVENT']={frame.predicate_token_ref}
    edges=[]
    def edge(parent,child,kind):
        children.setdefault(parent,set()).add(child)
        edges.append({'parent_ref':parent,'child_ref':child,'kind':kind})
    for t in frame.argument_token_refs:
        edge('EVENT',t,'ARGUMENT')
    for t,unit in frame.semantic.get('lexical_units',{}).items():
        owned.setdefault(t,{t}).update(unit['anchor_refs'])
    for d in frame.semantic.get('nominal_dependencies',()):
        edge(d['host_ref'],d['head_ref'],d['kind'])
    for u in units:
        if u.get('bound_host'):
            owned.setdefault(u['bound_host'],{u['bound_host']}).update(u['refs'])
        if u['entities']:
            tid=u['entities'][0][0].token_id
            # The preposition names the pending relation, not its nominal target.
            owned.setdefault(tid,{tid}).update(a.token_id for a,v in u['adjectives'])
            if tid in hosts:
                edge(hosts[tid],tid,'SELECTED_PP')
                owned[tid].add(u['token'].token_id)
    def subtree(root):
        found=set();pending=[root]
        while pending:
            t=pending.pop()
            if t in found:continue
            found.add(t);pending.extend(children.get(t,()))
        return found
    forbidden=subtree(head)  # a new parent inside this subtree would form a cycle
    result=[]
    for root in ['EVENT',*sorted(roots-forbidden,key=lambda t:evidence[t].start)]:
        nodes=subtree(root)-forbidden
        refs=set().union(*(owned.get(t,{t}) for t in nodes))
        refs=sorted((t for t in refs if t in evidence),key=lambda t:evidence[t].start)
        result.append({'candidate_id':root,'head_ref':frame.predicate_token_ref if root=='EVENT' else root,
            'token_refs':refs,'source_ranges':[[evidence[t].start,evidence[t].end] for t in refs],
            'surface':' '.join(evidence[t].span for t in refs),
            'established_edges':[e for e in edges if e['parent_ref'] in nodes and e['child_ref'] in nodes]})
    return result
