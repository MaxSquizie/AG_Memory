"""Whole participle readings and their released surface-role projection."""
from .refinement_boundaries import agreeing
from .component_policy import _morph


def projection(variant, attachment, cfg):
    if not attachment or variant.pos != 'PRTF':
        return None
    host, reading = attachment
    if not agreeing(reading, variant):
        return None
    matches = [r for r in cfg['refinement']['participle_voices']
               if r['feature'] in variant.features]
    if len(matches) != 1:
        return None
    return {'host':host, 'reading':reading, 'rule':matches[0]}


def add_host(frame, projected):
    host, reading, rule = (projected[k] for k in ('host','reading','rule'))
    tid = host.token_id
    frame.semantic['proposed_roles'][tid] = rule['host_role']
    frame.semantic['morph_bindings'][tid] = _morph(reading)
    frame.semantic['lexical_units'][tid] = {'head_ref':tid, 'anchor_refs':[tid],
        'surface':host.span, 'mention_ref':tid}
    frame.argument_token_refs = (*frame.argument_token_refs, tid)
    frame.semantic['refinement_binding'] = {'kind':'PARTICIPLE', 'host_token_ref':tid,
        'host_role':rule['host_role'], 'voice_feature':rule['feature'],
        'predicate_ref':frame.predicate_token_ref}
    frame.semantic['component_questions'].append({'kind':'PARTICIPLE_HOST',
        **frame.semantic['refinement_binding']})
