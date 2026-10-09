"""Verifier fault injection only; no SUT/project imports, no production test results."""
import sys,json,pathlib,copy,importlib.util,tempfile
root=pathlib.Path(sys.argv[1]) if len(sys.argv)>1 else pathlib.Path(__file__).resolve().parents[1];spec=importlib.util.spec_from_file_location('oc',root/'tools/check_formalizer_v7_oracle.py');oc=importlib.util.module_from_spec(spec);spec.loader.exec_module(oc)
corpus=root/'data/formalizer_v7_oracle';_,cases=oc.load_corpus(corpus)

# Independent verifier primitive checks. Fail closed for every comparator and absent/null.
actual={'x':[1,2],'n':None,'bool':True,'same':{'z':3}}
assert oc.evaluate({'op':'set_eq','path':'/x','value':[2,1]},actual,{})
assert not oc.evaluate({'op':'set_eq','path':'/x','value':[1]},actual,{})
assert not oc.evaluate({'op':'set_eq','path':'/x','value':[1,1,2]},actual,{})
assert not oc.evaluate({'op':'multiset_eq','path':'/x','value':[1,1,2]},actual,{})
assert oc.evaluate({'op':'contains','path':'/x','value':[2]},actual,{})
assert not oc.evaluate({'op':'contains','path':'/x','value':[2,2]},actual,{})
assert not oc.evaluate({'op':'excludes','path':'/x','value':[2]},actual,{})
assert oc.evaluate({'op':'count','path':'/x','value':2},actual,{})
assert not oc.evaluate({'op':'eq','path':'/bool','value':1},actual,{})
assert oc.evaluate({'op':'eq','path':'/n','value':None},actual,{})
try:oc.evaluate({'op':'eq','path':'/missing','value':None},actual,{})
except oc.OracleError:pass
else:raise AssertionError('missing field falsely passed null')
assert oc.evaluate({'op':'same_as','path':'/same','checkpoint':'first'},actual,{'first':actual})

# Spot-check within-checkpoint incompatible gold predicates without manufacturing SUT output.
conflicts=[]
for c in cases:
 for s in c['steps']:
  by={}
  for ck in s['checks']:by.setdefault(ck['path'],[]).append(ck)
  for p,cks in by.items():
   exact=[ck for ck in cks if ck['op'] in ('eq','set_eq','multiset_eq')]
   for a in exact:
    for b in cks:
     if b['op']=='same_as':continue
     # Same expected scalar/collection must satisfy all gold checks on that field.
     try:
      op=b['op'];v=a['value'];want=b['value']
      ok=oc.canonical(v)==oc.canonical(want) if op=='eq' else len(v)==want if op=='count' else (oc.collection(v)==oc.collection(want) and len(v)==len(oc.collection(v))) if op=='set_eq' else oc.collection(v)==oc.collection(want) if op=='multiset_eq' else all(oc.collection(v)[z]>=n for z,n in oc.collection(want).items()) if op=='contains' else not (set(oc.collection(v))&set(oc.collection(want)))
      if not ok:conflicts.append((c['case_id'],s['id'],p))
     except Exception:conflicts.append((c['case_id'],s['id'],p))
assert not conflicts,conflicts[:20]

# Whole report failures for missing/duplicate/extra case or checkpoint.
c=next(c for c in cases if c['case_id']=='A01');empty={'schema_version':'v7-oracle-trace-1','case_id':'A01','checkpoints':[{'step_id':'ingest','actual':{}}]}
with tempfile.TemporaryDirectory() as td:
 p=pathlib.Path(td)/'t.jsonl'
 p.write_text(json.dumps(empty)+'\n')
 r=oc.compare(corpus,p,['A01']);assert r['status']=='FAIL' and r['failed_cases']==1
 p.write_text(json.dumps(empty)+'\n'+json.dumps(empty)+'\n');assert oc.compare(corpus,p,['A01'])['status']=='FAIL'
 p.write_text('');assert oc.compare(corpus,p,['A01'])['status']=='FAIL'
print(json.dumps({'artifact_checks':'OK','cases_checked_for_internal_gold_conflicts':len(cases),'project_tests_run':False,'verifier_negative_checks':15}))

from fractions import Fraction
import runpy,itertools
x=runpy.run_path(str(root/'tools/build_formalizer_v7_oracle.py'))
coords={Fraction(i,2) for i in range(-2,15)}
def realizations(w):
 if w is None or x['norm'](w)[0]=='U':return None
 if w['kind']=='POINT':return [frozenset([Fraction(w['t'])])]
 a,b=map(Fraction,w['bounds']);inside=frozenset(t for t in coords if a<=t<=b)
 return [inside] if w['semantics']=='CONTINUOUS' else [frozenset([t]) for t in inside]
checked=0
for a,b in itertools.product(x['W'],repeat=2):
 ra,rb=realizations(a),realizations(b)
 if ra is None or rb is None:continue
 assert x['simultaneous'](a,b)==all(bool(h1&h2) for h1,h2 in itertools.product(ra,rb)),(a,b,'sim')
 assert x['or_license'](a,b)==all(h1<=h2 for h1,h2 in itertools.product(ra,rb)),(a,b,'OR')
 assert x['forall_license'](a,b)[0]==all(bool(h1&h2) for h1,h2 in itertools.product(ra,rb)),(a,b,'FORALL')
 checked+=1
print(json.dumps({'independent_realization_pairs':checked,'status':'OK','project_tests_run':False}))
