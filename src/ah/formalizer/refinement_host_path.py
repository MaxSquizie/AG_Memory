"""Check a nominal host inside a scoped description, never by global lookup."""


def node_path(child, frames, nodes, *, root_node=None, operations=()):
    if child.get('tree'):
        target=nodes[child.get('host_frame_ref',child['frame_ref'])]
        links=[o.payload for o in operations if o.op_type=='MATERIALIZE_USAGE_LINK' and o.payload['kind'] in {'ATTITUDE','OPERATOR'}]
        def paths(node,seen):
            if node in seen:raise ValueError('CYCLIC_PROPOSITION_ARGUMENT')
            if node==target:return [[node]]
            return [[node,*tail] for nxt in sorted({l['node_ref'] for l in links if l['parent_ref']==node})
                    for tail in paths(nxt,seen|{node})]
        found=paths(root_node,set())
        if len(found)!=1:raise ValueError('NOMINAL_HOST_PATH_AMBIGUOUS' if found else 'NOMINAL_HOST_UNRESOLVED')
        return found[0]
    start=child['frame_ref']; target=child.get('host_frame_ref',start)
    def visit(fid, seen):
        if fid in seen: raise ValueError('CYCLIC_PROPOSITION_ARGUMENT')
        if fid==target: return [nodes[fid]]
        found=[]
        for edge in frames[fid].semantic.get('proposition_args',{}).values():
            if 'frame_ref' not in edge: continue
            tail=visit(edge['frame_ref'],seen|{fid})
            if tail: found.append([nodes[fid],*tail])
        if len(found)>1: raise ValueError('NOMINAL_HOST_PATH_AMBIGUOUS')
        return found[0] if found else None
    result=visit(start,set())
    if not result: raise ValueError('NOMINAL_HOST_UNRESOLVED')
    return result


def validate_path(payload, ledger):
    path=payload.get('host_path',[payload.get('node_ref')])
    if not path or path[0]!=payload.get('node_ref') or len(set(path))!=len(path):
        raise ValueError('NOMINAL_HOST_PATH_INVALID')
    if not live(payload,ledger): raise ValueError('NOMINAL_HOST_PATH_INVALID')
    return path[-1]


def live(payload,ledger):
    path=payload.get('host_path',[payload.get('node_ref')])
    links=ledger.data['usage_links'].values()
    for parent,child in zip(path,path[1:]):
        if not any(l.get('parent_ref')==parent and l.get('node_ref')==child and
                   l.get('kind') in {'ATTITUDE','OPERATOR'} and l.get('status')=='LIVE' and
                   (l.get('kind')=='OPERATOR' or l.get('source_tag')==payload.get('source_tag')) for l in links):
            return False
    return True
