"""Local preposition/nominal structures, without lexical or semantic guessing."""
from .canonical_ledger import digest
from .component_policy import _features, compatible


def prepositional_groups(tokens, excluded=()):
    """Recognize PREP ADJF* (NOUN|NPRO), retaining whole PREP readings.

    A token with another POS reading requires a closed attachment probe. Multiword
    prepositions and coordination are not flattened by this local constructor.
    """
    result={}
    for i, prep in enumerate(tokens):
        variants=[v for v in prep.variants if v.pos=='PREP']
        if not variants or prep.token_id in excluded: continue
        j=i+1
        while j<len(tokens) and any(v.pos=='ADJF' for v in tokens[j].variants): j+=1
        if j==len(tokens): continue
        head=tokens[j]
        if head.token_id in excluded or not any(v.pos in {'NOUN','NPRO'} for v in head.variants): continue
        result[head.token_id]={'token_ref':prep.token_id,'variants':variants,
            'anchor_refs':[e.token_id for e in tokens[i:j+1]],
            'source_range':[prep.start,head.end],
            'ambiguous_pos':any(v.pos!='PREP' for v in prep.variants)}
    return result


def role_choices(token, roles, predicate, subject_role, group=None):
    choices=[]
    for mv in token.variants:
        if mv.pos not in {'NOUN','NPRO'}: continue
        for role in roles:
            if not set(mv.cases)&set(role.get('allowed_cases',())): continue
            if role['role_id']==subject_role and not compatible(_features(predicate),_features(mv)): continue
            preps=role.get('allowed_preps',())
            if group:
                for pv in group['variants']:
                    if pv.lemma in preps: choices.append((role['role_id'],mv,pv))
            elif not preps:
                choices.append((role['role_id'],mv,None))
    # Missing coverage remains an addressable source component, not an entity
    # forced into an unrelated case role and not a lost clause alternative.
    return choices or [(None,None,None)]


def nominal_units(state, tokens, assignments, used):
    units={}
    for e,(_,mv,_) in assignments:
        refs=[e.token_id]; idx=tokens.index(e)-1
        while idx>=0:
            adj=tokens[idx]
            if adj.token_id in used or not any(av.pos=='ADJF' and compatible(_features(av),_features(mv))
                    and set(av.cases)&set(mv.cases) for av in adj.variants): break
            used.add(adj.token_id); refs.insert(0,adj.token_id); idx-=1
        start=next(t.start for t in tokens if t.token_id==refs[0])
        units[e.token_id]={'head_ref':e.token_id,'anchor_refs':refs,
            'surface':state.text[start:e.end],
            'mention_ref':e.token_id if len(refs)==1 else 'mention:'+digest(refs)}
    return units


def phrase_questions(groups, assigned, frame_id):
    """Nested questions preserve the relation and its nominal complement."""
    return [{'kind':'RELATION_TO_EVENT','component_id':'component-pp:'+digest([frame_id,head]),
        'anchor_refs':g['anchor_refs'],'source_range':g['source_range'],
        'preposition_ref':g['token_ref'],'head_ref':head,
        'status':'BOUND' if head in assigned else 'UNRESOLVED',
        'role':assigned.get(head),
        'children':[{'kind':'ARGUMENT_CONTENT','anchor_ref':head}]}
        for head,g in groups.items()]
