"""Unify a direction's target with an explicit goal phrase before scope sealing."""
from copy import deepcopy
from .canonical_ledger import digest
from .component_policy import _morph
from .component_probe import _probe


def bundle(state,release,selector,region,tokens,frame,units,hosts,event,cfg):
    policy=release.entries('ProposalPolicy')[0].get('spatial_references',{})
    if len(event)!=2 or frame.semantic['morph_bindings'][frame.predicate_token_ref]['pos']!='VERB':
        return None
    options=[]
    for direction in event:
        if direction['entities']:continue
        for rule in policy.get('rules',()):
            if (rule['kind']!='ANCHOR' or rule.get('location_kind')!='DESTINATION' or
                (direction['variant'].lemma,direction['variant'].pos)!=(rule['lemma'],rule['POS'])):continue
            for goal in event:
                if len(goal['entities'])!=1 or goal['adjectives']:continue
                noun,reading=goal['entities'][0]
                for prep in rule.get('goal_prepositions',()):
                    if goal['variant'].pos=='PREP' and goal['variant'].lemma==prep['lemma'] and reading.cases & set(prep['cases']):
                        options.append((direction,goal,rule))
    if len(options)!=1:return None
    direction,goal,rule=options[0]
    raw=state.text[slice(*region.source_range)]
    if len(raw)>cfg['context_chars']:return None
    key=region.region_id+'|directional-goal:'+digest([direction['refs'],goal['refs'],rule])
    previous=state.decisions.get(key)
    choice=previous.selected[0] if previous and previous.outcome=='RESOLVED' and len(previous.selected)==1 else None
    if previous is None:
        phrase=state.text[goal['token'].start:goal['entities'][0][0].end]
        choice=_probe(state,selector,release,key,'component_attachment',[
            {'candidate_id':'SHARED_TARGET','label':'«'+direction['token'].span+'» gives the direction of «'+frame.anchor_span+
             '»; «'+phrase+'» names that SAME intended destination, whose identity may remain unknown'},
            {'candidate_id':'OTHER','label':'The source does not establish that the direction and goal phrase describe the same intended destination; retain separate scope alternatives'}],
            raw,region.source_range,question='Do these two source expressions constrain one destination of this movement? '+
            'This asks their local relationship, not which remembered place it is. Do not infer arrival, coordinates, distance or absolute height.')
    if choice!='SHARED_TARGET':return None
    from .component_nominal_tree import materialize
    result=materialize(state,region,tokens,frame,units,hosts,[direction,goal],cfg,
                       shape=('AND',(('MOD',0,None),('MOD',1,None))))
    d=next(f for f in result if f.predicate_token_ref==direction['token'].token_id)
    g=next(f for f in result if f.predicate_token_ref==goal['token'].token_id)
    head,reading=goal['entities'][0]
    d.argument_token_refs=(head.token_id,);d.arguments=(head.span,);d.participants=(d.anchor_span,head.span)
    d.semantic['proposed_roles']={head.token_id:rule['role_id']}
    d.semantic['lexical_units']=deepcopy(g.semantic['lexical_units'])
    d.semantic['morph_bindings'].update({head.token_id:_morph(reading),goal['token'].token_id:_morph(goal['variant'])})
    d.semantic['preposition_bindings']={head.token_id:{'token_ref':goal['token'].token_id,'lemma':goal['variant'].lemma}}
    d.semantic['explicit_directional_goal']={'decision_ref':key,'rule_id':rule['rule_id'],
        'role_id':rule['role_id'],'target_token_ref':head.token_id,'goal_anchor_refs':list(goal['refs']),
        'direction_anchor_ref':direction['token'].token_id,'reference_frame':'UNSPECIFIED',
        'origin':'MOVEMENT_ORIGIN_UNIDENTIFIED','arrival_asserted':False}
    # The preposition is a licensed role marker of this sense, not a second
    # destination or a second asserted lexical modifier.
    for f in result:
        if f.semantic.get('component_child')==g.frame_id:f.semantic['component_child']=d.frame_id
        f.semantic.pop('component_scope_tree',None);f.semantic.pop('component_scope_label',None)
        f.semantic['requires_attachment_probe']=False
    d.semantic.pop('component_child',None)
    state.syntax_trace.append({'kind':'DIRECTIONAL_GOAL','decision_ref':key,
        'source_range':list(region.source_range),**d.semantic['explicit_directional_goal']})
    return [f for f in result if f not in (d,g)]+[d]
