"""Validate the opt-in syntactic dependency constructor against released T maps."""
from .loader import ResourceMissing


def validate_dependency_policy(release,cfg):
    if cfg.get('nominal_composition')!='QUESTION_TREE_V1' or not cfg.get('apposition_markers') or set(cfg.get('dependency_senses',{}))!={'GENITIVE','APPOSITION'}:
        raise ResourceMissing('RESOURCE_MISSING: incomplete dependency constructor policy')
    if any(not marker or any(c.isalnum() for c in marker) for marker in cfg['apposition_markers']):
        raise ResourceMissing('RESOURCE_MISSING: apposition marker must be punctuation')
    expected={cfg['nominal_host_role'],cfg['preposition_nominal_role']}
    if len(set(cfg['dependency_senses'].values()))!=2:
        raise ResourceMissing('RESOURCE_MISSING: dependency kinds need distinct senses')
    for sid in cfg['dependency_senses'].values():
        senses=[s for s in release.entries('R-S') if s['sense_id']==sid]
        vals=[v for v in release.entries('R-V') if v['sense_id']==sid]
        maps=[m for m in release.entries('TemplateMap') if m['sense_id']==sid and set(m['roles'])==expected]
        if len(senses)!=1 or len(vals)!=1 or len(maps)!=1:
            raise ResourceMissing('RESOURCE_MISSING: dependency sense/valency/mapping absent or ambiguous')
        val=vals[0]
        if (val.get('state_class')!='STATE' or {r['role_id'] for r in val['roles']}!=expected or
            any(set(r.get('argument_types',()))!={'ENTITY'} or r.get('cardinality')!={'min':1,'max':1} for r in val['roles'])):
            raise ResourceMissing('RESOURCE_MISSING: dependency relation must be binary ENTITY STATE')
