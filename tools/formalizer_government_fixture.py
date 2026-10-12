"""TEST_ONLY preposition government, no source-name or identity dictionary."""


def policy():
    return {'version':'PROPER_NAME_GOVERNMENT_V1','rules':[
        {'rule_id':'TEST-PREP-CASE-'+lemma,'lemma':lemma,'cases':cases}
        for lemma,cases in [('с',['gen','acc','abl']),('со',['gen','acc','abl']),
            ('в',['acc','loc']),('во',['acc','loc']),('на',['acc','loc']),
            ('за',['acc','abl']),('под',['acc','abl']),('к',['dat']),
            ('от',['gen']),('у',['gen']),('о',['loc'])]]}
