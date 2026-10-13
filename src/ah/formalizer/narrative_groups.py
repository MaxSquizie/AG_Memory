"""Closed contextual hypotheses for open-membership narrated groups."""
from copy import deepcopy
from .canonical_ledger import digest
from .component_policy import policy


def config(release):
    return (policy(release) or {}).get('narrative_groups')


def option(gap, member, source):
    key='narrative-group:'+digest([gap['gap_id'],member['candidate_id']])
    return {'candidate_id':key,'kind':'NARRATIVE_GROUP','entity_ref':'M:implicit:'+digest([source,gap['gap_id']]),
        'participant_kind':'GROUP','member':deepcopy(member),
        'label':'Separate first-person group: narrator = '+member['label']+'; other members UNKNOWN. Requires supported narrator identity and perspective for this clause.'}


def add_local(state,gap,previous,release,frame):
    if not config(release) or gap['features'].get('number')!='plur' or gap['license']!='SUBJECT_AGREEMENT':return
    anchor=next(e for e in state.evidence if e.token_id==frame.predicate_token_ref)
    prefix=state.text[:anchor.start]
    if prefix.count('«')>prefix.count('»') or prefix.count(chr(34))%2:return
    if any(c.get('frame_ref')==frame.frame_id and c.get('attitude') in {'QUOTED','HYPOTHETICAL','EMBEDDED'}
           for f in state.frames for c in f.semantic.get('proposition_args',{}).values()):return
    source=state.observation.get('source_id') or state.source_uid
    cfg=policy(release);end=gap['context_range'][1]
    members=[dict(x,candidate_id=x['key']) for x in previous if x['features'].get('number')=='sing'
        and x['end']<=frame.source_range[0] and end-x['end']<=cfg['context_chars'] and x['features'].get('animacy')!='inan']
    # Introduction is a referent of the source's narrator, never the uploader.
    members.append({'candidate_id':'narrator:new','kind':'ANONYMOUS','entity_ref':'M:narrator:'+digest([source,gap['gap_id']]),
        'participant_kind':'INDIVIDUAL','label':'an unidentified narrator of this local narrative area (use an established narrator reference instead when the supplied context supports one)'})
    gap['options'].extend(option(gap,m,source) for m in members)
    gap['narrative_source']=source


def add_memory(gap,rows,release):
    if not config(release) or 'narrative_source' not in gap:return
    merged={}
    for row in sorted(rows,key=lambda r:(tuple(r.get('premise_support_refs',())),r.get('binding_ref',''))):
        features=row.get('features',())
        if row.get('reference_kind')=='EVENT' or not features or not any(x.get('number')=='sing' and x.get('animacy')!='inan' for x in features):continue
        key=row['entity_ref']
        m=merged.setdefault(key,{'candidate_id':'memory:'+key,'kind':'MEMORY','entity_ref':key,
            'label':'memory participant '+row['label'],'grounding_paths':[], 'anchor_binding_ref':row['binding_ref'],'context_decision_ref':gap['gap_id']})
        m['grounding_paths'].append(row['premise_support_refs'])
    gap['options'].extend(option(gap,m,gap['narrative_source']) for m in merged.values())


def resolved_group(opt,resolved,gap):
    m=opt['member']
    if m['kind']=='CHAIN':
        member=deepcopy(resolved.get(m['gap_ref']))
        if member is None: return None
    else:
        member={k:deepcopy(m[k]) for k in ('entity_ref','participant_kind','anchor_binding_ref','context_decision_ref') if k in m}
        member['anonymous']=m['kind']=='ANONYMOUS'
        if m['kind']=='MEMORY':member['premise_support_refs']=list(min(tuple(p) for p in m['grounding_paths']))
        if m['kind']=='MENTION':member.update(anchor_mention=m['mention_ref'],label=m['anchor_label'])
    member['features']={'number':'sing'}
    return {'entity_ref':opt['entity_ref'],'participant_kind':'GROUP','anonymous':True,
            'known_members':[member], 'perspective':'FIRST_PERSON','perspective_source_range':gap['context_range']}
