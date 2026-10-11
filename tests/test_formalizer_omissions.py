"""Resource-licensed missing ENTITY slots, never known-to-open fallback."""
from copy import deepcopy
import pytest
from ah.core import AHCore
from ah.core.journal import JournalChannel
from ah.formalizer.ah_adapter import AHStoreAdapter
from ah.formalizer.run_binding import InterpretationRunBinding
from ah.formalizer.resources.loader import ResourceRelease, ResourceMissing
from ah.formalizer.v7_pipeline import interpret_full
from ah.formalizer.component_omissions import licenses_match
from tools.formalizer_v7_test_support import test_release, role
from tools.formalizer_component_fixture import with_components
from test_formalizer_components import Choices, frontend, morph


def release_for(core, lemma='читать', licensed=True):
    obj=role('OBJECT',('acc',))
    if licensed: obj['omission']={'kind':'UNSPECIFIED_ENTITY','rule_id':'fixture-omission'}
    return with_components(test_release(core,[('TEST_ACTION',lemma,'VERB',
        [role('SUBJECT'),obj],'EVENT')]),predication=True)


@pytest.mark.parametrize('text,lemma',[('Читал.','читать'),('Рисовал.','рисовать')])
def test_real_commit_preserves_required_role_without_invented_identity(tmp_path,morph,text,lemma):
    core=AHCore(); release=release_for(core,lemma)
    journal=JournalChannel(tmp_path/'journal')
    store=AHStoreAdapter(core.store,journal,core)
    binding=InterpretationRunBinding(journal)
    st,receipt=interpret_full(text,None,Choices([0]*10),store,binding,release=release,morph=morph,
        observation_id='omission',run_id='licensed-omission')
    assert receipt.applied,receipt
    frames=[f for f in st.frames if f.semantic.get('implicit_arguments')]
    assert len(frames)==1
    frame=frames[0]; gaps=frame.semantic['implicit_arguments']
    assert set(gaps)=={'SUBJECT','OBJECT'}
    assert gaps['SUBJECT']['features']['number']=='sing'
    assert gaps['OBJECT']['features']=={}
    target=st.observation['implicit_bindings'][gaps['OBJECT']['gap_id']]
    entity=store._store.get_element_any_domain(target['entity_ref'])
    assert 'name' not in entity.properties
    assert entity.meta['implicit_participant']['participant_kind']=='ENTITY'
    assert entity.meta['implicit_participant']['number_status']=='UNKNOWN'
    restored_core=AHCore(); restored=AHStoreAdapter(restored_core.store,journal,restored_core)
    assert restored._store.get_element_any_domain(entity.uid).meta==entity.meta
    assert len(restored.ledger.paths())==len(store.ledger.paths())>0
    store.retract_observation(st.source_uid,1,trigger_ref='test-retract')
    assert not store.ledger.paths()


def test_unanswered_gap_does_not_commit_or_become_optional(morph):
    st=frontend('Читал.',morph,Choices(),release_for(AHCore()))
    assert not st.observation['implicit_bindings']
    assert any('OBJECT' in f.semantic.get('implicit_arguments',{}) for f in st.frames)


def test_missing_license_still_blocks(morph):
    st=frontend('Читал.',morph,Choices([0]*10),release_for(AHCore(),licensed=False))
    assert all(f.semantic['missing_required_roles']==['OBJECT'] for f in st.frames)
    assert not st.observation['implicit_bindings']


def test_explicit_object_does_not_create_second_slot(morph):
    st=frontend('Читал книгу.',morph,Choices([0]*10),release_for(AHCore()))
    assert all('OBJECT' not in f.semantic.get('implicit_arguments',{}) for f in st.frames)


def test_license_cannot_cross_sense_or_construction(morph):
    release=release_for(AHCore())
    st=frontend('Читал.',morph,Choices(),release)
    frame=next(f for f in st.frames if 'OBJECT' in f.semantic.get('implicit_arguments',{}))
    val=release.entries('R-V')[0]
    assert licenses_match(frame,val)
    other=deepcopy(val);other['sense_id']='ANOTHER'
    assert not licenses_match(frame,other)
    other=deepcopy(val);other['roles'][1].pop('omission')
    assert not licenses_match(frame,other)


def test_t3_does_not_admit_other_known_sense_using_same_role(morph):
    core=AHCore(); obj=role('OBJECT',('acc',))
    permitted={**obj,'omission':{'kind':'UNSPECIFIED_ENTITY','rule_id':'fixture-license'}}
    release=with_components(test_release(core,[
        ('LICENSED','читать','VERB',[role('SUBJECT'),permitted],'EVENT'),
        ('UNLICENSED','читать','VERB',[role('SUBJECT'),obj],'EVENT')]))
    st=frontend('Читал.',morph,Choices([0]*10),release)
    frame=next(f for f in st.frames if 'OBJECT' in f.semantic.get('implicit_arguments',{}))
    assert {s['sense_id'] for s in frame.semantic['candidate_specs'].values()}=={'LICENSED'}


@pytest.mark.parametrize('change',[{'argument_types':['PROPOSITION']},
    {'cardinality':{'min':0,'max':1}}, {'cardinality':{'min':1,'max':2}}, {'optionality':True}])
def test_write_boundary_rejects_unsupported_license(change):
    manifest=deepcopy(release_for(AHCore()).manifest)
    val=next(r for r in manifest['entries'] if r['kind']=='R-V')['entries'][0]
    val['roles'][1].update(change)
    manifest.pop('signed_review_id');manifest.pop('coverage_report')
    with pytest.raises(ResourceMissing,match='omission license'):
        ResourceRelease(manifest,require_review=False)
