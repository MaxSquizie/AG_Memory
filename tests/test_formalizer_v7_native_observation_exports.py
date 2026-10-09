"""Observed native exports and independent TEST_ONLY language data.

The scripted replies below are bounded syntax fixtures, not oracle expected
answers. Native T0–T6, canonical AH, ProviderAdapter and WAL remain real.
"""
import json
import pytest

from tools.formalizer_v7_extended_binding import Session
from tools.formalizer_v7_native_binding import ChatBackend, execute_native, fixture
from ah.formalizer.native_frontend import _temporal


def test_temporal_fixture_distinguishes_day_from_explicit_continuity(tmp_path):
    session=Session([],tmp_path/'temporal.log')
    release,_=fixture(session.core,'known')
    observation={'time_anchor':'2026-10-09T12:00:00+00:00'}
    generic,codes=_temporal('Иван работал вчера.',observation,release)
    continuous,other_codes=_temporal('Иван работал весь вчерашний день.',observation,release)
    assert not codes and not other_codes
    assert generic['kind']=='EXISTENTIAL'
    assert continuous['kind']=='CONTINUOUS'
    assert (generic['lo'],generic['hi'])==(continuous['lo'],continuous['hi'])
    release.assert_integrity();release.validate_store(session.core.store)


def test_declared_synonyms_and_optional_arguments_map_to_actual_templates(tmp_path):
    session=Session([],tmp_path/'templates.log')
    release,aliases=fixture(session.core,'known')
    onset=next(x for x in release.entries('TemplateMap') if x['sense_id']=='SLEEP_ONSET')
    assert onset['template_ref']=='fixture:T:SLEEP'
    assert aliases[onset['template_ref']][0]=='SLEEP'
    optional=[x for x in release.entries('TemplateMap')
              if x['sense_id']=='SIT_DOWN' and x['roles']==['SUBJECT']]
    assert len(optional)==1
    actual=session.core.store.get_template(optional[0]['template_ref'])
    assert [r.value for r in actual.roles]==['SUBJECT']
    assert aliases[actual.uid][0]=='SIT_STATE'
    release.validate_store(session.core.store)


def raw(text,source='native-export',kind='ASSERTION'):
    return {'raw_input':{'text':text,'source_id':source,'revision':1,'range':[0,len(text)],
                        'language':'ru','request_kind':kind,'batch_kind':'MESSAGE',
                        'source_timestamp':'2026-10-09T12:00:00+00:00'}}


def bounded_reply(monkeypatch,nodes,edges):
    def generate(self,prompt,**kwargs):
        data=json.loads(prompt)
        anchors={t['text']:t['id'] for t in data['tokens']}
        return json.dumps({'hypotheses':[{'local_id':'bounded-native-fixture',
            'nodes':[{'kind':kind,'anchor_spans':[anchors[text]]} for kind,text in nodes],
            'edges':edges,'alignment':list(anchors.values())}]},ensure_ascii=False)
    monkeypatch.setattr(ChatBackend,'generate',generate)


CONFIG={'provider':'lmstudio','base_url':'http://unused-test-endpoint','model':'bounded-native-fixture'}


def test_native_export_reads_selected_modes_decisions_and_real_time(monkeypatch,tmp_path):
    bounded_reply(monkeypatch,[('PREDICATE','работал'),('ENTITY','Иван')],
        [{'kind':'ARGUMENT','from':0,'to':1,'role_id':'SUBJECT'}])
    payload=raw('Иван работал весь вчерашний день.')
    session=Session([payload],tmp_path/'work.log')
    actual=execute_native(session,payload,CONFIG)
    assert actual['decision']['outcome']=='RESOLVED'
    assert actual['coverage']['status']=='FULL_CANONICAL'
    assert actual['generation']['event_frame_count']==1
    assert actual['generation']['frame_modes'][0]['mode']=='PROCESS'
    assert actual['time_assertions']['semantics']==['CONTINUOUS']
    assert not actual['time']['invented_past_intervals']
    assert actual['runtime']['provider_call_count']==1
    assert not actual['runtime']['coverage_evidence']['blocked_frame_ids']


def test_native_open_quote_exports_unasserted_entities_and_dictionary_lemma(monkeypatch,tmp_path):
    bounded_reply(monkeypatch,[('PREDICATE','сказал'),('ENTITY','Иван'),
        ('PREDICATE','переадресовал'),('ENTITY','Курьер'),('ENTITY','письмо')],
        [{'kind':'ARGUMENT','from':0,'to':1,'role_id':'SUBJECT'},
         {'kind':'ARGUMENT','from':0,'to':2,'role_id':'OBJECT'},
         {'kind':'ARGUMENT','from':2,'to':3,'role_id':'SUBJECT'},
         {'kind':'ARGUMENT','from':2,'to':4,'role_id':'OBJECT'}])
    payload=raw('Иван сказал: «Курьер переадресовал письмо».')
    session=Session([payload],tmp_path/'quote.log')
    actual=execute_native(session,payload,CONFIG)
    assert actual['coverage']['status']=='OPEN_LEXICAL'
    assert actual['structural']['entity_aliases']==['courier','letter']
    assert actual['structural']['formulas'][0]['predicate']=='OPEN:переадресовать'
    assert [f['predicate'] for f in actual['assertions']['ah']]==['SAY']
    assert actual['supports']['root_count']==1
    assert actual['aliases']==[]


