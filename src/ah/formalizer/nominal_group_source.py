"""Established flat K introductions, grounded in terminal member bindings."""
from copy import deepcopy
from .canonical_ledger import digest


def rows(state,constraint,entities=None):
    return domain(state,constraint,entities)[0]


def domain(state,constraint,entities=None):
    from .nominal_reference_source import rows as entity_rows
    from .component_nominal_groups import group_for
    entities=entity_rows(state,constraint) if entities is None else entities
    by_frame={}
    for row in entities:
        a=row['local_nominal_anchor']
        by_frame.setdefault(a['frame_ref'],{})[a['token_ref']]=row
    result=[];pending=[]
    own=set(constraint.get('anchor_refs',()))|{constraint['head_ref']}
    from .nominal_reference_source import eligible_frames
    from .nominal_reference_chain import rows as mention_rows
    mentions={(r['local_reference_anchor']['frame_ref'],r['local_reference_anchor']['token_ref']):r
              for r in mention_rows(state,constraint)}
    for frame,decision,spec in eligible_frames(state):
        available=by_frame.get(frame.frame_id,{})
        roles=spec.get('roles',{})
        for role in sorted(set(roles.values())):
            refs=[t for t,r in roles.items() if r==role]
            if len(refs)<2 or own.intersection(refs):continue
            try:group=group_for(frame,role,roles)
            except ValueError:
                pending.append({'frame_ref':frame.frame_id,'role':role,'member_refs':refs,
                    'reason':'GROUP_STRUCTURE_UNRESOLVED'})
                continue
            missing=[t for t in refs if t not in available]
            if missing:
                if all((frame.frame_id,t) in mentions for t in missing):
                    members=[{'terminal':deepcopy(available[t])} if t in available else
                             {'reference':deepcopy(mentions[frame.frame_id,t]['local_reference_anchor'])}
                             for t in refs]
                    dependency={'frame_ref':frame.frame_id,'role':role,'member_token_refs':refs,
                        'source_tag':[state.source_uid,state.interpretation_version],
                        'group_hash':digest(group),'members':members}
                    result.append({'reference_kind':'GROUP_MENTION',
                        'selection_target':'group-mention:'+digest(dependency),
                        'local_group_dependency':dependency,'features':[{'number':'plur'}],
                        'members':[{'source_token_ref':t} for t in refs],
                        'label':'The whole established group of source participants (member identities are separate dependencies)'})
                    continue
                pending.append({'frame_ref':frame.frame_id,'role':role,'member_refs':refs,
                    'group_hash':digest(group),'pending_member_refs':missing,
                    'reason':'GROUP_MEMBERS_NOT_TERMINAL'})
                continue
            members=[available[t] for t in refs]
            ids=sorted({m['entity_ref'] for m in members})
            if len(ids)<2:
                pending.append({'frame_ref':frame.frame_id,'role':role,'member_refs':refs,
                    'group_hash':digest(group),'reason':'GROUP_IDENTITY_REPRESENTATION_UNRESOLVED'})
                continue
            uid='K:'+digest(ids);tag=[state.source_uid,state.interpretation_version]
            anchor={'frame_ref':frame.frame_id,'role':role,'source_tag':tag,'entity_ref':uid,
                'member_refs':ids,'group_hash':digest(group),
                'member_anchors':[deepcopy(m['local_nominal_anchor']) for m in members],
                'member_binding_refs':[m['memory_binding_ref'] for m in members]}
            mention='nominal-group:'+digest([frame.frame_id,refs])
            anchor['mention_ref']=mention
            result.append({'entity_ref':uid,'reference_kind':'GROUP','member_refs':ids,
                'source_tag':tag,'memory_binding_ref':binding_id(anchor),
                'features':[{'number':'plur'}],
                'premise_support_refs':sorted({p for m in members for p in m['premise_support_refs']}),
                'label':'The whole established group: '+' + '.join(m['label'] for m in members),
                'members':[{'source_token_ref':t} for t in refs],
                'local_group_anchor':anchor})
    return result,pending


