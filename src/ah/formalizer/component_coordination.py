"""Released connective + finite clauses -> bounded AND candidate, never flattening."""
import re
from .canonical_ledger import digest
from .component_clause import build_clause
from .component_probe import _probe
from .regions import TextRegion


def coordinate(state,release,selector,region,tokens,predicates,cfg,protected):
    if 'AND' not in cfg.get('coordination_operators',()): return
    lo,hi=region.source_range; raw=state.text[lo:hi]
    if any(a<=p.start<b for p in predicates for a,b in protected): return
    if any(t.span in {'«','»','"','(',')','?',':'} for t in tokens): return
    matches=[]
    for rule in release.entries('ScopeLexicon'):
        for m in re.finditer(rule['pattern'],raw,re.I):
            if rule.get('operator')!='AND': return
            matches.append((lo+m.start(),lo+m.end()))
    matches=sorted(set(matches))
    if not matches or len(matches)+1>cfg['max_candidates']:
        state.diag('COMPONENT_COORDINATION_UNRESOLVED',region.region_id); return
    if any(a[1]>b[0] for a,b in zip(matches,matches[1:])): return
    # Temporal distribution across conjuncts needs its own scope alternatives.
    if any(re.search(rule['pattern'],raw,re.I) for rule in release.entries('TemporalRules')):
        state.diag('COMPONENT_COORDINATION_TEMPORAL_SCOPE',region.region_id); return
    ranges=list(zip([lo,*[end for start,end in matches]],[*[start for start,end in matches],hi]))
    all_frames=[]; selected=[]
    for index,(start,end) in enumerate(ranges):
        local=[e for e in tokens if start<=e.start and e.end<=end]
        child=TextRegion('region:'+digest([region.region_id,'CONJUNCT',index]),'CLAUSE',
            (start,end),tuple(e.token_id for e in local),region.region_id,grounds=('RELEASED_CONNECTIVE',))
        state.region_forest.regions.append(child)
        anchors=[p for p in predicates if start<=p.start and p.end<=end]
        if not anchors:
            frames=[]
        elif cfg.get('modifier_content_role') or cfg.get('quality_predicate_pos'):
            from .component_predication import compose_alternatives
            frames=compose_alternatives(state,release,selector,child,local,anchors,cfg)
        elif len(anchors)==1:
            frames=build_clause(state,release,selector,child,local,anchors[0],cfg)
        else:
            frames=[]
        for f in frames: f.semantic['coordination_owner']=region.region_id
        all_frames.extend(frames)
        selected.append([f for f in frames if not f.semantic['structural_unresolved'] and not f.semantic.get('component_child')])
    complete=all(len(group)==1 for group in selected)
    selected_frames=[group[0] for group in selected] if complete else []
    key=region.region_id+'|coordination'
    chosen=None
    if complete and len(raw)<=cfg['context_chars']:
        labels=[' AND '.join(state.text[slice(*f.source_range)].strip() for f in selected_frames)]
        options=[{'candidate_id':'coordination:'+digest([f.frame_id for f in selected_frames]),
            'label':labels[0]+'; asserted conjunction of these clauses; each keeps local arguments. '
                    'Omitted participants remain unresolved; no shared participant or event time is inferred.'}]
        chosen=_probe(state,selector,release,key,'coordination',options,raw,region.source_range)
    if chosen is not None:
        forest={'operator':'AND','operands':[{'frame_ref':f.frame_id} for f in selected_frames],
            'anchor_refs':[e.token_id for e in tokens if any(a<=e.start and e.end<=b for a,b in matches)]}
        for f in selected_frames:
            f.semantic['operator_forest']=[forest]
            f.semantic['coordination_decision']=key
    else:
        # No valid conjunct may escape an unresolved enclosing logical scope.
        for f in all_frames: f.semantic['structural_unresolved']=True
        state.diag('COMPONENT_COORDINATION_UNRESOLVED',region.region_id)
    state.frames.extend(all_frames)
    state.syntax_trace.append({'composition_region':region.region_id,'kind':'COORDINATION',
        'candidates':[f.frame_id for f in all_frames],'decision_ref':key,
        'coverage':'COMPLETE' if chosen else 'PARTIAL'})
