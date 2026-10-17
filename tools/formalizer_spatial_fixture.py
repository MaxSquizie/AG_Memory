"""Explicit TEST_ONLY lexical inventory for the generic relative-place contract."""
from ah.model.types import ActantRole, Domain


def extend(manifest, core):
    if core is None: raise ValueError('spatial fixture requires actual AH core')
    resources={r['kind']:r['entries'] for r in manifest['entries']}
    cfg={'version':'SOURCE_RELATIVE_PLACE_V1','context_chars':2048,'max_candidates':16,'rules':[]}
    resources['ProposalPolicy'][0]['spatial_references']=cfg
    for lemma,sid,kind,relation in (
        ('вверх','RELATIVE_UP_DESTINATION','ANCHOR','DESTINATION'),
        ('вниз','RELATIVE_DOWN_DESTINATION','ANCHOR','DESTINATION'),
        ('там','RELATIVE_AT_PLACE','REFERENCE',None)):
        symbol='fixture:S:'+sid;template='fixture:T:'+sid
        core.add_abstract_symbol({lemma},uid=symbol)
        core.add_template(Domain.C,core.ref(symbol),(ActantRole.OBJECT,ActantRole.LOCATION),uid=template)
        resources['R-S'].append({'sense_id':sid,'lemma':lemma,'POS':'ADVB','meaning_en':{'вверх':'OBJECT is directed towards a relatively higher LOCATION.', 'вниз':'OBJECT is directed towards a relatively lower LOCATION.', 'там':'OBJECT is situated at LOCATION identified from context.'}[lemma]})
        resources['R-V'].append({'sense_id':sid,'state_class':'EVENT','roles':[
            {'role_id':role,'argument_types':types,'cardinality':{'min':1,'max':1},
             'allowed_cases':['dat'] if role=='LOCATION' and kind=='ANCHOR' else [],
             **({'allowed_preps':['к']} if role=='LOCATION' and kind=='ANCHOR' else {}),'optionality':False}
            for role,types in [('OBJECT',['PROPOSITION']),('LOCATION',['ENTITY'])]]})
        resources['TemplateMap'].append({'sense_id':sid,'template_ref':template,'roles':['OBJECT','LOCATION']})
        cfg['rules'].append({'rule_id':'TEST-SPATIAL-'+sid,'lemma':lemma,'POS':'ADVB','sense_id':sid,
            'role_id':'LOCATION','kind':kind,**({'location_kind':relation,'goal_prepositions':[{'lemma':'к','cases':['dat']}]} if relation else {})})