def binding_id(anchor):
    return 'binding:nominal-group:'+digest([anchor['source_tag'],anchor['mention_ref'],anchor['entity_ref']])


def emit_anchor(state,release,anchor,tag,frag,emit):
    if anchor.get('group_dependency'):
        from .nominal_group_dependency import check_anchor
        row=check_anchor(state,anchor)
    else:
        row=next((r for r in rows(state,{'head_ref':None,'anchor_refs':[]})
                  if r.get('local_group_anchor')==anchor),None)
    if row is None or anchor['source_tag']!=tag:raise ValueError('NOMINAL_GROUP_ANCHOR_STALE')
    from .nominal_reference_source import emit_anchor as member
    for a in anchor['member_anchors']:
        if not a.get('reference_anchor'):member(state,release,a,tag,frag,emit)
    emit('ENSURE_GROUP',{'uid':anchor['entity_ref'],'members':anchor['member_refs']},frag)
    emit('SET_IDENTITY_BINDING',{'binding_id':binding_id(anchor),'binding_kind':'NOMINAL_GROUP_ANCHOR',
        'mention_ref':anchor['mention_ref'],'target_ref':anchor['entity_ref'],'source_tag':tag,
        'member_refs':anchor['member_refs'],'member_binding_refs':anchor['member_binding_refs'],
        'premise_support_refs':row['premise_support_refs'],'local_group_anchor':deepcopy(anchor)},frag)


def validate(p,ledger):
    if p.get('binding_kind')!='NOMINAL_GROUP_ANCHOR':return
    a=p.get('local_group_anchor',{});paths=ledger.paths()
    if (not a or p['binding_id']!=binding_id(a) or p['source_tag']!=a['source_tag']
            or p['target_ref']!=a['entity_ref'] or p['mention_ref']!=a['mention_ref']
            or p['member_refs']!=a['member_refs'] or not a.get('group_hash')
            or p.get('member_binding_refs')!=a['member_binding_refs']
            or len(a['member_anchors'])!=len(a['member_binding_refs'])):
        raise ValueError('NOMINAL_GROUP_ANCHOR_INVALID')
    targets=[];premises=set()
    for member,bid in zip(a['member_anchors'],a['member_binding_refs']):
        b=ledger.data['bindings'].get(bid,{})
        if member.get('reference_anchor'):
            from .nominal_group_dependency import validate_member
            validate_member(member,bid,b,a,ledger,paths)
            targets.append(b['target_ref']);premises.update(b.get('premise_support_refs',()))
            continue
        if (member.get('frame_ref')!=a['frame_ref'] or member.get('source_tag')!=p['source_tag']
                or not member.get('basis_hash') or not ledger.binding_live(bid,paths) or b.get('binding_kind')
                or b.get('source_tag')!=p['source_tag'] or b.get('mention_ref')!=member['mention_ref']
                or b.get('target_ref')!=member['entity_ref']
                or bid!='binding:'+digest([p['source_tag'],member['mention_ref'],member['entity_ref']])):
            raise ValueError('NOMINAL_GROUP_MEMBER_INVALID')
        targets.append(b['target_ref']);premises.update(b.get('premise_support_refs',()))
    if sorted(set(targets))!=p['member_refs'] or premises!=set(p.get('premise_support_refs',())):
        raise ValueError('NOMINAL_GROUP_MEMBER_INVALID')


def validate_reference(p,proof):
    a=p['local_group_anchor']
    own=set(p['reference_constraint'].get('anchor_refs',()))|{p['reference_constraint']['head_ref']}
    if (proof.get('binding_kind')!='NOMINAL_GROUP_ANCHOR' or digest(proof.get('local_group_anchor'))!=digest(a)
            or p['anchor_binding_ref']!=binding_id(a) or p['source_tag']!=a['source_tag']
            or any(m['token_ref'] in own for m in a['member_anchors'])
            or p.get('context_read_hash') or p.get('reference_kind')!='GROUP'
            or p.get('member_refs')!=a['member_refs']
            or set(p.get('premise_support_refs',()))!=set(proof.get('premise_support_refs',()))):
        raise ValueError('NOMINAL_GROUP_REFERENCE_INVALID')
