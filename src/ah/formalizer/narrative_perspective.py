"""Persistent source narrator; bounded prompt windows never reset identity."""
from .canonical_ledger import digest


def scope(state,frame,cfg):
    try:area=state.region_forest.container(*frame.source_range,kinds={'PARAGRAPH'})
    except ValueError:area=None
    bounds=tuple(area.source_range) if area else tuple(frame.source_range)
    if bounds[1]-bounds[0]>cfg['context_chars']:
        if cfg.get('narrative_continuity')!='SOURCE_CARRIER_V1':return None
        start=max(bounds[0],frame.source_range[0]-cfg['context_chars']//2)
        bounds=(start,min(bounds[1],start+cfg['context_chars']))
        if frame.source_range[1]>bounds[1]:return None
    anchor=next(e for e in state.evidence if e.token_id==frame.predicate_token_ref)
    prefix=state.text[:anchor.start]
    if prefix.count('«')>prefix.count('»') or prefix.count(chr(34))%2:return None
    if any(c.get('frame_ref')==frame.frame_id and c.get('attitude') in {'QUOTED','HYPOTHETICAL','EMBEDDED'}
           for f in state.frames for c in f.semantic.get('proposition_args',{}).values()):return None
    source=state.observation.get('source_id') or state.source_uid
    continuous=cfg.get('narrative_continuity')=='SOURCE_CARRIER_V1'
    key='narrative-area:'+digest([source,state.observation.get('source_revision',1),'SOURCE_NARRATOR'] if continuous else [source,bounds])
    return {'scope_ref':key,'source_range':list(bounds),'entity_ref':'M:narrator:'+digest([source,key]),'continuity':'SOURCE_CARRIER_V1' if continuous else 'LOCAL_AREA'}


def prepare(state,gap,frame,cfg):
    if not cfg.get('narrative_groups') or gap['license']!='SUBJECT_AGREEMENT':return
    area=scope(state,frame,cfg)
    if area is None:return
    gap['narrative_area']=area
    gap['context_range']=area['source_range']
    if gap['features'].get('number')!='sing':return
    gap['options'].append({'candidate_id':'narrator:'+area['scope_ref'],'kind':'NARRATOR',
        'entity_ref':area['entity_ref'],'participant_kind':'INDIVIDUAL',
        'perspective':'FIRST_PERSON','narrative_scope_ref':area['scope_ref'],
        'perspective_source_range':area['source_range'],
        'label':('Current unidentified narrator of this SOURCE. A new paragraph, date heading or reading window does not change this referent. Select for first-person narration unless the text establishes a different speaker; do not confuse another character or a quotation with the narrator.' if area['continuity']=='SOURCE_CARRIER_V1' else 'The unidentified narrator of this narrative area. Select ONLY if this clause continues that same first-person perspective, not another character or a quotation. Nearby names do not identify the narrator.')})
    if area['continuity']!='SOURCE_CARRIER_V1':return
    offset=state.observation.get('range',[0,0])[0]+frame.source_range[0]
    source=state.observation.get('source_id') or state.source_uid
    shifted='narrative-area:'+digest([source,state.observation.get('source_revision',1),'NARRATOR_SWITCH',offset])
    gap['options'].append({'candidate_id':'narrator-switch:'+shifted,'kind':'NARRATOR_SHIFT',
        'entity_ref':'M:narrator:'+digest([source,shifted]),'participant_kind':'INDIVIDUAL',
        'perspective':'FIRST_PERSON','narrative_scope_ref':shifted,'perspective_source_range':area['source_range'],
        'label':'A DIFFERENT unidentified narrator takes over here. Select ONLY with positive evidence of a speaker/viewpoint change, never because the paragraph, date or scene changed. An unrelated third-person action is not a narrator switch.'})


def current(resolved):
    for value in reversed(list(resolved.values())):
        if value.get('perspective')!='FIRST_PERSON':continue
        members=value.get('known_members',[]) if value.get('participant_kind')=='GROUP' else [value]
        for member in members:
            if member.get('narrative_scope_ref'):return member
    return None
