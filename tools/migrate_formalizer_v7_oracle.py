#!/usr/bin/env python3
"""Publish observer contract 2 from authored gold, never from an SUT run.

The finite vocabulary below is an annotation of this test fixture, not a
language algorithm. Production code does not import or receive these labels.
"""
from pathlib import Path
import argparse
import copy
import hashlib
import json
import os
import re
import shutil
import tempfile

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = 'v7-observer-2'
SURFACES = {
    'холодно': ('холодно',), 'переадресовать': ('переадресовал',),
    'перестать': ('перестала', 'перестал'), 'начать': ('начал',),
    'снова-мочь': ('снова смог',), 'глоркнуть': ('глоркнул',),
    'зумбировать': ('зумбировал',), 'флукнуть': ('флукнул',),
    'квелировать': ('квелировал',), 'бронкнуть': ('бронкнул',),
    'шарпировать': ('шарпировал',), 'траверсировать': ('траверсировал',),
}
OPEN_ROLES = {'AGENT': 'SUBJECT', 'THEME': 'OBJECT', 'CONTENT': 'OBJECT'}


def source_refs(text, lemma):
    hits = [(m.start(), m.group()) for form in SURFACES[lemma]
            for m in re.finditer(r'(?<!\w)' + re.escape(form) + r'(?!\w)', text, re.I)]
    if len(hits) != 1:
        raise ValueError('AUTHORED_OPEN_SOURCE_NOT_UNIQUE: ' + lemma + ': ' + text)
    start, surface = hits[0]
    return [f'tok:{start+m.start()}:{start+m.end()}' for m in re.finditer(r'\S+', surface)]


def formula(value, text):
    if isinstance(value, list):
        return [formula(v, text) for v in value]
    if not isinstance(value, dict):
        return value
    result = {k: formula(v, text) for k, v in value.items()}
    predicate = value.get('predicate')
    if isinstance(predicate, str) and predicate.startswith('OPEN:'):
        result['predicate'] = {'open_source': source_refs(text, predicate[5:])}
        roles = result['roles']
        renamed = {OPEN_ROLES.get(k, k): v for k, v in roles.items()}
        if len(renamed) != len(roles):
            raise ValueError('AUTHORED_OPEN_ROLE_COLLISION')
        result['roles'] = renamed
    if result.get('operator') in {'AND', 'OR', 'XOR'}:
        result['operands'].sort(key=lambda v: json.dumps(v, sort_keys=True))
    return result


def migrate(source, target):
    from tools.check_formalizer_v7_oracle import load_corpus, validate, canonical
    validate(source)
    manifest, cases = load_corpus(source)
    if target.exists():
        raise ValueError('CORPUS_ALREADY_EXISTS')
    target.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=target.name+'.building-', dir=target.parent))
    changes = []
    try:
        for path in source.iterdir():
            if path.is_file(): shutil.copyfile(path, staging/path.name)
        for case in cases:
            case['schema_version'] = 'v7-symbolic-oracle-2'
            if case['tier'] != 'pipeline': continue
            for step in case['steps']:
                text = step['payload']['raw_input']['text']
                before = copy.deepcopy(step['checks'])
                step['checks'] = formula(before, text)
                step['checks'].append({'op':'eq', 'path':'/observer/contract', 'value':CONTRACT})
                if not any(c['path']=='/time/invented_past_intervals' for c in step['checks']):
                    step['checks'].append({'op':'eq','path':'/time/invented_past_intervals','value':[]})
                if not any(c['path']=='/modus' for c in step['checks']):
                    kind=step['payload']['raw_input'].get('request_kind')
                    if kind in {'ASSERTION','QUERY','COMMAND'}:
                        step['checks'].append({'op':'eq','path':'/modus',
                                               'value':'DECLARATIVE' if kind=='ASSERTION' else kind})
                changes.append({'case_id':case['case_id'], 'step_id':step['id'],
                    'open_projection_changed': formula(before,text)!=before,
                    'added_guards':[c['path'] for c in step['checks'][len(before):]]})
        def write(name, value):
            (staging/name).write_text(json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2)+'\n',encoding='utf-8',newline='\n')
        (staging/'cases.jsonl').write_text(''.join(canonical(c)+'\n' for c in cases),encoding='utf-8',newline='\n')
        stats=manifest['stats'];stats['checks']=sum(len(s['checks']) for c in cases for s in c['steps'])
        coverage=json.loads((staging/'coverage.json').read_text());coverage['stats']=stats;write('coverage.json',coverage)
        schema=json.loads((staging/'oracle.schema.json').read_text())
        schema['properties']['schema_version']['const']='v7-symbolic-oracle-2';write('oracle.schema.json',schema)
        write('MIGRATION.json',{'observer_contract':CONTRACT,
            'base_manifest_sha256':hashlib.sha256((source/'manifest.json').read_bytes()).hexdigest(),
            'authored_open_surfaces':SURFACES,'open_role_namespace':OPEN_ROLES,
            'reason':'Source occurrence identity replaces mandatory OOV lemmatization. Open roles retain runtime IDs; semantic names require a known template. Modus/time guards are now checked.',
            'changes':changes})
        readme=(staging/'README.md').read_text(encoding='utf-8')
        (staging/'README.md').write_text('# Контракт наблюдений 2\n\n'
            'Открытый предикат: `{"open_source":["tok:start:end", ...]}`; роли сохраняют реальные ID. '
            'KNOWN продолжает использовать карту конкретного шаблона. Исходные слова доступны в raw_input; '
            'лемма не требуется без подтверждения. Экспорт не читает ожидаемые ответы.\n\n'
            'Изменения ожиданий перечислены в MIGRATION.json. Дополнительно проверяются речевой акт и временные основания. '
            'Старый корпус остаётся неизменным. Формат контейнера trace остаётся v7-oracle-trace-1; '
            'версия наблюдений проверяется обязательным /observer/contract.\n\n'+readme,
            encoding='utf-8',newline='\n')
        manifest.update(observer_contract=CONTRACT,status='AUTHORED_NOT_EXECUTED',
            migration_tool_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            checker_sha256=hashlib.sha256((ROOT/'tools/check_formalizer_v7_oracle.py').read_bytes()).hexdigest())
        manifest['artifacts']={p.name:hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(staging.iterdir()) if p.is_file() and p.name!='manifest.json'}
        write('manifest.json',manifest)
        validate(staging)
        os.rename(staging,target)
    finally:
        if staging.exists():shutil.rmtree(staging)
    return {'cases':len(cases),'checks':stats['checks'],'pipeline_cases':len(changes)}


if __name__=='__main__':
    import sys
    sys.path.insert(0,str(ROOT))
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,default=ROOT/'data/formalizer_v7_oracle')
    parser.add_argument('--out',type=Path,default=ROOT/'data/formalizer_v7_oracle_v2')
    args=parser.parse_args()
    print(json.dumps(migrate(args.source,args.out)))
