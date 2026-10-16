"""T2 reading areas: punctuation proposes a boundary, a task licenses it.

Physical delimiter containment joins windows before semantic composition.
Other boundaries are checked in bounded adjacent context. An unknown boundary
keeps the dependent area pending; it never licenses its children as facts.
"""
from .canonical_ledger import digest
from .regions import TextRegion, delimiter_scopes


def merged(state, windows):
    refs=tuple(dict.fromkeys(t for r in windows for t in r.token_refs))
    lo,hi=windows[0].source_range[0],windows[-1].source_range[1]
    return TextRegion('region:'+digest([state.source_uid,'COMPOSITION_WINDOW',refs]),
        'COMPOSITION_WINDOW',(lo,hi),refs,state.region_forest.regions[0].region_id,
        grounds=('SOURCE_AREA_TASK',))


def areas(state,release,selector,cfg):
    windows=[r for r in state.region_forest.regions if r.kind=='SENTENCE']
    if not windows:return []
    scopes=delimiter_scopes(state.text)
    groups=[];current=[windows[0]]
    for window in windows[1:]:
        boundary=current[-1].source_range[1]
        if any(a['source_range'][0]<boundary<a['source_range'][1] for a in scopes):
            current.append(window)
        else:groups.append(current);current=[window]
    groups.append(current)
    physical=[merged(state,g) if len(g)>1 else g[0] for g in groups]
    result=[];current=physical[0];pending=False
    from .structural_tasks import choose
    for following in physical[1:]:
        combined=merged(state,[current,following])
        # A confirmed calendar scope is an existing parent contract, not a
        # newline heuristic. Its header is never consumed by a sentence.
        header=any(current.source_range[1]<=s['header_range'][0]<=following.source_range[0]
                   for s in state.document_scopes)
        if header:
            result.append((current,pending));current=following;pending=False;continue
        selected=choose(state,release,selector,combined,cfg,'structural_source_boundary',[
            {'candidate_id':'SEPARATE','label':'Independent composition areas; neither side supplies an unfinished construction or scope of the other'},
            {'candidate_id':'JOIN','label':'One composition area: a clause, quotation, operator or other construction spans this boundary'}],
            'Boundary at source offset '+str(current.source_range[1])+'. '
            'Does the next text complete a construction or scope begun here? Ordinary reference to an earlier entity alone does not require joining.')
        if selected and selected[0]['candidate_id']=='SEPARATE':
            result.append((current,pending));current=following;pending=False
        else:
            current=combined;pending=pending or selected is None
    result.append((current,pending))
    for area,_ in result:
        if all(r.region_id!=area.region_id for r in state.region_forest.regions):
            state.region_forest.regions.append(area)
    return result
