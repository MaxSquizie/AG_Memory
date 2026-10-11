"""Released relative-place slots and bounded, source-local anaphora choices."""
from copy import deepcopy
from .canonical_ledger import digest
from .component_probe import _probe


def policy(release):
    return release.entries('ProposalPolicy')[0].get('spatial_references')


def prepare(state, release):
    cfg = policy(release)
    if not cfg: return
    state.require_structures_open('SPATIAL_REFERENCE_CANDIDATES')
    from .regions import protected_intervals
    protected = protected_intervals(state.text)
    evidence = {e.token_id:e for e in state.evidence}
    anchors = {}
    for frame in state.frames:
        if frame.semantic.get('structural_unresolved'): continue
        ev = evidence[frame.predicate_token_ref]
        if any(a <= ev.start < b for a,b in protected): continue
        morph = frame.semantic.get('morph_bindings',{}).get(ev.token_id)
        forms = {(morph['lemma'],morph['pos'])} if morph else {(v.lemma,v.pos) for v in ev.variants}
        slots = frame.semantic['spatial_slots'] = {}
        for rule in cfg['rules']:
            if (rule['lemma'],rule['POS']) not in forms: continue
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
                 if s['rule']['sense_id']==sense_id), None)


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
                    '; relation='+a['location_kind']+'; absolute coordinates UNKNOWN'} for a in slot['options'] if a['entity_ref'] in grounded]
        selected = _probe(state,selector,release,slot['decision_ref'],'spatial_reference',options,
                          state.text[lo:hi],slot['target_range'],
                          question='What place does «'+frame.anchor_span+'» refer to in the TARGET clause: '+
                          state.text[slice(*slot['target_range'])]+
                          '? Select only a source-supported antecedent. Direction and location are not synonyms; '
                          'a directed movement can introduce its relative destination. No coordinates are required. '
                          'If none of the supplied antecedents is established, answer ?. This is a bounded context read, not a global search.')
        if selected:
            slot['selected_place'] = deepcopy(next(a for a in slot['options'] if a['entity_ref']==selected))
            state.decisions[slot['decision_ref']].grounds.append(Ground('D','source-addressed relative place; no absolute coordinates inferred',selected))
        else:
            state.diag('SPATIAL_REFERENCE_UNRESOLVED',slot['decision_ref'])
        resolved_mentions[slot['decision_ref']]=deepcopy(slot.get('selected_place'))
        state.syntax_trace.append({'kind':'SPATIAL_REFERENCE','frame_ref':frame.frame_id,
            'decision_ref':slot['decision_ref'],'options':deepcopy(slot['options']),
            'selected_place':deepcopy(slot.get('selected_place'))})
