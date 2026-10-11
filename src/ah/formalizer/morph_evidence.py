"""Separate lexical evidence from productive analyzer guesses before grammar."""


def partition(token, variants):
    variants=tuple(variants)
    token.morph_guesses=tuple(v for v in variants if v.origin=='PREDICTED')
    accepted=tuple(v for v in variants if v.origin!='PREDICTED')
    if any(c.isalpha() for c in token.span) and not any(v.origin in {'DICTIONARY','DECLARED'} for v in accepted):
        token.lex_status='OOV_KEEP_AS_IS'
    token.variants=accepted
    if not accepted:
        token.lemma=token.span.casefold();token.pos=None;token.cases=frozenset();token.score=0.0
    return accepted
