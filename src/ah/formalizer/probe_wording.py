"""Small presentation vocabulary; it never admits or selects a reading."""

TERMS = {
    'NOUN':'noun', 'NPRO':'pronoun', 'VERB':'conjugated verb', 'INFN':'infinitive',
    'ADJF':'adjective', 'ADJS':'short adjective', 'ADVB':'adverb', 'PRED':'predicative',
    'PRTS':'short participle', 'PRTF':'participle', 'pssv':'passive voice', 'actv':'active voice',
    'PREP':'preposition', 'CONJ':'conjunction', 'PRCL':'particle',
    'nom':'nominative', 'gen':'genitive', 'dat':'dative', 'acc':'accusative',
    'ins':'instrumental', 'abl':'instrumental', 'loc':'prepositional', 'voc':'vocative',
    'sing':'singular', 'plur':'plural', 'masc':'masculine', 'femn':'feminine', 'neut':'neuter',
    'perf':'perfective', 'impf':'imperfective', 'tran':'transitive', 'intr':'intransitive',
    'anim':'animate', 'inan':'inanimate', 'Name':'personal name',
}

ROLE_MEANINGS = {
    'SUBJECT':'core subject: grammatical subject in active voice, or actor projected from passive voice; not an oblique experiencer',
    'OBJECT':'core object: direct object or propositional content in active voice, or patient projected from passive voice',
    'RECIPIENT':'recipient or addressee of the action',
    'LOCATION':'place or spatial endpoint of the situation',
    'SOURCE':'place or entity from which something comes',
    'EXPERIENCER':'oblique or impersonal participant experiencing a state, outside the core SUBJECT/OBJECT slots',
    'PURPOSE':'goal for which the parent action is performed',
    'AUXILLIARY':'secondary participant assisting the action',
    'ABSENTEE':'participant whose absence is expressed',
    'STATE':'state attributed to a participant',
    'TIME':'time when the situation holds',
    'DURATION':'length of time for which the situation holds',
    'CAUSE':'situation or reason causing this situation',
    'TOOL':'instrument used to perform the action',
    'MATERIAL':'material consumed or transformed by the action',
    'AMOUNT':'quantity or amount involved',
    'HOW-TO':'manner or method of performing the action',
    'SURFACE_ARG':'source participant whose more specific role is not established',
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
    def describe(tid,morph):
        if morph.get('origin')=='CONTEXTUAL' and (morph.get('lemma') or '').casefold()==evidence[tid].span.casefold():
            return 'lemma unknown; '+reading({k:v for k,v in morph.items() if k!='lemma'})
        return reading(morph)
    return ' | '.join('«'+evidence[tid].span+'» @'+str(evidence[tid].start)+': '+describe(tid,morph)
                     for tid,morph in bindings.items())
