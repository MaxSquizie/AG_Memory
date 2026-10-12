"""Whole participle readings and their released surface-role projection."""
from .refinement_boundaries import agreeing
from .component_policy import _morph


def projection(variant, attachment, cfg):
    if isinstance(attachment,dict) and attachment.get('kind')=='RELATIVE_PRONOUN':
        from .relative_pronoun import projection as relative_projection
        return relative_projection(variant,attachment,cfg)
    if not attachment or variant.pos != 'PRTF':
        return None
    host, reading = attachment[:2]
    if not agreeing(reading, variant):
        return None
    matches = [r for r in cfg.get('refinement',{}).get('participle_voices',())
               if r['feature'] in variant.features]
    if len(matches) != 1:
        return None
    return {'host':host, 'reading':reading, 'rule':matches[0],
            **({'group':attachment[2]} if len(attachment)>2 else {})}


def add_host(frame, projected):
    if projected.get('group'):
        from .refinement_group_hosts import add_host as add_group_host
        add_group_host(frame,projected)
        return
    host, reading, rule = (projected[k] for k in ('host','reading','rule'))
    tid = host.token_id
    frame.semantic['proposed_roles'][tid] = rule['host_role']
    frame.semantic['morph_bindings'][tid] = _morph(reading)
    frame.semantic['lexical_units'][tid] = {'head_ref':tid, 'anchor_refs':[tid],
        'surface':host.span, 'mention_ref':tid}
    frame.argument_token_refs = (*frame.argument_token_refs, tid)
    frame.semantic['refinement_binding'] = {'kind':'RELATIVE_PRONOUN' if projected.get('relative_marker') else 'PARTICIPLE', 'host_token_ref':tid,
        'host_role':rule['host_role'], 'voice_feature':rule.get('feature'),
        'predicate_ref':frame.predicate_token_ref}
    if projected.get('relative_marker'):
        marker=projected['relative_marker']
        frame.semantic['morph_bindings'][marker.token_id]=_morph(projected['marker_reading'])
        frame.semantic['refinement_binding']['marker_ref']=marker.token_id
    frame.semantic['component_questions'].append({'kind':'PARTICIPLE_HOST',
        **frame.semantic['refinement_binding']})
