"""Agreeing residual descriptions; order does not decide attachment."""
from .component_policy import _features, _morph, compatible
from .state import MorphVariant


def units(tokens, missing, frame, established):
    covered={t for u in established for t in u['refs']}
    readings=dict(frame.semantic['morph_bindings'])
    readings.update({d['head_ref']:d['morph'] for d in frame.semantic.get('nominal_dependencies',())})
    for token in tokens:
        if token.token_id not in missing-covered: continue
        for variant in token.variants:
            if variant.pos not in {'ADJF','PRTF'}: continue
            for head,raw in readings.items():
                if raw['pos'] not in {'NOUN','NPRO'}: continue
                noun=MorphVariant(**{**raw,'cases':frozenset(raw['cases']),
                                     'features':frozenset(raw['features'])})
                if not variant.cases & noun.cases or not compatible(_features(variant),_features(noun)): continue
                yield {'token':token,'variant':variant,'refs':(token.token_id,),
                       'entities':[],'adjectives':[],'bound_host':head,
                       'host_reading':_morph(noun),'requires_host_probe':True}
