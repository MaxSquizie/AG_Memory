"""Build typed recursive nominal descriptions and event scopes from questions."""
from copy import deepcopy
from itertools import permutations
from math import factorial
from .canonical_ledger import digest
from .component_policy import _morph
from .component_phrases import prepositional_groups
from .state import FrameCandidate


def bundles(state,release,selector,region,tokens,frame,cfg):
    from .component_modifier_forest import nominal_variants,unique
    from .component_nominal_questions import select_units,select_hosts
    from .nominal_prefix_descriptions import pending_refs
    missing=set(frame.semantic['uncovered_token_refs'])|pending_refs(frame,tokens)
    limit=cfg['max_candidates']
    deps=frame.semantic.get('nominal_dependencies',[])
    if (not missing and not deps) or frame.semantic['missing_required_roles']:
        return [[frame]]
    if missing or deps: frame.semantic['structural_unresolved']=True  # must discharge every pending description
    try:
        from .nominal_prefix_descriptions import units as prefix_units
        units=list(prefix_units(tokens,missing,frame))
        from .nominal_residual_descriptions import units as residual_units
        units.extend(list(residual_units(tokens,missing,frame,units)))
        from .implicit_descriptions import units as implicit_units
        units.extend(implicit_units(tokens,missing,frame,cfg))
        from .qualitative_quantity import units as quantity_units
        quantities=list(quantity_units(tokens,missing,frame))
        units.extend(quantities)
        quantity_refs={t for u in quantities for t in u['refs']}
        for group in prepositional_groups(tokens).values():
            if set(group['anchor_refs'])<=missing: units.extend(nominal_variants(tokens,group,limit))
        for e in tokens:
            if e.token_id in missing and e.token_id not in quantity_refs:
                units.extend({'token':e,'variant':v,'refs':(e.token_id,),'entities':[],'adjectives':[]}
                             for v in unique(v for v in e.variants if v.pos=='ADVB'))
        covers=[]
        def visit(remaining,chosen):
            if not remaining:
                covers.append(chosen)
                if len(covers)>limit: raise OverflowError
                return
            first=next(e.token_id for e in tokens if e.token_id in remaining)
            for u in units:
                if first in u['refs'] and set(u['refs'])<=remaining:
                    visit(remaining-set(u['refs']),[*chosen,u])
        visit(missing,[])
    except OverflowError:
        state.diag('COMPONENT_SEARCH_INCOMPLETE',region.region_id);return [[frame]]
    if not covers: return [[frame]]
    if region.source_range[1]-region.source_range[0]>cfg['context_chars']:
        state.diag('COMPONENT_SEARCH_INCOMPLETE',region.region_id);return [[frame]]
    units=select_units(state,release,selector,region,covers,frame,cfg)
    if units is None: return [[frame]]
    if any(u.get('requires_host_probe') for u in units):
        frame.semantic['requires_attachment_probe']=True
    hosts=select_hosts(state,release,selector,region,units,frame,cfg)
    if hosts is None: return [[frame]]
    event=[u for u in units if not u.get('bound_host') and not u.get('implicit_host_role') and (not u['entities'] or hosts[u['entities'][0][0].token_id]=='EVENT')]
    if cfg.get('modifier_scope')=='SHARED_EVENT_V1' and len(event)>1:
        from .modifier_scope_shapes import shapes
        try: topology=shapes(len(event),limit)
        except OverflowError:
            state.diag('COMPONENT_SEARCH_INCOMPLETE',region.region_id);return [[frame]]
        return [materialize(state,region,tokens,frame,units,hosts,event,cfg,shape=s) for s in topology]
    if factorial(len(event))>limit:
        state.diag('COMPONENT_SEARCH_INCOMPLETE',region.region_id);return [[frame]]
    return [materialize(state,region,tokens,frame,units,hosts,order,cfg) for order in permutations(event)]


