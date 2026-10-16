#!/usr/bin/env python3
"""Authored v3 upgrade: accepted query roots and a documented core-slot correction.

Reads only the pinned authored v2 corpus, never traces or model answers.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import shutil
import tempfile

ROOT=Path(__file__).resolve().parents[1]
CONTRACT='v7-observer-3'


def contains_nested(container,value):
    children=container.values() if isinstance(container,dict) else container if isinstance(container,list) else ()
    return any(child==value or contains_nested(child,value) for child in children)


def migrate(source,target):
    from tools.check_formalizer_v7_oracle import validate,load_corpus,canonical
    validate(source);manifest,cases=load_corpus(source)
    if manifest.get('observer_contract')!='v7-observer-2':raise ValueError('V2_SOURCE_REQUIRED')
    if target.exists():raise ValueError('CORPUS_ALREADY_EXISTS')
    staging=Path(tempfile.mkdtemp(prefix=target.name+'.building-',dir=target.parent))
    changes=[]
    try:
        for path in source.iterdir():
            if path.is_file():shutil.copyfile(path,staging/path.name)
        (staging/'MIGRATION.json').rename(staging/'BASE_MIGRATION_V2.json')
        for case in cases:
            case['schema_version']='v7-symbolic-oracle-3'
            if case['tier']!='pipeline':continue
            for step in case['steps']:
                for check in step['checks']:
                    if check['path']=='/observer/contract':check['value']=CONTRACT
                if case['case_id']=='A35':
                    # Authored annotation: Мария is the overt core subject of
                    # перестала. V2 accidentally retained the old semantic
                    # EXPERIENCER name while exporting other OPEN core slots.
                    for check in step['checks']:
                        if check['path'].startswith('/assertions/') and check['op']=='set_eq':
                            roles=check['value'][0]['roles']
                            assert roles['EXPERIENCER']=={'entity':'maria'} and 'SUBJECT' not in roles
                            roles['SUBJECT']=roles.pop('EXPERIENCER')
                    changes.append({'case_id':case['case_id'],'change':'OPEN core subject EXPERIENCER -> SUBJECT',
                        'reason':'overt subject of the parent predicate; architecture A35 requires scoped lexical content, not an EXPERIENCER label'})
                if step['payload'].get('raw_input',{}).get('request_kind')=='QUERY':
                    patterns=next(c['value'] for c in step['checks'] if c['path']=='/generation/gold_patterns')
                    roots=[p for p in patterns if not any(contains_nested(other,p) for other in patterns if other!=p)]
                    if len(roots)!=1:raise ValueError('QUERY_ROOT_REQUIRES_AUTHOR_ANNOTATION:'+case['case_id'])
                    step['checks'].extend([
                        {'op':'eq','path':'/query/status','value':'COMPILED'},
                        {'op':'set_eq','path':'/query/formulas','value':roots}])
                    changes.append({'case_id':case['case_id'],'change':'require compiled query and exact accepted root',
                        'root':roots[0],'reason':'maximal tree of existing authored gold, preserving all nested scopes and roles'})
        def write(name,value):
            (staging/name).write_text(json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2)+'\n',encoding='utf-8',newline='\n')
        (staging/'cases.jsonl').write_text(''.join(canonical(c)+'\n' for c in cases),encoding='utf-8',newline='\n')
        manifest['stats']['checks']=sum(len(s['checks']) for c in cases for s in c['steps'])
        coverage=json.loads((staging/'coverage.json').read_text());coverage['stats']=manifest['stats'];write('coverage.json',coverage)
        schema=json.loads((staging/'oracle.schema.json').read_text());schema['properties']['schema_version']['const']='v7-symbolic-oracle-3';write('oracle.schema.json',schema)
        write('MIGRATION.json',{'observer_contract':CONTRACT,'base_manifest_sha256':hashlib.sha256((source/'manifest.json').read_bytes()).hexdigest(),
            'changes':changes,'prior_migration':'BASE_MIGRATION_V2.json'})
        readme=(staging/'README.md').read_text(encoding='utf-8')
        (staging/'README.md').write_text('# Контракт наблюдений 3\n\n'
            'Все 72 вопроса требуют `/query/status=COMPILED` и точного `/query/formulas`: '
            'принятого и скомпилированного дерева со всеми участниками и областями. '
            'Наличие кандидата и отсутствие записанных фактов проверяются отдельно. '
            'Роли OPEN сохраняют ID ядра; отдельное исправление A35 обосновано в MIGRATION.json. '
            'Корпуса v1/v2 не изменены.\n\n'+readme,encoding='utf-8',newline='\n')
        manifest.update(observer_contract=CONTRACT,status='AUTHORED_NOT_EXECUTED',
            migration_tool_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            checker_sha256=hashlib.sha256((ROOT/'tools/check_formalizer_v7_oracle.py').read_bytes()).hexdigest())
        manifest['artifacts']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(staging.iterdir()) if p.is_file() and p.name!='manifest.json'}
        write('manifest.json',manifest);validate(staging);os.rename(staging,target)
    finally:
        if staging.exists():shutil.rmtree(staging)
    return {'cases':len(cases),'checks':manifest['stats']['checks'],'changes':len(changes)}


if __name__=='__main__':
    import sys
    sys.path.insert(0,str(ROOT))
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=ROOT/'data/formalizer_v7_oracle_v2')
    parser.add_argument('--out',type=Path,default=ROOT/'data/formalizer_v7_oracle_v3')
    args=parser.parse_args();print(json.dumps(migrate(args.source,args.out)))
