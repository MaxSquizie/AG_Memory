"""Lexical relation wording competes with content; morphology cannot decide it."""
from .structural_tasks import choose


def function_label(token,kind,role,owner=None):
    from .relation_composition import RELATIONS
    if kind=='CONTENT':
        holder='«'+owner.span+'» @'+str(owner.start) if owner else 'the selected parent predicate'
        if role=='RELATION':
            return ('Relation wording «'+token.span+'»: this occurrence introduces the DEPENDENT CONTENT taken by '+holder+
                    '; it is outside both the parent part and the dependent-content part.')
        return ('«'+token.span+'» belongs inside the content parts: keep it in the PARENT part or the DEPENDENT-CONTENT part. '
                'It does not introduce this dependent content of '+holder+
                '; a link between other parent clauses stays in the parent part.')
    meaning=RELATIONS[kind]
    if role=='RELATION':
        return ('Relation wording «'+token.span+'»: use this occurrence to express '+meaning+
                '. It supplies that outer meaning, which applies to content expressed by other occurrences.')
    return ('«'+token.span+'» belongs inside the content: '+meaning+
            ' applies to content INCLUDING this occurrence. This occurrence does not supply that outer meaning; '
            'an operator it expresses would be nested inside the content.')


def confirm(state,release,selector,region,cfg,kind,links,groups,*,established=None,owner=None):
    lexical=list(links)
    if not lexical:return True
    from .relation_composition import RELATIONS
    content='; '.join('«'+' '.join(t.span for t in g)+'»' for g in groups)
    empty=not any(groups)
    # One occurrence per question: the peer need not perform a universal check
    # over an abstract split or remember the preceding boundary choice.
    for token in lexical:
        if established is not None and token.token_id in established:
            from .partition_role_revision import read_proof
            if not read_proof(state,established[token.token_id],marker_relation_ref=token.token_id,
                              relation=kind,owner_ref=owner.token_id if owner else None):return False
            continue
        options=[{'candidate_id':'RELATION_ONLY','marker_relation_ref':token.token_id,
                  'label':function_label(token,kind,'RELATION',owner)},
                 {'candidate_id':token.token_id,'marker_content_ref':token.token_id,
                  'label':function_label(token,kind,'CONTENT',owner)}]
        for option in options:option.update(relation=kind,owner_ref=owner.token_id if owner else None)
        result=choose(state,release,selector,region,cfg,'relation_marker_role',options,
            'Outer relation: '+kind+' ('+RELATIONS[kind]+'). Words assigned to it: «'+
            ' '.join(t.span for t in links)+'». Content parts: '+('none retained' if empty else content)+'. '
            +('The selected content owner is «'+owner.span+'» @'+str(owner.start)+'. '
              'The first part is the PARENT, including its other clauses; the second is THIS owner\'s DEPENDENT CONTENT. '
              'A link between clauses of the parent is internal to the parent, not an introducer of this dependent content. ' if owner else '')+
            'Question about ONE source word: «'+token.span+'» @'+str(token.start)+'. '
            'Is it part of this outer wording, or does it belong to the content, including a nested negation, modality or quantifier? '
            'The current split removes this word from the content. Judge its meaning in the original source. '
            'An action remains content even when it is negated or has not happened. '
            'Choose only this occurrence\'s function. The other assigned words may still be misplaced; '
            'this choice does not approve the whole split or the completeness of the remaining content.')
        if not result:return False
        ref=result[0].get('marker_content_ref')
        if ref:
            state.syntax_trace.append({'kind':'STRUCTURAL_PARTITION_COVERAGE','region_ref':region.region_id,
                'source_range':list(region.source_range),'relation':kind,'uncovered_token_refs':[ref],
                'operands':[[t.token_id for t in g] for g in groups],'reason':'CONTENT_INSIDE_RELATION_MARKER',
                'decision_ref':result[1]['decision_ref']})
            from .partition_domain import ContentRequired
            return ContentRequired((ref,),'CONTENT_INSIDE_RELATION_MARKER',result[1])
        if established is not None:established[token.token_id]=result[1]
    return True
