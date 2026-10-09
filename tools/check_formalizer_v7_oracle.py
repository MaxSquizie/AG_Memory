#!/usr/bin/env python3
"""Strict oracle verifier / adapter driver. Contains no formalizer implementation.
Missing observations never satisfy an UNKNOWN/null/empty expected value.
"""
from __future__ import annotations
import argparse, collections, copy, hashlib, importlib, json, pathlib, sys, traceback

class OracleError(ValueError): pass

def canonical(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def readjson(path):return json.loads(path.read_text(encoding='utf-8'))
def strictkeys(obj,required,optional=()):
    if not isinstance(obj,dict):raise OracleError('expected object')
    missing=set(required)-obj.keys();extra=obj.keys()-set(required)-set(optional)
    if missing or extra:raise OracleError(f'fields missing={sorted(missing)} extra={sorted(extra)}')

def pointer(root,path):
    if not isinstance(path,str) or not path.startswith('/'):raise OracleError('invalid JSON Pointer')
    obj=root
    for raw in path[1:].split('/'):
        key=raw.replace('~1','/').replace('~0','~')
        if isinstance(obj,dict):
            if key not in obj:raise OracleError('missing observed path '+path)
            obj=obj[key]
        elif isinstance(obj,list):
            if not key.isdecimal():raise OracleError('invalid array path '+path)
            k=int(key)
            if k>=len(obj):raise OracleError('missing observed index '+path)
            obj=obj[k]
        else:raise OracleError('non-container path '+path)
    return obj

def collection(value):
    if not isinstance(value,list):raise OracleError('expected observed array')
    return collections.Counter(canonical(x) for x in value)

def evaluate(ck,actual,previous):
    value=pointer(actual,ck['path']);op=ck['op']
    if op=='same_as':
        other=previous.get(ck['checkpoint'])
        if other is None:raise OracleError('missing prior checkpoint '+ck['checkpoint'])
        expect=pointer(other,ck['path']);return canonical(value)==canonical(expect)
    expect=ck['value']
    if op=='eq':return canonical(value)==canonical(expect)
    if op=='count':
        if not isinstance(value,(list,dict,str)) or isinstance(expect,bool) or not isinstance(expect,int):raise OracleError('invalid count operands')
        return len(value)==expect
    got,want=collection(value),collection(expect)
    if op=='multiset_eq':return got==want
    if op=='set_eq':return all(n==1 for n in got.values()) and all(n==1 for n in want.values()) and got==want
    if op=='contains':return all(got[v]>=n for v,n in want.items())
    if op=='excludes':return not any(v in got for v in want)
    raise OracleError('unknown comparison '+op)

def load_corpus(root):
    manifest=readjson(root/'manifest.json')
    for filename,expected in manifest['artifacts'].items():
        p=root/filename
        if not p.is_file() or digest(p)!=expected:raise OracleError('artifact hash mismatch '+filename)
    cases=[]
    with (root/'cases.jsonl').open(encoding='utf-8') as f:
        for n,line in enumerate(f,1):
            if not line.strip():raise OracleError(f'blank case at line {n}')
            cases.append(json.loads(line))
    ids=[c['case_id'] for c in cases]
    if len(ids)!=len(set(ids)):raise OracleError('duplicate case ids')
    if len(cases)!=manifest['stats']['cases']:raise OracleError('case count mismatch')
    return manifest,cases

def validate(root):
    manifest,cases=load_corpus(root);mechanisms=readjson(root/'mechanisms.json');fixtures=readjson(root/'fixtures.json');coverage=readjson(root/'coverage.json')
    known=set(mechanisms);required=['schema_version','case_id','title','tier','mechanisms','norm_refs','acceptance_refs','dry_run_refs','fixture_profile','tags','description','initial_state','steps']
    for c in cases:
        strictkeys(c,required)
        if c['schema_version']!='v7-symbolic-oracle-1':raise OracleError('case schema version')
        if not c['mechanisms'] or set(c['mechanisms'])-known:raise OracleError('unknown/empty mechanisms '+c['case_id'])
        if len(c['mechanisms'])!=len(set(c['mechanisms'])):raise OracleError('duplicate mechanism '+c['case_id'])
        if c['fixture_profile'] not in fixtures['profiles']:raise OracleError('unknown fixture')
        if not isinstance(c['steps'],list) or not c['steps']:raise OracleError('empty steps')
        seen=set();checkcount=0
        for s in c['steps']:
            strictkeys(s,['id','action','payload','checks'])
            if s['id'] in seen:raise OracleError('duplicate step id')
            if not isinstance(s['payload'],dict):raise OracleError('payload not object')
            for ck in s['checks']:
                checkcount+=1
                if ck['op']=='same_as':
                    strictkeys(ck,['op','path','checkpoint'])
                    if ck['checkpoint'] not in seen:raise OracleError('forward/missing same_as')
                else:
                    strictkeys(ck,['op','path','value'])
                    if ck['op'] not in ['eq','set_eq','multiset_eq','contains','excludes','count']:raise OracleError('invalid check op')
                    if ck['op'] in ['set_eq','multiset_eq','contains','excludes'] and not isinstance(ck['value'],list):raise OracleError('nonarray collection gold')
                    if ck['op']=='set_eq' and any(v>1 for v in collection(ck['value']).values()):raise OracleError('duplicate gold set member')
                if not ck['path'].startswith('/'):raise OracleError('invalid pointer')
            seen.add(s['id'])
            raw=s['payload'].get('raw_input')
            if raw:
                if type(raw['revision']) is not int or raw['revision']<1:raise OracleError('invalid fixture revision')
                if raw['range']!=[0,len(raw['text'])]:raise OracleError('raw span mismatch '+c['case_id'])
        if checkcount==0:raise OracleError('case has no gold checks')
    for m in mechanisms:
        actual=sorted(c['case_id'] for c in cases if m in c['mechanisms'])
        if not actual or actual!=sorted(coverage['mechanisms'][m]) or actual!=sorted(mechanisms[m]['case_ids']):raise OracleError('mechanism coverage mismatch '+m)
    for field,ref in [('acceptance_refs','acceptance'),('dry_run_refs','dry_runs')]:
        for key,listed in coverage[ref].items():
            actual=sorted(c['case_id'] for c in cases if key in c[field])
            if not actual or actual!=listed:raise OracleError('A/DR coverage mismatch '+key)
    if set(coverage['acceptance'])!={f'A{i:02}' for i in range(1,40)} or set(coverage['dry_runs'])!={f'DR{i}' for i in range(1,32)}:raise OracleError('incomplete mandatory corpus')
    return {'status':'CORPUS_VALID','execution_status':'NOT_EXECUTED','stats':manifest['stats'],'document_sha256':manifest['source_document']['sha256']}

def compare(root,actual_path,case_filter=None):
    manifest,cases=load_corpus(root);selected=[c for c in cases if not case_filter or c['case_id'] in case_filter]
    if case_filter and {c['case_id'] for c in selected}!=set(case_filter):raise OracleError('unknown requested case')
    observed={};errors=[]
    for n,line in enumerate(actual_path.read_text(encoding='utf-8').splitlines(),1):
        try:
            record=json.loads(line);strictkeys(record,['schema_version','case_id','checkpoints'],['binding_manifest_ref','execution_status','blockers','runtime_error','binding_manifest'])
            if record['schema_version']!='v7-oracle-trace-1':raise OracleError('trace version')
            if record['case_id'] in observed:raise OracleError('duplicate actual case')
            observed[record['case_id']]=record
        except (ValueError,KeyError) as e:errors.append({'line':n,'error':str(e)})
    requested={c['case_id'] for c in selected}
    for extra in set(observed)-requested:errors.append({'case_id':extra,'error':'unexpected case'})
    results=[]
    for c in selected:
        ce=[];trace=observed.get(c['case_id'])
        if trace is None:ce.append({'error':'missing case'})
        elif trace.get('execution_status')=='BLOCKED':
            if not trace.get('blockers') or trace['checkpoints']:
                ce.append({'error':'invalid BLOCKED trace'})
            else:
                results.append({'case_id':c['case_id'],'status':'BLOCKED','blockers':trace['blockers'],'errors':[]})
                continue
        elif trace.get('execution_status')=='ERROR':
            ce.append({'error':'runtime error','detail':trace.get('runtime_error')})
        else:
            execution=trace.get('execution_status')
            if execution not in (None,'EXECUTED'):ce.append({'error':'unknown execution_status'})
            if execution=='EXECUTED':
                binding=trace.get('binding_manifest')
                if not isinstance(binding,dict) or not binding.get('api_refs'):
                    ce.append({'error':'missing concrete binding manifest'})
                elif hashlib.sha256(canonical(binding).encode()).hexdigest()!=trace.get('binding_manifest_ref'):
                    ce.append({'error':'binding manifest digest mismatch'})
            checkpoints={};stepids=[s['id'] for s in c['steps']]
            for cp in trace['checkpoints']:
                try:
                    strictkeys(cp,['step_id','actual'])
                    if not isinstance(cp['actual'],dict):raise OracleError('actual must be object')
                    if cp['step_id'] in checkpoints:raise OracleError('duplicate checkpoint')
                    checkpoints[cp['step_id']]=cp['actual']
                except (ValueError,KeyError) as e:ce.append({'error':str(e)})
            # Order matters for crashes, durable boundaries and same_as.
            if [cp.get('step_id') for cp in trace['checkpoints']]!=stepids:ce.append({'error':'missing/extra/out-of-order checkpoint'})
            previous={}
            for s in c['steps']:
                actual=checkpoints.get(s['id'])
                if actual is None:ce.append({'step':s['id'],'error':'missing checkpoint'});continue
                for ck in s['checks']:
                    try:
                        if not evaluate(ck,actual,previous):ce.append({'step':s['id'],'path':ck['path'],'op':ck['op'],'error':'gold mismatch'})
                    except (ValueError,KeyError,TypeError) as e:ce.append({'step':s['id'],'path':ck['path'],'error':str(e)})
                previous[s['id']]=actual
        results.append({'case_id':c['case_id'],'status':'FAIL' if ce else 'PASS','errors':ce})
    failing=sum(r['status']=='FAIL' for r in results)
    # This is comparison status, not G0–G5 verdict. Full concrete binding is checked by integration owner.
    blocked=sum(r['status']=='BLOCKED' for r in results)
    passed=sum(r['status']=='PASS' for r in results)
    bound=sum(t.get('execution_status')=='EXECUTED' for t in observed.values())
    status='FAIL' if failing or errors else 'BLOCKED' if blocked else 'PARTIAL' if case_filter else 'ORACLE_MATCH'
    return {'status':status,'gates_pass_claim':False,'binding_status':'RUNTIME_BINDINGS_RECORDED' if bound else 'UNVERIFIED_SYMBOLIC','document_sha256':manifest['source_document']['sha256'],'corpus_manifest_sha256':digest(root/'manifest.json'),'expected_cases':len(selected),'observed_cases':len(observed),'passed_cases':passed,'blocked_cases':blocked,'runtime_bound_cases':bound,'failed_cases':failing,'errors':errors,'results':results}

def run(root,adapter_spec,out_path,case_filter=None):
    _,cases=load_corpus(root);fixtures=readjson(root/'fixtures.json')
    module,name=adapter_spec.split(':',1);adapter=getattr(importlib.import_module(module),name)
    if case_filter:cases=[c for c in cases if c['case_id'] in case_filter]
    if not cases:raise OracleError('empty selected run')
    with out_path.open('w',encoding='utf-8') as out:
        for gold in cases:
            stimulus=copy.deepcopy(gold)
            for s in stimulus['steps']:del s['checks']
            try:
                result=adapter(stimulus,copy.deepcopy(fixtures))
            except Exception as exc:
                result={'schema_version':'v7-oracle-trace-1','case_id':gold['case_id'],'checkpoints':[],
                        'execution_status':'ERROR','runtime_error':{'type':type(exc).__name__,'message':str(exc),'traceback':traceback.format_exc()}}

            if not isinstance(result,dict):raise OracleError('adapter result not object')
            out.write(canonical(result)+'\n');out.flush()
    return {'status':'TRACES_WRITTEN','cases':len(cases),'out':str(out_path)}

def main():
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest='command',required=True)
    v=sub.add_parser('validate');v.add_argument('corpus',type=pathlib.Path)
    c=sub.add_parser('compare');c.add_argument('corpus',type=pathlib.Path);c.add_argument('actual',type=pathlib.Path);c.add_argument('--case',action='append');c.add_argument('--report',type=pathlib.Path)
    r=sub.add_parser('run');r.add_argument('corpus',type=pathlib.Path);r.add_argument('--adapter',required=True);r.add_argument('--out',required=True,type=pathlib.Path);r.add_argument('--case',action='append')
    args=p.parse_args()
    try:
        result=validate(args.corpus) if args.command=='validate' else compare(args.corpus,args.actual,args.case) if args.command=='compare' else run(args.corpus,args.adapter,args.out,args.case)
        if getattr(args,'report',None):args.report.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        # Large per-case errors are in the file, not hidden from an explicit --report consumer.
        compact={k:v for k,v in result.items() if k!='results'};print(json.dumps(compact,ensure_ascii=False))
        return 1 if result['status']=='FAIL' else 3 if result['status']=='BLOCKED' else 0
    except Exception as e:
        print(json.dumps({'status':'ERROR','error':str(e)},ensure_ascii=False),file=sys.stderr);return 2

if __name__=='__main__':sys.exit(main())
