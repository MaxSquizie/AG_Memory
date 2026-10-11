"""Unmapped prepositional attachment as lexical scope, never guessed valency."""
from .component_phrases import prepositional_groups
from .component_policy import _morph


def prepositional_bundle(state, region, tokens, frame, cfg):
    role = cfg.get('preposition_nominal_role')
    if not role or role == cfg['modifier_content_role']:
        return [frame]
    missing = set(frame.semantic['uncovered_token_refs'])
    groups = [g for g in prepositional_groups(tokens).values()
              if set(g['anchor_refs']) == missing and len(g['anchor_refs']) == 2]
    if len(groups) != 1:
        return [frame]
    group = groups[0]
    evidence = {e.token_id:e for e in tokens}
    prep = evidence[group['token_ref']]
    head = evidence[group['anchor_refs'][-1]]
    def unique(variants):
        return {tuple(sorted((k,str(value)) for k,value in _morph(v).items() if k!='score')):v
                for v in variants}
    preps = unique(v for v in prep.variants if v.pos == 'PREP')
    nouns = unique(v for v in head.variants if v.pos in {'NOUN','NPRO'})
    if len(preps) != 1 or len(nouns) != 1:
        return [frame]
    from .component_modifiers import wrap
    return wrap(frame, region, prep, next(iter(preps.values())), cfg['modifier_content_role'],
                entities=[(head,next(iter(nouns.values())))], nominal_role=role)
