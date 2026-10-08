"""Create an unsigned resource draft or validate an externally reviewed release.

No command manufactures a reviewer, signature, coverage result or PASS status.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from .loader import ResourceRelease
from ...model.types import ActantRole
from .schemas import candidate_schema_entries


def main():
    parser=argparse.ArgumentParser(__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    init=sub.add_parser('init'); init.add_argument('path',type=Path)
    check=sub.add_parser('check'); check.add_argument('path',type=Path); check.add_argument('--draft',action='store_true'); check.add_argument('--trusted-reviews',type=Path)
    check.add_argument('--ah-snapshot',type=Path)
    build=sub.add_parser('build'); build.add_argument('directory',type=Path); build.add_argument('output',type=Path); build.add_argument('--version',required=True); build.add_argument('--ah-snapshot',type=Path,required=True)
    cover=sub.add_parser('coverage'); cover.add_argument('path',type=Path); cover.add_argument('corpus',type=Path); cover.add_argument('output',type=Path); cover.add_argument('--ah-snapshot',type=Path,required=True)
    sign=sub.add_parser('sign'); sign.add_argument('path',type=Path); sign.add_argument('coverage',type=Path); sign.add_argument('output',type=Path)
    sign.add_argument('--private-key',type=Path,required=True); sign.add_argument('--reviewer',required=True); sign.add_argument('--key-id',required=True); sign.add_argument('--timestamp',required=True); sign.add_argument('--ah-snapshot',type=Path,required=True)
    compile_cmd=sub.add_parser('compile'); compile_cmd.add_argument('path',type=Path); compile_cmd.add_argument('release',type=Path); compile_cmd.add_argument('output',type=Path)
    catalog=sub.add_parser('catalog'); catalog.add_argument('output',type=Path); catalog.add_argument('--ah-snapshot',type=Path,required=True)
    schemas=sub.add_parser('schemas'); schemas.add_argument('output',type=Path)
    profile=sub.add_parser('profile-rx'); profile.add_argument('path',type=Path); profile.add_argument('corpus',type=Path); profile.add_argument('output',type=Path)
    profile.add_argument('--ah-snapshot',type=Path,required=True); profile.add_argument('--trusted-reviews',type=Path,required=True); profile.add_argument('--limit',type=int,default=4096)
    args=parser.parse_args()
    def write(path,value):
        with path.open('x',encoding='utf-8') as f: json.dump(value,f,ensure_ascii=False,indent=2,allow_nan=False)
    if args.command=='schemas':
        from .schemas import RESOURCE_SCHEMAS,EMIT_SCHEMAS
        write(args.output,{'schema_version':'v7-runtime-records-v1','resource_records':RESOURCE_SCHEMAS,'emit':EMIT_SCHEMAS}); return
    if args.command=='catalog':
        from .authoring import template_catalog,load_store
        write(args.output,template_catalog(load_store(args.ah_snapshot))); return
    if args.command=='profile-rx':
        from .authoring import profile_experience,load_store
        trusted=json.loads(args.trusted_reviews.read_text(encoding='utf-8'))
        release=ResourceRelease.load(args.path,trusted_reviews=trusted)
        store=load_store(args.ah_snapshot); release.validate_store(store)
        import hashlib
        report=profile_experience(store,release,args.corpus,limit=args.limit)
        report['input_ah_sha256']=hashlib.sha256(args.ah_snapshot.read_bytes()).hexdigest()
        write(args.output,report)
        print('Actual-snapshot retrieval cost and hit counts; semantic benefit/G5 not inferred.'); return
    if args.command=='build':
        from .authoring import build_release,load_store
        write(args.output,build_release(args.directory,version=args.version,store=load_store(args.ah_snapshot)))
        print('Unsigned resource bundle; actual AH mappings validated. External review still required.'); return
    if args.command=='coverage':
        from .authoring import resource_coverage,load_store
        release=ResourceRelease.load(args.path,require_review=False)
        release.validate_store(load_store(args.ah_snapshot))
        write(args.output,resource_coverage(release,args.corpus))
        print('Measured lexical resource availability; execution coverage and gate PASS not claimed.'); return
    if args.command=='sign':
        from .authoring import load_store
        from .signatures import sign_review
        manifest=json.loads(args.path.read_text(encoding='utf-8'))
        manifest['coverage_report']=json.loads(args.coverage.read_text(encoding='utf-8'))
        release=ResourceRelease(manifest,require_review=False)
        release.validate_store(load_store(args.ah_snapshot))
        if not {'corpus_id','corpus_sha256','units_by_kind','categories'}<=set(manifest['coverage_report']): raise ValueError('coverage report missing')
        manifest['signed_review_id']=sign_review(release.sha256,reviewer=args.reviewer,timestamp=args.timestamp,key_id=args.key_id,private_key_pem=args.private_key.read_bytes())
        write(args.output,manifest)
        print('Signed using the supplied reviewer key. Trust registry pin and independent approval remain external.'); return
    if args.command=='compile':
        from .rule_dsl import compile_rules
        release=ResourceRelease.load(args.release,require_review=False)
        compiled=compile_rules(args.path.read_text(encoding='utf-8'),{r['role_id'] for r in release.entries('RoleRegistry')},release.resources['SyntaxRules']['dependency_versions'])
        write(args.output,{'rules':list(compiled.rules),'dependency_versions':compiled.dependency_versions}); return
    if args.command=='init':
        defaults={'CandidateSchema':candidate_schema_entries(),'RoleRegistry':[{'role_id':r.value} for r in ActantRole],
                  'OpenTemplatePolicy':[{'allow':False}],
                  'ProposalPolicy':[{'max_nodes':64,'max_edges':128,'max_depth':16,'max_source_tokens':256,'max_rule_steps':20000,'max_rule_matches':256,'verify_deterministic':False}]}
        dependencies={'R-V':{'R-S':'1','RoleRegistry':'1'},'TemplateMap':{'R-S':'1','RoleRegistry':'1'},'PredicateSchema':{'R-S':'1'},'R-X3':{'R-S':'1'},'SyntaxRules':{'RoleRegistry':'1'}}
        manifest={'kind':'FORMALIZER_RESOURCE_RELEASE','version':'1','schema_version':'v7','entries':[{'kind':k,'version':'1','schema_version':'v7','entries':defaults.get(k,[]),'dependency_versions':dependencies.get(k,{})} for k in sorted(ResourceRelease.REQUIRED)],'dependency_versions':{k:'1' for k in sorted(ResourceRelease.REQUIRED)}}
        # Exclusive creation preserves an existing release.
        with args.path.open('x',encoding='utf-8') as f: json.dump(manifest,f,ensure_ascii=False,indent=2)
        print('Unsigned, empty draft. Populate and obtain external review before production use.')
        return
    trusted=json.loads(args.trusted_reviews.read_text(encoding='utf-8')) if args.trusted_reviews else None
    release=ResourceRelease.load(args.path,require_review=not args.draft,trusted_reviews=trusted)
    if args.ah_snapshot:
        from .authoring import load_store
        release.validate_store(load_store(args.ah_snapshot))
    elif not args.draft:
        parser.error('production check requires --ah-snapshot to validate actual T refs')
    print(release.sha256)
    print('DRAFT schema only; review/coverage not approved' if args.draft else 'Ed25519 signature, external key pin and actual AH mappings validated; no gate PASS claimed')


if __name__=='__main__': main()
