"""Exercise real HTTP, T0–T6, AH and WAL replay; no model-quality claims."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
import json
from tools.formalizer_v7_extended_binding import Session
from tools.formalizer_v7_native_binding import execute_native
from ah.core.journal import JournalChannel
from ah.formalizer.t3_sources import no_candidate_allowed, CandidateSourceTrace
import pytest


def test_native_http_and_offline_replay(tmp_path):
    requests=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def do_POST(self):
            body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            requests.append((self.path,body))
            prompt=body['messages'][-1]['content']
            if prompt.startswith('{'):
                data=json.loads(prompt)
                tokens=data['tokens']; anchors={t['text']:t['id'] for t in tokens}
                reply={'hypotheses':[{'local_id':'unary','nodes':[
                    {'kind':'PREDICATE','anchor_spans':[anchors['пришёл']]},
                    {'kind':'ENTITY','anchor_spans':[anchors['Иван']]}],
                    'edges':[{'kind':'ARGUMENT','from':0,'to':1,'role_id':'SUBJECT'}],
                    'alignment':[anchors['пришёл'],anchors['Иван']]}]}
            else:
                lines=prompt.split('closed set):\n',1)[1].split('\nTask:',1)[0].splitlines()
                ids=[line.split('. ',1)[0] for line in lines if '. ' in line and 'ARRIVE' in line]
                reply={'outcome':'ONE_SELECTED','selected':ids[:1],'note':'bounded fixture'}
            raw=json.dumps({'choices':[{'message':{'content':json.dumps(reply)}}]}).encode()
            self.send_response(200); self.send_header('Content-Type','application/json')
            self.send_header('Content-Length',str(len(raw))); self.end_headers();self.wfile.write(raw)
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    config={'provider':'lmstudio','base_url':f'http://127.0.0.1:{server.server_port}',
            'model':'http-fixture','timeout':5,'max_tokens':1024}
    payload={'raw_input':{'text':'Иван пришёл.','source_id':'http-case','revision':1,
             'range':[0,12],'language':'ru','request_kind':'ASSERTION','batch_kind':'MESSAGE'}}
    live=Session([payload],tmp_path/'live.log')
    try: actual=execute_native(live,payload,config)
    finally:server.shutdown();server.server_close();thread.join(timeout=5)
    assert requests and all(path=='/v1/chat/completions' for path,_ in requests)
    assert actual['assertions']['ah']==[{'predicate':'ARRIVE','roles':{'AGENT':{'entity':'ivan'}}}],actual
    assert actual['store']['marker_count']==1
    replay=Session([payload],tmp_path/'replay.log')
    for record in live.store._journal.scan_unprocessed(0):
        if record['payload'].get('kind') in {'prov_call','RUN_STARTED'}:
            replay.store._journal.append(record['channel'],record['payload'],run_id=record.get('run_id',''))
    replayed=execute_native(replay,payload,{**config,'provider':'replay'})
    assert replayed['assertions']==actual['assertions']
    assert replayed['runtime']['report']==actual['runtime']['report']
    assert len(requests)==len([r for r in live.store._journal.scan_unprocessed(0)
        if r['payload'].get('kind')=='prov_call' and r['payload'].get('state')=='RECEIVED'])


def test_empty_source_trace_cannot_be_exhaustion():
    with pytest.raises(ValueError):no_candidate_allowed([])
    with pytest.raises(ValueError):CandidateSourceTrace('F','slot',1,'CHECKED_EMPTY',('invented',))


def test_extended_audit_recovery_keeps_both_support_events(tmp_path):
    s=Session([],tmp_path/'audit.log')
    created=s.action('commit_two_state_supports',{'node':'N','support_ids':['s_a','s_b'],'tx_ref':'H_B1'})
    assert created['events']['N']['types']==['CREATED','SUPPORT_ADDED','SUPPORT_ADDED']
    s.action('retract_support_batch',{'support_ids':['s_b','s_a'],'tx_ref':'R_B2'})
    final=s.action('recover',{})
    assert final['events']['N']['count']==6
    assert final['service']['factual_reads_enabled']
    assert not final['audit']['mutated']


def test_count_uses_real_domain_evidence_without_extra_student(tmp_path):
    s=Session([],tmp_path/'count.log')
    result=s.action('count_query',{'body':{'predicate':'STUDENT','roles':{'THEME':{'bound_var':'x'}}},
        'count_variable':'x','certificate':'VALID','window':None,'witness_entities':['e0']})
    assert result['answer']['exact_count']==1
    assert result['answer']['domain_complete']
    assert result['store']['fictitious_entity_count']==0


def test_failed_registry_write_rolls_back_open_template(tmp_path):
    s=Session([],tmp_path/'rollback.log')
    result=s.action('invalid_write_transaction',{'fault':'unknown_g','create_open_t_first':True})
    assert result['diagnostics']['codes']
    assert result['store']['canonical_unchanged']
    assert result['store']['new_template_count']==0


def test_binding_refuses_gold_checks(tmp_path):
    from tools.formalizer_v7_extended_binding import run_case
    with pytest.raises(ValueError,match='GOLD_CHECKS_MUST_BE_REMOVED'):
        run_case({'case_id':'bad','steps':[{'action':'query','checks':[],'payload':{}}]}, {})


@pytest.mark.parametrize('feature',['gender','number','person'])
def test_agreement_fixture_preserves_distinct_known_values(tmp_path,feature):
    s=Session([],tmp_path/'agreement.log')
    result=s.action('morph_agreement',{'feature':feature,'left':'known_a','right':'known_b'})
    assert result['constraint']['result'] is False
    result=s.action('morph_agreement',{'feature':feature,'left':'UNKNOWN','right':'KNOWN'})
    assert result['constraint']['result']=='UNKNOWN'
