"""Two-boundary time: source coverage, uncertainty, commit and replay."""
from copy import deepcopy
from datetime import datetime
import pytest
from ah.core import AHCore
from ah.core.journal import JournalChannel
from ah.formalizer.ah_adapter import AHStoreAdapter
from ah.formalizer.canonical_ledger import digest, region
from ah.formalizer.clock_expressions import validate_evidence
from ah.formalizer.clock_ranges import resolve, validate_rule
from ah.formalizer.native_frontend import _temporal
from ah.formalizer.pipeline import MorphProvider
from ah.formalizer.run_binding import InterpretationRunBinding
from ah.formalizer.v7_pipeline import interpret_full
from tools.formalizer_component_fixture import with_components
from tools.formalizer_clock_fixture import range_rule
from tools.formalizer_v7_test_support import test_release
from test_formalizer_components import Choices, frontend

TEXT='С полудня пошел дождь до три часа тридцать минут.'


def release(core):
    return with_components(test_release(core),predication=True,relative_time=True,clock_time=True,clock_ranges=True)


def test_unknown_interval_keeps_discontinuous_boundaries_and_all_day_readings():
    value,ds=_temporal(TEXT,{},release(AHCore()),source_start=50)
    expr=value['expressions'][0]
    assert ds==['REFERENCE_UNKNOWN'] and value['lo'] is value['hi'] is None
    assert expr['realizations']==[[12,3,1],[12,15,0],[12,15,1]]
    for b in expr['boundaries']:
        lo,hi=b['source_range'];assert TEXT[lo-50:hi-50]==b['raw']
    validate_evidence(value['expressions'],region(value))


def test_intervening_predicate_and_subject_are_not_consumed_as_time():
    state=frontend(TEXT,MorphProvider(),Choices([0]*30),release(AHCore()))
    complete=[f for f in state.frames if not f.semantic['structural_unresolved']]
    assert complete
    assert any(f.anchor_span=='пошел' and 'дождь' in f.arguments for f in complete)
    assert all('часа' not in f.arguments for f in complete)


class Rules:
    sha256='test-resource'
    def __init__(self,rule): self.rule=rule
    def entries(self,key): return [self.rule] if key=='TemporalRules' else []


def test_unique_declared_day_and_hour_resolves_with_explicit_same_day_rule():
    rule=range_rule();rule['end_day_offsets']=[0]
    value,ds=resolve(TEXT,{'time_anchor':'2020-03-02T00:00:00+00:00'},Rules(rule))
    assert ds==[]
    assert value['lo']==datetime.fromisoformat('2020-03-02T12:00:00+00:00').timestamp()
    assert value['hi']==datetime.fromisoformat('2020-03-02T15:30:00+00:00').timestamp()
    validate_evidence(value['expressions'],region(value))
    unknown,ds=resolve(TEXT,{'time_anchor':'2020-03-02'},Rules(rule))
    assert ds==['REFERENCE_UNKNOWN'] and unknown['lo'] is None


def test_anchor_does_not_select_next_day_or_am_pm():
    value,ds=_temporal(TEXT,{'time_anchor':'2020-03-02T00:00:00+00:00'},release(AHCore()))
    assert ds==['REFERENCE_AMBIGUOUS'] and value['lo'] is None


@pytest.mark.parametrize('text',[
    'С полудня шёл дождь до двадцать пять часов.',
    'С полудня шёл дождь до три часа шестьдесят минут.',
    'С полудня шёл дождь до два три часа.',
])
def test_invalid_boundary_does_not_become_undated(text):
    assert _temporal(text,{},release(AHCore()))==(None,['TEMPORAL_EXPRESSION_INVALID'])


def test_competing_clock_outside_boundaries_needs_scope():
    value,ds=_temporal(TEXT+' В четыре часа ушли.',{},release(AHCore()))
    assert value is None and ds==['TEMPORAL_SCOPE_UNRESOLVED']


