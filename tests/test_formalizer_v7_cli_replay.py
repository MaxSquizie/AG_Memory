"""The CLI replays a partial real HTTP run without expanding its selection."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
import json
import pytest

from tools.run_formalizer_v7_oracle import main


@pytest.mark.parametrize('provider',['lmstudio','ollama'])
def test_cli_partial_http_history_replays_without_transport(tmp_path,provider):
    calls=[]
    from test_structural_relation_tasks import Script,relation
    from ah.formalizer.relation_composition import RELATIONS
    script=Script([('structural_relation',RELATIONS['LEXICAL'])])
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def do_POST(self):
            request=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            calls.append(self.path)
            if provider=='lmstudio':
                assert request['reasoning']=='off' and request['store'] is False
                prompt=request['input']
            else:
                assert request['think'] is False and request['stream'] is False
                prompt=request['messages'][-1]['content']
            assert 'Audit mapping' not in prompt and 'fixture:T:' not in prompt
            assert 'predicate value of frame' not in prompt
            reply=script.generate(prompt)
            response=({'output':[{'type':'message','content':reply}]}
                      if provider=='lmstudio' else
                      {'message':{'role':'assistant','content':reply},'done':True})
            raw=json.dumps(response).encode()
            self.send_response(200)
            self.send_header('Content-Type','application/json')
            self.send_header('Content-Length',str(len(raw)))
            self.end_headers();self.wfile.write(raw)
    live=tmp_path/'live';replay=tmp_path/'replay'
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        assert main(['--provider',provider,'--base-url',f'http://127.0.0.1:{server.server_port}',
                     '--model','independent-http-fixture','--timeout','5',
                     '--case','LANG-00-0-bare','--out',str(live)])==0
    finally:
        server.shutdown();server.server_close();thread.join(timeout=5)
    original_calls=len(calls)
    assert not script.errors and not script.steps
    assert original_calls and set(calls)=={'/api/v1/chat' if provider=='lmstudio' else '/api/chat'}
    provenance=json.loads((live/'provenance.json').read_text())
    assert provenance['model_live_execution'] is True
    assert main(['--provider','replay','--replay-from',str(live),'--out',str(replay)])==0
    assert len(calls)==original_calls
    config=json.loads((replay/'run_config.json').read_text())
    comparison=json.loads((replay/'comparison.json').read_text())
    assert config['selected_case_ids']==['LANG-00-0-bare']
    assert comparison['expected_cases']==comparison['passed_cases']==1
    assert not comparison['failed_cases'] and not comparison['blocked_cases']
