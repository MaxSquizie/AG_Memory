"""Explicit TEST_ONLY composition policy; never a production resource default."""
from copy import deepcopy
from ah.formalizer.canonical_ledger import digest
from tools.formalizer_v7_test_support import sign_test_release


def with_components(release, *, regional_probes=True, relative_time=False):
    manifest=deepcopy(release.manifest)
    policy=next(r for r in manifest['entries'] if r['kind']=='ProposalPolicy')
    policy['entries'][0]['composition']={
        'version':'COMPONENTS_V1','subject_role':'SUBJECT','coordination_operators':['AND'],
        'open_case_roles':{'nom':'SUBJECT','acc':'OBJECT','dat':'RECIPIENT'},
        'max_candidates':16,'context_chars':2048}
    scopes=next(r for r in manifest['entries'] if r['kind']=='ScopeLexicon')['entries']
    if not any(r.get('operator')=='AND' for r in scopes):
        scopes.append({'pattern':r'\bи\b','operator':'AND'})
    if relative_time:
        scopes.extend({'pattern':pattern,'operator':operator,'attachment_kinds':['TEMPORAL_NOMINAL'],
            'restriction_pattern':{'anchor_cases':['gen']}} for pattern,operator in
            [(r'\bпосле\b','AFTER'),(r'\bдо\b','BEFORE')])
    if regional_probes:
        policy['entries'][0]['probe_budget']={'version':'SOURCE_WINDOW_V1','window_tokens':64,
            'calls_per_window':24,'tokens_per_window':16384}
    content={k:manifest[k] for k in ('kind','version','schema_version','entries','dependency_versions')}
    manifest['coverage_report']['resource_content_sha256']=digest(content)
    result,trust=sign_test_release(manifest)
    result._oracle_test_trust=trust
    return result
