"""Oracle requests disable thinking at the actual HTTP boundary, without fallback."""
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Event, Thread
import json

import pytest

from ah.llm.lmstudio_client import LMStudioClientError
from ah.llm.ollama_client import OllamaClientError
from tools.formalizer_v7_native_binding import ChatBackend
from tools import formalizer_v7_native_binding as binding


@contextmanager
def local_server(reply, status=200, *, wait=None):
    requests=[]
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def do_POST(self):
            body=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            requests.append({'path':self.path,'body':body})
            if wait:wait.wait(timeout=5)
            raw=reply if isinstance(reply,bytes) else json.dumps(reply).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type','application/json')
            self.send_header('Content-Length',str(len(raw)))
            self.end_headers();self.wfile.write(raw)
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    try:yield f'http://127.0.0.1:{server.server_port}',requests
    finally:server.shutdown();server.server_close();thread.join(timeout=5)


def backend(base,provider='lmstudio'):
    return ChatBackend({'provider':provider,'base_url':base,'model':'local-model',
                        'timeout':5,'max_tokens':321})


@pytest.mark.parametrize('suffix',['','/v1'])
def test_native_request_explicit_off_stateless_preserves_prefix(suffix):
    response={'output':[{'type':'reasoning','content':'never protocol data'},
                        {'type':'message','content':'{"outcome":"NO_SELECTION"}'}]}
    with local_server(response) as (base,requests):
        actual=backend(base+'/proxy'+suffix).generate('payload',system='protocol',
            role='formalizer',override={'enable_thinking':True,'max_new_tokens':52})
    assert actual=='{"outcome":"NO_SELECTION"}'
    assert len(requests)==1 and requests[0]['path']=='/proxy/api/v1/chat'
    body=requests[0]['body']
    assert body['input']=='payload' and body['system_prompt']=='protocol'
    assert body['reasoning']=='off' and body['store'] is False and body['stream'] is False
    assert body['max_output_tokens']==52 and 'previous_response_id' not in body
    assert 'messages' not in body and 'top_k' not in body


def test_native_400_reasoning_rejection_has_no_compatibility_fallback():
    with local_server({'error':'reasoning option not supported'},400) as (base,requests):
        with pytest.raises(RuntimeError,match='HTTP 400'):
            backend(base).generate('payload')
    assert len(requests)==1 and requests[0]['path']=='/api/v1/chat'
    assert requests[0]['body']['reasoning']=='off'


@pytest.mark.parametrize('reply,exception,match',[
    ({'output':[{'type':'reasoning','content':'{"outcome":"ONE_SELECTED"}'}]},
     LMStudioClientError,'no message content'),
    ({'choices':[{'message':{'content':'wrong endpoint schema'}}]},
     LMStudioClientError,'missing output list'),
    (b'not JSON',RuntimeError,'INVALID_JSON'),
    (b'[]',RuntimeError,'NOT_OBJECT'),
])
def test_native_protocol_errors_fail_closed(reply,exception,match):
    with local_server(reply) as (base,requests):
        with pytest.raises(exception,match=match):backend(base).generate('payload')
    assert len(requests)==1


def test_openai_compatible_off_store_false_visible_content_only():
    reply={'choices':[{'message':{'reasoning_content':'hidden',
        'content':[{'type':'reasoning','text':'must not be consumed'},
                   {'type':'text','text':'{"answer":true}'}]}}]}
    with local_server(reply) as (base,requests):
        actual=backend(base+'/proxy/v1','openai').generate('payload',system='protocol')
    assert actual=='{"answer":true}'
    assert requests[0]['path']=='/proxy/v1/chat/completions'
    body=requests[0]['body']
    assert body['store'] is False and body['stream'] is False
    assert body['enable_thinking'] is False
    assert body['chat_template_kwargs']=={'enable_thinking':False}
    assert body['messages']==[{'role':'system','content':'protocol'},
                              {'role':'user','content':'payload'}]


def test_openai_hidden_reasoning_never_used_as_answer():
    reply={'choices':[{'message':{'content':'','reasoning_content':'{"answer":true}'}}]}
    with local_server(reply) as (base,requests):
        with pytest.raises(LMStudioClientError,match='empty assistant content'):
            backend(base,'openai').generate('payload')
    assert len(requests)==1


