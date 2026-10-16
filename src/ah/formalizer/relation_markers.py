"""Lexical relation wording competes with content; morphology cannot decide it."""
from .structural_tasks import choose


def confirm(state,release,selector,region,cfg,kind,links,groups):
    functions={'CONJ','PRCL','PREP','ADVB','INTJ','PRED'}
    lexical=[t for t in links if not any(v.pos in functions for v in t.variants) and
        any(v.pos=='INFN' or len(links)>1 and v.pos in {'VERB','NOUN','ADJF','ADJS','PRTF','PRTS'} for v in t.variants)]
    if not lexical:return True
    from .relation_composition import RELATIONS
    content='; '.join('«'+' '.join(t.span for t in g)+'»' for g in groups)
    # One occurrence per question: the peer need not perform a universal check
    # over an abstract split or remember the preceding boundary choice.
    for token in lexical:
        options=[{'candidate_id':'RELATION_ONLY','marker_relation_ref':token.token_id,'label':
            'Relation wording «'+token.span+'» only expresses '+RELATIONS[kind]+'; '+content+' already names what this relation applies to'},
            {'candidate_id':token.token_id,'marker_content_ref':token.token_id,'label':
            '«'+token.span+'» names an action, state or participant that this relation applies to; keep its meaning in the content'}]
        result=choose(state,release,selector,region,cfg,'relation_marker_role',options,
            'Outer relation: '+kind+' ('+RELATIONS[kind]+'). Words assigned to it: «'+
            ' '.join(t.span for t in links)+'». Content parts: '+content+'. '
            'Question about ONE source word: «'+token.span+'» @'+str(token.start)+'. '
            'Does it express the relation itself, or name what is negated, possible, necessary, related or asked about? '
            'The current split removes this word from the content. Judge its meaning in the original source. '
            'An action remains content even when it is negated or has not happened. '
            'Choose its role, not whether the whole sentence expresses the outer relation.')
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
