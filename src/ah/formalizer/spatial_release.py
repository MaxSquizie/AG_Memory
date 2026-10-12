"""A relative-place slot must belong to a declared lexical sense and valency."""


def validate(release, cfg):
    rules=cfg['rules']
    if len({r['rule_id'] for r in rules})!=len(rules) or len({r['sense_id'] for r in rules})!=len(rules):
        raise ValueError('SPATIAL_POLICY_DUPLICATE')
    roles={r['role_id'] for r in release.entries('RoleRegistry')}
    for rule in rules:
        if (rule['kind']=='ANCHOR')!=('location_kind' in rule):
            raise ValueError('SPATIAL_POLICY_INVALID')
        if rule['role_id'] not in roles or not any(
                (r['sense_id'],r['lemma'],r['POS'])==(rule['sense_id'],rule['lemma'],rule['POS']) for r in release.entries('R-S')):
            raise ValueError('SPATIAL_SENSE_MISSING')
        valencies=[v for v in release.entries('R-V') if v['sense_id']==rule['sense_id']]
        if rule.get('goal_prepositions'):
            if rule['kind']!='ANCHOR' or rule.get('location_kind')!='DESTINATION':
                raise ValueError('SPATIAL_GOAL_POLICY_INVALID')
            for prep in rule['goal_prepositions']:
                if not any(r['role_id']==rule['role_id'] and prep['lemma'] in r.get('allowed_preps',())
                           and set(prep['cases'])<=set(r.get('allowed_cases',())) for v in valencies for r in v['roles']):
                    raise ValueError('SPATIAL_GOAL_VALENCY_MISSING')
        if not valencies or any(not any(r['role_id']==rule['role_id'] and
                set(r.get('argument_types',())) & {'ENTITY','LOCATION'} and r.get('cardinality',{}).get('max')==1
                for r in v['roles']) for v in valencies):
            raise ValueError('SPATIAL_VALENCY_MISSING')
