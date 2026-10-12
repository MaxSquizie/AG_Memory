"""Released connective + finite clauses -> bounded AND candidate, never flattening."""
import re
from .canonical_ledger import digest
from .component_clause import build_clause
from .component_probe import _probe
from .regions import TextRegion


def coordinate(state,release,selector,region,tokens,predicates,cfg,protected, *, compose_child=None):
    from .component_area_scope import allowed, connectives
    from .component_source import view
    lo,hi=region.source_range; raw=view(state,region,tokens)
    if 'AND' not in cfg.get('coordination_operators',()) or not allowed(state,release,region,tokens,conjunction=True):
        state.diag('COMPONENT_COORDINATION_UNRESOLVED',region.region_id); return []
    matches=connectives(state,release,region,tokens)
    matches=sorted(set(matches))
    if not matches or len(matches)+1>cfg['max_candidates']:
        state.diag('COMPONENT_COORDINATION_UNRESOLVED',region.region_id); return []
    if any(a[1]>b[0] for a,b in zip(matches,matches[1:])): return []
    # Temporal distribution across conjuncts needs its own scope alternatives.
    if cfg.get('temporal_coordination')!='NAMED_PERIOD_SCOPE_V1' and any(re.search(rule['pattern'],raw,re.I) for rule in release.entries('TemporalRules')):
        state.diag('COMPONENT_COORDINATION_TEMPORAL_SCOPE',region.region_id); return []
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
        elif compose_child is not None:
            frames=compose_child(child,local)
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
    choices=[]
    eligible={f.frame_id:not f.semantic['structural_unresolved'] for f in all_frames}
    anchors=[e.token_id for e in tokens if any(a<=e.start and e.end<=b for a,b in matches)]
    if complete and len(raw)<=cfg['context_chars']:
        from .coordination_scope import alternatives
        choices=alternatives(state,region,selected_frames,all_frames,anchors,cfg['max_candidates'],release=release)
        if choices:
            options=[{'candidate_id':c['candidate_id'],'label':c['label']} for c in choices]
            clauses='; '.join(str(i+1)+' = «'+state.text[slice(*f.source_range)].strip()+'»' for i,f in enumerate(selected_frames))
            chosen=_probe(state,selector,release,key,'coordination',options,raw,region.source_range,
                question='Which clauses does each modifier actually describe here? '+clauses+
                '. Local nesting is already fixed; shared lifting may not reverse it. Participant identities are a separate question.')
    if chosen is not None:
        from .coordination_scope import install
        install(next(c for c in choices if c['candidate_id']==chosen),selected_frames,all_frames,region,key)
    else:
        # No valid conjunct may escape an unresolved enclosing logical scope.
        for f in all_frames: f.semantic['structural_unresolved']=True
        state.diag('COMPONENT_COORDINATION_UNRESOLVED',region.region_id)
    from .coordination_scope import trace
    state.syntax_trace.append({'composition_region':region.region_id,'kind':'COORDINATION',
        'candidates':[f.frame_id for f in all_frames],'decision_ref':key,
        'conjunct_refs':[f.frame_id for f in selected_frames],'local_eligible':eligible,
        'coordination_anchors':anchors,'selected_scope':chosen,
        'scope_alternatives':trace(choices),
        'coverage':'COMPLETE' if chosen else 'PARTIAL'})

    return all_frames
