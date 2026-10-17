"""Entity-free open roles in nonasserted action descriptions.

A description uses the ordinary predicate template. Unassigned roles remain in
that schema, but have no actant, entity, agreement features or identity binding.
This is neither an existential witness nor a universal actor. Only a containing
modal/content expression may be asserted; the description itself may not.
"""
from copy import deepcopy
from .canonical_ledger import digest


def passive_rule(variant, cfg):
    if variant.pos != 'PRTS' or 'pssv' not in variant.features:
        return None
    rules=[r for r in cfg.get('refinement',{}).get('participle_voices',()) if r['feature']=='pssv']
    return rules[0] if len(rules)==1 else None


def surface_roles(roles, rule):
    """Open vocabulary still uses the released voice projection, not a lemma."""
    result=deepcopy(roles)
    for role in result:
        rid=role['role_id']
        role['allowed_cases']=(['nom'] if rid==rule['host_role'] else
                               [c for c,r in rule['case_roles'].items() if r==rid])
    return result


def unassigned(roles, assigned):
    return sorted(r['role_id'] for r in roles if r['role_id'] not in assigned
                  and set(r.get('argument_types',('ENTITY',)))=={'ENTITY'})


def schema_roles(spec, assigned):
    """Template roles include open description slots; actants do not.

    Writers, queries and observers must use the same distinction. This adds
    no participant and grants no license to bind an unspecified role.
    """
    return set(assigned)|set(spec.get('description_roles',()))


def independent_roles(roles, cfg):
    """Infinitival subject case is a released construction, not finite agreement."""
    cases=cfg.get('infinitive_composition',{}).get('independent_subject_cases')
    if not cases:return roles
    result=deepcopy(roles)
    for role in result:
        if role['role_id']==cfg['subject_role'] and not role.get('allowed_preps'):
            role['allowed_cases']=list(cases)
    return result


def licensed_roles(frame, valency):
    """T3 rechecks the same construction and valency used by composition."""
    description=frame.semantic.get('action_description')
    if not description or digest(valency) not in {description.get('valency_digest'),*description.get('valency_digests',())}:
        return None
    reading=frame.semantic.get('morph_bindings',{}).get(frame.predicate_token_ref,{})
    if reading.get('pos')!='INFN' and not (reading.get('pos')=='PRTS' and 'pssv' in reading.get('features',())):
        return None
    assigned=set(frame.semantic.get('proposed_roles',{}).values())|set(frame.semantic.get('proposition_args',{}))
    expected=unassigned(valency['roles'],assigned)
    return tuple(expected) if expected==description.get('unassigned_roles') else None


def validate_scope(tree, frames, guarded=False):
    """Check every path: sharing a description with a modal cannot license a
    second, independently asserted occurrence of that same description.
    """
    fid=tree.get('frame_ref')
    if fid is not None:
        frame=frames[fid]
        if frame.semantic.get('action_description') and not guarded:
            raise ValueError('ACTION_DESCRIPTION_WITHOUT_SCOPE')
        from .composition_tree import slots,unary_modifier
        for slot in slots(frame):
            validate_scope(slot.tree,frames,guarded or slot.kind=='PROPOSITION' and unary_modifier(frame) is None)
        return
    guarded=guarded or tree.get('operator') in {'POSSIBLE','NECESSARY'}
    for child in tree.get('operands',()):
        validate_scope(child,frames,guarded)
