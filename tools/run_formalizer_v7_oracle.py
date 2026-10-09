#!/usr/bin/env python3
"""One entry point for AH component cases and a real local-model native run."""
from pathlib import Path
from collections import Counter
import argparse, gzip, hashlib, json, shutil, sys, time

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'src')]
from tools import check_formalizer_v7_oracle as checker
from tools import formalizer_v7_extended_binding as adapter
from tools import formalizer_v7_runtime_adapter as base
from tools import formalizer_v7_progress as progress
from tools.run_formalizer_v7_bound_oracle import coverage,dump,sha

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--corpus',type=Path,default=ROOT/'data/formalizer_v7_oracle')
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--provider',choices=['disabled','lmstudio','ollama','openai','replay'],default='disabled')
    p.add_argument('--base-url',default=None)
    p.add_argument('--model',default='')
    p.add_argument('--timeout',type=float,default=120)
    p.add_argument('--max-tokens',type=int,default=4096)
    p.add_argument('--case',action='append',default=[],help='repeatable exact case ID')
    p.add_argument('--tier',action='append',default=[])
    p.add_argument('--mechanism',action='append',default=[])
    p.add_argument('--acceptance',action='append',default=[],help='repeatable A01–A39 reference')
    p.add_argument('--dry-run',action='append',default=[],help='repeatable DR1–DR31 reference')
    p.add_argument('--replay-from',type=Path)
    p.add_argument('--list',action='store_true',help='list selected cases; no writes or provider calls')
    p.add_argument('--progress-jsonl',action='store_true',help='emit flushed V7_PROGRESS JSON events to stdout (also saved in progress.jsonl)')
    a=p.parse_args(argv)
    if a.timeout<=0 or a.max_tokens<1:p.error('positive timeout/max-tokens required')
    if a.provider in {'lmstudio','ollama','openai'} and not a.model:p.error('--model must name the loaded local model')
    if a.base_url is None:
        a.base_url='http://127.0.0.1:11434' if a.provider=='ollama' else 'http://127.0.0.1:1234'
    if a.provider=='replay' and not a.replay_from:p.error('--replay-from is required')
    if a.replay_from and a.provider!='replay':p.error('--replay-from requires --provider replay')
    validation=checker.validate(a.corpus);manifest,cases=checker.load_corpus(a.corpus)
    prior=None
    if a.replay_from:
        prior=json.loads((a.replay_from/'run_config.json').read_text(encoding='utf-8'))
        if prior['corpus_manifest_sha256']!=sha(a.corpus/'manifest.json'):p.error('replay corpus hash changed')
        if prior['source_snapshot']!=base.source_snapshot():p.error('replay implementation hashes changed')
        # With no explicit filter, replay the original selection, not the
        # entire corpus against a one-case provider history.
        if not any((a.case,a.tier,a.mechanism,a.acceptance,a.dry_run)):
            a.case=list(prior['selected_case_ids'])
    if a.case and set(a.case)-{c['case_id'] for c in cases}:p.error('unknown --case ID')
    selected=[c for c in cases if (not a.case or c['case_id'] in a.case) and (not a.tier or c['tier'] in a.tier) and (not a.mechanism or set(a.mechanism)&set(c['mechanisms'])) and (not a.acceptance or set(a.acceptance)&set(c['acceptance_refs'])) and (not a.dry_run or set(a.dry_run)&set(c['dry_run_refs']))]
    if not selected:p.error('selection is empty')
    if prior and {c['case_id'] for c in selected}-set(prior['selected_case_ids']):
        p.error('replay selection includes cases absent from the original run')
    if a.list:
        print('\n'.join(c['case_id'] for c in selected));return 0
    config={'provider':a.provider,'model':a.model,'base_url':a.base_url,'timeout':a.timeout,'max_tokens':a.max_tokens}
    # A new directory means a new execution, never silent reuse of another model's WAL.
    if a.out.exists() and any(a.out.iterdir()):p.error('output directory is not empty; choose a new --out')
    a.out.mkdir(parents=True,exist_ok=True)
    if a.replay_from:
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
    progress.configure(a.out/'progress.jsonl',stdout=a.progress_jsonl)
    live_counts={'completed':0,'total':len(selected),'passed':0,'failed':0,'blocked':0}
    progress.emit('run_started',provider=a.provider,model=a.model,output_dir=str(a.out),
        selected_case_ids=[c['case_id'] for c in selected],**live_counts)
    with actual.open('w',encoding='utf-8') as out:
        for i,gold in enumerate(selected,1):
            stimulus=json.loads(json.dumps(gold))
            for s in stimulus['steps']:del s['checks']
            case_started=time.monotonic()
            with progress.context(case_id=gold['case_id'],case_index=i,**live_counts):
                progress.emit('case_started',title=gold['title'],tier=gold['tier'],step_total=len(stimulus['steps']))
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
            compared=checker.compare_case(gold,result)
            live_counts['completed']=i
            live_counts[{'PASS':'passed','FAIL':'failed','BLOCKED':'blocked'}[compared['status']]]+=1
            progress.emit('case_finished',case_id=gold['case_id'],case_index=i,
                status=compared['status'],execution_status=result['execution_status'],
                errors=compared['errors'],blockers=compared.get('blockers',[]),
                runtime_error=result.get('runtime_error'),case_elapsed_seconds=round(time.monotonic()-case_started,3),
                received_provider_calls=received_calls,**live_counts)
            if i%25==0 or i==len(selected):print(f'{i}/{len(selected)}: {gold["case_id"]} ({result["execution_status"]})',flush=True)
    case_filter=[c['case_id'] for c in selected] if len(selected)!=len(cases) else None
    report=checker.compare(a.corpus,actual,case_filter)
    source_at_end=base.source_snapshot(refresh=True)
    source_unchanged=source_at_end==base.source_snapshot()
    if not source_unchanged:
        report['status']='FAIL'
        report['errors'].append({'error':'implementation changed during execution'})
    dump(a.out/'comparison.json',report)
    required_actions={s['action'] for c in cases for s in c['steps']}
    records=[json.loads(line) for line in actual.read_text(encoding='utf-8').splitlines()]
    errors={r['case_id']:r['runtime_error'] for r in records if r.get('runtime_error')}
    issues=[]
    for result in report['results']:
        if result['status']!='FAIL':continue
        detail=result['errors']
        attribution=('BINDING_OR_RUNTIME_EXCEPTION' if result['case_id'] in errors else
            'ORACLE_STIMULUS_INVALID' if any(e.get('error')=='invalid oracle stimulus' for e in detail) else
            'OBSERVATION_EXPORT_GAP' if any('missing observed path' in e.get('error','') for e in detail) else
            'IMPLEMENTATION_OR_MODEL_MISMATCH_REQUIRES_REVIEW')
        issues.append({**result,'attribution':attribution})
    dump(a.out/'issues.json',{'gates_pass_claim':False,'counts':dict(Counter(x['attribution'] for x in issues)),'cases':issues})
    summary={k:report[k] for k in ('status','passed_cases','failed_cases','blocked_cases')}
    summary.update(registered_actions=len(adapter.SUPPORTED&required_actions),total_actions=len(required_actions),
        unbound_actions=sorted(required_actions-adapter.SUPPORTED),runtime_exceptions=len(errors),
        blocker_counts=dict(Counter(b['reason'] for r in records for b in r.get('blockers',[]))),
        cases_with_missing_observation_paths=[x['case_id'] for x in issues if x['attribution']=='OBSERVATION_EXPORT_GAP'],
        failure_attribution_counts=dict(Counter(x['attribution'] for x in issues)),provider=a.provider,
        source_unchanged=source_unchanged,gates_pass_claim=False)
    dump(a.out/'summary.json',summary)
    # Original coverage formatter accepts the extended action registry too.
    old=base.SUPPORTED
    try:base.SUPPORTED=adapter.SUPPORTED;measured=coverage(selected,report)
    finally:base.SUPPORTED=old
    measured['execution_scope']='NATIVE_PIPELINE + COMPONENT_OR_WAL';dump(a.out/'runtime_coverage.json',measured)
    dump(a.out/'bindings.json',{'registered_actions':sorted(adapter.SUPPORTED),'cases':bindings})
    archive=a.out/'actual.jsonl.gz';archive.write_bytes(gzip.compress(actual.read_bytes(),mtime=0))
    dump(a.out/'provenance.json',{'source_snapshot':base.source_snapshot(),'source_snapshot_at_end':source_at_end,'source_unchanged':source_unchanged,'corpus_manifest_sha256':sha(a.corpus/'manifest.json'),'document_sha256':validation['document_sha256'],'actual_sha256':sha(actual),'archive_sha256':sha(archive),'comparison_sha256':sha(a.out/'comparison.json'),'elapsed_seconds':time.monotonic()-started,'python':sys.version,'production_release':False,'gates_pass_claim':False,'model_live_execution':a.provider in {'lmstudio','ollama','openai'} and received_calls>0,'received_provider_calls':received_calls,'process_kill_crashes':False})
    actual.unlink()
    counts={k:report[k] for k in ('status','passed_cases','failed_cases','blocked_cases')}
    (a.out/'README.md').write_text('# Runtime oracle run\n\n```json\n'+json.dumps(counts,indent=2)+'\n```\n\nFull provider WAL, typed IR, observed AH facts, signed TEST_ONLY fixture resources and comparison are retained. BLOCKED records an unavailable prerequisite (for example, a disabled model provider); FAIL records a comparison, invalid stimulus or runtime failure. See summary.json and issues.json for attribution. This is not G0–G5 PASS or a reviewed production resource release.\n',encoding='utf-8')
    print(json.dumps(counts,ensure_ascii=False))
    progress.emit('run_finished',status=report['status'],summary=summary,
        errors=report['errors'],received_provider_calls=received_calls,**live_counts)
    progress.close()
    return 1 if report['status']=='FAIL' else 3 if report['blocked_cases'] else 0

if __name__=='__main__':raise SystemExit(main())
