"""Orchestrate source-grounded clauses; substantive stages live in small modules."""
import re
from .component_policy import policy
from .component_probe import _probe
from .component_candidates import enumerate_candidates
from .component_participants import prepare_implicit, resolve_implicit, add_memory_options


def compose(state, release, selector):
    """Build finite-clause alternatives including missing subject slots.

    First slice deliberately cannot assert coordination/control or infer the
    semantics of an arbitrary adjunct. Those become uncovered components, not
    silently discarded words. Existing complete SyntaxRules frames take priority
    as coverage, not as lexical winners over a newly guessed analysis.
    """
    cfg = policy(release)
    if not cfg:
        return
    state.require_structures_open('COMPONENT_COMPOSITION')
    evidence = {e.token_id:e for e in state.evidence}
    covered = {f.predicate_token_ref for f in state.frames}
    from .regions import protected_intervals
    protected_ranges=protected_intervals(state.text)
    for region in state.region_forest.regions:
        if region.kind != 'SENTENCE':
            continue
        tokens = [evidence[t] for t in region.token_refs]
        predicates = [e for e in tokens if any(v.pos == 'VERB' and v.mood != 'imperative' for v in e.variants)]
        # A multi-predicate region needs a licensed attachment/coordination.
        if len(predicates) != 1 or predicates[0].token_id in covered:
            continue
        p = predicates[0]
        raw = state.text[region.source_range[0]:region.source_range[1]]
        # Never flatten a scoped region into an asserted finite clause.
        protected = any(lo <= p.start < hi for lo,hi in protected_ranges)
        scope = protected or any(re.search(r['pattern'], raw, re.I) for r in release.entries('ScopeLexicon'))
        scope |= any(e.span in {'«','»','"','(',')','?',':'} for e in tokens)
        if scope:
            state.diag('COMPONENT_SCOPE_UNRESOLVED', region.region_id)
            continue
        temporal = set()
        for rule in release.entries('TemporalRules'):
            for m in re.finditer(rule['pattern'],raw,re.I):
                lo,hi = region.source_range[0]+m.start(),region.source_range[0]+m.end()
                temporal.update(e.token_id for e in tokens if lo <= e.start and e.end <= hi)
        from .component_phrases import prepositional_groups
        groups=prepositional_groups(tokens,temporal)
        prep_markers={g['token_ref'] for g in groups.values()}
        allowed_cases=set(cfg['open_case_roles']) | {c for val in release.entries('R-V') for role in val['roles'] for c in role.get('allowed_cases',())}
        nominals = [e for e in tokens if e.token_id not in temporal|prep_markers and e != p
                    and (e.token_id in groups or any(v.pos in {'NOUN','NPRO'} and set(v.cases)&allowed_cases for v in e.variants))]
        # No arbitrary truncation of the argument candidate inventory.
        if len(nominals) > 3:
            state.diag('COMPONENT_SEARCH_INCOMPLETE', region.region_id)
            continue
        candidates=enumerate_candidates(state,release,cfg,region,tokens,p,temporal,nominals,groups)
        if not candidates: continue
        if len(candidates)>cfg['max_candidates']:
            state.diag('COMPONENT_SEARCH_INCOMPLETE',region.region_id)
            for f in candidates: f.semantic['structural_unresolved']=True
        elif len(candidates)>1 or any(f.semantic['requires_attachment_probe'] for f in candidates):
            options=[]
            for f in candidates:
                roles=', '.join(r+'='+evidence[t].span for t,r in f.semantic['proposed_roles'].items())
                if f.semantic['preposition_bindings']: roles += '; prepositions='+str(f.semantic['preposition_bindings'])
                if f.semantic['missing_required_roles']: roles += '; UNRESOLVED mandatory roles='+str(f.semantic['missing_required_roles'])
                if f.semantic.get('implicit_arguments'): roles += '; subject omitted (identity unresolved)'
                options.append({'candidate_id':f.frame_id,'label':str(f.semantic['morph_bindings'][p.token_id]['lemma'])+'; '+roles+'; morphology='+str({t:{k:v for k,v in m.items() if k in {'cases','number','gender','pos'}} for t,m in f.semantic['morph_bindings'].items()})})
            if len(raw)>cfg['context_chars'] or all(f.semantic['structural_unresolved'] for f in candidates):
                chosen=None
            else:
                chosen=_probe(state,selector,release,region.region_id+'|composition','component_attachment',options,raw)
            for f in candidates:
                f.semantic['composition_decision']=region.region_id+'|composition'
                if f.frame_id!=chosen: f.semantic['structural_unresolved']=True
        state.frames.extend(candidates)
        state.syntax_trace.append({'composition_region':region.region_id,
            'candidates':[f.frame_id for f in candidates], 'coverage':'PARTIAL' if any(f.semantic['uncovered_token_refs'] or f.semantic['missing_required_roles'] for f in candidates) else 'COMPLETE'})
