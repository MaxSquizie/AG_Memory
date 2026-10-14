"""TEST_ONLY grammatical relations; no diary words or name bindings."""
from ah.model.types import ActantRole,Domain


def extend(manifest,core,cfg):
    if core is None: raise ValueError('dependency reduction fixture requires its actual AH core')
    cfg.update(dependency_reduction='CONSTRAINT_TREE_V1',apposition_markers=['—','–'],
               apposition_rules=[{'rule_id':'NOMINATIVE_EXPLANATION','mode':'NOMINATIVE','markers':['—','–']},
                                 {'rule_id':'AGREED_EXPLANATION','mode':'AGREEMENT','markers':[',','—','–']}],
               dependency_senses={k:'SYNTAX_'+k for k in ('GENITIVE','APPOSITION','CASE_DEPENDENCY')},
               nominal_dependency_cases=['acc','dat','abl','ins','loc','loct'])
    cfg['open_case_roles'].update(abl='SURFACE_ARG',ins='SURFACE_ARG')
    resources={r['kind']:r['entries'] for r in manifest['entries']}
    roles=[cfg['nominal_host_role'],cfg['preposition_nominal_role']]
    for kind,sid in cfg['dependency_senses'].items():
        symbol='fixture:S:'+sid;template='fixture:T:'+sid
        core.add_abstract_symbol({'syntax:'+kind},uid=symbol)
        core.add_template(Domain.C,core.ref(symbol),tuple(ActantRole(r) for r in roles),uid=template)
        resources['R-S'].append({'sense_id':sid,'lemma':'@syntax/'+kind,'POS':'NOUN'})
        resources['R-V'].append({'sense_id':sid,'state_class':'STATE','roles':[
            {'role_id':r,'argument_types':['ENTITY'],'cardinality':{'min':1,'max':1},
             'allowed_cases':[],'optionality':False} for r in roles]})
        resources['TemplateMap'].append({'sense_id':sid,'template_ref':template,'roles':roles})
