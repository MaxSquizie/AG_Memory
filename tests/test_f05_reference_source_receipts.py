"""Admitted source groups cannot silently disappear from a reference union."""
from types import SimpleNamespace as NS
from ah.formalizer.pipeline import t0
from ah.formalizer.nominal_group_source import domain
from ah.formalizer.nominal_reference_domain import snapshot,inspect


def setup(monkeypatch):
    state=t0('source');state.source_uid='s'
    frame=NS(frame_id='f',semantic={'nominal_groups':[{'member_refs':['a','b']}]})
    selected=NS(selected=('p',))
    spec={'roles':{'a':'SUBJECT','b':'SUBJECT'}}
    monkeypatch.setattr('ah.formalizer.nominal_reference_source.eligible_frames',lambda s:iter([(frame,selected,spec)]))
    def row(tid):
        return {'entity_ref':'M:'+tid,'memory_binding_ref':'binding:'+tid,'premise_support_refs':[],
            'label':tid,'local_nominal_anchor':{'frame_ref':'f','token_ref':tid,'mention_ref':tid}}
    entities=[row('a')]
    monkeypatch.setattr('ah.formalizer.nominal_reference_source.rows',lambda s,c:list(entities))
    monkeypatch.setattr('ah.formalizer.nominal_reference_local.rows',lambda s,c:[])
    monkeypatch.setattr('ah.formalizer.nominal_reference_chain.rows',lambda s,c:[])
    state.observation['nominal_reference_reads']={'q':{'rows':[],'search_incomplete':False}}
    constraint={'head_ref':'query','anchor_refs':[],'raw':'source','source_range':[0,6],'identity_constraint':'same referent'}
    return state,constraint,entities,row


def test_missing_member_is_open_then_grounded_source_changes_receipt(monkeypatch):
    state,c,entities,row=setup(monkeypatch)
    available,pending=domain(state,c,entities)
    assert not available and pending[0]['pending_member_refs']==['b']
    rows,incomplete,old=snapshot(state,c,'q')
    assert incomplete and len(rows)==1
    receipt=inspect(state,c,'q')[1]
    assert receipt['obligations'][0]['producer']=='LOCAL_GROUP'
    entities.append(row('b'))
    rows,incomplete,new=snapshot(state,c,'q')
    assert not incomplete and old!=new
    assert len(rows)==3 and rows[2]['reference_kind']=='GROUP'
    assert not inspect(state,c,'q')[1]['language_complete']


def test_self_containing_group_is_excluded_by_address_not_reported_missing(monkeypatch):
    state,c,entities,row=setup(monkeypatch)
    c['head_ref']='b'
    assert domain(state,c,entities)==([],[])
    assert not snapshot(state,c,'q')[1]


def test_memory_and_local_obligations_are_independent(monkeypatch):
    state,c,entities,row=setup(monkeypatch)
    state.observation['nominal_reference_reads']={}
    assert {r['producer'] for r in inspect(state,c,'q')[1]['obligations']}=={'LOCAL_GROUP','ACTIVE_MEMORY'}
    entities.append(row('b'))
    assert {r['producer'] for r in inspect(state,c,'q')[1]['obligations']}=={'ACTIVE_MEMORY'}


def test_incomplete_group_withdraws_old_success_without_prompt(monkeypatch):
    from ah.formalizer.nominal_reference_memory import resolve
    from ah.formalizer.state import Decision
    state,c,entities,row=setup(monkeypatch)
    monkeypatch.setattr('ah.formalizer.nominal_reference_memory.groups',lambda s:{'q':('mention',c)})
    state.observation['nominal_reference_reads']['q|referent']=state.observation['nominal_reference_reads'].pop('q')
    state.decisions['q|referent']=Decision('reference','q|referent',('old',),selected=('old',),outcome='RESOLVED')
    state.observation['nominal_reference_bindings']={'mention':{'interpretation_decision_ref':'q|referent'}}
    selector=NS(select=lambda p: (_ for _ in ()).throw(AssertionError('incomplete domain prompted')))
    resolve(state,None,selector)
    assert not state.observation['nominal_reference_bindings']
    assert state.decisions['q|referent'].outcome=='UNRESOLVED'
    assert any(d.code=='NOMINAL_REFERENCE_SEARCH_INCOMPLETE' for d in state.diagnostics)
    assert any(r.get('kind')=='NOMINAL_REFERENCE_SOURCE_RECEIPT' and r['obligations'] for r in state.syntax_trace)
