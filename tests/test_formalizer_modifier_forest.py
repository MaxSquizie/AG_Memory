"""Whole-variant modifier forests and incomplete search boundaries."""
from copy import deepcopy
import pytest
from ah.core import AHCore
from ah.core.journal import JournalChannel
from ah.formalizer.ah_adapter import AHStoreAdapter
from ah.formalizer.run_binding import InterpretationRunBinding
from ah.formalizer.v7_pipeline import interpret_full
from ah.formalizer.pipeline import MorphProvider
from ah.formalizer.resources.loader import ResourceRelease, ResourceMissing
from tools.formalizer_component_fixture import with_components
from tools.formalizer_v7_test_support import test_release
from test_formalizer_components import Choices, frontend


def release(core):
    return with_components(test_release(core),predication=True,modifier_forest=True)


@pytest.mark.parametrize('text',['Гулял в садике.','Отдыхал в комнате.',
    'Работал об австрийском инженерном искусстве.','Очень быстро ушёл.'])
def test_complete_forest_still_requires_selection_and_preserves_every_token(text):
    selector=Choices();st=frontend(text,MorphProvider(),selector,release(AHCore()))
    assert any(d.slot_id=='component_attachment' and d.candidates for d in st.decisions.values())
    assert all(f.semantic['structural_unresolved'] for f in st.frames)
    assert not st.observation['implicit_bindings']
    assert len({f.frame_id for f in st.frames})==len(st.frames)


def test_two_adverbs_offer_both_orders():
    st=frontend('Очень быстро ушёл.',MorphProvider(),Choices(),release(AHCore()))
    choice=next(d for d in st.decisions.values() if d.slot_id=='component_attachment')
    roots=[f for f in st.frames if f.frame_id in choice.candidates]
    assert {f.anchor_span for f in roots}=={'Очень','быстро'}
    assert len(roots)==2


@pytest.mark.parametrize('order',[0,1])
def test_each_scope_order_commits_without_other_alternative_leaking(tmp_path,order):
    core=AHCore();r=release(core);journal=JournalChannel(tmp_path/'j')
    store=AHStoreAdapter(core.store,journal,core);binding=InterpretationRunBinding(journal)
    kw=dict(release=r,morph=MorphProvider(),run_id='two-modifiers',observation_id='O')
    from ah.formalizer.real_backend import RealBackendSelector
    class Backend:
        model='scripted-forest-contract'
        calls=0
        def generate(self,prompt,**kwargs):
            self.calls+=1
            return str(order+1) if self.calls==1 else '1'
    backend=Backend();selector=RealBackendSelector(backend,journal=journal)
    st,report=interpret_full('Очень быстро ушёл.',None,selector,store,binding,**kw)
    assert report.applied,(report,st.diagnostics)
    assert len(store.ledger.data['nodes'])==3
    assert len(store.ledger.f_visible())==1 and len(store.ledger.s_accessible())==3
    assert len(store.ledger.data['usage_links'])==2
    calls=backend.calls
    _,again=interpret_full('Очень быстро ушёл.',None,selector,store,binding,**kw)
    assert again.batch_hash==report.batch_hash
    assert backend.calls==calls


def test_linked_adjectives_and_head_survive_real_commit_recovery(tmp_path):
    core=AHCore();r=release(core);journal=JournalChannel(tmp_path/'j')
    store=AHStoreAdapter(core.store,journal,core);binding=InterpretationRunBinding(journal)
    st,report=interpret_full('Гулял в зелёном садике.',None,Choices([0]*20),store,binding,
        release=r,morph=MorphProvider(),run_id='forest')
    assert report.applied,(report,st.diagnostics)
    selected=[f for f in st.frames if not f.semantic['structural_unresolved']]
    assert len(selected)==2
    root=next(f for f in selected if f.anchor_span=='в')
    unit=next(iter(root.semantic['lexical_units'].values()))
    assert unit['surface']=='зелёном садике' and len(unit['anchor_refs'])==2
    assert set(unit['anchor_refs'])<=set(root.semantic['morph_bindings'])
    assert len(store.ledger.f_visible())==1 and len(store.ledger.s_accessible())==2
    rebuilt=AHCore();restored=AHStoreAdapter(rebuilt.store,journal,rebuilt)
    from ah.formalizer.canonical_ledger import digest
    assert digest(restored.ledger.data)==digest(store.ledger.data)
    store.retract_observation(st.source_uid,1,trigger_ref='retract')
    assert not store.ledger.f_visible() and not store.ledger.s_accessible()


@pytest.mark.parametrize('text',['Гулял в садике с товарищами.',
    'Прочитал сообщение об искусстве.'])
def test_missing_nominal_attachment_is_not_hidden_by_event_only_forest(text):
    st=frontend(text,MorphProvider(),Choices([0]*20),release(AHCore()))
    assert any(d.code=='COMPONENT_NOMINAL_ATTACHMENT_INCOMPLETE' for d in st.diagnostics)
    assert all(f.semantic['structural_unresolved'] for f in st.frames)


def test_scope_budget_keeps_no_successful_prefix():
    st=frontend('Очень быстро тихо спокойно ушёл.',MorphProvider(),Choices([0]*20),release(AHCore()))
    assert any(d.code=='COMPONENT_SEARCH_INCOMPLETE' for d in st.diagnostics)
    assert all(f.semantic['structural_unresolved'] for f in st.frames)


def test_nested_clause_modifier_needs_complete_cross_conjunct_scope():
    st=frontend('Очень быстро ушёл и вернулся.',MorphProvider(),Choices([0]*20),release(AHCore()))
    assert any(d.code=='COMPONENT_COORDINATION_SCOPE_INCOMPLETE' for d in st.diagnostics)
    assert all(f.semantic['structural_unresolved'] for f in st.frames)


def test_release_rejects_incomplete_constructor_contract():
    manifest=deepcopy(release(AHCore()).manifest)
    cfg=next(r for r in manifest['entries'] if r['kind']=='ProposalPolicy')['entries'][0]['composition']
    cfg.pop('preposition_nominal_role')
    manifest.pop('coverage_report');manifest.pop('signed_review_id')
    with pytest.raises(ResourceMissing,match='modifier composition roles'):
        ResourceRelease(manifest,require_review=False)
