"""Whole-clause alternatives across predicate POS; no early lexical winner."""
from .component_policy import _features, _morph, compatible
from .component_clause import build_clause
from .component_probe import _probe


def consume_copula(tokens, predicate, variant, cfg, used, morph):
    """A released copula is grammatical evidence, not a second world event."""
    choices = [(e, v) for e in tokens if e.token_id not in used for v in e.variants
               if v.pos == 'VERB' and v.mood != 'imperative'
               and v.lemma in cfg.get('copula_lemmas', ())
               and compatible(_features(variant), _features(v))]
    unique = {(e.token_id, tuple(sorted((k, str(val)) for k, val in _morph(v).items()
                                      if k != 'score'))): (e, v) for e, v in choices}
    if len(unique) != 1:
        return None
    e, v = next(iter(unique.values()))
    used.add(e.token_id)
    morph[e.token_id] = _morph(v)
    return e.token_id


def compose_alternatives(state, release, selector, region, tokens, predicates, cfg, *, attachment=None, nominal_groups=(), infinitive=None):
    from .component_modifiers import scoped_bundle
    from .contextual_name_case import overlay as coordinated_readings
    from .contextual_preposition_case import overlay as governed_readings
    tokens=governed_readings(state,release,selector,region,coordinated_readings(tokens,nominal_groups),cfg)
    if tokens is None:return []
    bundles = []
    diagnostics_before = len(state.diagnostics)
    for predicate in predicates:
        for frame in build_clause(state, release, selector, region, tokens, predicate, cfg, select=False, attachment=attachment, nominal_groups=nominal_groups,infinitive=infinitive):
            if cfg.get('modifier_composition')=='BOUNDED_FOREST_V1':
                from .component_modifier_forest import bundles as modifier_bundles
                if cfg.get('nominal_composition')=='QUESTION_TREE_V1':
                    from .component_nominal_tree import bundles as nominal_bundles
                    bundles.extend(nominal_bundles(state,release,selector,region,tokens,frame,cfg))
                else:
                    bundles.extend(modifier_bundles(state,region,tokens,frame,cfg))
            else:
                bundles.append(scoped_bundle(state, release, region, tokens, frame, cfg))
    frames = [f for bundle in bundles for f in bundle]
    complete = [b for b in bundles if all(not f.semantic['structural_unresolved'] for f in b)]
    incomplete_search = any(d.code in {'COMPONENT_SEARCH_INCOMPLETE','COMPONENT_NOMINAL_SELECTION_UNRESOLVED',
        'COMPONENT_DEPENDENCY_UNRESOLVED','COMPONENT_NOMINAL_SEGMENTATION_UNRESOLVED','COMPONENT_NOMINAL_CYCLE','COMPONENT_NOMINAL_HOST_UNRESOLVED'} and d.detail==region.region_id
                            for d in state.diagnostics[diagnostics_before:])
    if incomplete_search or len(complete) > cfg['max_candidates']:
        state.diag('COMPONENT_SEARCH_INCOMPLETE', region.region_id)
        for frame in frames:
            frame.semantic['structural_unresolved'] = True
        return frames
    # Partial alternatives stay addressable but cannot masquerade as a complete
    # source interpretation. Each complete choice includes every child frame.
    needs_probe = len(bundles) > 1 or any(f.semantic['requires_attachment_probe'] for f in frames)
    chosen = complete[0][-1].frame_id if len(complete) == 1 and not needs_probe else None
    from .component_source import view
    raw = view(state,region,tokens)
    if complete and needs_probe and len(raw) <= cfg['context_chars']:
        evidence = {e.token_id:e for e in state.evidence}
        options = []
        for bundle in complete:
            labels = []
            for f in bundle:
                m = f.semantic['morph_bindings'][f.predicate_token_ref]
                roles = ', '.join(role+'='+evidence[tid].span for tid, role in f.semantic['proposed_roles'].items())
                label = f.semantic.get('nominal_dependency_kind',m['lemma'])+' ['+m['pos']+']; '+roles
                if cfg.get('modifier_composition')=='BOUNDED_FOREST_V1':
                    label += '; linked morphology='+str({evidence[t].span:{k:v for k,v in morph.items()
                        if k in {'lemma','pos','cases','gender','number'}} for t,morph in f.semantic['morph_bindings'].items()})
                if f.semantic.get('nominal_groups'):
                    label += '; one coordinated slot per group='+str([
                        [evidence[t].span for t in g['member_refs']] for g in f.semantic['nominal_groups']])
                if f.semantic.get('shared_implicit_arguments'):
                    label += '; uses the SAME omitted participant slot: '+str(f.semantic['shared_implicit_arguments'])+'; no new participant or identity'
                if f.semantic.get('implicit_arguments'):
                    label += '; omitted roles, identity unresolved='+str(list(f.semantic['implicit_arguments']))
                if f.semantic.get('copula_ref'):
                    label += '; copula='+evidence[f.semantic['copula_ref']].span
                if f.semantic.get('nominal_args'):
                    by_id={item.frame_id:item for item in bundle}
                    label += '; nominal descriptions='+str([{'host':evidence[c['host_token_ref']].span if 'host_token_ref' in c else 'omitted '+c['host_implicit_role']+' of '+f.anchor_span,
                        'description':by_id[c['frame_ref']].anchor_span} for c in f.semantic['nominal_args']])
                if f.semantic.get('relative_temporal'):
                    label += '; relative anchors='+str(f.semantic['relative_temporal'])
                labels.append(label)
            if any(r['kind'] in {'WORD_CLOCK','CLOCK_RANGE'} for r in release.entries('TemporalRules')):
                from .native_frontend import _temporal
                clock=_temporal(raw,state.observation,release,source_start=region.source_range[0])
                if clock and clock[0] and clock[0].get('expressions'):
                    labels.append('clock expression attaches to this clause: '+str(clock[0]['expressions'][0]['raw']))
            options.append({'candidate_id':bundle[-1].frame_id, 'label':' -> '.join(labels)
                + ('; event modifiers wrap propositions; nominal descriptions attach ONLY to their named entity hosts'
                   if cfg.get('nominal_composition') else
                   '; lexical modifier attaches to the preceding proposition (structural attachment)' if len(bundle)>1 else '')})
        for option,bundle in zip(options,complete):
            if bundle[-1].semantic.get('component_scope_label'):
                option['label'] += '; EXACT scope: '+bundle[-1].semantic['component_scope_label']
        from .component_scope_contrast import contrast
        local=contrast(complete,evidence)
        if local:
            options=local['options']
            state.syntax_trace.append({'kind':'LOCAL_SCOPE_CONTRAST','decision_ref':region.region_id+'|composition',
                                       **{k:v for k,v in local.items() if k not in {'options','question'}}})
        from .component_source import probe_context
        context, target_question=probe_context(state,region,cfg,raw)
        from .component_constraints import question as established_constraints
        target_question += established_constraints(state,region)
        chosen = _probe(state, selector, release, region.region_id+'|composition',
                        'component_attachment', options, context, region.source_range,
                        question=target_question+(local['question'] if local else ''))
    for bundle in complete:
        if bundle[-1].frame_id==chosen:
            from .component_temporal_scope import resolve
            if not resolve(state,release,selector,region,tokens,bundle,cfg): chosen=None
    for bundle in bundles:
        for f in bundle:
            f.semantic['composition_decision'] = region.region_id+'|composition'
            f.semantic['composition_bundle_root'] = bundle[-1].frame_id
            if bundle[-1].frame_id != chosen:
                f.semantic['structural_unresolved'] = True
    return frames
