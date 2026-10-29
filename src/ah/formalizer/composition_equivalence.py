"""Conservative equality of explicit atomic interpretations across producers.

Producer identity is provenance, not a linguistic alternative. Equality here
is deliberately stricter than logical equivalence: no scope, implicit identity,
role, lexical sense or linked morphology may be inferred by this comparison.
"""
from copy import deepcopy
from .canonical_ledger import digest


_BOOKKEEPING={
    'nominal_host_evidence','function_inventory_refs','hypothesis','grammar_ambiguity','composition_source','composition_source_ref',
    'source_frame_ref','component_region','composition_decision','composition_bundle_root',
    'composition_domain','structural_unresolved','requires_attachment_probe','reading_domains',
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
    for group in data.get('nominal_groups',()):group.pop('source_evidence',None)
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
    from .probe_wording import role as role_text,reading as reading_text
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
        args=[role_text(role)+'='+word(tid) for tid,role in sorted(sem.get('proposed_roles',{}).items())]
        args.extend(role_text(role)+'='+tree(slot.get('tree') or {'frame_ref':slot.get('frame_ref')},seen)+
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
            readings.append(word(tid)+': '+reading_text(m))
    return text+'; linked readings: '+'; '.join(dict.fromkeys(readings))


_EMPTY_COMPONENT_FIELDS={'pp_readings':{},'group_readings':{},
                         'nominal_dependencies':[],'attribute_constraints':[]}


def component_signature(bundle):
    """Exact alpha-renaming of a complete component graph, not logical inference.

    Unknown fields participate in equality. Only declared administrative fields,
    checked proof annotations and known empty defaults are normalized away.
    """
    from dataclasses import asdict
    refs={f.frame_id:'frame:'+str(i) for i,f in enumerate(bundle)}
    if len(refs)!=len(bundle):return None
    for i,f in enumerate(bundle):
        for role,gap in f.semantic.get('implicit_arguments',{}).items():
            refs[gap['gap_id']]='frame:'+str(i)+'|gap:'+role
    def normalize(value):
        if isinstance(value,str):return refs.get(value,value)
        if isinstance(value,dict):return {refs.get(k,k):normalize(v) for k,v in value.items()}
        if isinstance(value,(list,tuple)):return [normalize(v) for v in value]
        return value
    result=[]
    for f in bundle:
        row=asdict(f);sem=row['semantic']
        # The original frame/provenance records are retained in the receipt.
        row.pop('provenance',None);row.pop('rank',None)
        for key in _BOOKKEEPING:sem.pop(key,None)
        # Future producer admission is a union of capabilities, not a reading
        # of this source. coalesce_components preserves that union below.
        sem.pop('allowed_proposition_roles',None)
        if sem.get('action_description') is not None:
            # Licensing provenance differs between a released and an open
            # producer of the same explicit action/role arrangement.
            sem['action_description'].pop('valency_digest',None)
            sem['action_description'].pop('valency_digests',None)
        for key,empty in _EMPTY_COMPONENT_FIELDS.items():
            if sem.get(key) is None or sem.get(key)==empty:sem.pop(key,None)
        questions=[]
        for q in sem.get('component_questions',[]):
            if (q.get('kind')=='FIXED_DEPENDENCY' and q.get('token_ref') in sem.get('proposed_roles',{})
                    and q.get('ground') in {'D','M'} and q.get('selected') in q.get('remaining_domain_ids',())):continue
            questions.append(q)
        sem['component_questions']=questions
        result.append(normalize(row))
    return digest(result)


def coalesce_components(state,region,bundles):
    from dataclasses import asdict
    seen={};retained=[];duplicates=set()
    for bundle in bundles:
        signature=component_signature(bundle)
        if signature is None or signature not in seen:
            retained.append(bundle)
            if signature is not None:seen[signature]=bundle
            continue
        representative=seen[signature]
        duplicates.add(bundle[-1].frame_id)
        capabilities=[]
        for target,other in zip(representative,bundle):
            a=target.semantic.get('allowed_proposition_roles');b=other.semantic.get('allowed_proposition_roles')
            joined=None if a is None or b is None else sorted(set(a)|set(b))
            capabilities.append({'frame_ref':target.frame_id,'producer_domains':[a,b],'union':joined})
            target.semantic['allowed_proposition_roles']=joined
            if target.semantic.get('action_description') is not None:
                def licences(frame):
                    description=frame.semantic['action_description']
                    return set(description.get('valency_digests',()))|{description.get('valency_digest')}
                domains=[licences(target),licences(other)]
                joined_digests=sorted((domains[0]|domains[1])-{None})
                target.semantic['action_description']['valency_digests']=joined_digests
                capabilities[-1]['action_valency_domains']=[sorted(d-{None}) for d in domains]
                capabilities[-1]['action_valency_union']=joined_digests
        state.syntax_trace.append({'kind':'COMPONENT_EQUIVALENT_INTERPRETATIONS','region_ref':region.region_id,
            'signature':signature,'representative_ref':representative[-1].frame_id,
            'equivalent_ref':bundle[-1].frame_id,'capability_union':capabilities,'proof_frames':[asdict(f) for f in bundle]})
    return retained,duplicates