def test_native_partial_coverage_uses_uncovered_spans_not_payload_gold(monkeypatch,tmp_path):
    def generate(self,prompt,**kwargs):
        data=json.loads(prompt);anchors={t['text']:t['id'] for t in data['tokens']}
        return json.dumps({'hypotheses':[{'local_id':'covered-prefix',
            'nodes':[{'kind':'PREDICATE','anchor_spans':[anchors['спит']]},
                     {'kind':'ENTITY','anchor_spans':[anchors['Мария']]}],
            'edges':[{'kind':'ARGUMENT','from':0,'to':1,'role_id':'SUBJECT'}],
            'alignment':[anchors['Мария'],anchors['спит']]}]})
    monkeypatch.setattr(ChatBackend,'generate',generate)
    payload=raw('Мария спит; Иван глоркнул как-то неизвестно.')
    payload['resolved_fragments']=[{'predicate':'DO_NOT_READ_PAYLOAD_EXPECTATION'}]
    session=Session([payload],tmp_path/'partial.log')
    actual=execute_native(session,payload,CONFIG)
    assert actual['coverage']['status']=='PARTIAL'
    assert actual['coverage']['unresolved_span_ids']
    assert [f['predicate'] for f in actual['assertions']['ah']]==['SLEEP']
    assert not actual['coverage']['opaque_full_claim']


@pytest.mark.parametrize('request_kind',['ASSERTION','QUERY'])
def test_verified_tp_candidate_pattern_survives_without_gold_or_factivity(monkeypatch,tmp_path,request_kind):
    bounded_reply(monkeypatch,[('PREDICATE','вошёл'),('ENTITY','Иван')],
        [{'kind':'ARGUMENT','from':0,'to':1,'role_id':'SUBJECT'}])
    payload=raw('Иван вошёл.','candidate-pattern:'+request_kind,request_kind)
    session=Session([payload],tmp_path/'candidate-pattern.log')
    actual=execute_native(session,payload,CONFIG)
    pattern={'predicate':'ENTER','roles':{'AGENT':{'entity':'ivan'}}}
    assert pattern in actual['generation']['gold_patterns']
    assert actual['generation']['observed_candidate_patterns']==actual['generation']['gold_patterns']
    assert actual['generation']['candidate_pattern_sources'][0]['pattern_ids']==['TP_VALIDATED']
    assert not actual['generation']['pattern_export_truncated']
    assert actual['assertions']['ah']==([pattern] if request_kind=='ASSERTION' else [])


def test_failed_tp_exports_observed_empty_quantifier_and_entity_sets(monkeypatch,tmp_path):
    def unavailable(self,prompt,**kwargs):raise RuntimeError('independent missing transport fixture')
    monkeypatch.setattr(ChatBackend,'generate',unavailable)
    payload=raw('Кто-то вошёл, а затем он сел.','empty-native-ir')
    session=Session([payload],tmp_path/'empty-native-ir.log')
    actual=execute_native(session,payload,CONFIG)
    assert 'PROVIDER_UNAVAILABLE' in actual['diagnostics']['codes']
    assert actual['assertions']['ah']==[]
    assert actual['runtime']['ir']['frames']==[]
    assert actual['store']['forall_instance_count']==0
    assert actual['store']['fictitious_entities']==[]
    assert actual['store']['created_entity_refs']==[]
    assert not actual['bindings']['discourse_variable']
    assert actual['bindings']['discourse_variable_uses']=={}
    assert actual['coverage']['status']=='NONE'


def test_write_projection_detects_unanchored_entity_from_actual_store(tmp_path):
    from ah.formalizer.graph_ops import ensure_entity
    from ah.formalizer.pipeline import t0
    from tools.formalizer_v7_native_binding import native_entity_refs,native_write_observations
    session=Session([],tmp_path/'unanchored.log')
    before=native_entity_refs(session)
    ensure_entity(session.core,{'uid':'unanchored:fixture','name':'unanchored test object'})
    writes,bindings=native_write_observations(session,t0('Иван вошёл.'),before)
    assert writes['fictitious_entities']==['unanchored:fixture']
    assert writes['created_entity_refs']==['unanchored:fixture']
    assert not bindings['discourse_variable']
