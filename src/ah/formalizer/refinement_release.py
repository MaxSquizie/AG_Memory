"""Validate the released grammar projection without diary-specific defaults."""
from .resources.loader import ResourceMissing


def validate(release,cfg):
    if cfg.get('nominal_composition')!='QUESTION_TREE_V1':
        raise ResourceMissing('refinement requires nominal composition')
    roles={r['role_id']:r for r in release.entries('RoleRegistry')}
    content=roles.get(cfg.get('modifier_content_role'),{})
    # RoleRegistry's optional kind restriction follows the existing nominal
    # contract: absence means no registry-level restriction; R-V still checks
    # the actual known sense and T5 checks the mapped slot.
    if (cfg.get('modifier_content_role') not in roles or content.get('allowed_argument_kinds')
            and not set(content['allowed_argument_kinds']) & {'PROPOSITION','EVENT'}):
        raise ResourceMissing('relative content role must allow PROPOSITION/EVENT')
    rules=cfg['refinement']
    voices=rules['participle_voices']
    markers=rules['relative_markers']
    if len({v['feature'] for v in voices})!=len(voices) or len({(m['lemma'],m['POS']) for m in markers})!=len(markers):
        raise ResourceMissing('duplicate refinement rule')
    for v in voices:
        used={v['host_role'],*v['case_roles'].values()}
        if not used<=roles.keys() or not set(v['case_roles'])<={'nom','gen','dat','acc','abl','ins','loc'}:
            raise ResourceMissing('invalid participle projection')
        if v['host_role'] in v['case_roles'].values():
            raise ResourceMissing('bound participle slot cannot be rebound')
        if any(roles[r].get('allowed_argument_kinds') and 'ENTITY' not in roles[r]['allowed_argument_kinds'] for r in used):
            raise ResourceMissing('participle slots require ENTITY')
