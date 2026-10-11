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


def compose_alternatives(state, release, selector, region, tokens, predicates, cfg):
    from .component_modifiers import scoped_bundle
    bundles = []
    diagnostics_before = len(state.diagnostics)
    for predicate in predicates:
        for frame in build_clause(state, release, selector, region, tokens, predicate, cfg, select=False):
            bundles.append(scoped_bundle(state, release, region, tokens, frame, cfg))
    frames = [f for bundle in bundles for f in bundle]
    complete = [b for b in bundles if all(not f.semantic['structural_unresolved'] for f in b)]
    incomplete_search = any(d.code=='COMPONENT_SEARCH_INCOMPLETE' and d.detail==region.region_id
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
    raw = state.text[slice(*region.source_range)]
    if complete and needs_probe and len(raw) <= cfg['context_chars']:
        evidence = {e.token_id:e for e in tokens}
        options = []
        for bundle in complete:
            labels = []
            for f in bundle:
                m = f.semantic['morph_bindings'][f.predicate_token_ref]
                roles = ', '.join(role+'='+evidence[tid].span for tid, role in f.semantic['proposed_roles'].items())
                label = m['lemma']+' ['+m['pos']+']; '+roles
                if f.semantic.get('implicit_arguments'):
                    label += '; subject omitted, identity unresolved'
                if f.semantic.get('copula_ref'):
                    label += '; copula='+evidence[f.semantic['copula_ref']].span
                if f.semantic.get('relative_temporal'):
                    label += '; relative anchors='+str(f.semantic['relative_temporal'])
                labels.append(label)
            options.append({'candidate_id':bundle[-1].frame_id, 'label':' -> '.join(labels)
                + ('; lexical modifier attaches to the preceding proposition (structural attachment)' if len(bundle)>1 else '')})
        chosen = _probe(state, selector, release, region.region_id+'|composition',
                        'component_attachment', options, raw, region.source_range)
    for bundle in bundles:
        for f in bundle:
            f.semantic['composition_decision'] = region.region_id+'|composition'
            f.semantic['composition_bundle_root'] = bundle[-1].frame_id
            if bundle[-1].frame_id != chosen:
                f.semantic['structural_unresolved'] = True
    return frames
