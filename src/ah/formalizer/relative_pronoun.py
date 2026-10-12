"""Bind a released relative pronoun to its antecedent's existing nominal slot."""
from .canonical_ledger import digest
from .component_policy import _morph, _features, compatible
from .component_probe import _probe


def compose(state,release,selector,region,body,owner,host,reading,rule,cfg,depth):
    from .component_refinement import compose_area,region_for,root,accepted
    marker=body[0]; options={}
    for mv in marker.variants:
        if mv.lemma!=rule['lemma'] or mv.pos!=rule['POS'] or not compatible(_features(mv),_features(reading)):continue
        for case in sorted(mv.cases):
            role=cfg['open_case_roles'].get(case)
            if not role:continue
            morph={k:v for k,v in _morph(mv).items() if k!='score'}
            options[digest([marker.token_id,morph,role])]={'marker':marker,'marker_reading':mv,
                'host':host,'reading':reading,'host_role':role,'kind':'RELATIVE_PRONOUN'}
    if not options or len(options)>cfg['max_candidates']:
        state.diag('RELATIVE_PRONOUN_ROLE_UNRESOLVED',marker.token_id);return [],None
    key=region.region_id+'|relative-pronoun-role:'+marker.token_id
    choices=[{'candidate_id':cid,'label':'«'+marker.span+'» refers to the already selected «'+host.span+
        '» and fills '+spec['host_role']+' inside its relative clause; whole reading='+str(
        {k:v for k,v in _morph(spec['marker_reading']).items() if k in {'lemma','pos','cases','number','gender'}})}
        for cid,spec in options.items()]
    chosen=_probe(state,selector,release,key,'relative_pronoun_role',choices,
        state.text[slice(*region.source_range)],region.source_range,
        question='Select the relative pronoun grammatical role inside the description. Its antecedent is already selected. '
        'The antecedent case in the parent does not determine its role here. Do not create another person or assert the description independently.')
    if chosen is None:return [],None
    child_tokens=body[1:]
    if not child_tokens:return [],None
    cr=region_for(state,region,child_tokens,'RELATIVE_PRONOUN')
    frames=compose_area(state,release,selector,cr,child_tokens,cfg,depth+1,attachment=options[chosen])
    content=root(frames)
    hosts=[f for f in accepted(frames) if f.semantic.get('refinement_binding',{}).get('marker_ref')==marker.token_id]
    if content is None or len(hosts)!=1:return frames,None
    host_frame=hosts[0]
    host_frame.semantic['lexical_units'][host.token_id]=dict(owner.semantic['lexical_units'][host.token_id])
    state.syntax_trace.append({'kind':'RELATIVE_PRONOUN_BINDING','decision_ref':key,
        'marker_ref':marker.token_id,'host_token_ref':host.token_id,'host_role':options[chosen]['host_role'],
        'predicate_ref':host_frame.predicate_token_ref,'content_ref':content.frame_id})
    return frames,host_frame


def projection(pv,attachment,cfg):
    if pv.pos!='VERB' or pv.mood=='imperative':return None
    if attachment['host_role']==cfg['subject_role'] and not compatible(_features(pv),_features(attachment['marker_reading'])):return None
    return {**attachment,'relative_marker':attachment['marker'],
        'rule':{'host_role':attachment['host_role'],'case_roles':
            {c:r for c,r in cfg['open_case_roles'].items() if r!=attachment['host_role']}}}


def role_readings(frame,tid,evidence,default):
    """Use the pronoun's case for its clause role, never rewrite the antecedent."""
    binding=frame.semantic.get('refinement_binding',{})
    if binding.get('kind')!='RELATIVE_PRONOUN' or binding.get('host_token_ref')!=tid:
        return default
    if frame.semantic.get('proposed_roles',{}).get(tid)!=binding.get('host_role'):return ()
    marker=evidence.get(binding.get('marker_ref'))
    selected=frame.semantic.get('morph_bindings',{}).get(binding.get('marker_ref'))
    if marker is None or not selected:return ()
    clean=lambda row:{k:v for k,v in row.items() if k!='score'}
    return tuple(v for v in marker.variants if clean(_morph(v))==clean(selected))
