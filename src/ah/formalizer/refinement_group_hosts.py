"""Expose established nominal groups as whole refinement hosts."""
from copy import deepcopy
from .canonical_ledger import digest
from .state import MorphVariant, TokenEvidence


def candidates(frames, evidence, body, *, all_hosts=False):
    found={}
    for frame in frames:
        for group in frame.semantic.get('nominal_groups',()):
            members=group['member_refs']
            if not all_hosts and any(evidence[t].start>=body[0].start for t in members):continue
            bindings=frame.semantic.get('morph_bindings',{})
            if any(t not in bindings for t in members):continue
            from .component_nominal_groups import compatible_cases,intersect_cases
            readings=[bindings[t] for t in members]
            if not compatible_cases(readings):continue
            cases=intersect_cases([set(r['cases']) if r['cases'] else None for r in readings])
            reading=MorphVariant(None,'NOUN',frozenset(cases or ()),number='plur',
                origin='CONTEXTUAL' if cases is None else 'DECLARED',evidence_refs=tuple(members))
            from .refinement_boundaries import agreeing
            if not any(agreeing(reading,v) for v in body[0].variants if v.pos=='PRTF'):continue
            key='nominal-group:'+digest(members)
            host=TokenEvidence(' + '.join(evidence[t].span for t in members),key,
                min(evidence[t].start for t in members),max(evidence[t].end for t in members),variants=(reading,))
            data={'group':deepcopy(group),'bindings':{t:deepcopy(bindings[t]) for t in members},
                  'units':{t:deepcopy(frame.semantic['lexical_units'][t]) for t in members}}
            found.setdefault(key,(frame,host,reading,data))
    return found


def add_host(frame, projected):
    data=projected['group'];members=data['group']['member_refs'];role=projected['rule']['host_role']
    for tid in members:
        frame.semantic['proposed_roles'][tid]=role
        frame.semantic['morph_bindings'][tid]=deepcopy(data['bindings'][tid])
        frame.semantic['lexical_units'][tid]=deepcopy(data['units'][tid])
    frame.argument_token_refs=(*frame.argument_token_refs,*members)
    group=deepcopy(data['group']);group['marker_refs']=[]
    frame.semantic['nominal_groups']=[*frame.semantic.get('nominal_groups',()),group]
    frame.semantic['refinement_binding']={'kind':'PARTICIPLE','host_token_ref':projected['host'].token_id,
        'host_member_refs':list(members),'host_role':role,'voice_feature':projected['rule']['feature'],
        'predicate_ref':frame.predicate_token_ref}
    frame.semantic['component_questions'].append({'kind':'PARTICIPLE_GROUP_HOST',**frame.semantic['refinement_binding']})
