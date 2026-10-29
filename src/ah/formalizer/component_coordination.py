"""Released connective + finite clauses -> bounded AND candidate, never flattening."""
import re
from .canonical_ledger import digest
from .component_clause import build_clause
from .component_probe import _probe
from .regions import TextRegion


def coordinate(state,release,selector,region,tokens,predicates,cfg,protected, *, compose_child=None,inside_attitude=False,boundary=None):
    from .component_area_scope import allowed, connectives
    from .component_source import view
    lo,hi=region.source_range; raw=view(state,region,tokens)
    # A selected outer edge owns only its connective. Child operators are
    # checked by the same recursive composer, not rejected by the parent guard.
    if 'AND' not in cfg.get('coordination_operators',()) or (boundary is None and not allowed(state,release,region,tokens,conjunction=True,inside_attitude=inside_attitude)):
        state.diag('COMPONENT_COORDINATION_UNRESOLVED',region.region_id); return []
    matches=[boundary] if boundary is not None else connectives(state,release,region,tokens)
    matches=sorted(set(matches))
    if not matches or len(matches)+1>cfg['max_candidates']:
        state.diag('COMPONENT_COORDINATION_UNRESOLVED',region.region_id); return []
    if any(a[1]>b[0] for a,b in zip(matches,matches[1:])): return []
    ranges=list(zip([lo,*[end for start,end in matches]],[*[start for start,end in matches],hi]))
    source_proof=None
    if boundary is None:
        # Lexicon matches and rejection of a nominal grouping merely propose
        # this partition. They do not establish proposition-level AND.
        from .structural_tasks import choose
        proposal={'candidate_id':'COORDINATION','relation':'AND',
            'operand_refs':[[t.token_id for t in tokens if a<=t.start and t.end<=b] for a,b in ranges],
            'label':'Conjunction of these complete proposition parts: '+
                '; '.join('«'+state.text[a:b].strip()+'»' for a,b in ranges)}
        result=choose(state,release,selector,region,cfg,'coordination_boundary',[proposal],
            'Does the source connect these parts as propositions by conjunction (AND)? '
            'Each part retains its own participants, descriptions, negation and modality. '
            'This choice does not assert the parts independently. '
            'Answer 0 if this relation or these boundaries do not fit, or ? if undecidable.')
        if not result:
            state.diag('COMPONENT_COORDINATION_UNRESOLVED',region.region_id)
            return []
        source_proof=result[1]
        state.syntax_trace.append({'kind':'COORDINATION_SOURCE_PARTITION','region_ref':region.region_id,
            'proposal':proposal,'proof':source_proof})
    all_frames=[]; selected=[]
    for index,(start,end) in enumerate(ranges):
        local=[e for e in tokens if start<=e.start and e.end<=end]
        child=TextRegion('region:'+digest([region.region_id,'CONJUNCT',index]),'CLAUSE',
            (start,end),tuple(e.token_id for e in local),region.region_id,grounds=('RELEASED_CONNECTIVE',))
        if not any(r.region_id==child.region_id for r in state.region_forest.regions):
            state.region_forest.regions.append(child)
        anchors=[p for p in predicates if start<=p.start and p.end<=end]
        if compose_child is not None:
            frames=compose_child(child,local)
        else:
            from .component_refinement import compose_area
            frames=compose_area(state,release,selector,child,local,cfg)
        for f in frames: f.semantic['coordination_owner']=region.region_id
        from .composition_children import select_child
        root=select_child(state,release,selector,region,frames,'AND conjunct '+str(index+1),
            'Sibling source areas: '+str([state.text[a:b] for i,(a,b) in enumerate(ranges) if i!=index]))
        for f in frames:f.semantic['coordination_owner']=region.region_id
        all_frames.extend(frames)
        selected.append([root] if root is not None else [])
    complete=all(len(group)==1 for group in selected)
    selected_frames=[group[0] for group in selected] if complete else []
    key=region.region_id+'|coordination'
    chosen=None
    eligible={f.frame_id:not f.semantic['structural_unresolved'] for f in all_frames}
    anchors=[e.token_id for e in tokens if any(a<=e.start and e.end<=b for a,b in matches)]
    if complete and len(raw)<=cfg['context_chars']:
        if source_proof:
            from .structural_tasks import licensed
            if not licensed(state,source_proof,relation='AND',operand_refs=proposal['operand_refs']):
                for f in all_frames:f.semantic['structural_unresolved']=True
                state.diag('COORDINATION_SOURCE_UNGROUNDED',region.region_id)
                return all_frames
        from .coordination_assignment import compose
        chosen=compose(state,release,selector,region,selected_frames,all_frames,anchors,cfg)
    if chosen is None:
        for f in all_frames:f.semantic['structural_unresolved']=True
        state.diag('COMPONENT_COORDINATION_UNRESOLVED',region.region_id)
    state.syntax_trace.append({'composition_region':region.region_id,'kind':'COORDINATION',
        'candidates':[f.frame_id for f in all_frames],'decision_ref':key,
        'conjunct_refs':[f.frame_id for f in selected_frames],'local_eligible':eligible,
        'coordination_anchors':anchors,'selected_tree':chosen,'source_proof':source_proof,
        'coverage':'COMPLETE' if chosen is not None else 'PARTIAL'})

    return all_frames
