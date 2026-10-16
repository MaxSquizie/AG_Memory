"""Versioned observations; no lexical guessing or access to expected answers."""
from ah.formalizer.canonical_ledger import digest, region, region_data

CONTRACT = 'v7-observer-3'


def modern(session):
    return getattr(session,'observer_contract','v7-observer-1') in {'v7-observer-2','v7-observer-3'}


def queries(session,state,release,coverage):
    """Observe the production query compiler, not the generator's candidate set."""
    if discourse(state)['modus'] not in {'QUERY','MIXED'}:
        return {'status':'NOT_APPLICABLE','formulas':[],'records':[],'blockers':[]}
    from ah.formalizer.native_queries import project_native_queries,compile_native_queries,Pattern,QueryVar
    from ah.agent import InteractionContext
    from tools.formalizer_v7_native_binding import decode_native
    import json
    roots=project_native_queries(state,release)
    context=InteractionContext()
    for name in ('user_ref','self_ref'):
        ref=state.observation.get(name)
        if ref:setattr(context,name,session.core.ref(ref))
    built=compile_native_queries(session.core,roots,context)
    def decode(value):
        if isinstance(value,QueryVar):return {'query_var':value.name,'sort':value.sort.value}
        if not isinstance(value,Pattern):return decode_native(session,value)
        if value.operator:
            children=[decode(v) for v in value.members]
            if value.operator in {'AND','OR','XOR'}:children.sort(key=lambda v:json.dumps(v,sort_keys=True))
            return {'operator':value.operator,'operands':children}
        if value.lexical_anchor:
            predicate=open_predicate(value.source_refs);roles={r.value:r.value for r,v in value.actants}
        else:predicate,roles=session.native_aliases[value.template_ref]
        return {'predicate':predicate,'roles':{roles.get(r.value,r.value):decode(v) for r,v in value.actants}}
    records=[];formulas=[];blockers=[]
    for root,result in zip(roots,built):
        row={'tree':root.tree,'request':root.request,'temporal':root.temporal,'diagnostics':list(result.diagnostics),
             'compiled':result.goal is not None}
        if result.goal is not None:
            target=result.goal.goal.target
            pattern=getattr(target,'pattern',None)
            if pattern is None:
                row['compiled']=False;blockers.append('QUERY_OBSERVATION_TARGET_UNSUPPORTED')
            else:
                row['formula']=decode(pattern);formulas.append(row['formula'])
        else:blockers.extend(result.diagnostics)
        records.append(row)
    if not roots:blockers.append('QUERY_ROOT_MISSING')
    if coverage['level'] not in {'FULL_CANONICAL','OPEN_LEXICAL'}:blockers.append('QUERY_SOURCE_INCOMPLETE')
    return {'status':'COMPILED' if roots and not blockers else 'BLOCKED','formulas':session.unique(formulas),
            'records':records,'blockers':sorted(set(blockers))}


def open_predicate(source_refs):
    if not source_refs:
        raise ValueError('OPEN_SOURCE_NOT_RECORDED')
    return {'open_source': list(source_refs)}


def discourse(state):
    roots = state.observation.get('discourse_roots', [])
    acts = {row['speech_act'] for row in roots}
    act = next(iter(acts)) if len(acts) == 1 else 'MIXED' if acts else 'UNKNOWN'
    requested=state.observation.get('request_kind')
    if requested in {'QUERY','COMMAND','UNKNOWN'}:act=requested
    return {'modus': 'DECLARATIVE' if act == 'ASSERTION' else act,
            'roots': roots, 'host_request_kind': requested}


def temporal(state, release, assertions):
    """Expose selected sources and verify the normalizer's current input API.

    Expected calendar values remain authored in the independent corpus. This
    observation is a source-licence check, not an independent calendar oracle.
    """
    from ah.formalizer.temporal_functions import normalize
    licenses = []
    allowed = set()
    for frame in state.frames:
        if frame.semantic.get('structural_unresolved'):
            continue
        for unit in frame.semantic.get('temporal_functions', ()):
            value, errors = normalize(state, release, unit)
            licenses.append({'frame_ref': frame.frame_id, 'source_range': unit['source_range'],
                'token_refs': unit['token_refs'], 'proofs': unit['proofs'],
                'region': value, 'errors': errors})
            if value is not None and not errors:
                allowed.add(digest(region_data(region(value))))
    # Explicit typed time slots carry their normalization before seal too.
    for frame in state.frames:
        value=frame.semantic.get('explicit_region')
        if value is not None and not frame.semantic.get('structural_unresolved'):
            allowed.add(digest(region_data(region(value))))
    invented = [a for a in assertions
        if a['provenance']['source'].get('source_tag') == [state.source_uid, state.interpretation_version]
        and digest(region_data(region(a['region']))) not in allowed]
    return {'invented_past_intervals': invented, 'clock_default_used': False,
            'licenses': licenses}
