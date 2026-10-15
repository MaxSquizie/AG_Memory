"""Lexical forms from a frame's selected reading, never the top analyzer guess."""


def selected_forms(frame, token):
    unit=frame.semantic.get('lexical_units',{}).get(token.token_id,{})
    surface=unit.get('surface',token.span)
    if len(unit.get('anchor_refs',()))>1:
        return surface, None
    reading=frame.semantic.get('morph_bindings',{}).get(token.token_id)
    # A bare OOV function uses the surface as a technical lemma placeholder.
    # It establishes no additional wordform. Contextual readings reach here only
    # through the existing morphology-use and complete-frame validation.
    lemma=reading.get('lemma') if reading else None
    if not lemma or lemma.casefold()==surface.casefold():
        return surface, None
    return surface, lemma
