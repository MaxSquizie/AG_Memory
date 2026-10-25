"""Capture exact isolated provider inputs; never choose an answer in the harness.

Supply mailbox/<request hash>.reply as the actual executor's raw reply.
Matching is by complete system and prompt, so changed questions are new calls.
"""
import argparse,hashlib,json,time
from pathlib import Path
from tools.formalizer_v7_native_binding import ChatBackend,execute_native
from tools.formalizer_v7_extended_binding import Session

parser=argparse.ArgumentParser()
parser.add_argument('--mailbox',type=Path);parser.add_argument('text');parser.add_argument('--out',type=Path,required=True)
args=parser.parse_args();args.out.mkdir(parents=True,exist_ok=True)
mailbox=args.mailbox or args.out/'mailbox';mailbox.mkdir(exist_ok=True)
ordinal=0

def generate(self,prompt,*,system='',**kwargs):
    global ordinal
    ordinal+=1
    content={'system':str(system),'prompt':str(prompt)}
    key=hashlib.sha256(json.dumps(content,ensure_ascii=False,sort_keys=True).encode()).hexdigest()
    request={**content,'request_id':key,'ordinal':ordinal,'executor':'gpt-6-luna','reasoning_effort':'low'}
    (mailbox/(key+'.request.json')).write_text(json.dumps(request,ensure_ascii=False,indent=2))
    reply=mailbox/(key+'.reply')
    if not reply.exists():
        (args.out/'pending.json').write_text(json.dumps(request,ensure_ascii=False,indent=2))
        print(json.dumps({'waiting':key,'ordinal':ordinal}),flush=True)
        while not reply.exists():time.sleep(.1)
    raw=reply.read_text().strip()
    with (args.out/'calls.jsonl').open('a') as f:f.write(json.dumps({**request,'response':raw},ensure_ascii=False)+'\n')
    return raw

ChatBackend.generate=generate
payload={'raw_input':{'text':args.text,'source_id':'recovery-live','revision':1,'range':[0,len(args.text)],
    'language':'ru','request_kind':'ASSERTION','batch_kind':'MESSAGE','source_timestamp':'2026-10-26T12:00:00+03:00','timezone':'Europe/Moscow','probe_limits':{'max_elapsed_seconds':86400.0}}}
session=Session([payload],args.out/'journal.jsonl');session.observer_contract='v7-observer-1'
result=execute_native(session,payload,{'provider':'lmstudio','model':'isolated-gpt-6-luna-low',
    'structure_mode':'region_probes'})
(args.out/'result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
(args.out/'state.json').write_text(json.dumps(session.native_states[-1],ensure_ascii=False,indent=2))
(args.out/'report.json').write_text(json.dumps(session.native_reports[-1],ensure_ascii=False,indent=2))
(args.out/'pending.json').unlink(missing_ok=True)
print(json.dumps({'complete':True,'calls':ordinal,'diagnostics':result.get('diagnostics'),
    'assertions':result.get('assertions')},ensure_ascii=False),flush=True)
