"""Local/shared scope is a closed choice, not nearest-clause attachment."""
import json
from types import SimpleNamespace
import pytest
from ah.core import AHCore
from ah.core.journal import JournalChannel
from ah.formalizer.ah_adapter import AHStoreAdapter
from ah.formalizer.canonical_ledger import digest
from ah.formalizer.pipeline import MorphProvider
from ah.formalizer.run_binding import InterpretationRunBinding
from ah.formalizer.v7_pipeline import interpret_full
from tools.formalizer_component_fixture import with_components
from tools.formalizer_v7_test_support import test_release
from test_formalizer_components import Choices, AddressedChoices, frontend


class ScopeChoice(Choices):
    def __init__(self, mode='shared'):
        super().__init__([0]*40)
        self.mode = mode

    def select(self, prompt):
        if 'Decision slot: modifier_scope ' not in prompt or 'SHARED scope' not in prompt:
            return super().select(prompt)
        self.prompts.append(prompt)
        section=prompt.split('closed set):\n',1)[1].split('\nTask:',1)[0]
        ids=[line.split('. ',1)[0] for line in section.splitlines() if '. ' in line]
        if self.mode=='ambiguous':
            return json.dumps({'outcome':'MULTIPLE_ADMISSIBLE','selected':ids})
        if self.mode=='insufficient':
            return json.dumps({'outcome':'INSUFFICIENT_CONTEXT','selected':[]})
        lines=section.splitlines()
        chosen=next(line.split('. ',1)[0] for line in lines
                    if ('SHARED scope' in line) is (self.mode=='shared'))
        return json.dumps({'outcome':'ONE_SELECTED','selected':[chosen]})


@pytest.mark.parametrize('text',[
    'Завтракали и обедали на балконе.',
    'Отдыхали и работали на балконах.',
    'Читал и гулял долго.',
    'Долго читал и гулял.',
])
def test_shared_scope_commits_outer_only_and_restores(tmp_path,text):
    core=AHCore();release=with_components(test_release(core),predication=True)
    journal=JournalChannel(tmp_path/'j');store=AHStoreAdapter(core.store,journal,core)
    binding=InterpretationRunBinding(journal);sel=ScopeChoice()
    kw=dict(release=release,morph=MorphProvider(),run_id='scope',observation_id='O')
    st,result=interpret_full(text,None,sel,store,binding,**kw)
    assert result.applied,(result,st.diagnostics)
    assert len(result.committed_fragments)==1
    visible=store.ledger.f_visible()
    assert len(visible)==1
    nodes=store.ledger.data['nodes'];root=nodes[next(iter(visible))]
    assert root.get('template_ref') and not root.get('function_id')
    conjunction=next(n for n,v in nodes.items() if v.get('function_id')=='AND')
    assert conjunction not in visible and conjunction in store.ledger.s_accessible()
    assert len(nodes)==4 and len(store.ledger.data['supports'])==1
    assert any(l['parent_ref']==root['uid'] and l['node_ref']==conjunction and l['attitude']=='UNKNOWN'
               for l in store.ledger.data['usage_links'].values() if l['kind']=='ATTITUDE')
    trace=next(t for t in st.syntax_trace if t.get('kind')=='SCOPE_SLOT' and len(t['alternatives'])==2)
    assert {bool(o['base']) for o in trace['alternatives']}=={False,True}
    assert next(o for o in trace['alternatives'] if o['candidate_id']==trace['selected'])['base']==()
    _,again=interpret_full(text,None,sel,store,binding,**kw)
    assert again.batch_hash==result.batch_hash
    fresh=AHCore();restored=AHStoreAdapter(fresh.store,journal,fresh)
    assert digest(restored.ledger.data)==digest(store.ledger.data)
    store.retract_observation(st.source_uid,1,trigger_ref='retract-shared')
    assert not store.ledger.f_visible() and not store.ledger.s_accessible()


@pytest.mark.parametrize('mode',['ambiguous','insufficient'])
def test_unresolved_enclosing_scope_cannot_leak_local_facts(tmp_path,mode):
    core=AHCore();release=with_components(test_release(core),predication=True)
    journal=JournalChannel(tmp_path/'j');store=AHStoreAdapter(core.store,journal,core)
    selector=ScopeChoice(mode)
    st,result=interpret_full('Читал и гулял долго.',None,selector,store,InterpretationRunBinding(journal),
        release=release,morph=MorphProvider(),run_id='unresolved')
    assert not result.applied and not store.ledger.data['supports']
    assert all(f.semantic['structural_unresolved'] for f in st.frames)
    assert any('SHARED scope' in p and 'Decision slot: modifier_scope ' in p for p in selector.prompts)
    assert not st.observation['implicit_bindings']
    # Clarification options and the frozen generation snapshot are durable
    # data, not the temporary FrameCandidate objects of the scope constructor.
    json.dumps({'offers':st.clarification_candidates,'generation':st.generation_snapshot},ensure_ascii=False)


