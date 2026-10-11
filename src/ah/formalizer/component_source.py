"""Source views for a clause with detached descriptions; offsets never move."""


def view(state, region, tokens):
    lo, hi = region.source_range
    chars = [c if c.isspace() else ' ' for c in state.text[lo:hi]]
    for token in tokens:
        start, end = max(lo, token.start), min(hi, token.end)
        chars[start-lo:end-lo] = state.text[start:end]
    return ''.join(chars)


def frame_view(state, frame):
    refs = frame.semantic.get('owned_token_refs')
    if refs is None:
        return state.text[slice(*frame.source_range)]
    return view(state, frame, [e for e in state.evidence if e.token_id in refs])


def probe_context(state, region, cfg, local):
    """Reading context may cross the area; token ownership never does."""
    if 'MORPHOLOGICAL_REFINEMENT' not in region.grounds:
        return local, ''
    regions={r.region_id:r for r in state.region_forest.regions}
    current=region; seen=set()
    while current.parent_ref in regions and current.region_id not in seen:
        seen.add(current.region_id)
        parent=regions[current.parent_ref]
        if parent.source_range[1]-parent.source_range[0]>cfg['context_chars']:
            break
        current=parent
        if current.kind=='SENTENCE': break
    return state.text[slice(*current.source_range)], ('Resolve ONLY the target area «'+local.strip()+
        '». The surrounding source is context for morphology/references, not additional arguments of this area. ')
