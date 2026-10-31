"""One component source, shared by scalar and conditional lexical execution."""

def produce(state,release,selector,region,tokens,cfg,depth=0,attachment=None,infinitive=None,request=None):
    from .component_refinement import block,compose_area
    from .component_predication import compose_alternatives
    from .component_area_scope import connectives
    participial=isinstance(attachment,tuple)
    from .action_descriptions import passive_rule
    descriptive=bool(request and request.description_context)
    passive_heads=[t for t in tokens if any(passive_rule(v,cfg) for v in t.variants)]
    # A dependent infinitive requires a possible lexical parent. With no
    # parent, retain the whole area as a predication candidate instead of
    # requiring its object to become a fictitious parent clause.
    has_parent=any(v.pos in {'VERB','ADJS','PRED'} or v.pos=='ADJF' and 'nom' in v.cases
                   for t in tokens for v in t.variants)
    if not passive_heads and has_parent and attachment is None and infinitive is None and (request is None or
            request.output_sort=='PROPOSITION' and request.agreement_source is None):
        from .component_infinitives import compose as compose_infinitive
        nested=compose_infinitive(state,release,selector,region,tokens,cfg,depth,request=request)
        if nested is not None:return nested
    if request is not None and request.output_sort=='EVENT_DESCRIPTION':
        predicates=[]
    elif request is not None and request.agreement_source is not None:
        predicates=[t for t in tokens if any(v.pos=='INFN' for v in t.variants)] + passive_heads
    elif participial:
        predicates=[tokens[0]]
    elif infinitive:
        predicates=[t for t in tokens if any(v.pos=='INFN' for v in t.variants)
                    and (not request or not request.head_ref or request.head_ref==t.token_id)]
    else:
        from .component_predication import impersonal_predicate
        predicates=[t for t in tokens if any(v.pos=='VERB' and v.mood!='imperative' or
            v.pos in cfg.get('quality_predicate_pos',()) or impersonal_predicate(v,cfg) for v in t.variants)]
        from .component_predication import nominal_predicates
        predicates.extend(t for t in [*nominal_predicates(tokens,cfg),*passive_heads] if t not in predicates)
        if descriptive:
            predicates.extend(t for t in tokens if t not in predicates and
                (t in passive_heads or any(v.pos=='INFN' for v in t.variants)))
    nominal_groups=[]
    from .structural_tasks import enabled as structural_enabled
    if structural_enabled(release) or connectives(state,release,region,tokens):
        from .component_nominal_groups import select as select_nominal_groups
        nominal_groups=select_nominal_groups(state,release,selector,region,tokens,cfg)
        if nominal_groups is False:
            return block(state,region,[],'COMPONENT_NOMINAL_COORDINATION_UNRESOLVED')
    if nominal_groups is None:
        from .component_coordination import coordinate
        return coordinate(state,release,selector,region,tokens,predicates,cfg,[],
            compose_child=lambda area,owned:compose_area(state,release,selector,area,owned,cfg,depth+1,request=request),
            inside_attitude=bool(request and request.inside_attitude))
    frames=compose_alternatives(state,release,selector,region,tokens,predicates,cfg,attachment=attachment,nominal_groups=nominal_groups,infinitive=infinitive,request=request)
    for f in frames:
        f.semantic['owned_token_refs']=[t.token_id for t in tokens]
    return frames
