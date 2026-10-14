"""Released shared-destination constraint, before ordinary scope materialization.

This rule binds a referent slot. It neither constructs nor rewires a tree.
"""
from .canonical_ledger import digest
from .component_policy import _morph
from .component_probe import _probe


def constrain(state,release,selector,region,frame,units,hosts,event,cfg):
    policy=release.entries('ProposalPolicy')[0].get('spatial_references',{})
    replacements={}; consumed=set()
    for direction in event:
        if direction['entities']:continue
        options={}
        for rule in policy.get('rules',()):
            if (rule['kind']!='ANCHOR' or rule.get('location_kind')!='DESTINATION' or
                (direction['variant'].lemma,direction['variant'].pos)!=(rule['lemma'],rule['POS'])):continue
            for goal in event:
                if len(goal['entities'])!=1 or id(goal) in consumed:continue
                head,reading=goal['entities'][0]
                for prep in rule.get('goal_prepositions',()):
                    if goal['variant'].pos=='PREP' and goal['variant'].lemma==prep['lemma'] and reading.cases & set(prep['cases']):
                        options[digest([direction['refs'],goal['refs'],rule])]=(goal,rule)
        if not options:continue
        if len(options)+1>cfg['max_candidates']:
            state.diag('COMPONENT_SEARCH_INCOMPLETE',region.region_id)
            return None
        key=region.region_id+'|shared-destination:'+digest([direction['refs'],sorted(options)])
        choices=[{'candidate_id':cid,'label':'«'+direction['token'].span+'» and «'+
                  state.text[g['source_range'][0]:g['source_range'][1]]+'» describe the SAME intended destination'}
                 if g.get('source_range') else {'candidate_id':cid,'label':'«'+direction['token'].span+
                  '» and «'+g['token'].span+' '+g['entities'][0][0].span+'» describe the SAME intended destination'}
                 for cid,(g,r) in options.items()]
        choices.append({'candidate_id':'SEPARATE','label':'No shared destination is established; retain separate scope slots'})
        choice=_probe(state,selector,release,key,'referent_constraint',choices,
            state.text[slice(*region.source_range)],region.source_range,
            question='Do these expressions constrain one destination of «'+frame.anchor_span+'»? '
            'This is a local slot constraint, not identification of a remembered place. '
            'Do not infer arrival, coordinates, distance or absolute height.')
        if choice is None:return None
        if choice=='SEPARATE':continue
        goal,rule=options[choice];head,reading=goal['entities'][0]
        binding={'decision_ref':key,'rule_id':rule['rule_id'],'role_id':rule['role_id'],
                 'target_token_ref':head.token_id,'goal_anchor_refs':list(goal['refs']),
                 'direction_anchor_ref':direction['token'].token_id,'reference_frame':'UNSPECIFIED',
                 'origin':'MOVEMENT_ORIGIN_UNIDENTIFIED','arrival_asserted':False}
        replacements[id(direction)]={**direction,'refs':tuple(dict.fromkeys((*direction['refs'],*goal['refs']))),
            'entities':goal['entities'],'adjectives':goal['adjectives'],'nominal_role':rule['role_id'],
            'role_marker':(goal['token'],goal['variant']),'referent_constraint':binding}
        consumed.add(id(goal))
        state.syntax_trace.append({'kind':'DIRECTIONAL_GOAL','source_range':list(region.source_range),**binding})
    return ([replacements.get(id(u),u) for u in units if id(u) not in consumed],
            [replacements.get(id(u),u) for u in event if id(u) not in consumed])