def materialize(state,region,tokens,original,units,hosts,order,cfg,*,shape=None):
    from .component_modifiers import wrap
    signature=[(u['refs'],_morph(u['variant']),u.get('bound_host'),u.get('host_reading'),u.get('implicit_host_role'),[(e.token_id,_morph(v)) for e,v in
                 [*u['entities'],*u['adjectives']]]) for u in units]
    seed=digest([original.frame_id,signature,hosts,[u['refs'] for u in order],*([shape] if shape else [])])
    base=deepcopy(original);base.frame_id='component-nominal:'+seed
    base.semantic['uncovered_token_refs']=[];base.semantic['structural_unresolved']=False
    base.semantic['component_questions']=[q for q in base.semantic['component_questions']
        if q['kind'] not in {'UNRESOLVED_COMPONENT','RELATION_TO_EVENT'}]
    for role,gap in base.semantic.get('implicit_arguments',{}).items():
        old=gap['gap_id'];gap['gap_id']='gap:'+digest([base.frame_id,role])
        for q in base.semantic['component_questions']:
            if q.get('gap_id')==old:q['gap_id']=gap['gap_id']
    evidence={e.token_id:e for e in state.evidence}; frames=[base]; owners={t:base for t in base.argument_token_refs}
    morphology=deepcopy(base.semantic['morph_bindings']); lexical=deepcopy(base.semantic['lexical_units'])
    for u in units:
        for e,v in u['entities']:
            refs=[a.token_id for a,av in u['adjectives']]+[e.token_id]
            lexical[e.token_id]={'head_ref':e.token_id,'anchor_refs':refs,
                'surface':state.text[evidence[refs[0]].start:e.end],
                'mention_ref':e.token_id if len(refs)==1 else 'mention:'+digest(refs)}
            morphology[e.token_id]=_morph(v)
    def describe(token,variant,roles):
        fid='component-description:'+digest([seed,token.token_id,roles,_morph(variant)])
        sem={'proposed_roles':roles,'morph_bindings':{token.token_id:_morph(variant),
            **{t:morphology[t] for t in roles}},'lexical_units':{t:deepcopy(lexical[t]) for t in roles},
            'preposition_bindings':{},'missing_required_roles':[],'requires_attachment_probe':False,
            'uncovered_token_refs':[],'structural_unresolved':False,'relative_temporal':[],
            'component_region':region.region_id,'component_questions':[], 'nominal_description':True,
            'qualitative_groups':[deepcopy(g) for g in base.semantic.get('qualitative_groups',()) if g['head_ref'] in roles]}
        f=FrameCandidate(fid,'FLAT',token.span,(token.span,*[evidence[t].span for t in roles]),
            tuple(evidence[t].span for t in roles),construction='COMPONENTS_V1',predicate_token_ref=token.token_id,
            argument_token_refs=tuple(roles),source_range=tuple(region.source_range),semantic=sem,provenance=base.provenance)
        frames.append(f);return f
    from .component_dependency_materialization import prepare_entities,describe_dependencies
    prepare_entities(base.semantic.get('nominal_dependencies',()),evidence,morphology,lexical)
    pending=[]
    describe_dependencies(base.semantic.get('nominal_dependencies',()),describe,evidence,owners,pending,cfg)
    for u in units:
        if not u['entities']:continue
        head=u['entities'][0][0].token_id;host=hosts[head]
        if host!='EVENT':
            f=describe(u['token'],u['variant'],{host:cfg['nominal_host_role'],head:cfg['preposition_nominal_role']})
            owners[head]=f;pending.append((host,f))
    root=base
    def apply(unit,inner,content=None):
        outer=wrap(inner,region,unit['token'],unit['variant'],cfg['modifier_content_role'],
            entities=unit['entities'],nominal_role=cfg['preposition_nominal_role'] if unit['entities'] else None)[-1]
        if content is not None:
            outer.semantic['proposition_args'][cfg['modifier_content_role']]={'tree':content,'attitude':'UNKNOWN'}
        for e,v in unit['entities']:
            outer.semantic['lexical_units'][e.token_id]=deepcopy(lexical[e.token_id]);owners[e.token_id]=outer
        frames.append(outer)
        return outer
    if shape is None:
        for u in order:root=apply(u,root)
    else:
        from .modifier_scope_shapes import label
        def build(s):
            if s is None:return {'frame_ref':base.frame_id},base
            if s[0]=='AND':
                children=[build(child) for child in s[1]]
                return {'operator':'AND','operands':[t for t,f in children]},children[-1][1]
            content,inner=build(s[2])
            outer=apply(order[s[1]],inner,content if 'operator' in content else None)
            return {'frame_ref':outer.frame_id},outer
        scope,root=build(shape)
        # The carrier is a lexical frame too. The explicit tree, rather than
        # component_child, owns all roots and shared edges of this alternative.
        root.semantic.pop('component_child',None)
        root.semantic['component_scope_tree']=scope
        root.semantic['component_scope_label']=label(shape,base.anchor_span,order)
    for u in units:
        if u.get('implicit_host_role'):
            from .implicit_descriptions import materialize as implicit_description
            frames.append(implicit_description(u,base,region,cfg))
        if u.get('bound_host'):
            from .nominal_prefix_descriptions import host_role as prefix_role
            head=u['bound_host'];role=prefix_role(u,cfg)
            if role is None:
                base.semantic['structural_unresolved']=True
                state.diag('PARTICIPLE_PROJECTION_UNRESOLVED',u['token'].token_id)
                continue
            f=describe(u['token'],u['variant'],{head:role})
            f.semantic['nominal_host_role']=role;pending.append((head,f))
        for adj,av in u['adjectives']:
            head=u['entities'][0][0].token_id
            host_role=cfg['nominal_host_role']
            if av.pos=='PRTF':
                from .participial_roles import projection
                projected=projection(av,(u['entities'][0][0],u['entities'][0][1]),cfg)
                if projected is None:
                    base.semantic['structural_unresolved']=True
                    state.diag('PARTICIPLE_PROJECTION_UNRESOLVED',adj.token_id)
                    continue
                host_role=projected['rule']['host_role']
            f=describe(adj,av,{head:host_role});f.semantic['nominal_host_role']=host_role;pending.append((head,f))
    for host,child in pending:
        parent=owners[host];child.semantic['component_child']=parent.frame_id
        parent.semantic.setdefault('nominal_args',[]).append({'host_token_ref':host,
            'host_role':child.semantic.get('nominal_host_role',cfg['nominal_host_role']),'frame_ref':child.frame_id})
        parent.semantic['component_questions'].append({'kind':'NOMINAL_DESCRIPTION','host_token_ref':host,
            'description_ref':child.frame_id,'anchor_ref':child.predicate_token_ref,'independently_asserted':False})
    return [f for f in frames if f is not root]+[root]
