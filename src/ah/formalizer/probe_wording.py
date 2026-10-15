"""Small presentation vocabulary; it never admits or selects a reading."""

TERMS = {
    'NOUN':'noun', 'NPRO':'pronoun', 'VERB':'conjugated verb', 'INFN':'infinitive',
    'ADJF':'adjective', 'ADJS':'short adjective', 'ADVB':'adverb', 'PRED':'predicative',
    'PREP':'preposition', 'CONJ':'conjunction', 'PRCL':'particle',
    'nom':'nominative', 'gen':'genitive', 'dat':'dative', 'acc':'accusative',
    'ins':'instrumental', 'loc':'prepositional', 'voc':'vocative',
    'sing':'singular', 'plur':'plural', 'masc':'masculine', 'femn':'feminine', 'neut':'neuter',
    'perf':'perfective', 'impf':'imperfective', 'tran':'transitive', 'intr':'intransitive',
    'anim':'animate', 'inan':'inanimate', 'Name':'personal name',
}


def reading(value):
    parts=[]
    for field in ('lemma','pos','cases','number','gender','tense','person','mood','voice','aspect','features'):
        item=value.get(field)
        if item is None or item==[] or item=='':continue
        items=item if isinstance(item,(list,tuple)) else [item]
        if field=='features':items=[x for x in items if x!=value.get('pos')]
        if items:parts.append(field+': '+', '.join(TERMS.get(str(x),str(x)) for x in items))
    return '; '.join(parts)


def linked_readings(bindings,evidence):
    return ' | '.join('«'+evidence[tid].span+'» @'+str(evidence[tid].start)+': '+reading(morph)
                     for tid,morph in bindings.items())
