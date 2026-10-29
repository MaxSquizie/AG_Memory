"""Bind a released relative pronoun to its antecedent's existing nominal slot."""
from .canonical_ledger import digest
from .component_policy import _morph, _features, compatible
from .component_probe import _probe


def compose(state,release,selector,region,body,owner,host,reading,rule,cfg,depth,*,group=None):
    from .component_refinement import compose_area,region_for,root,accepted
    marker=body[0]; options={}
    for mv in marker.variants:
        if (not rule.get('general') and (mv.lemma!=rule['lemma'] or mv.pos!=rule['POS'])) or not rule.get('general') and not compatible(_features(mv),_features(reading)):continue
        for case in sorted(mv.cases):
            role=cfg['open_case_roles'].get(case)
            if not role:continue
            morph={k:v for k,v in _morph(mv).items() if k!='score'}
            options[digest([marker.token_id,morph,role])]={'marker':marker,'marker_reading':mv,
                'host':host,'reading':reading,'host_role':role,'kind':'RELATIVE_PRONOUN'}
    if rule.get('general'):
        from .structural_tasks import choose,licensed
        from .probe_prerequisites import accepted as prerequisite
        from .probe_wording import reading as describe,role as role_text
        role=choose(state,release,selector,region,cfg,'relative_argument_role',[
            {'candidate_id':r['role_id'],'label':r['role_id']+': '+role_text(r['role_id'])} for r in release.entries('RoleRegistry')],
            'Which semantic role does «'+marker.span+'» fill inside the description? Its antecedent is «'+host.span+'». '
            'Account for passive voice; neither the antecedent case nor the pronoun case alone decides the role.')
        if not role:return [],None
        variants={digest(_morph(m)):m for m in marker.variants}
        selected=choose(state,release,selector,region,cfg,'relative_marker_reading',[
            {'candidate_id':cid,'label':describe(_morph(m))} for cid,m in variants.items()],
            'Which whole reading of «'+marker.span+'» at '+str(marker.start)+' fits this use? '
            'Established antecedent: «'+host.span+'» at '+str(host.start)+'. '
            'Established role inside the description: '+role_text(role[0]['candidate_id'])+'. '
            'Preserve this role; do not select another role or copy the antecedent case.',
            prerequisites=(prerequisite('relative_argument_role',role),))
        if not selected:return [],None
        mv=variants[selected[0]['candidate_id']]
        options={'general:'+digest([marker.token_id,role[0],selected[0]]):{'marker':marker,'marker_reading':mv,
            'host':host,'reading':reading,'host_role':role[0]['candidate_id'],'kind':'RELATIVE_PRONOUN','general':True,
            'function_proofs':[role[1],selected[1]]}}
    if not options or len(options)>cfg['max_candidates']:
        state.diag('RELATIVE_PRONOUN_ROLE_UNRESOLVED',marker.token_id);return [],None
    key=region.region_id+'|relative-pronoun-role:'+marker.token_id
    from .probe_wording import reading as reading_text,role as role_text
    choices=[{'candidate_id':cid,'label':'«'+marker.span+'» refers to the already selected «'+host.span+
        '» @'+str(host.start)+' and fills '+role_text(spec['host_role'])+' inside its relative clause; whole reading='+reading_text(_morph(spec['marker_reading']))}
        for cid,spec in options.items()]
    chosen=next(iter(options)) if rule.get('general') else _probe(state,selector,release,key,'relative_pronoun_role',choices,
        state.text[slice(*region.source_range)],region.source_range,
        question='Select the relative pronoun grammatical role inside the description. Its antecedent is already selected. '
        'The antecedent case in the parent does not determine its role here. Do not create another person or assert the description independently.', target_refs=(marker.token_id,))
    if chosen is None:return [],None
    child_tokens=body[1:]
    if not child_tokens:return [],None
    cr=region_for(state,region,child_tokens,'RELATIVE_PRONOUN')
    if group is not None:options[chosen]['group']=group
    frames=compose_area(state,release,selector,cr,child_tokens,cfg,depth+1,attachment=options[chosen])
    if rule.get('general') and not all(licensed(state,p) for p in options[chosen]['function_proofs']):
        state.diag('RELATIVE_PRONOUN_PREMISE_RETIRED',marker.token_id)
        for frame in frames:frame.semantic['structural_unresolved']=True
        return frames,None
    content=root(frames)
    hosts=[f for f in accepted(frames) if f.semantic.get('refinement_binding',{}).get('marker_ref')==marker.token_id]
    if content is None or len(hosts)!=1:return frames,None
    host_frame=hosts[0]
    if rule.get('general'):
        host_frame.semantic['refinement_binding']['source_relative_binding']=True
        host_frame.semantic['refinement_binding']['function_proofs']=options[chosen]['function_proofs']
    if group is None:
        host_frame.semantic['lexical_units'][host.token_id]=dict(owner.semantic['lexical_units'][host.token_id])
    state.syntax_trace.append({'kind':'RELATIVE_PRONOUN_BINDING','decision_ref':key,
        'marker_ref':marker.token_id,'host_token_ref':host.token_id,'host_role':options[chosen]['host_role'],
        'predicate_ref':host_frame.predicate_token_ref,'content_ref':content.frame_id})
    return frames,host_frame


def projection(pv,attachment,cfg):
    if not attachment.get('general') and attachment['host_role']==cfg['subject_role'] and not compatible(_features(pv),_features(attachment['marker_reading'])):return None
    return {**attachment,'relative_marker':attachment['marker'],
        'rule':{'host_role':attachment['host_role'],'case_roles':
            {c:r for c,r in cfg['open_case_roles'].items() if r!=attachment['host_role']}}}


def role_readings(frame,tid,evidence,default):
    """Use the pronoun's case for its clause role, never rewrite the antecedent."""
    binding=frame.semantic.get('refinement_binding',{})
    if binding.get('kind')!='RELATIVE_PRONOUN' or tid not in {binding.get('host_token_ref'),*binding.get('host_member_refs',())}:
        return default
    if frame.semantic.get('proposed_roles',{}).get(tid)!=binding.get('host_role'):return ()
    marker=evidence.get(binding.get('marker_ref'))
    selected=frame.semantic.get('morph_bindings',{}).get(binding.get('marker_ref'))
    if marker is None or not selected:return ()
    clean=lambda row:{k:v for k,v in row.items() if k!='score'}
    return tuple(v for v in marker.variants if clean(_morph(v))==clean(selected))


def binding_live(state,frame):
    """Retain relative-role and reading evidence beyond child construction."""
    binding=frame.semantic.get('refinement_binding',{})
    proofs=binding.get('function_proofs')
    if proofs is None:return not binding.get('source_relative_binding')  # legacy resource-defined projection
    from .structural_tasks import licensed
    if len(proofs)!=2 or not all(licensed(state,p) for p in proofs):return False
    marker=binding.get('marker_ref')
    reading=frame.semantic.get('morph_bindings',{}).get(marker)
    return (proofs[0].get('candidate_id')==binding.get('host_role')
            and reading is not None and proofs[1].get('candidate_id')==digest(reading)
            and all(frame.semantic.get('proposed_roles',{}).get(t)==binding.get('host_role')
                    for t in binding.get('host_member_refs',[binding.get('host_token_ref')])))
