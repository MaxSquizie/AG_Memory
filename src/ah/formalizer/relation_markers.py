"""Lexical relation wording competes with content; morphology cannot decide it."""
from .structural_tasks import choose


def confirm(state,release,selector,region,cfg,kind,links,groups):
    lexical=list(links)
    if not lexical:return True
    from .relation_composition import RELATIONS
    content='; '.join('«'+' '.join(t.span for t in g)+'»' for g in groups)
    empty=not any(groups)
    # One occurrence per question: the peer need not perform a universal check
    # over an abstract split or remember the preceding boundary choice.
    for token in lexical:
        options=[{'candidate_id':'RELATION_ONLY','marker_relation_ref':token.token_id,'label':
            'Relation wording «'+token.span+'» contributes to this outer relation; this occurrence is not part of its content'},
            {'candidate_id':token.token_id,'marker_content_ref':token.token_id,'label':
            '«'+token.span+'» belongs inside the content: a participant, action, state or nested relation; keep its meaning there'}]
        result=choose(state,release,selector,region,cfg,'relation_marker_role',options,
            'Outer relation: '+kind+' ('+RELATIONS[kind]+'). Words assigned to it: «'+
            ' '.join(t.span for t in links)+'». Content parts: '+('none retained' if empty else content)+'. '
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
    return True
