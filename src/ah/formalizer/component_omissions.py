"""Released omission licenses; mandatory roles remain in the mapped template."""
from .canonical_ledger import digest
from .component_policy import _features


def licensed_gaps(roles, missing, variant, cfg, *, quality=False, valency=None):
    gaps = {}
    subject = cfg['subject_role']
    if not quality and subject in missing and variant.number in {'sing', 'plur'}:
        gaps[subject] = {'features': _features(variant), 'license': 'SUBJECT_AGREEMENT'}
    for role in roles:
        rid = role['role_id']
        license = role.get('omission')
        if rid not in missing or rid == subject or not license or valency is None:
            continue
        # No predicate agreement is copied to an object. One ENTITY-valued
        # slot does not establish singularity, animacy, a name or membership.
        gaps[rid] = {'features': {}, 'license': 'UNSPECIFIED_ENTITY',
                     'omission_rule_id': license['rule_id'],
                     'valency_digest': digest(valency)}
    return gaps


def licenses_match(frame, valency):
    """T3 cannot borrow a license from a different sense/construction."""
    return all(g.get('license') != 'UNSPECIFIED_ENTITY' or
               g['valency_digest'] == digest(valency)
               for g in frame.semantic.get('implicit_arguments', {}).values())
