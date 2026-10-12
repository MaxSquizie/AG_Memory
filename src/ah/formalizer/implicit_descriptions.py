"""Descriptions and dependent areas can share one licensed omitted subject."""
from .canonical_ledger import digest
from .component_policy import _features, _morph, compatible
from .state import FrameCandidate


def units(tokens, missing, frame, cfg):
    role = cfg['subject_role']
    gap = frame.semantic.get('implicit_arguments', {}).get(role)
    if not gap or gap.get('license') != 'SUBJECT_AGREEMENT':
        return
    for token in tokens:
        if token.token_id not in missing:
            continue
        for variant in token.variants:
            # Nominative agreement licenses a candidate, never an identity or
            # an automatically true description. Oblique predicates need their
            # own released construction; passive agreement is not an agent.
            if (variant.pos != 'ADJF' or 'nom' not in variant.cases
                or not compatible(_features(variant), gap['features'])):
                continue
            yield {'token': token, 'variant': variant, 'refs': (token.token_id,),
                   'entities': [], 'adjectives': [], 'implicit_host_role': role,
                   'requires_host_probe': True}


def materialize(unit, base, region, cfg):
    token, variant = unit['token'], unit['variant']
    owner_role, description_role = unit['implicit_host_role'], cfg['nominal_host_role']
    alias = {description_role: {'frame_ref': base.frame_id, 'role': owner_role}}
    fid = 'component-implicit-description:' + digest([base.frame_id, token.token_id, _morph(variant), alias])
    sem = {'proposed_roles': {}, 'morph_bindings': {token.token_id: _morph(variant)},
           'lexical_units': {}, 'preposition_bindings': {}, 'missing_required_roles': [],
           'requires_attachment_probe': True, 'uncovered_token_refs': [],
           'structural_unresolved': False, 'relative_temporal': [],
           'component_region': region.region_id, 'nominal_description': True,
           'shared_implicit_arguments': alias, 'component_child': base.frame_id,
           'component_questions': [{'kind': 'IMPLICIT_SUBJECT_DESCRIPTION',
                'owner_frame_ref': base.frame_id, 'owner_role': owner_role,
                'description_role': description_role, 'anchor_ref': token.token_id}]}
    base.semantic.setdefault('nominal_args', []).append({
        'host_implicit_role': owner_role, 'host_role': description_role, 'frame_ref': fid})
    return FrameCandidate(fid, 'FLAT', token.span, (token.span,), (),
        construction='COMPONENTS_V1', predicate_token_ref=token.token_id,
        argument_token_refs=(), source_range=tuple(region.source_range),
        semantic=sem, provenance=base.provenance)


def roles(frame):
    return tuple(dict.fromkeys((*frame.semantic.get('implicit_arguments', {}),
                               *frame.semantic.get('shared_implicit_arguments', {}))))


def gap_for(frame, role, frames):
    alias = frame.semantic.get('shared_implicit_arguments', {}).get(role)
    if alias is None:
        return frame.semantic['implicit_arguments'][role]
    owner = frames.get(alias['frame_ref'])
    if owner is None or owner is frame or owner.semantic.get('structural_unresolved'):
        raise ValueError('IMPLICIT_DESCRIPTION_OWNER_UNRESOLVED')
    gap = owner.semantic.get('implicit_arguments', {}).get(alias['role'])
    if gap is None or gap.get('license') != 'SUBJECT_AGREEMENT':
        raise ValueError('IMPLICIT_DESCRIPTION_OWNER_UNRESOLVED')
    return gap
