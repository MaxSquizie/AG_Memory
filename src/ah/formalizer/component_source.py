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


def probe_context(state, region, cfg, local, *, include_surrounding=True):
    """Reading context may cross the area; token ownership never does."""
    if not include_surrounding:
        return 'TARGET: '+local.strip(), ''
    # A region boundary proves ownership, not independence of interpretation
    # from the rest of this observation. No relevance proof licenses dropping
    # sibling sentences or a long ancestor. The caller's budget must report
    # incompleteness rather than silently making that semantic assumption.
    surrounding=state.text
    if surrounding.strip()==local.strip():
        return 'TARGET: '+local.strip(), ''
    return 'TARGET: '+local.strip()+'\nCONTEXT (evidence only): '+surrounding, (
        'Choose only inside TARGET; CONTEXT is evidence and supplies no additional selectable words. ')
