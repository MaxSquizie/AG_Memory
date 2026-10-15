"""Control reuses a parent's selected argument, including a coordinated group.

The alias carries the original mention references, never fresh entities or an
assertion that the dependent event happened. The ordinary group planner owns K.
"""
from copy import deepcopy


def controllers(frame):
    sem=frame.semantic
    for role,gap in sem.get('implicit_arguments',{}).items():
        if gap.get('license')=='SUBJECT_AGREEMENT':
            yield {'frame_ref':frame.frame_id,'role':role},'omitted '+role
    by_role={}
    for tid,role in sem.get('proposed_roles',{}).items():
        by_role.setdefault(role,[]).append(tid)
    for role,refs in by_role.items():
        if any(t not in sem.get('lexical_units',{}) or t not in sem.get('morph_bindings',{}) for t in refs):continue
        alias={'frame_ref':frame.frame_id,'role':role}
        quantities=[g for g in sem.get('qualitative_groups',()) if g['head_ref'] in refs]
        if quantities:alias['qualitative_groups']=quantities
        if len(refs)==1:
            tid=refs[0]
            alias.update(token_ref=tid,morph=sem['morph_bindings'][tid],lexical_unit=sem['lexical_units'][tid])
        else:
            from .component_nominal_groups import group_for
            try:group=group_for(frame,role,sem['proposed_roles'])
            except ValueError:continue
            alias.update(nominal_group=group,members=[{'token_ref':tid,'morph':sem['morph_bindings'][tid],
                         'lexical_unit':sem['lexical_units'][tid]} for tid in refs])
        yield deepcopy(alias),role+' «'+' + '.join(sem['lexical_units'][t]['surface'] for t in refs)+'»'


def members(alias):
    return alias.get('members', [alias] if alias.get('token_ref') else [])


def bind(semantic,alias,subject_role):
    explicit=members(alias)
    if not explicit:
        semantic['shared_implicit_arguments']={subject_role:deepcopy(alias)}
        return
    for member in explicit:
        tid=member['token_ref']
        semantic['proposed_roles'][tid]=subject_role
        semantic['morph_bindings'][tid]=deepcopy(member['morph'])
        semantic['lexical_units'][tid]=deepcopy(member['lexical_unit'])
    if alias.get('nominal_group'):
        semantic['nominal_groups']=[*semantic.get('nominal_groups',()),deepcopy(alias['nominal_group'])]
    semantic['control_binding']={**deepcopy(alias),'child_role':subject_role}


def inherited_role(frame,token_ref,parents):
    """An established controller supplies identity, not a new surface case."""
    binding=frame.semantic.get('control_binding') or {}
    role=binding.get('child_role')
    if not role or frame.construction!='COMPONENTS_V1':return None
    if frame.semantic.get('morph_bindings',{}).get(frame.predicate_token_ref,{}).get('pos')!='INFN':return None
    parent=(parents or {}).get(binding.get('frame_ref'))
    if parent is None or parent.semantic.get('structural_unresolved'):return None
    alias={k:v for k,v in binding.items() if k!='child_role'}
    if not any(candidate==alias for candidate,_ in controllers(parent)):return None
    member=next((m for m in members(alias) if m['token_ref']==token_ref),None)
    if member is None or frame.semantic.get('proposed_roles',{}).get(token_ref)!=role:return None
    if (frame.semantic.get('morph_bindings',{}).get(token_ref)!=member['morph'] or
            frame.semantic.get('lexical_units',{}).get(token_ref)!=member['lexical_unit']):return None
    return role


def expose_mentions(candidate,alias,evidence):
    by_id={e.token_id:e for e in evidence}
    for member in members(alias):
        ev=by_id[member['token_ref']]
        candidate.argument_token_refs=(*candidate.argument_token_refs,ev.token_id)
        candidate.arguments=(*candidate.arguments,ev.span)
        candidate.participants=(*candidate.participants,ev.span)
