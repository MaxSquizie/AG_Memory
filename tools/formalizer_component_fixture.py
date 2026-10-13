"""Explicit TEST_ONLY composition policy; never a production resource default."""
from copy import deepcopy
from ah.formalizer.canonical_ledger import digest
from tools.formalizer_v7_test_support import sign_test_release


def with_components(release, *, regional_probes=True, relative_time=False, predication=False, clock_time=False, omissions=False, modifier_forest=False, clock_ranges=False, nominal_tree=False,dependency_reduction=False,refinement=False,document_scopes=False,spatial_references=False,core=None):
    manifest=deepcopy(release.manifest)
    policy=next(r for r in manifest['entries'] if r['kind']=='ProposalPolicy')
    policy['entries'][0]['composition']={
        'version':'COMPONENTS_V1','subject_role':'SUBJECT','coordination_operators':['AND'],
        'open_case_roles':{'nom':'SUBJECT','acc':'OBJECT','dat':'RECIPIENT'},
        'max_candidates':16,'context_chars':2048}
    if predication:
        policy['entries'][0]['composition'].update(quality_predicate_pos=['ADJF','ADJS'],
            copula_lemmas=['быть'], modifier_content_role='OBJECT',preposition_nominal_role='SURFACE_ARG')
    if modifier_forest:
        if not predication: raise ValueError('modifier_forest requires predication')
        policy['entries'][0]['composition']['modifier_composition']='BOUNDED_FOREST_V1'
    if nominal_tree:
        if not modifier_forest: raise ValueError('nominal_tree requires modifier_forest')
        policy['entries'][0]['composition'].update(narrative_continuity='SOURCE_CARRIER_V1',substantive_readings='CONTEXTUAL_SUBSTANTIVE_V1',nominal_utterances='NOMINATIVE_DESCRIPTION_V1',nominal_composition='QUESTION_TREE_V1',nominal_host_role='SUBJECT',modifier_scope='SHARED_EVENT_V1')
        policy['entries'][0]['composition']['nominal_references']={'version':'DETERMINER_GROUP_V1',
            'demonstratives':[{'rule_id':'TEST-DEMONSTRATIVE-'+str(i),'lemma':lemma,'POS':'ADJF'}
                             for i,lemma in enumerate(('тот','этот'))],
            'identity_modifiers':[{'rule_id':'TEST-SAME-'+str(i),'lemma':lemma,'POS':pos}
                                  for i,(lemma,pos) in enumerate((('же','PRCL'),('самый','ADJF')))]}
        policy['entries'][0]['composition']['qualitative_quantity']={'version':'LEXICAL_GROUP_V1',
            'rules':[{'rule_id':'TEST-QUALITATIVE-'+str(i),'lemma':lemma,'POS':'NUMR'}
                     for i,lemma in enumerate(('несколько','много','мало'))]}
    if dependency_reduction:
        if not nominal_tree: raise ValueError('dependency_reduction requires nominal_tree')
        from tools.formalizer_dependency_fixture import extend
        extend(manifest,core,policy['entries'][0]['composition'])
    if predication:
        policy['entries'][0]['composition']['oov_morphology']='CONTEXTUAL_NOMINAL_V1'
        from tools.formalizer_government_fixture import policy as government_policy
        policy['entries'][0]['composition']['contextual_preposition_case']=government_policy()
        policy['entries'][0]['composition']['agreement_recovery']={'version':'MODIFIER_AGREEMENT_V1','max_edits':2}
    if refinement:
        if not dependency_reduction: raise ValueError('refinement requires dependency_reduction')
        from tools.formalizer_refinement_fixture import extend
        extend(policy['entries'][0]['composition'])
        registry=next(r for r in manifest['entries'] if r['kind']=='RoleRegistry')['entries']
        if not any(r['role_id']=='PURPOSE' for r in registry):
            registry.append({'role_id':'PURPOSE','allowed_argument_kinds':['PROPOSITION','EVENT']})
    scopes=next(r for r in manifest['entries'] if r['kind']=='ScopeLexicon')['entries']
    if not any(r.get('operator')=='AND' for r in scopes):
        scopes.append({'pattern':r'\bи\b','operator':'AND'})
    if relative_time:
        scopes.extend({'pattern':pattern,'operator':operator,'attachment_kinds':['TEMPORAL_NOMINAL'],
            'restriction_pattern':{'anchor_cases':['gen']}} for pattern,operator in
            [(r'\bпосле\b','AFTER'),(r'\bдо\b','BEFORE')])
        scopes.append({'pattern':r'\bперед\b','operator':'BEFORE','attachment_kinds':['TEMPORAL_NOMINAL'],
            'restriction_pattern':{'anchor_cases':['abl']}})
    if clock_time:
        from tools.formalizer_clock_fixture import clock_rule, bound_rules
        next(r for r in manifest['entries'] if r['kind']=='TemporalRules')['entries'].extend([clock_rule(),*bound_rules()])
    if clock_time:
        from tools.formalizer_period_fixture import rules
        next(r for r in manifest['entries'] if r['kind']=='TemporalRules')['entries'].extend(rules())
    if clock_ranges:
        from tools.formalizer_clock_fixture import range_rule
        next(r for r in manifest['entries'] if r['kind']=='TemporalRules')['entries'].append(range_rule())
    if document_scopes:
        from tools.formalizer_document_scope_fixture import policy as document_policy, periods
        policy['entries'][0]['document_scopes']=document_policy()
        policy['entries'][0]['composition']['temporal_coordination']='NAMED_PERIOD_SCOPE_V1'
        next(r for r in manifest['entries'] if r['kind']=='TemporalRules')['entries'].extend(periods())
    if spatial_references:
        if not predication: raise ValueError('spatial_references requires predication')
        from tools.formalizer_spatial_fixture import extend
        extend(manifest,core)
    if omissions and core is not None:
        from tools.formalizer_narrative_fixture import extend as extend_narrative
        extend_narrative(manifest,core)
    if omissions:
        # Explicit lexical fixture data, not a runtime verb/spelling heuristic.
        for valency in next(r for r in manifest['entries'] if r['kind']=='R-V')['entries']:
            if valency['sense_id']=='READ':
                for role in valency['roles']:
                    if role['role_id']=='OBJECT':
                        role['omission']={'kind':'UNSPECIFIED_ENTITY','rule_id':'TEST-READ-UNSPECIFIED-THEME'}
    if regional_probes:
        policy['entries'][0]['probe_budget']={'version':'SOURCE_WINDOW_V2','window_tokens':64,
            'calls_per_window':0,'tokens_per_window':0}
    content={k:manifest[k] for k in ('kind','version','schema_version','entries','dependency_versions')}
    manifest['coverage_report']['resource_content_sha256']=digest(content)
    result,trust=sign_test_release(manifest)
    result._oracle_test_trust=trust
    return result
