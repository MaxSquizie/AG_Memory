"""Cardinal clocks preserve uncertainty, scope, durability and short probes."""
from copy import deepcopy
from datetime import datetime
import pytest

from ah.core import AHCore
from ah.core.journal import JournalChannel
from ah.formalizer.ah_adapter import AHStoreAdapter
from ah.formalizer.canonical_ledger import digest, region
from ah.formalizer.clock_expressions import cardinal, validate_evidence
from ah.formalizer.native_frontend import _temporal
from ah.formalizer.pipeline import MorphProvider
from ah.formalizer.run_binding import InterpretationRunBinding
from ah.formalizer.temporal_license import or_elimination_license, forall_inst_license, cont, undated
from ah.formalizer.v7_pipeline import interpret_full
from tools.formalizer_component_fixture import with_components
from tools.formalizer_v7_test_support import test_release
from test_formalizer_components import Choices


def release(core):
    return with_components(test_release(core), predication=True, clock_time=True)


@pytest.mark.parametrize('text,hours,minute',[
    ('В два часа сорок пять минут вышли.',[2,14],45),
    ('В один час одну минуту ушёл.',[1,13],1),
    ('В двадцать три часа пятьдесят девять минут вернулся.',[23],59),
    ('В 0 часов 00 минут пошли.',[0],0),
    ('В двенадцать часов встал.',[0,12],0),
])
def test_unknown_anchor_is_dated_symbolic_not_undated(text,hours,minute):
    r,ds=_temporal(text,{},release(AHCore()),source_start=100)
    assert ds==['REFERENCE_UNKNOWN'] and r['kind']=='EXISTENTIAL'
    e=r['expressions'][0]
    assert e['hour_candidates']==hours and e['minute']==minute
    assert e['source_range']==[100,100+len(e['raw'])]
    assert r['lo'] is r['hi'] is None
    assert or_elimination_license(region(r),cont(0,10000000000)).status=='UNKNOWN'
    assert forall_inst_license(region(r),undated()).status=='UNKNOWN'


@pytest.mark.parametrize('text',[
    'В двадцать пять часов ушли.', 'В два часа шестьдесят минут ушли.',
    'В два три часа ушли.', 'В двадцать двадцать часов ушли.',
])
def test_invalid_cardinal_is_not_silently_repaired(text):
    r,ds=_temporal(text,{},release(AHCore()))
    assert r is None and ds==['TEMPORAL_EXPRESSION_INVALID']


def test_absolute_clock_requires_unique_hour_and_declared_zone():
    r=release(AHCore())
    obs={'time_anchor':'2020-03-02T00:00:00+00:00'}
    value,ds=_temporal('В четырнадцать часов пятнадцать минут ушли.',obs,r)
    assert not ds and value['point']==datetime.fromisoformat('2020-03-02T14:15:00+00:00').timestamp()
    assert value['expressions'][0]['status']=='RESOLVED'
    ambiguous,ds=_temporal('В два часа ушли.',obs,r)
    assert ds==['REFERENCE_AMBIGUOUS'] and ambiguous['kind']=='EXISTENTIAL'
    unknown,ds=_temporal('В четырнадцать часов ушли.',{'time_anchor':'2020-03-02'},r)
    assert ds==['REFERENCE_UNKNOWN'] and unknown['expressions'][0]['status']=='SYMBOLIC'


def test_multiple_clocks_require_scope_and_duration_is_not_a_clock():
    r=release(AHCore())
    assert _temporal('В два часа и в три часа ушли.',{},r)==(None,['TEMPORAL_SCOPE_UNRESOLVED'])
    assert _temporal('Два часа шли.',{},r)==(None,[])


def test_word_vocabulary_is_data_not_parser_code():
    assert cardinal('veinte tres',{'veinte':20,'tres':3})==23
    with pytest.raises(ValueError): cardinal('tres veinte',{'veinte':20,'tres':3})


def test_symbolic_clock_and_direction_commit_restore_retract(tmp_path):
    c=AHCore();r=release(c);j=JournalChannel(tmp_path/'j');store=AHStoreAdapter(c.store,j,c)
    binding=InterpretationRunBinding(j)
    kw=dict(release=r,morph=MorphProvider(),run_id='clock',observation_id='O')
    text='В два часа сорок пять минут отправились вверх.'
    s,out=interpret_full(text,None,Choices([0]*20),store,binding,**kw)
    assert out.applied
    assert len(store.ledger.data['assertions'])==1
    a=next(iter(store.ledger.data['assertions'].values()))
    assert a['temporal_expressions'][0]['raw']=='В два часа сорок пять минут'
    assert a['temporal_expressions'][0]['hour_candidates']==[2,14]
    assert store.ledger.query(a['target_ref'],window=(0,10000000000))['answer']=='UNKNOWN'
    assert store.ledger.query(a['target_ref'])['answer']=='YES'
    assert len(store.ledger.data['usage_links'])==1  # direction preserves inner event
    _,again=interpret_full(text,None,Choices([0]*20),store,binding,**kw)
    assert again.batch_hash==out.batch_hash
    fresh=AHCore();restored=AHStoreAdapter(fresh.store,j,fresh)
    assert digest(restored.ledger.data)==digest(store.ledger.data)
    store.retract_observation(s.source_uid,1,trigger_ref='retract-clock')
    assert store.ledger.data['assertions'][a['assertion_id']]['status']=='RETRACTED'
    assert not store.ledger.paths()


def test_symbolic_expression_cannot_claim_numeric_region():
    raw,_=_temporal('В два часа ушли.',{},release(AHCore()))
    with pytest.raises(ValueError,match='SYMBOLIC_TIME_REQUIRES_UNKNOWN_REGION'):
        validate_evidence(raw['expressions'],region({'kind':'POINT','point':123}))
    broken=deepcopy(raw['expressions']);broken[0]['minute']=65
    with pytest.raises(ValueError): validate_evidence(broken,region(raw))