@pytest.mark.parametrize('mutation',[
    lambda e:e['boundaries'][0].update(raw='wrong'),
    lambda e:e['boundaries'][1].update(minute=99),
    lambda e:e.update(realizations=[[12,15,0]]),
    lambda e:e.update(end_day_offsets=[]),
])
def test_write_boundary_rejects_lost_or_corrupted_constraints(mutation):
    value,_=_temporal(TEXT,{},release(AHCore()))
    mutation(value['expressions'][0])
    with pytest.raises(ValueError): validate_evidence(value['expressions'],region(value))


def test_resource_contract_rejects_unbounded_days_or_missing_groups():
    for key,value in [('end_day_offsets',list(range(10))),('pattern','nothing'),
                      ('start_clock',{'kind':'FIXED','hour':25,'minute':0})]:
        rule=range_rule();rule[key]=value
        with pytest.raises(ValueError):validate_rule(rule)


def test_clock_range_has_no_language_defaults():
    rule={'kind':'CLOCK_RANGE','pattern':r'(?P<start>from noon).*?(?P<end>until tres horas)',
          'start_clock':{'kind':'FIXED','hour':12,'minute':0},
          'end_clock':{'kind':'WORD_CLOCK','pattern':r'until (?P<hour>tres) horas(?P<minute>)',
                       'number_values':{'tres':3},'clock_cycle':12},'end_day_offsets':[0]}
    validate_rule(rule)
    value,_=resolve('from noon rained until tres horas',{},Rules(rule))
    assert value['expressions'][0]['realizations']==[[12,15,0]]


def test_interval_commits_recovers_replays_and_retracts_through_actual_store(tmp_path):
    from ah.formalizer.real_backend import RealBackendSelector
    class Backend:
        model='scripted-range-contract'
        calls=0
        def generate(self,prompt,**kwargs):
            self.calls+=1
            return '1'
    core=AHCore();r=release(core);journal=JournalChannel(tmp_path/'j')
    store=AHStoreAdapter(core.store,journal,core);binding=InterpretationRunBinding(journal)
    backend=Backend();selector=RealBackendSelector(backend,journal=journal)
    kw=dict(release=r,morph=MorphProvider(),run_id='range',observation_id='O')
    state,report=interpret_full(TEXT,None,selector,store,binding,**kw)
    assert report.applied,(report,state.diagnostics)
    assert len(store.ledger.data['assertions'])==1
    assertion=next(iter(store.ledger.data['assertions'].values()))
    assert assertion['temporal_expressions'][0]['kind']=='CLOCK_RANGE'
    assert store.ledger.query(assertion['target_ref'],window=(0,1e10))['answer']=='UNKNOWN'
    calls=backend.calls;before=digest(store.ledger.data)
    _,again=interpret_full(TEXT,None,selector,store,binding,**kw)
    assert again.batch_hash==report.batch_hash and backend.calls==calls
    assert digest(store.ledger.data)==before
    core2=AHCore();restored=AHStoreAdapter(core2.store,journal,core2)
    assert digest(restored.ledger.data)==before
    store.retract_observation(state.source_uid,1,trigger_ref='retract-range')
    assert not store.ledger.paths()
    assert store.ledger.data['assertions'][assertion['assertion_id']]['status']=='RETRACTED'


def test_overlapping_temporal_rule_is_not_silently_shadowed():
    class ConflictingRules(Rules):
        def entries(self,key):
            return super().entries(key)+[{'kind':'DAY_INTERVAL','pattern':'полудня'}]
    assert resolve(TEXT,{},ConflictingRules(range_rule()))==(None,['TEMPORAL_SCOPE_UNRESOLVED'])


def test_consumption_is_per_occurrence_and_only_for_temporal_nominal_scopes():
    import re
    from ah.formalizer.clock_ranges import consumed_scope_spans, scope_consumed
    text=TEXT+' До завтрака ушёл.'
    spans=consumed_scope_spans(text,{},release(AHCore()))
    rule={'pattern':r'\bдо\b','operator':'BEFORE','attachment_kinds':['TEMPORAL_NOMINAL']}
    matches=list(re.finditer(rule['pattern'],text,re.I))
    assert len(matches)==2
    assert scope_consumed(rule,matches[0],spans)
    assert not scope_consumed(rule,matches[1],spans)
    assert not scope_consumed({**rule,'operator':'NOT'},matches[0],spans)
