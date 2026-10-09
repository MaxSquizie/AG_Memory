#!/usr/bin/env python3
"""One entry point for AH component cases and a real local-model native run."""
from pathlib import Path
import argparse, gzip, hashlib, json, shutil, sys, time

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'src')]
from tools import check_formalizer_v7_oracle as checker
from tools import formalizer_v7_extended_binding as adapter
from tools import formalizer_v7_runtime_adapter as base
from tools.run_formalizer_v7_bound_oracle import coverage,dump,sha

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--corpus',type=Path,default=ROOT/'data/formalizer_v7_oracle')
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--provider',choices=['disabled','lmstudio','openai','replay'],default='disabled')
    p.add_argument('--base-url',default='http://127.0.0.1:1234')
    p.add_argument('--model',default='')
    p.add_argument('--timeout',type=float,default=120)
    p.add_argument('--max-tokens',type=int,default=4096)
    p.add_argument('--case',action='append',default=[],help='repeatable exact case ID')
    p.add_argument('--tier',action='append',default=[])
    p.add_argument('--mechanism',action='append',default=[])
    p.add_argument('--replay-from',type=Path)
    p.add_argument('--list',action='store_true',help='list selected cases; no writes or provider calls')
    a=p.parse_args(argv)
    if a.timeout<=0 or a.max_tokens<1:p.error('positive timeout/max-tokens required')
    if a.provider in {'lmstudio','openai'} and not a.model:p.error('--model must name the loaded local model')
    if a.provider=='replay' and not a.replay_from:p.error('--replay-from is required')
    if a.replay_from and a.provider!='replay':p.error('--replay-from requires --provider replay')
    validation=checker.validate(a.corpus);manifest,cases=checker.load_corpus(a.corpus)
    if a.case and set(a.case)-{c['case_id'] for c in cases}:p.error('unknown --case ID')
    selected=[c for c in cases if (not a.case or c['case_id'] in a.case) and (not a.tier or c['tier'] in a.tier) and (not a.mechanism or set(a.mechanism)&set(c['mechanisms']))]
    if not selected:p.error('selection is empty')
    if a.list:
        print('\n'.join(c['case_id'] for c in selected));return 0
    config={'provider':a.provider,'model':a.model,'base_url':a.base_url,'timeout':a.timeout,'max_tokens':a.max_tokens}
    # A new directory means a new execution, never silent reuse of another model's WAL.
    if a.out.exists() and any(a.out.iterdir()):p.error('output directory is not empty; choose a new --out')
    a.out.mkdir(parents=True,exist_ok=True)
    if a.replay_from:
        prior=json.loads((a.replay_from/'run_config.json').read_text(encoding='utf-8'))
        if prior['corpus_manifest_sha256']!=sha(a.corpus/'manifest.json'):p.error('replay corpus hash changed')
        if prior['source_snapshot']!=base.source_snapshot():p.error('replay implementation hashes changed')
        config={**prior['provider_config'],'provider':'replay'}
        # Only immutable completed provider histories are copied. Actual/gold
        # checkpoints are never read by the runtime binding.
        for c in selected:
            cid=base.digest(c['case_id']);src=a.replay_from/'cases'/cid/'journal.log'
            if not src.is_file():continue
            rows=[json.loads(line) for line in src.read_text(encoding='utf-8').splitlines() if line.strip()]
            rows=[r for r in rows if r['payload'].get('kind') in {'prov_call','RUN_STARTED'}]
            dest=a.out/'cases'/cid;dest.mkdir(parents=True,exist_ok=True)
            # JournalChannel checks checksums/seq; use its append boundary.
            from ah.core.journal import JournalChannel
            journal=JournalChannel(dest/'journal.log')
            for r in rows:journal.append(r['channel'],r['payload'],run_id=r.get('run_id',''))
    adapter.CONFIG=config;adapter.RUN_DIR=a.out/'cases';base.RESOURCE_ARTIFACT_DIR=a.out/'resources'
    dump(a.out/'run_config.json',{'provider_config':config,'corpus_manifest_sha256':sha(a.corpus/'manifest.json'),'source_snapshot':base.source_snapshot(),'selected_case_ids':[c['case_id'] for c in selected],'production_release':False})
    actual=a.out/'actual.jsonl';started=time.monotonic();fixtures=checker.readjson(a.corpus/'fixtures.json');bindings=[];received_calls=0
    with actual.open('w',encoding='utf-8') as out:
        for i,gold in enumerate(selected,1):
            stimulus=json.loads(json.dumps(gold))
            for s in stimulus['steps']:del s['checks']
            try:result=adapter.run_case(stimulus,fixtures)
            except Exception as exc:
                import traceback
                result={'schema_version':'v7-oracle-trace-1','case_id':gold['case_id'],'checkpoints':[],'execution_status':'ERROR','runtime_error':{'type':type(exc).__name__,'message':str(exc),'traceback':traceback.format_exc()}}
            out.write(checker.canonical(result)+'\n');out.flush()
            bindings.append({'case_id':gold['case_id'],'execution_status':result['execution_status'],
                'level':result.get('binding_manifest',{}).get('execution_level'),
                'api_refs':result.get('binding_manifest',{}).get('api_refs',[]),'blockers':result.get('blockers',[])})
            wal=a.out/'cases'/base.digest(gold['case_id'])/'journal.log'
            if wal.is_file():received_calls+=sum(json.loads(line)['payload'].get('kind')=='prov_call' and json.loads(line)['payload'].get('state')=='RECEIVED' for line in wal.read_text(encoding='utf-8').splitlines() if line.strip())
            if i%25==0 or i==len(selected):print(f'{i}/{len(selected)}: {gold["case_id"]} ({result["execution_status"]})',flush=True)
    case_filter=[c['case_id'] for c in selected] if len(selected)!=len(cases) else None
    report=checker.compare(a.corpus,actual,case_filter);dump(a.out/'comparison.json',report)
    # Original coverage formatter accepts the extended action registry too.
    old=base.SUPPORTED
    try:base.SUPPORTED=adapter.SUPPORTED;measured=coverage(selected,report)
    finally:base.SUPPORTED=old
    measured['execution_scope']='NATIVE_PIPELINE + COMPONENT_OR_WAL';dump(a.out/'runtime_coverage.json',measured)
    dump(a.out/'bindings.json',{'registered_actions':sorted(adapter.SUPPORTED),'cases':bindings})
    archive=a.out/'actual.jsonl.gz';archive.write_bytes(gzip.compress(actual.read_bytes(),mtime=0))
    dump(a.out/'provenance.json',{'source_snapshot':base.source_snapshot(),'corpus_manifest_sha256':sha(a.corpus/'manifest.json'),'document_sha256':validation['document_sha256'],'actual_sha256':sha(actual),'archive_sha256':sha(archive),'comparison_sha256':sha(a.out/'comparison.json'),'elapsed_seconds':time.monotonic()-started,'python':sys.version,'production_release':False,'gates_pass_claim':False,'model_live_execution':a.provider in {'lmstudio','openai'} and received_calls>0,'received_provider_calls':received_calls,'process_kill_crashes':False})
    actual.unlink()
    counts={k:report[k] for k in ('status','passed_cases','failed_cases','blocked_cases')}
    (a.out/'README.md').write_text('# Runtime oracle run\n\n```json\n'+json.dumps(counts,indent=2)+'\n```\n\nFull provider WAL, typed IR, observed AH facts, signed TEST_ONLY fixture resources and comparison are retained. BLOCKED is an absent binding; FAIL is a comparison or runtime failure. This is not G0–G5 PASS or a reviewed production resource release.\n',encoding='utf-8')
    print(json.dumps(counts,ensure_ascii=False))
    return 1 if report['status']=='FAIL' else 3 if report['blocked_cases'] else 0

if __name__=='__main__':raise SystemExit(main())
