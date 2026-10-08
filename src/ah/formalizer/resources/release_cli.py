"""Create an unsigned resource draft or validate an externally reviewed release.

No command manufactures a reviewer, signature, coverage result or PASS status.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from .loader import ResourceRelease
from ...model.types import ActantRole


def main():
    parser=argparse.ArgumentParser(__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    init=sub.add_parser('init'); init.add_argument('path',type=Path)
    check=sub.add_parser('check'); check.add_argument('path',type=Path); check.add_argument('--draft',action='store_true'); check.add_argument('--trusted-reviews',type=Path)
    args=parser.parse_args()
    if args.command=='init':
        defaults={'RoleRegistry':[{'role_id':r.value} for r in ActantRole],
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
    print(release.sha256)
    print('DRAFT schema only; review/coverage not approved' if args.draft else 'Reviewed snapshot and pinned review record validated; no gate PASS claimed')


if __name__=='__main__': main()