def test_progress_started_is_emitted_before_server_unblocks(monkeypatch):
    release=Event();started=Event();events=[];result=[]
    def emit(event,**fields):
        events.append((event,fields))
        if event=='request_started':started.set()
    monkeypatch.setattr(binding,'_provider_progress',emit)
    reply={'output':[{'type':'message','content':'{"answer":true}'}]}
    with local_server(reply,wait=release) as (base,requests):
        worker=Thread(target=lambda:result.append(backend(base).generate('payload',system='protocol')))
        worker.start()
        try:
            assert started.wait(timeout=2)
            assert events[0][0]=='request_started' and not result
            assert not any(name=='request_finished' for name,_ in events)
        finally:release.set();worker.join(timeout=5)
    assert result==['{"answer":true}']
    assert [name for name,_ in events]==['request_started','request_finished']
    first,last=events[0][1],events[1][1]
    assert first['request_id']==last['request_id']
    assert first['prompt']=='payload' and first['system']=='protocol'
    assert last['status']=='SUCCESS' and last['elapsed_seconds']>=0
    assert json.loads(last['raw_response'])==reply and last['response']==result[0]


def test_progress_error_is_emitted_on_http_failure(monkeypatch):
    events=[]
    monkeypatch.setattr(binding,'_provider_progress',lambda event,**fields:events.append((event,fields)))
    with local_server({'error':'native reasoning invalid'},400) as (base,requests):
        with pytest.raises(RuntimeError):backend(base).generate('payload')
    assert [event for event,_ in events]==['request_started','request_finished']
    final=events[-1][1]
    assert final['status']=='ERROR' and final['http_status']==400
    assert 'native reasoning invalid' in final['raw_response']
    assert 'HTTP 400' in final['error']


def test_https_uses_https_connection_and_prefix(monkeypatch):
    calls=[]
    class Response:
        status=200;reason='OK'
        def read(self):return b'{"output":[{"type":"message","content":"visible"}]}'
    class HTTPS:
        def __init__(self,host,port,timeout):calls.append(('connect',host,port,timeout))
        def request(self,method,path,body,headers):calls.append(('request',method,path))
        def getresponse(self):return Response()
        def close(self):calls.append(('close',))
    monkeypatch.setattr(binding.http.client,'HTTPSConnection',HTTPS)
    assert backend('https://local.example:9443/prefix/v1').generate('payload')=='visible'
    assert calls[0]==('connect','local.example',9443,5.0)
    assert calls[1]==('request','POST','/prefix/api/v1/chat')


def test_observability_failure_cannot_change_provider_result(monkeypatch):
    from tools import formalizer_v7_progress as progress
    def broken(*args,**kwargs):raise OSError('disconnected UI')
    monkeypatch.setattr(progress,'emit',broken)
    with local_server({'output':[{'type':'message','content':'visible'}]}) as (base,_):
        assert backend(base).generate('payload')=='visible'


@pytest.mark.parametrize('suffix',['','/v1'])
def test_ollama_native_think_false_visible_message_stateless(suffix):
    reply={'message':{'role':'assistant','content':'{"answer":true}',
                      'thinking':'not the protocol reply'},'done':True}
    with local_server(reply) as (base,requests):
        actual=backend(base+'/proxy'+suffix,'ollama').generate('payload',system='protocol',
            override={'enable_thinking':True,'max_new_tokens':73,'repetition_penalty':1.05})
    assert actual=='{"answer":true}'
    assert len(requests)==1 and requests[0]['path']=='/proxy/api/chat'
    body=requests[0]['body']
    assert body['think'] is False and body['stream'] is False
    assert body['messages']==[{'role':'system','content':'protocol'},
                              {'role':'user','content':'payload'}]
    assert body['options']=={'temperature':0,'top_p':1,'top_k':0,
                              'repeat_penalty':1.05,'num_predict':73}
    assert 'context' not in body and 'previous_response_id' not in body


@pytest.mark.parametrize('reply,match',[
    ({'message':{'content':'','thinking':'{"answer":true}'}},'no visible'),
    ({'message':{'content':123,'thinking':'hidden'}},'no visible'),
    ({'error':'unknown model'},'unknown model'),
    ({'response':'wrong generate response'},'missing message'),
    ({'message':{'content':'partial'},'done':False},'incomplete'),
])
def test_ollama_protocol_failures_never_fall_back(reply,match):
    with local_server(reply) as (base,requests):
        with pytest.raises(OllamaClientError,match=match):
            backend(base,'ollama').generate('payload')
    assert len(requests)==1 and requests[0]['path']=='/api/chat'


def test_ollama_http_failure_has_no_endpoint_retry():
    with local_server({'error':'think mode rejected'},400) as (base,requests):
        with pytest.raises(RuntimeError,match='HTTP 400'):
            backend(base,'ollama').generate('payload')
    assert len(requests)==1 and requests[0]['body']['think'] is False


def test_ollama_cli_requires_model_before_creating_output(tmp_path):
    from tools.run_formalizer_v7_oracle import main
    out=tmp_path/'missing-model'
    with pytest.raises(SystemExit) as failure:
        main(['--provider','ollama','--out',str(out)])
    assert failure.value.code==2 and not out.exists()
