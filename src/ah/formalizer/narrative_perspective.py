"""A shared, bounded narrator hypothesis; choosing it still requires evidence."""
from .canonical_ledger import digest


def scope(state,frame,cfg):
    area=state.region_forest.container(*frame.source_range,kinds={'PARAGRAPH'})
    bounds=tuple(area.source_range) if area else tuple(frame.source_range)
    if bounds[1]-bounds[0]>cfg['context_chars']:return None
    anchor=next(e for e in state.evidence if e.token_id==frame.predicate_token_ref)
    prefix=state.text[:anchor.start]
    if prefix.count('«')>prefix.count('»') or prefix.count(chr(34))%2:return None
    if any(c.get('frame_ref')==frame.frame_id and c.get('attitude') in {'QUOTED','HYPOTHETICAL','EMBEDDED'}
           for f in state.frames for c in f.semantic.get('proposition_args',{}).values()):return None
    source=state.observation.get('source_id') or state.source_uid
    key='narrative-area:'+digest([source,bounds])
    return {'scope_ref':key,'source_range':list(bounds),'entity_ref':'M:narrator:'+digest([source,key])}


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
        'label':'The unidentified narrator of this narrative area. Select ONLY if this clause continues that same first-person perspective, not another character or a quotation. Nearby names do not identify the narrator.'})
