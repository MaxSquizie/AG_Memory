#!/usr/bin/env python3
"""Execute and compare concrete bindings; exit 3 means incomplete coverage."""
from pathlib import Path
from collections import Counter,defaultdict
import argparse,json,gzip,hashlib,subprocess,sys
from importlib.metadata import version
from tools import check_formalizer_v7_oracle as verifier
from tools import formalizer_v7_runtime_adapter as adapter


def dump(path,value):path.write_text(json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2)+'\n')
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def coverage(cases,report):
    statuses={r['case_id']:r['status'] for r in report['results']};groups={k:defaultdict(Counter) for k in ('tiers','mechanisms','acceptance','dry_runs','actions')}
    for case in cases:
        st=statuses[case['case_id']]
        for key,items in [('tiers',[case['tier']]),('mechanisms',case['mechanisms']),('acceptance',case['acceptance_refs']),('dry_runs',case['dry_run_refs']),('actions',sorted({s['action'] for s in case['steps']}))]:
            for item in items:groups[key][item][st]+=1
    data={k:{name:dict(counter) for name,counter in sorted(v.items())} for k,v in groups.items()}
    data['mechanism_case_sets']={}
    for level in ('COMPLETE','PARTIAL','NONE'):
        data['mechanism_case_sets'][level]=sorted(m for m,c in groups['mechanisms'].items() if ('COMPLETE' if c['PASS'] and not c['BLOCKED'] and not c['FAIL'] else 'PARTIAL' if c['PASS'] else 'NONE')==level)
    data['binding_action_count']=len(adapter.SUPPORTED);data['total_action_count']=len(data['actions'])
    data['coverage_claim']='Executed corpus cases only; not a production release or G0–G5 PASS.'
    return data


def main():
    p=argparse.ArgumentParser();p.add_argument('--corpus',type=Path,default=Path('data/formalizer_v7_oracle'));p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    a.out.mkdir(parents=True,exist_ok=True);adapter.RESOURCE_ARTIFACT_DIR=a.out/'resources'
    validation=verifier.validate(a.corpus);actual=a.out/'actual.jsonl'
    verifier.run(a.corpus,'tools.formalizer_v7_runtime_adapter:run_case',actual)
    report=verifier.compare(a.corpus,actual);dump(a.out/'comparison.json',report)
    _,cases=verifier.load_corpus(a.corpus);measured=coverage(cases,report);dump(a.out/'runtime_coverage.json',measured)
    baseline=subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip()
    repo=Path(__file__).resolve().parents[1]
    deps={name:version(name) for name in ('pymorphy3','cryptography','jsonschema','pytest')}
    provenance={'baseline_commit':baseline,'source_snapshot':adapter.source_snapshot(),'python_version':sys.version,'dependencies':deps,'corpus_manifest_sha256':sha(a.corpus/'manifest.json'),'document_sha256':validation['document_sha256'],'actual_sha256':sha(actual),'comparison_sha256':sha(a.out/'comparison.json'),'runtime_coverage_sha256':sha(a.out/'runtime_coverage.json'),'harness_files':{str(f.relative_to(repo)):sha(f) for f in [Path(__file__).resolve(),repo/'tools/check_formalizer_v7_oracle.py',repo/'tools/build_formalizer_v7_oracle.py']},'resources':{f.name:sha(f) for f in sorted((a.out/'resources').glob('*.json'))},'execution_level':'COMPONENT_OR_WAL','closed_oracle_expected_snapshot_hashes':'NOT_COMPILED','true_process_kill_crashes':'NOT_EXECUTED','reviewed_production_release':'NOT_PROVIDED','gates_pass_claim':False}
    archive=a.out/'actual.jsonl.gz';archive.write_bytes(gzip.compress(actual.read_bytes(),mtime=0))
    assert hashlib.sha256(gzip.decompress(archive.read_bytes())).hexdigest()==provenance['actual_sha256']
    provenance['actual_gzip_sha256']=sha(archive);dump(a.out/'provenance.json',provenance);actual.unlink()
    rows='\n'.join(f'| {name} | {n.get("PASS",0)} | {n.get("FAIL",0)} | {n.get("BLOCKED",0)} |' for name,n in measured['tiers'].items())
    (a.out/'README.md').write_text(f'''# V7 concrete oracle execution

Baseline: `{baseline}`; exact implementation hashes are in `provenance.json`.

Result: **{report['passed_cases']} PASS / {report['failed_cases']} FAIL / {report['blocked_cases']} BLOCKED**. Full run status: **{report['status']}**.

| Tier | PASS | FAIL | BLOCKED |
|---|---:|---:|---:|
{rows}

`actual.jsonl.gz` contains actual checkpoints and concrete binding manifests; its decompressed hash is pinned. `comparison.json` lists every result and blocker. `runtime_coverage.json` reports case coverage per mechanism/A/DR/action. Signed resource files use a public TEST_ONLY fixture key and are not a reviewed production release.

No raw-text case is claimed executed without its API binding. These are component and file-WAL checks; `crash` discards the adapter and restores a fresh AH core, not a killed operating-system process. Compiler IR export currently means admitted typed T5 plans, not a full parser IR snapshot. Gates G0–G5 are not evaluated. Missing actions block the entire case before writes; runtime exceptions fail the case.
''')
    print(json.dumps({k:report[k] for k in ('status','passed_cases','failed_cases','blocked_cases')},ensure_ascii=False))
    return 1 if report['status']=='FAIL' else 3 if report['status']=='BLOCKED' else 0

if __name__=='__main__':raise SystemExit(main())
