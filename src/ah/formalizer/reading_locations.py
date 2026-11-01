"""Explicit morphology locations. Candidate collections are not selected uses."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Location:
    path: str
    token_ref: str
    reading: dict
    context: dict
    selected: bool = True


def locations(frame):
    s=frame.semantic
    def item(path,tid,reading,context=None,selected=True):
        return Location(path,tid,reading,{'predicate_ref':frame.predicate_token_ref,
            'role':s.get('proposed_roles',{}).get(tid),**(context or {})},selected)
    for field in ('morph_bindings','pp_readings'):
        for tid,r in s.get(field,{}).items():yield item(field,tid,r)
    for field in ('nominal_dependencies','attribute_constraints'):
        for d in s.get(field,()):
            ctx={k:d.get(k) for k in ('kind','host_ref','host_layer','case','apposition_rule')}
            yield item(field+'.morph',d['head_ref'],d['morph'],ctx)
            if d.get('host_morph'):yield item(field+'.host_morph',d['host_ref'],d['host_morph'],ctx)
    d=s.get('dependency_evidence')
    if d:
        ctx={k:d.get(k) for k in ('kind','host_ref','host_layer','case','apposition_rule')}
        yield item('dependency_evidence.morph',d['head_ref'],d['morph'],ctx)
        if d.get('host_morph'):yield item('dependency_evidence.host_morph',d['host_ref'],d['host_morph'],ctx)
    for tid,g in s.get('group_readings',{}).items():
        for field in ('selected_head_reading','external_reading'):
            yield item('group_readings.'+field,tid,g[field])
    groups=[('qualitative_groups',g) for g in s.get('qualitative_groups',())]
    groups += [('control_binding.qualitative_groups',g) for g in s.get('control_binding',{}).get('qualitative_groups',())]
    for prefix,g in groups:
        ctx={'head_ref':g['head_ref'],'marker_ref':g['marker_ref'],'quantity_refs':g.get('quantity_token_refs',())}
        for field in ('internal_readings','marker_variants'):
            tid=g['head_ref'] if field=='internal_readings' else g['marker_ref']
            for r in g.get(field,()):yield item(prefix+'.'+field,tid,r,ctx,False)
        for case,readings in g.get('internal_by_case',{}).items():
            for r in readings:yield item(prefix+'.internal_by_case',g['head_ref'],r,{**ctx,'external_case':case},False)
        for field in ('selected_head_reading','external_reading'):
            if g.get(field):yield item(prefix+'.'+field,g['head_ref'],g[field],ctx)
    control=s.get('control_binding')
    if control:
        from .control_arguments import members
        for member in members(control):
            yield item('control_binding.morph',member['token_ref'],member['morph'],
                {'owner_frame':control['frame_ref'],'owner_role':control['role'],'child_role':control.get('child_role')})
    binding=s.get('quantifier_restriction')
    if binding and binding.get('selected_reading'):
        yield item('quantifier_restriction.selected_reading',binding['head_ref'],binding['selected_reading'],
            {'binding_slot':binding['binding_slot'],'marker_refs':binding['marker_refs']})
