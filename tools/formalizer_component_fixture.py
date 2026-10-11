"""Explicit TEST_ONLY composition policy; never a production resource default."""
from copy import deepcopy
from ah.formalizer.canonical_ledger import digest
from tools.formalizer_v7_test_support import sign_test_release


def with_components(release, *, regional_probes=True, relative_time=False, predication=False, clock_time=False, omissions=False, modifier_forest=False, clock_ranges=False):
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
    scopes=next(r for r in manifest['entries'] if r['kind']=='ScopeLexicon')['entries']
    if not any(r.get('operator')=='AND' for r in scopes):
        scopes.append({'pattern':r'\bи\b','operator':'AND'})
    if relative_time:
        scopes.extend({'pattern':pattern,'operator':operator,'attachment_kinds':['TEMPORAL_NOMINAL'],
            'restriction_pattern':{'anchor_cases':['gen']}} for pattern,operator in
            [(r'\bпосле\b','AFTER'),(r'\bдо\b','BEFORE')])
    if clock_time:
        from tools.formalizer_clock_fixture import clock_rule
        next(r for r in manifest['entries'] if r['kind']=='TemporalRules')['entries'].append(clock_rule())
    if clock_ranges:
        from tools.formalizer_clock_fixture import range_rule
        next(r for r in manifest['entries'] if r['kind']=='TemporalRules')['entries'].append(range_rule())
    if omissions:
        # Explicit lexical fixture data, not a runtime verb/spelling heuristic.
        for valency in next(r for r in manifest['entries'] if r['kind']=='R-V')['entries']:
            if valency['sense_id']=='READ':
                for role in valency['roles']:
                    if role['role_id']=='OBJECT':
                        role['omission']={'kind':'UNSPECIFIED_ENTITY','rule_id':'TEST-READ-UNSPECIFIED-THEME'}
    if regional_probes:
        policy['entries'][0]['probe_budget']={'version':'SOURCE_WINDOW_V1','window_tokens':64,
            'calls_per_window':24,'tokens_per_window':16384}
    content={k:manifest[k] for k in ('kind','version','schema_version','entries','dependency_versions')}
    manifest['coverage_report']['resource_content_sha256']=digest(content)
    result,trust=sign_test_release(manifest)
    result._oracle_test_trust=trust
    return result
