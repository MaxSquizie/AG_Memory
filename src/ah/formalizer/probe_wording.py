"""Small presentation vocabulary; it never admits or selects a reading."""

TERMS = {
    'NOUN':'noun', 'NPRO':'pronoun', 'VERB':'conjugated verb', 'INFN':'infinitive',
    'ADJF':'adjective', 'ADJS':'short adjective', 'ADVB':'adverb', 'PRED':'predicative',
    'PREP':'preposition', 'CONJ':'conjunction', 'PRCL':'particle',
    'nom':'nominative', 'gen':'genitive', 'dat':'dative', 'acc':'accusative',
    'ins':'instrumental', 'abl':'instrumental', 'loc':'prepositional', 'voc':'vocative',
    'sing':'singular', 'plur':'plural', 'masc':'masculine', 'femn':'feminine', 'neut':'neuter',
    'perf':'perfective', 'impf':'imperfective', 'tran':'transitive', 'intr':'intransitive',
    'anim':'animate', 'inan':'inanimate', 'Name':'personal name',
}

ROLE_MEANINGS = {
    'SUBJECT':'grammatical subject of the predicate',
    'OBJECT':'direct object or content of the predicate',
    'RECIPIENT':'recipient or addressee of the action',
    'LOCATION':'place or spatial endpoint of the situation',
    'SOURCE':'place or entity from which something comes',
    'EXPERIENCER':'participant experiencing the state',
    'PURPOSE':'goal for which the parent action is performed',
}


def proposition_role(value):
    return {'OBJECT':'content specifying what the parent predicate is about, including an action whose phase is described',
            'CONTENT':'content specifying what the parent predicate is about',
            'PURPOSE':'goal for which a separate parent action is performed; answers why that action is done'}.get(value,role(value))


def role(value):
    return ROLE_MEANINGS.get(value,value)


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