def test_two_modifiers_preserve_both_orders_and_partial_lifts():
    release=with_components(test_release(AHCore()),predication=True)
    st=frontend('Читал долго и гулял быстро.',MorphProvider(),ScopeChoice(),release)
    trace=next(t for t in st.syntax_trace if t.get('kind')=='SCOPE_DOMAIN' and len(t.get('values',{}))==2)
    # Both nesting directions coexist in local edge domains, without enumerating whole trees.
    domains=trace['values']
    for mid,values in domains.items():
        peer=next(other for other in domains if other!=mid)
        assert any(v['target']==peer and not v['base'] for v in values.values())
        assert any(v['target'] is None and v['base'] for v in values.values())
        assert any(v['target'] is None and not v['base'] for v in values.values())


def test_scope_budget_blocks_instead_of_selecting_local_default():
    release=with_components(test_release(AHCore()),predication=True)
    st=frontend('Читал долго и гулял быстро и отдыхал тихо и работал усердно.',
                MorphProvider(),ScopeChoice(),release)
    assert any(d.code=='COMPONENT_SEARCH_INCOMPLETE' for d in st.diagnostics)
    assert all(f.semantic['structural_unresolved'] for f in st.frames)


def test_scope_does_not_repair_an_unresolved_nominal_morphology():
    # The whole-phrase morphology probe must be answered before scope can close.
    release=with_components(test_release(AHCore()),predication=True)
    selector=AddressedChoices({'composition_boundary':['Outer AND:'],'nominal_attachment':[None,None]})
    st=frontend('Отдыхали и работали в комнате.',MorphProvider(),selector,release)
    selector.assert_complete()
    assert all(f.semantic['structural_unresolved'] for f in st.frames)


def test_nary_subgroup_scope_is_not_silently_missing_from_choices():
    release=with_components(test_release(AHCore()),predication=True)
    st=frontend('Плавал и гулял и отдыхал долго.',MorphProvider(),ScopeChoice(),release)
    trace=next(t for t in st.syntax_trace if t.get('kind')=='SCOPE_SLOT' and len(t['alternatives'])==5)
    groups=[o for o in trace['alternatives'] if any(kind=='group' for kind,_ in o['base'])]
    assert {tuple(o['base'][-1][1]) for o in groups}=={(0,2),(1,3)}
    assert not any(d.code=='COMPONENT_COORDINATION_SCOPE_INCOMPLETE' for d in st.diagnostics)


@pytest.mark.parametrize('shared',[False,True])
def test_durable_offer_replay_and_declared_scope_choice(tmp_path,shared):
    from ah.formalizer.clarifications import persist_offers, resolve
    core=AHCore();release=with_components(test_release(core),predication=True)
    journal=JournalChannel(tmp_path/'j');store=AHStoreAdapter(core.store,journal,core)
    binding=InterpretationRunBinding(journal);morph=MorphProvider();selector=ScopeChoice('ambiguous')
    st,result=interpret_full('Читал и гулял долго.',None,selector,store,binding,
        release=release,morph=morph,run_id='unresolved',observation_id='O')
    assert not result.applied
    offers=persist_offers(st,store,binding,release)
    assert offers and persist_offers(st,store,binding,release)==offers
    rows=[r['payload'] for r in journal.scan_unprocessed() if r['payload'].get('kind')=='CLARIFICATION_REQUEST']
    assert len(rows)==1
    request=rows[0];option=next(o for o in request['options'] if ('SHARED scope' in o['label']) is shared)
    key='v7:'+request['request_id']+':'+digest(option)
    adapter=SimpleNamespace(_store=store,_binding=binding,_release=release,_morph=morph,
                            _selector=Choices([0]*20),_ignition=None)
    clarified,committed=resolve(adapter,key)
    assert committed.applied,(committed,clarified.diagnostics)
    assert clarified.interpretation_version==2
    assert len(store.ledger.f_visible())==(1 if shared else 3)
    before=digest(store.ledger.data)
    _,again=resolve(adapter,key)
    assert again.batch_hash==committed.batch_hash and digest(store.ledger.data)==before
