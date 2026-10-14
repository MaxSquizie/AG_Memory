"""Quantity child boundaries and lossless symbolic content, without arithmetic.

Numeric lexemes come from R1/NumeralRules. A neighbouring qualifier is a
candidate parent of the quantity, never an automatic comparison operator.
"""
from .component_policy import _morph


def candidates(tokens,release,policy):
    qualitative={(r['lemma'],r['POS']):r for r in policy.get('rules',())}
    numerals={r['lemma'] for r in release.resources.get('NumeralRules',{}).get('entries',())}
    def numeric(t):
        return t.span.isdecimal() or any(v.pos=='NUMR' or v.lemma in numerals for v in t.variants)
    def leaf(t):
        return {'kind':'LEXICAL','raw':t.span,'source_range':[t.start,t.end],
                'token_refs':[t.token_id]}
    for i,head in enumerate(tokens):
        nouns=[v for v in head.variants if v.pos=='NOUN']
        if not nouns or i==0:continue
        end=i
        # Descriptions belong to the nominal head, not to the quantity AST.
        while end>0 and any(v.pos in {'ADJF','PRTF'} for v in tokens[end-1].variants):end-=1
        start=end
        while start>0 and numeric(tokens[start-1]):start-=1
        if start==end:continue
        numbers=tokens[start:end]
        # Scale nouns licensed by the release remain in the quantity child;
        # they are not mistaken for the counted head of a shorter prefix.
        if numeric(head):continue
        marker=numbers[0]
        variants=[v for v in marker.variants if v.pos=='NUMR' or v.lemma in numerals]
        cases={c for v in variants for c in v.cases}
        if marker.span.isdecimal() and not variants:
            from .state import MorphVariant
            variants=[MorphVariant(marker.span,'NUMR',frozenset({'nom','acc'}))]
            cases={'acc','nom'}
        # Direct cases govern a genitive head; in oblique cases cardinal
        # components and head agree. Scale-noun grammar needs its own child.
        number_cases=[{c for v in t.variants if v.pos=='NUMR' for c in v.cases} for t in numbers]
        internal_by_case={}
        for case in sorted(cases):
            compatible=[v for v in nouns if ('gen' in v.cases if case in {'nom','acc'}
                        else case in v.cases and all(case in cs for cs in number_cases))]
            if compatible:internal_by_case[case]=[_morph(v) for v in compatible]
        cases=sorted(internal_by_case)
        if not cases:continue
        nouns=[v for v in nouns if any(_morph(v) in rows for rows in internal_by_case.values())]
        qrules={r['rule_id']:r for v in variants if (r:=qualitative.get((v.lemma,v.pos))) is not None}
        expression=leaf(marker) if len(numbers)==1 else {'kind':'SEQUENCE','children':[leaf(t) for t in numbers]}
        base={'head':head,'nouns':nouns,'marker':marker,'variants':variants,'cases':cases,
              'quantity_tokens':numbers,'expression':expression,'internal_by_case':internal_by_case,
              'rule_id':next(iter(qrules)) if len(qrules)==1 and len(numbers)==1 else 'SYMBOLIC_QUANTITY_GROUP_V1'}
        yield base
        if start>0 and any(v.pos in {'COMP','ADVB'} for v in tokens[start-1].variants):
            qualifier=tokens[start-1]
            yield {**base,'quantity_tokens':[qualifier,*numbers],
                   'expression':{'kind':'QUALIFIED','qualifier':leaf(qualifier),'content':expression},
                   'rule_id':'SYMBOLIC_QUANTITY_GROUP_V1'}


def validate_expression(value):
    if not isinstance(value,dict):raise ValueError('QUANTITY_EXPRESSION_INVALID')
    kind=value.get('kind')
    if kind=='LEXICAL':
        if set(value)!={'kind','raw','source_range','token_refs'}:raise ValueError('QUANTITY_EXPRESSION_INVALID')
        span=value['source_range']
        if (not isinstance(value['raw'],str) or not isinstance(span,(list,tuple)) or len(span)!=2 or any(type(i) is not int for i in span)
            or not 0<=span[0]<span[1] or span[1]-span[0]!=len(value['raw'])
            or not isinstance(value['token_refs'],(list,tuple)) or not value['token_refs'] or not all(isinstance(r,str) and r for r in value['token_refs'])):
            raise ValueError('QUANTITY_EXPRESSION_INVALID')
    elif kind=='SEQUENCE' and set(value)=={'kind','children'} and isinstance(value['children'],(list,tuple)) and len(value['children'])>=2:
        for child in value['children']:validate_expression(child)
    elif kind=='QUALIFIED' and set(value)=={'kind','qualifier','content'}:
        validate_expression(value['qualifier']);validate_expression(value['content'])
    else:raise ValueError('QUANTITY_EXPRESSION_INVALID')
