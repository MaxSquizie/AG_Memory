"""Released relative-place slots and bounded source/memory anaphora choices."""
from copy import deepcopy
from .canonical_ledger import digest
from .component_probe import _probe


def policy(release):
    return release.entries('ProposalPolicy')[0].get('spatial_references')


def prepare(state, release, selector=None):
    cfg = policy(release)
    if not cfg: return
    state.require_structures_open('SPATIAL_REFERENCE_CANDIDATES')
    evidence = {e.token_id:e for e in state.evidence}
    anchors = {}
    for frame in state.frames:
        if frame.semantic.get('structural_unresolved'): continue
        ev = evidence[frame.predicate_token_ref]
        morph = frame.semantic.get('morph_bindings',{}).get(ev.token_id)
        forms = {(morph['lemma'],morph['pos'])} if morph else {(v.lemma,v.pos) for v in ev.variants}
        slots = frame.semantic['spatial_slots'] = {}
        rules=[r for r in cfg['rules'] if (r['lemma'],r['POS']) in forms]
        if selector is not None:
            key=frame.frame_id+'|spatial-function'
            choice=_probe(state,selector,release,key,'spatial_function',[
                {'candidate_id':'NONE','label':'No separate contextual place slot is expressed by this lexical occurrence'},
                {'candidate_id':'LOCATION','label':'An unspecified relative location is introduced'},
                {'candidate_id':'DESTINATION','label':'An unspecified relative destination is introduced'},
                {'candidate_id':'ORIGIN','label':'An unspecified relative origin is introduced'},
                {'candidate_id':'REFERENCE','label':'The occurrence refers to a place supplied by context'}],
                state.text[slice(*frame.source_range)],frame.source_range,
                question='What spatial function, if any, does «'+ev.span+'» have? Preserve its surrounding scope, including quotation. No coordinates can be inferred.')
            if choice is None:
                frame.semantic['structural_unresolved']=True;state.diag('SPATIAL_FUNCTION_UNRESOLVED',frame.frame_id);continue
            if choice=='NONE':continue
            selected_kind='REFERENCE' if choice=='REFERENCE' else 'ANCHOR'
            matching=[r for r in rules if r['kind']==selected_kind and (choice=='REFERENCE' or r.get('location_kind')==choice)]
            role=None
            if not matching:
                role=_probe(state,selector,release,key+'|role','spatial_role',[
                    {'candidate_id':r['role_id'],'label':r['role_id']} for r in release.entries('RoleRegistry')],
                    state.text[slice(*frame.source_range)],frame.source_range,
                    question='Which role does this '+choice+' place fill in «'+ev.span+'»?')
                if role is None:
                    frame.semantic['structural_unresolved']=True;state.diag('SPATIAL_FUNCTION_UNRESOLVED',frame.frame_id);continue
            rules=matching or [{'rule_id':'SOURCE_SPATIAL_FUNCTION_V1','sense_id':None,'role_id':role,
                               'kind':selected_kind,'generic':True,**({'location_kind':choice} if selected_kind=='ANCHOR' else {})}]
        for rule in rules:
            if rule['role_id'] in frame.semantic.get('proposed_roles',{}).values():
                if selector is not None:
                    frame.semantic['structural_unresolved']=True
                    state.diag('SPATIAL_ROLE_CONFLICT',frame.frame_id)
                continue
            slot = {'rule':deepcopy(rule), 'mention_ref':ev.token_id,
                    'decision_ref':frame.frame_id+'|spatial:'+rule['rule_id']}
            if rule['kind']=='ANCHOR':
                place = {'anchor_ref':ev.token_id,'source_tag':[state.source_uid,state.interpretation_version],
                         'source_range':[ev.start,ev.end],'raw':ev.span,
                         'rule_id':rule['rule_id'],'resource_sha256':release.sha256,
                         'location_kind':rule['location_kind'],'coordinates_status':'UNKNOWN'}
                place['entity_ref'] = 'M:place:'+digest(place)
                slot['place'] = place
                # Alternative structural uses of one source occurrence do not
                # introduce several physical places or several identical choices.
                anchors[place['entity_ref']] = place
            slots[rule['rule_id']] = slot
    for frame in state.frames:
        for slot in frame.semantic.get('spatial_slots',{}).values():
            if slot['rule']['kind']!='REFERENCE': continue
            ev = evidence[slot['mention_ref']]
            regions=[r.source_range for r in state.region_forest.regions if r.kind=='SENTENCE' and r.source_range[0]<=ev.start<ev.end<=r.source_range[1]]
            target=min(regions,key=lambda r:r[1]-r[0]) if regions else frame.source_range
            slot['target_range']=list(target)
            slot['decision_ref']='spatial:'+digest([state.source_uid,state.interpretation_version,ev.token_id,slot['rule']['rule_id']])
            slot['context_range'] = [max(0,target[0]-cfg['context_chars']//2),target[1]]
            lo,hi = slot['context_range']
            slot['options'] = [deepcopy(a) for a in anchors.values()
                               if lo <= a['source_range'][0] < a['source_range'][1] <= ev.start]
            slot['options'].sort(key=lambda a:(a['source_range'],a['entity_ref']))
            slot['search_incomplete'] = len(slot['options'])>cfg['max_candidates'] or hi-lo>cfg['context_chars']


def for_sense(frame, sense_id):
    return next((s for s in frame.semantic.get('spatial_slots',{}).values()
                 if s['rule']['sense_id']==sense_id or s['rule'].get('generic')), None)


def resolve(state, release, selector):
    if not policy(release): return
    from .state import Ground
    grounded = set()
    for source in state.frames:
        decision=state.decisions.get(source.frame_id+'|predicate_value')
        selected=source.semantic.get('candidate_specs',{}).get(decision.selected[0]) if decision and len(decision.selected)==1 else None
        anchor=for_sense(source,selected.get('sense_id')) if selected else None
        if decision and decision.outcome=='RESOLVED' and not source.semantic.get('structural_unresolved') and anchor and anchor['rule']['kind']=='ANCHOR':
            grounded.add(anchor['place']['entity_ref'])
    resolved_mentions = {}
    for frame in state.frames:
        d = state.decisions.get(frame.frame_id+'|predicate_value')
        spec = frame.semantic.get('candidate_specs',{}).get(d.selected[0]) if d and len(d.selected)==1 else None
        slot = for_sense(frame,spec.get('sense_id')) if spec and d.outcome=='RESOLVED' else None
        if slot is None: continue
        if slot['rule']['kind']=='ANCHOR':
            slot['selected_place'] = deepcopy(slot['place'])
            slot['decision_ref'] = frame.frame_id+'|predicate_value'
            continue
        if slot['decision_ref'] in resolved_mentions:
            if resolved_mentions[slot['decision_ref']] is not None:
                slot['selected_place']=deepcopy(resolved_mentions[slot['decision_ref']])
            state.syntax_trace.append({'kind':'SPATIAL_REFERENCE_REUSED','frame_ref':frame.frame_id,
                                      'decision_ref':slot['decision_ref']})
            continue
        if slot['search_incomplete']:
            state.diag('SPATIAL_REFERENCE_SEARCH_INCOMPLETE',slot['decision_ref']); continue
        lo,hi = slot['context_range']
        options = [{'candidate_id':a['entity_ref'], 'label':
                    'Same relative place introduced by «'+a['raw']+'» at '+str(a['source_range'])+
                    '; relation='+a['location_kind']+'; absolute coordinates UNKNOWN'+
                    ('; prior source '+str(a['source_tag'])+' excerpt: «'+a['memory_excerpt']+'»' if a.get('memory_binding_ref') else '')}
                   for a in slot['options'] if a.get('memory_binding_ref') or a['entity_ref'] in grounded]
        if sum(len(o['label']) for o in options)+hi-lo > policy(release)['context_chars']:
            state.diag('SPATIAL_REFERENCE_SEARCH_INCOMPLETE',slot['decision_ref']); continue
        selected = _probe(state,selector,release,slot['decision_ref'],'spatial_reference',options,
                          state.text[lo:hi],slot['target_range'],
                          question='What place does «'+frame.anchor_span+'» refer to in the TARGET clause: '+
                          state.text[slice(*slot['target_range'])]+
                          '? Select only a source-supported antecedent. Direction and location are not synonyms; '
                          'a directed movement can introduce its relative destination. No coordinates are required. '
                          'If none of the supplied antecedents is established, answer ?. This is a bounded context read, not a global search.')
        if selected:
            slot['selected_place'] = deepcopy(next(a for a in slot['options'] if a['entity_ref']==selected))
            chosen=slot['selected_place']
            state.decisions[slot['decision_ref']].grounds.append(Ground(
                'P' if chosen.get('memory_binding_ref') else 'D',
                'frozen active-place binding '+chosen['memory_binding_ref']+'; read '+slot['memory_read_hash']
                if chosen.get('memory_binding_ref') else 'source-addressed relative place; no absolute coordinates inferred',selected))
        else:
            state.diag('SPATIAL_REFERENCE_UNRESOLVED',slot['decision_ref'])
        resolved_mentions[slot['decision_ref']]=deepcopy(slot.get('selected_place'))
        state.syntax_trace.append({'kind':'SPATIAL_REFERENCE','frame_ref':frame.frame_id,
            'decision_ref':slot['decision_ref'],'options':deepcopy(slot['options']),
            'selected_place':deepcopy(slot.get('selected_place'))})
