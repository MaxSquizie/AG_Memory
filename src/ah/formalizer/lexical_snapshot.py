"""Freeze pre-seal lexical decisions for declared structural clarification."""
from copy import deepcopy
from .component_policy import _morph
from .state import MorphVariant


def freeze(evidence):
    return [{'token_ref':e.token_id,'source_surface':e.span,'lex_status':e.lex_status,
             'variants':[_morph(v) for v in e.variants], 'lexical_recovery':deepcopy(e.lexical_recovery)}
            for e in evidence if e.lexical_recovery or any(v.origin=='CONTEXTUAL' for v in e.variants)]


def restore(evidence,rows):
    by_id={e.token_id:e for e in evidence};seen=set()
    for row in rows:
        e=by_id.get(row['token_ref'])
        if e is None or e.token_id in seen or e.span!=row['source_surface']:
            raise ValueError('CLARIFICATION_LEXICAL_STALE')
        seen.add(e.token_id)
        variants=tuple(MorphVariant(**{**v,'cases':frozenset(v['cases']),
            'features':frozenset(v['features']),'evidence_refs':tuple(v.get('evidence_refs',()))}) for v in row['variants'])
        if not variants or any(v.origin not in {'CONTEXTUAL','RECOVERED'} for v in variants):
            raise ValueError('CLARIFICATION_LEXICAL_STALE')
        e.variants=variants;e.lex_status=row['lex_status'];e.lexical_recovery=deepcopy(row['lexical_recovery'])
        e.lemma=variants[0].lemma;e.pos=variants[0].pos;e.cases=variants[0].cases
