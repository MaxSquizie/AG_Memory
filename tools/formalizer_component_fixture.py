"""Explicit TEST_ONLY composition policy; never a production resource default."""
from copy import deepcopy
from ah.formalizer.canonical_ledger import digest
from tools.formalizer_v7_test_support import sign_test_release


def with_components(release):
    manifest=deepcopy(release.manifest)
    policy=next(r for r in manifest['entries'] if r['kind']=='ProposalPolicy')
    policy['entries'][0]['composition']={
        'version':'COMPONENTS_V1','subject_role':'SUBJECT',
        'open_case_roles':{'nom':'SUBJECT','acc':'OBJECT','dat':'RECIPIENT'},
        'max_candidates':16,'context_chars':2048}
    content={k:manifest[k] for k in ('kind','version','schema_version','entries','dependency_versions')}
    manifest['coverage_report']['resource_content_sha256']=digest(content)
    result,trust=sign_test_release(manifest)
    result._oracle_test_trust=trust
    return result
