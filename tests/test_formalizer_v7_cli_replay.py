"""The CLI replays a partial real HTTP run without expanding its selection."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
import json

from tools.run_formalizer_v7_oracle import main


def test_cli_partial_http_history_replays_without_transport(tmp_path):
    calls=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def do_POST(self):
            request=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            calls.append(self.path)
            prompt=request['messages'][-1]['content']
            if prompt.startswith('{'):
                tokens=json.loads(prompt)['tokens']
                anchors={t['text']:t['id'] for t in tokens}
                reply={'hypotheses':[{'local_id':'independent-enter-fixture',
                    'nodes':[{'kind':'PREDICATE','anchor_spans':[anchors['вошёл']]},
                             {'kind':'ENTITY','anchor_spans':[anchors['Иван']]}],
                    'edges':[{'kind':'ARGUMENT','from':0,'to':1,'role_id':'SUBJECT'}],
                    'alignment':list(anchors.values())}]}
            else:
                lines=prompt.split('closed set):\n',1)[1].split('\nTask:',1)[0].splitlines()
                reply={'outcome':'ONE_SELECTED','selected':[
                    line.split('. ',1)[0] for line in lines if '. ' in line and 'ENTER' in line][:1]}
            raw=json.dumps({'choices':[{'message':{'content':json.dumps(reply)}}]}).encode()
            self.send_response(200)
            self.send_header('Content-Type','application/json')
            self.send_header('Content-Length',str(len(raw)))
            self.end_headers();self.wfile.write(raw)
    live=tmp_path/'live';replay=tmp_path/'replay'
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        assert main(['--provider','lmstudio','--base-url',f'http://127.0.0.1:{server.server_port}',
                     '--model','independent-http-fixture','--timeout','5',
                     '--case','LANG-00-0-bare','--out',str(live)])==0
    finally:
        server.shutdown();server.server_close();thread.join(timeout=5)
    original_calls=len(calls)
    assert original_calls and set(calls)=={'/v1/chat/completions'}
    assert main(['--provider','replay','--replay-from',str(live),'--out',str(replay)])==0
    assert len(calls)==original_calls
    config=json.loads((replay/'run_config.json').read_text())
    comparison=json.loads((replay/'comparison.json').read_text())
    assert config['selected_case_ids']==['LANG-00-0-bare']
    assert comparison['expected_cases']==comparison['passed_cases']==1
    assert not comparison['failed_cases'] and not comparison['blocked_cases']
