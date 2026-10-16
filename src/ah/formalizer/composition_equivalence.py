"""Conservative equality of explicit atomic interpretations across producers.

Producer identity is provenance, not a linguistic alternative. Equality here
is deliberately stricter than logical equivalence: no scope, implicit identity,
role, lexical sense or linked morphology may be inferred by this comparison.
"""
from copy import deepcopy
from .canonical_ledger import digest


_BOOKKEEPING={
    'hypothesis','grammar_ambiguity','composition_source','composition_source_ref',
    'source_frame_ref','component_region','composition_decision','composition_bundle_root',
    'composition_domain','structural_unresolved',
}


def atomic_signature(state,release,root,owned):
    if len(owned)!=1 or owned[0] is not root or root.kind!='FLAT':return None
    if root.construction not in {'GRAMMAR','COMPONENTS_V1'}:return None
    sem=root.semantic
    if any(sem.get(k) for k in ('implicit_arguments','proposition_args','bound_arguments',
            'operator_forest','component_scope_tree','preposition_bindings','missing_required_roles',
            'uncovered_token_refs','pending_proposition_roles','query_request','structural_rejection')):
        return None
    reading=sem.get('morph_bindings',{}).get(root.predicate_token_ref,{})
    if reading.get('pos')!='VERB':return None
    evidence={e.token_id:e for e in state.evidence}
    from .native_frontend import _bindings
    senses={r['sense_id'] for r in release.entries('R-S')
            if r['lemma']==reading['lemma'] and r['POS']==reading['pos']}
    # GRAMMAR and COMPONENTS_V1 have different PP admission checks. Include
    # the resulting valency bindings, even when there is no sealed PP field.
    bindings=[(digest(v),_bindings(root,evidence,v)) for v in release.entries('R-V')
              if v['sense_id'] in senses]
    data=deepcopy(sem)
    for key in _BOOKKEEPING:data.pop(key,None)
    questions=data.pop('component_questions',[])
    for q in questions:
        if q=={'kind':'WHAT_EVENT','anchor_ref':root.predicate_token_ref}:continue
        # A completed direct-role reduction records how the same role was
        # obtained. The resulting roles/readings are still compared below.
        if (q.get('kind')=='FIXED_DEPENDENCY' and q.get('token_ref') in sem.get('proposed_roles',{})
                and q.get('ground') in {'D','M'} and q.get('selected') in q.get('remaining_domain_ids',())):
            continue
        return None
    units=data.setdefault('lexical_units',{})
    for tid in (root.predicate_token_ref,*root.argument_token_refs):
        units.setdefault(tid,{'head_ref':tid,'anchor_refs':[tid],
                             'surface':evidence[tid].span,'mention_ref':tid})
    from .morphology_domain import clean
    data['morph_bindings']={tid:clean(m) for tid,m in data.get('morph_bindings',{}).items()}
    data={k:v for k,v in data.items() if v not in (None,False,[],{},())}
    return digest([root.kind,root.predicate_token_ref,sorted(root.argument_token_refs),
                   root.source_range,root.copula_ellipsis,root.attachment,data,bindings])


def coalesce(state,release,region,bundles):
    seen={};retained=[];duplicates=set()
    for root,owned,label in bundles:
        signature=atomic_signature(state,release,root,owned)
        if signature is None or signature not in seen:
            retained.append((root,owned,label))
            if signature is not None:seen[signature]=root
            continue
        representative=seen[signature]
        duplicates.add(root.frame_id)
        state.syntax_trace.append({'kind':'COMPOSITION_EQUIVALENT_SOURCES',
            'region_ref':region.region_id,'source_range':list(region.source_range),
            'representative_ref':representative.frame_id,'equivalent_ref':root.frame_id,
            'signature':signature,'predicate_ref':root.predicate_token_ref,
            'roles':deepcopy(root.semantic['proposed_roles']),
            'sources':[{'source':f.semantic.get('composition_source','COMPONENT'),
                        'frame_ref':f.frame_id,'pattern_ids':list(f.provenance.pattern_ids),
                        'component_questions':deepcopy(f.semantic.get('component_questions',[])),
                        'resource_versions':dict(f.provenance.resource_versions)}
                       for f in (representative,root)],
            'reason':'SAME_EXPLICIT_ATOMIC_INTERPRETATION'})
    return retained,duplicates


def describe(state,root,owned):
    """Expose semantic distinctions instead of asking a model to pick code paths."""
    evidence={e.token_id:e for e in state.evidence};by_id={f.frame_id:f for f in owned}
    def word(tid):
        e=evidence.get(tid)
        return '«'+e.span+'» @'+str(e.start) if e else str(tid)
    def tree(node,seen=frozenset()):
        if 'frame_ref' in node:
            fid=node['frame_ref']
            if fid in seen:return '[recursive reference]'
            return frame(by_id[fid],seen|{fid}) if fid in by_id else '[external child]'
        if 'operator' in node:
            return node['operator']+'('+', '.join(tree(n,seen) for n in node.get('operands',()))+')'
        if 'bound_var' in node:return 'bound variable '+str(node['bound_var'])
        return str(node)
    def frame(f,seen):
        sem=f.semantic
        args=[role+'='+word(tid) for tid,role in sorted(sem.get('proposed_roles',{}).items())]
        args.extend(role+'='+tree(slot.get('tree') or {'frame_ref':slot.get('frame_ref')},seen)+
                    ' ['+slot.get('attitude','UNKNOWN')+']' for role,slot in sem.get('proposition_args',{}).items())
        args.extend(role+'=omitted, identity unresolved' for role in sem.get('implicit_arguments',{}))
        args.extend(role+'=unspecified in action description' for role in sem.get('action_description',{}).get('unassigned_roles',()))
        args.extend(word(tid)+'=bound variable '+str(var) for tid,var in sem.get('bound_arguments',{}).items())
        args.extend('preposition '+pp['lemma']+' for '+word(tid) for tid,pp in sem.get('preposition_bindings',{}).items())
        senses=sorted({str(spec.get('sense_id') or spec.get('label')) for spec in sem.get('candidate_specs',{}).values()})
        return word(f.predicate_token_ref)+'('+', '.join(args)+')'+(' senses: '+', '.join(senses) if senses else '')
    expression=root.semantic.get('component_scope_tree')
    forest=root.semantic.get('operator_forest',())
    text=tree(expression) if expression else tree(forest[0]) if len(forest)==1 else frame(root,frozenset({root.frame_id}))
    readings=[]
    for f in owned:
        for tid,m in sorted(f.semantic.get('morph_bindings',{}).items()):
            value=word(tid)+': '+str(m.get('lemma'))+' / '+str(m.get('pos'))
            features=[k+'='+str(m[k]) for k in ('cases','number','gender','person','tense','mood') if m.get(k)]
            readings.append(value+(' ('+', '.join(features)+')' if features else ''))
    return text+'; linked readings: '+'; '.join(dict.fromkeys(readings))
