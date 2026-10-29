"""TD references to selected nominal groups preserve their member identities."""
from .canonical_ledger import digest


def candidates(state,mention_ref=None,window_size=None):
    evidence={t.token_id:t for t in state.evidence};found={}
    for frame in state.frames:
        if frame.semantic.get('structural_unresolved'):continue
        for group in frame.semantic.get('nominal_groups',()):
            if mention_ref is not None and window_size is not None:
                at=evidence[mention_ref].start
                if any(sum(min(at,evidence[t].start)<=x.start<max(at,evidence[t].start) for x in state.evidence)>window_size
                       for t in group['member_refs']):continue
            members=[]
            for tid in group['member_refs']:
                if tid in frame.semantic.get('bound_arguments',{}):break
                unit=frame.semantic.get('lexical_units',{}).get(tid,{})
                mention=unit.get('mention_ref',tid)
                # Pronouns with unresolved identities cannot create members.
                known=state.observation.get('entity_bindings',{}).get(mention)
                if not known and any(v.pos=='NPRO' for v in evidence[tid].variants):break
                members.append({'entity_ref':known or 'M:'+digest([state.source_uid,mention]),
                    'mention_ref':mention,'source_token_ref':tid,'label':unit.get('surface',evidence[tid].span),'existing':bool(known)})
            else:
                ids=sorted({m['entity_ref'] for m in members})
                if len(ids)<2:continue
                uid='K:'+digest(ids)
                found[uid]={'entity_ref':uid,'reference_kind':'GROUP','binding_ref':'local-group:'+uid,
                    'members':members,'member_refs':ids,'premise_support_refs':[],
                    'source_tag':[state.source_uid,state.interpretation_version],
                    'features':[{'number':'plur'}],'label':'The whole group: '+' + '.join(m['label'] for m in members)}
    return list(found.values())


def emit(state,tid,tag,frag,write):
    row=state.observation.get('group_reference_bindings',{}).get(tid)
    if not row:return None
    decision=state.decisions.get(tid+'|reference')
    if not decision or decision.outcome!='RESOLVED' or tuple(decision.selected)!=(row['entity_ref'],):
        raise ValueError('GROUP_REFERENCE_UNGROUNDED')
    for member in row.get('members',()):
        write('ENSURE_ENTITY',{'uid':member['entity_ref'],'mention_ref':member['mention_ref'],
            'name':member['label'],'source_tag':tag,'reference_existing':member['existing']},frag)
    if row.get('members'):write('ENSURE_GROUP',{'uid':row['entity_ref'],'members':row['member_refs']},frag)
    bid='binding:group:'+digest([tag,tid,row['entity_ref']])
    write('SET_IDENTITY_BINDING',{'binding_id':bid,'binding_kind':'GROUP_REFERENCE','mention_ref':tid,
        'target_ref':row['entity_ref'],'member_refs':row['member_refs'],'source_tag':tag,
        'premise_support_refs':row['premise_support_refs'],'interpretation_decision_ref':tid+'|reference'},frag)
    return row['entity_ref']
