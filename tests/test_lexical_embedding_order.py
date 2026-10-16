"""Ranking evidence preserves the lexical domain and never reopens structure."""
from types import SimpleNamespace
import pytest
from ah.formalizer.lexical_embedding import LexicalEmbeddingRanker,order
from ah.formalizer.provider_adapter import IntegrityError
from rag.embeddings import FakeEmbeddingClient


def fixture(tmp_path):
    from tools.formalizer_v7_test_support import native_fixture
    store,binding,release=native_fixture(tmp_path/'journal')
    client=FakeEmbeddingClient({'entry a':[0,1],'entry b':[1,0]})
    # Supply a literal query vector; hash embeddings are never quality evidence.
    query='Meaning of predicate «word» in this selected clause: source'
    client.table[query.casefold()]=[1,0]
    ranker=LexicalEmbeddingRanker(client,'test-model')
    selector=SimpleNamespace(run_id='run',journal=store._journal,lexical_ranker=ranker)
    state=SimpleNamespace(structural_closed=True,syntax_trace=[])
    options=[{'candidate_id':k,'label':'display '+k} for k in ('a','b','open')]
    specs={k:{'sense_kind':'KNOWN' if k!='open' else 'OPEN_LEXICAL','label':'entry '+k,'sense_id':k} for k in ('a','b','open')}
    frame=SimpleNamespace(frame_id='f',anchor_span='word',semantic={'candidate_specs':specs})
    return state,selector,release,frame,options,client


def test_rank_is_not_a_decision_and_keeps_original_options_and_open(tmp_path):
    state,selector,release,frame,options,client=fixture(tmp_path)
    ranked=order(state,selector,release,frame,options,'source')
    assert ranked==[options[1],options[0],options[2]]
    row=state.syntax_trace[-1]
    assert row['margin']==1 and row['probe_required'] and not row['automatic_selection']
    assert not any('open' in text for batch in client.calls for text in batch)
    assert frame.semantic['candidate_specs']['a']['sense_kind']=='KNOWN'


def test_replay_uses_recorded_scores_without_server_or_warm_cache(tmp_path):
    state,selector,release,frame,options,client=fixture(tmp_path)
    first=order(state,selector,release,frame,options,'source')
    class Offline:
        def embed(self,texts):raise AssertionError('network on replay')
    selector.lexical_ranker=LexicalEmbeddingRanker(Offline(),'test-model')
    assert order(state,selector,release,frame,options,'source')==first
    with pytest.raises(IntegrityError,match='REPLAY_MISMATCH'):
        order(state,selector,release,frame,options,'changed source')


@pytest.mark.parametrize('bad',[[],[0,0],[float('nan'),1],[True,1]])
def test_bad_embedding_cannot_remove_a_candidate_or_select_a_sense(tmp_path,bad):
    state,selector,release,frame,options,client=fixture(tmp_path)
    client.embed=lambda texts:[bad for _ in texts]
    assert order(state,selector,release,frame,options,'source')==options
    assert state.syntax_trace[-1]['status']=='UNAVAILABLE'
    assert state.syntax_trace[-1]['probe_required']


def test_dictionary_vectors_are_cached_and_cache_is_bounded():
    client=FakeEmbeddingClient({'entry a':[1,0],'entry b':[0,1],'query 1':[1,0],'query 2':[0,1]})
    ranker=LexicalEmbeddingRanker(client,'test',cache_size=3)
    ranker.vectors(['query 1','entry a','entry b'])
    ranker.vectors(['query 2','entry a','entry b'])
    assert client.calls==[('query 1','entry a','entry b'),('query 2',)]
    assert len(ranker.cache)==3


def test_embedding_ranker_cannot_run_before_structural_seal(tmp_path):
    state,selector,release,frame,options,client=fixture(tmp_path)
    state.structural_closed=False
    with pytest.raises(ValueError,match='before structural seal'):
        order(state,selector,release,frame,options,'source')
    assert not client.calls


def test_oracle_configuration_skips_useless_ranking_of_one_sense(tmp_path,monkeypatch):
    from tools.formalizer_v7_extended_binding import Session
    from tools import formalizer_v7_native_binding as binding
    from test_structural_relation_tasks import Script,relation
    text='Иван читает книгу.'
    item={'raw_input':{'text':text,'source_id':'embedding-test','revision':1,'range':[0,len(text)],
        'language':'ru','request_kind':'ASSERTION','batch_kind':'MESSAGE'}}
    session=Session([item],tmp_path/'journal')
    script=Script(relation('LEXICAL'));calls=[]
    monkeypatch.setattr(binding.ChatBackend,'generate',lambda self,prompt,**kw:script.generate(prompt,**kw))
    def embed(self,texts):calls.append(tuple(texts));return [[1,0] for _ in texts]
    monkeypatch.setattr(binding.OracleEmbeddingClient,'embed',embed)
    result=binding.execute_native(session,item,{'provider':'lmstudio','model':'chat','base_url':'http://localhost',
        'embedding_model':'embed','structure_mode':'region_probes'})
    assert not script.errors and not script.steps
    assert result['assertions']['ah'][0]['predicate']=='READ'
    rows=[r for r in result['runtime']['ir']['syntax_trace'] if r.get('kind')=='LEXICAL_EMBEDDING_RANKING']
    assert len(rows)==1 and rows[0]['status']=='SKIPPED' and rows[0]['probe_required']
    assert not calls and any(s=='predicate_value' for s,p in script.calls)


def test_gui_passes_explicit_embedding_model(tmp_path):
    from ah.gui.oracle_semantic_runner import build_oracle_command
    args=build_oracle_command(tmp_path,'http://localhost','chat',tmp_path/'out',embedding_model='embedding')
    assert args[args.index('--embedding-model')+1]=='embedding'
