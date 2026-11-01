"""Validate P00 evidence inventory, not runtime correctness or language coverage."""
import ast,gzip,hashlib,json
from pathlib import Path

def main():
    root=Path(__file__).resolve().parents[2]
    out=root/'docs/audits/probe_contract_20261028'
    registry=json.loads((out/'F05_CAPABILITIES.json').read_text())['capabilities']
    ids=[x['id'] for x in registry];assert len(ids)==len(set(ids))
    tree=ast.parse((root/'src/ah/formalizer/relation_composition.py').read_text())
    relations=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign)
        and any(isinstance(t,ast.Name) and t.id=='RELATIONS' for t in n.targets))
    assert {'R-'+k for k in relations}=={i for i in ids if i.startswith('R-')}
    assert set(range(1,7))=={b for x in registry for b in x['blocks']}
    assert all(x['architecture'] and x['route'] and x['cards'] and x['acceptance_contrast'] for x in registry)
    assert all(c in {'P'+str(i).zfill(2) for i in range(24)} for x in registry for c in x['cards'])
    manifest=json.loads((out/'p00/manifest.json').read_text())
    for name,sha in manifest['files'].items():assert hashlib.sha256((root/name).read_bytes()).hexdigest()==sha,name
    with gzip.open(out/'p00/current_capture.json.gz','rt') as f:rows=json.load(f)
    failed=[x for x in rows if x['outcome']=='failed']
    historical=[]
    for file in ['reading-baseline.log','reading-nominal-baseline.log']:
        historical += [line.removeprefix('FAILED ') for line in (out/'p00'/file).read_text().splitlines() if line.startswith('FAILED ')]
    assert len(failed)==len(historical)==19
    assert {x['nodeid'] for x in failed}==set(historical)
    report=(out/'F05_P00_BASELINE.md').read_text()
    assert all(x['nodeid'] in report for x in failed)
    assert len([l for l in report.splitlines() if l.startswith('## B')])==19
    print(f'P00 inventory OK: {len(registry)} capabilities, {len(relations)} relations, 19/19 historical failures reproduced. Runtime correctness NOT assessed.')

if __name__=='__main__':main()
