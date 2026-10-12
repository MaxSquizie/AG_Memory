"""TEST_ONLY grammatical connector/voice data, no diary predicates or names."""


def extend(cfg):
    cfg['infinitive_composition']={'version':'DEPENDENT_INFINITIVE_V1','relations':[
        {'role':'PURPOSE','attitude':'HYPOTHETICAL'}, {'role':'OBJECT','attitude':'UNKNOWN'}]}
    cfg['refinement']={'version':'POSTNOMINAL_AREAS_V1','max_depth':8,
        'relative_markers':[{'lemma':lemma,'POS':'ADVB'} for lemma in ('где','куда','откуда')],
        'participle_voices':[
            {'feature':'pssv','host_role':'OBJECT','case_roles':{'abl':'SUBJECT','ins':'SUBJECT','dat':'RECIPIENT'}},
            {'feature':'actv','host_role':'SUBJECT','case_roles':{'acc':'OBJECT','dat':'RECIPIENT'}}]}
