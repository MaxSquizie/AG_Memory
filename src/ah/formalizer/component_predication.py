"""Whole-clause alternatives across predicate POS; no early lexical winner."""
from .component_policy import _features, _morph, compatible
from .component_clause import build_clause
from .component_probe import _probe


def nominal_predicate(variant, cfg):
    return (cfg.get('nominal_predication')=='NOUN_PREDICATE_V1' and variant.pos=='NOUN'
            and bool(variant.cases & {'nom','abl'}))


def impersonal_predicate(variant,cfg):
    return cfg.get('impersonal_predication')=='DATIVE_STATE_V1' and (
        variant.pos=='PRED' or bool(variant.features & {'Impe','Prdx'}))


def nominal_predicates(tokens, cfg):
    """Offer noun predication without treating arbitrary noun arguments as verbs."""
    return [t for t in tokens if any(nominal_predicate(v,cfg) for v in t.variants)
            and any(other.token_id!=t.token_id and any(v.pos in {'NOUN','NPRO'} and 'nom' in v.cases
                for v in other.variants) for other in tokens)]


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


def _compose_alternatives(state, release, selector, region, tokens, predicates, cfg, *, attachment=None, nominal_groups=(), infinitive=None, request=None):
    from .nominal_coordination_source import live as group_live
    if not all(group_live(state,g) for g in nominal_groups):
        state.diag('NOMINAL_COORDINATION_EVIDENCE_UNRESOLVED',region.region_id)
        return []
    from .nominal_functions import prepare as nominal_functions
    if not nominal_functions(state,release,selector,region,tokens,cfg):
        state.diag('NOMINAL_FUNCTION_UNRESOLVED',region.region_id)
        return []
    from .temporal_functions import prepare as temporal_functions
    if not temporal_functions(state,release,selector,region,tokens,cfg):
        state.diag('TEMPORAL_FUNCTION_UNRESOLVED',region.region_id)
        return []
    from .predicate_functions import head as select_head
    selected_head=(False,None) if request and request.output_sort=='EVENT_DESCRIPTION' else select_head(state,release,selector,region,tokens,predicates,cfg,request=request)
    if selected_head is None:
        state.diag('PREDICATE_FUNCTION_UNRESOLVED',region.region_id);return []
    predicate,proof=selected_head
    predicates=[predicate] if predicate else []
    cfg={**cfg,'_predicate_function':proof if predicate else None}
    from .contextual_name_case import overlay as coordinated_readings
    from .contextual_preposition_case import overlay as governed_readings
    tokens=governed_readings(state,release,selector,region,coordinated_readings(tokens,nominal_groups),cfg)
    if tokens is None:return []
    from .contextual_substantives import overlay as substantive_readings
    tokens=substantive_readings(state,release,selector,region,tokens,cfg)
    # Predicate inventories must see the same occurrence-local readings.
    by_token={e.token_id:e for e in tokens}
    predicates=[by_token[e.token_id] for e in predicates]
    from .qualitative_quantity import resolve as quantity_groups
    tokens, quantities=quantity_groups(state,release,selector,region,tokens,cfg)
    if tokens is None:return []
    from .nominal_reference_groups import project as reference_groups, attach as attach_references
    tokens, references=reference_groups(state,release,selector,region,tokens,cfg)
    if tokens is None:return []
    bundles = []
    diagnostics_before = len(state.diagnostics)
    bases=[]
    for predicate in predicates:
        bases.extend(build_clause(state, release, selector, region, tokens, predicate, cfg, select=False, attachment=attachment, nominal_groups=nominal_groups,infinitive=infinitive,qualitative_groups=quantities,
            proposition_slots=(request.proposition_slots or {}).get(predicate.token_id,{}) if request else {},
            agreement_source=request.agreement_source if request else None,
            description_context=bool(request and request.description_context),
            pending_roles=request.pending_for(predicate.token_id) if request else (),
            required_pending_roles=(request.pending_propositions or {}).get(predicate.token_id,()) if request else ()))
    if attachment is None and infinitive is None:
        from .component_nominal_utterance import candidates as nominatives
        bases.extend(nominatives(state,release,region,tokens,cfg,request=request if request and request.output_sort=='EVENT_DESCRIPTION' else None,selector=selector,quantities=quantities))
    from .component_nominal_tree import bundles as nominal_bundles
    for frame in bases:
        if cfg.get('modifier_content_role'):
            bundles.extend(nominal_bundles(state,release,selector,region,tokens,frame,cfg))
        else:
            bundles.append([frame])
    from copy import deepcopy
    from .temporal_functions import units as time_units
    selected_times=time_units(state,[t.token_id for t in tokens])
    for bundle in bundles:
        for f in bundle:f.semantic['temporal_functions']=[]
        if bundle:bundle[-1].semantic['temporal_functions']=deepcopy(selected_times)
    frames = [f for bundle in bundles for f in bundle]
    attach_references(frames,references)
    from .component_constraints import accepts_bundle
    for b in bundles:
        if not accepts_bundle(state,region,tokens,b):
            for f in b:f.semantic['structural_unresolved']=True
            state.syntax_trace.append({'kind':'ESTABLISHED_ROLE_CONSTRAINT_REJECTION','region_ref':region.region_id,'frame_refs':[f.frame_id for f in b]})
    complete = [b for b in bundles if all(not f.semantic['structural_unresolved'] for f in b)]
    # Producer provenance is not a language ambiguity. Compare interpretations,
    # never labels, before offering the component domain to a model.
    from .composition_equivalence import coalesce_components
    complete,duplicates=coalesce_components(state,region,complete)
    bundles=[b for b in bundles if b[-1].frame_id not in duplicates]
    frames=[f for b in bundles for f in b]
    local_diagnostics=[d for d in state.diagnostics[diagnostics_before:] if d.detail==region.region_id]
    incomplete_search=any(d.code=='COMPONENT_SEARCH_INCOMPLETE' for d in local_diagnostics)
    pending_search=any(d.code in {'COMPONENT_NOMINAL_SELECTION_UNRESOLVED',
        'PREDICATE_ARGUMENT_DOMAIN_UNRESOLVED',
        'COMPONENT_DEPENDENCY_UNRESOLVED','COMPONENT_NOMINAL_SEGMENTATION_UNRESOLVED',
        'COMPONENT_NOMINAL_CYCLE','COMPONENT_NOMINAL_HOST_UNRESOLVED'} for d in local_diagnostics)
    if pending_search and not incomplete_search:
        for frame in frames:frame.semantic['structural_unresolved']=True
        return frames
    if incomplete_search or len(complete) > cfg['max_candidates']:
        state.diag('COMPONENT_SEARCH_INCOMPLETE', region.region_id)
        for frame in frames:
            frame.semantic['structural_unresolved'] = True
        return frames
    # Partial alternatives stay addressable but cannot masquerade as a complete
    # source interpretation. Each complete choice includes every child frame.
    from .partial_readings import bundles as common_readings
    reading_domains=common_readings(state,region,complete)
    needs_probe = len(bundles) > 1 or any(f.semantic['requires_attachment_probe'] for f in frames)
    chosen = complete[0][-1].frame_id if len(complete) == 1 and not needs_probe else None
    from .component_source import view
    raw = view(state,region,tokens)
    options = []
    if complete and needs_probe and len(raw) <= cfg['context_chars']:
        evidence = {e.token_id:e for e in state.evidence}
        from .probe_wording import role as role_text,TERMS
        for bundle in complete:
            labels = []
            for f in bundle:
                m = f.semantic['morph_bindings'][f.predicate_token_ref]
                roles = ', '.join(role_text(role)+'=«'+evidence[tid].span+'» @'+str(evidence[tid].start) for tid, role in f.semantic['proposed_roles'].items())
                label = f.semantic.get('nominal_dependency_kind',m['lemma'])+' ['+TERMS.get(m['pos'],m['pos'])+']; '+roles
                if f.semantic.get('nominal_predication'):
                    subject=next((evidence[t].span for t,r in f.semantic['proposed_roles'].items() if r==cfg['subject_role']),'the selected participant')
                    label+='; noun predicate: «'+f.anchor_span+'» describes what «'+subject+'» is'
                if f.semantic.get('impersonal_predication'):
                    label+='; impersonal state; dative participant experiences it; no separate grammatical subject'
                if f.semantic.get('action_description'):
                    label+='; action description; occurrence is NOT asserted; unassigned participant slots: '+(', '.join(role_text(r) for r in f.semantic['action_description']['unassigned_roles']) or 'none proposed')+'; no participant identity is supplied for them'
                if f.semantic.get('passive_predication'):
                    label+='; passive: the nominative participant receives the action, not performs it'
                if cfg.get('modifier_composition')=='BOUNDED_FOREST_V1':
                    from .probe_wording import linked_readings
                    label += '; linked morphology='+linked_readings(f.semantic['morph_bindings'],evidence)
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
        chosen = None if reading_domains else _probe(state, selector, release, region.region_id+'|composition',
                        'component_attachment', options, context, region.source_range,
                        question=target_question+(local['question'] if local else
                            'Which remaining interpretation fits the target? Previously selected roles, readings and attachments '
                            'are constraints, not questions to reopen. Retain alternatives when the text does not distinguish them.'), target_refs=tuple(t.token_id for t in tokens))
    decision=state.decisions.get(region.region_id+'|composition')
    deferred=bool(reading_domains) or chosen is None and decision is not None and decision.selector_outcome in {
        'MULTIPLE_ADMISSIBLE','INSUFFICIENT_CONTEXT'}
    admissible=set(options[i]['candidate_id'] for i in range(len(options)))
    if deferred and decision is not None and not reading_domains and decision.selector_outcome=='MULTIPLE_ADMISSIBLE':
        admissible=set(next((h['selected'] for h in reversed(decision.history)
                             if h.get('kind')=='CLOSED_PROBE_ALTERNATIVES'),()))
    labels={o['candidate_id']:o['label'] for o in options}
    if chosen is not None:
        # An empty dependency domain rejects that reading, not a different
        # complete reading selected for the same area. Keep its source trace.
        state.diagnostics[diagnostics_before:]=[d for d in state.diagnostics[diagnostics_before:]
            if not (d.detail==region.region_id and d.code=='COMPONENT_DEPENDENCY_CONTRADICTION')]
    for bundle in complete:
        carrier=bundle[-1]
        if deferred and carrier.frame_id in admissible:
            carrier.semantic['composition_domain']={'decision_ref':region.region_id+'|composition',
                'candidate_id':carrier.frame_id,'frame_refs':[f.frame_id for f in bundle],
                'label':labels[carrier.frame_id],**({'reading_domains':reading_domains} if reading_domains else {})}
    for bundle in bundles:
        for f in bundle:
            f.semantic['composition_decision'] = region.region_id+'|composition'
            f.semantic['composition_bundle_root'] = bundle[-1].frame_id
            if bundle[-1].frame_id != chosen:
                f.semantic['structural_unresolved'] = True
            elif decision is not None:
                from .morphology_domain import license_use
                for tid,reading in f.semantic.get('morph_bindings',{}).items():
                    license_use(state,tid,reading,region.region_id+'|composition',chosen)
    return frames


def compose_alternatives(state,release,selector,region,tokens,predicates,cfg,**kwargs):
    from .function_inventory import InventoryUnavailable,attach
    try:
        frames=_compose_alternatives(state,release,selector,region,tokens,predicates,cfg,**kwargs)
        return attach(state,tokens,cfg,frames)
    except InventoryUnavailable as exc:
        state.diag('FUNCTION_INVENTORY_UNRESOLVED',str(exc))
        return []
