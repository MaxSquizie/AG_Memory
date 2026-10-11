"""Candidate nominal cases from released predicate roles, never lexical identity."""
from .state import MorphVariant


def candidates(tokens, index, release, cfg):
    token = tokens[index]
    preps = {v.lemma for v in tokens[index - 1].variants if v.pos == 'PREP'} if index else set()
    evidence = {}
    for predicate in tokens:
        for reading in predicate.variants:
            if reading.pos != 'VERB' or reading.mood == 'imperative':
                continue
            senses = [s for s in release.entries('R-S')
                      if s['lemma'] == reading.lemma and s['POS'] == reading.pos
                      and not s.get('anchor_pattern')]
            valencies = [v for v in release.entries('R-V')
                         if v['sense_id'] in {s['sense_id'] for s in senses}]
            if senses:
                # Missing known valency is not permission to invent an open one.
                roles = [r for v in valencies for r in v['roles']
                         if set(r.get('argument_types', ())) == {'ENTITY'}]
            elif release.entries('OpenTemplatePolicy')[0]['allow']:
                roles = [{'role_id': role, 'allowed_cases': [case]}
                         for case, role in cfg['open_case_roles'].items()]
            else:
                continue
            for role in roles:
                allowed_preps = set(role.get('allowed_preps', ()))
                if (preps and not preps & allowed_preps) or (not preps and allowed_preps):
                    continue
                for case in role.get('allowed_cases', ()):
                    evidence.setdefault(case, set()).add(predicate.token_id)
    for case, refs in sorted(evidence.items()):
        # Number, gender, animacy and named-entity identity remain unknown.
        yield MorphVariant(token.span.casefold(), 'NOUN', frozenset({case}),
                           origin='CONTEXTUAL', evidence_refs=tuple(sorted(refs)))
