"""Contracts of code-generated gaps; scripted choices do not measure a model."""
import json
from copy import deepcopy
import pytest
from ah.core import AHCore
from ah.core.journal import JournalChannel
from ah.formalizer.ah_adapter import AHStoreAdapter
from ah.formalizer.run_binding import InterpretationRunBinding
from ah.formalizer.v7_pipeline import interpret_full
from ah.formalizer.native_frontend import run_native
from ah.formalizer.pipeline import MorphProvider
from ah.formalizer.resources.loader import ResourceRelease, ResourceMissing
from tools.formalizer_v7_test_support import test_release, role
from tools.formalizer_component_fixture import with_components


class Choices:
    def __init__(self, choices=()): self.choices=iter(choices); self.prompts=[]
    def propose(self,prompt): raise AssertionError('model must not generate graphs')
    def select(self,prompt):
        self.prompts.append(prompt)
        section=prompt.split('closed set):\n',1)[1].split('\nTask:',1)[0]
        ids=[line.split('. ',1)[0] for line in section.splitlines() if '. ' in line]
        choice=next(self.choices,None)
        if choice is None: return json.dumps({'outcome':'INSUFFICIENT_CONTEXT','selected':[]})
        cid=next(i for i in ids if choice(i)) if callable(choice) else ids[choice]
        return json.dumps({'outcome':'ONE_SELECTED','selected':[cid]})


@pytest.fixture(scope='module')
def morph(): return MorphProvider()


def frontend(text,morph,selector=None,release=None):
    release=release or with_components(test_release(AHCore()))
    return run_native(text,selector or Choices(),release,{'observation_id':'doc','source_id':'source',
        'interpretation_version':1,'text':text,'structural_contract':'region_probes'},morph)


def test_gap_inventory_is_sealed_without_fabricated_tokens(morph):
    st=frontend('Принял Алека.',morph)
    assert len(st.frames)==1
    f=st.frames[0]; gap=f.semantic['implicit_arguments']['SUBJECT']
    assert gap['gap_id'] not in {e.token_id for e in st.evidence}
    assert f.semantic['proposed_roles']=={next(e.token_id for e in st.evidence if e.span=='Алека'):'OBJECT'}
    assert st.structural_closed and st.structural_hash
    assert st.observation['implicit_bindings']=={}
    assert len([o for o in gap['options'] if o['kind']=='ANONYMOUS'])==1
    assert all(o['candidate_id']!='narrative-centre' for o in gap['options'])


def test_real_commit_chain_group_and_recovery(tmp_path,morph):
    core=AHCore(); release=with_components(test_release(core))
    journal=JournalChannel(tmp_path/'journal.jsonl'); store=AHStoreAdapter(core.store,journal,core)
    binding=InterpretationRunBinding(journal)
    text='Принял Алека. Занимался. Отправились. Купались.'
    selector=Choices([0,lambda i:i.startswith('gap:'),0,lambda i:i.startswith('gap:')])
    st,receipt=interpret_full(text,None,selector,store,binding,release=release,morph=morph,
        raw_input={'source_id':'source','range':[0,len(text)]},run_id='components-run')
    assert receipt.applied and len(receipt.committed_fragments)==4,receipt
    values=list(st.observation['implicit_bindings'].values())
    assert len(values)==4
    assert values[0]['entity_ref']==values[1]['entity_ref']
    assert values[2]['entity_ref']==values[3]['entity_ref']
    assert values[0]['entity_ref']!=values[2]['entity_ref']
    for target in (values[0],values[2]):
        entity=store._store.get_element_any_domain(target['entity_ref'])
        assert 'name' not in entity.properties
        assert entity.meta['implicit_participant']['identity_status']=='UNIDENTIFIED'
    group=store._store.get_element_any_domain(values[2]['entity_ref'])
    assert group.meta['implicit_participant']['membership_status']=='UNKNOWN'
    assert 'members' not in group.meta['implicit_participant']
    assert len(store.ledger.paths())==4
    restored_core=AHCore()
    restored=AHStoreAdapter(restored_core.store,journal,restored_core)
    assert len(restored.ledger.paths())==4
    assert restored._store.get_element_any_domain(group.uid).meta==group.meta
    # All events were one source observation: retraction kills each binding
    # and support, not another source nor a guessed real-world identity.
    store.retract_observation(st.source_uid,1,trigger_ref="test-retract")
    assert not store.ledger.paths()


def test_singleton_group_still_requires_grounded_answer(morph):
    sel=Choices()
    st=frontend('Купались.',morph,sel)
    assert len(sel.prompts)==1
    assert st.observation['implicit_bindings']=={}


def test_context_has_both_people_not_first_compatible_winner(morph):
    # No named lexicon needed: grammatical OPEN roles only.
    st=frontend('Иван проводил Петра. Вернулся.',morph,Choices())
    gaps=[g for f in st.frames for g in f.semantic.get('implicit_arguments',{}).values()]
    assert gaps
    labels=' '.join(o['label'] for o in gaps[-1]['options'])
    assert 'Иван' in labels and 'Петра' in labels
    assert not st.observation['implicit_bindings']


@pytest.mark.parametrize('text',['После завтрака принял Алека.','Вечером занимался.'])
def test_uncovered_adjunct_is_retained_and_blocks_commit(morph,text):
    st=frontend(text,morph)
    assert st.frames
    assert all(f.semantic['structural_unresolved'] for f in st.frames)
    assert all(f.semantic['uncovered_token_refs'] for f in st.frames)
    assert not st.observation['implicit_bindings']


@pytest.mark.parametrize('text',['«Принял Алека.»','(Принял Алека.)','Принял ли Алека?'])
def test_scope_not_flattened(morph,text):
    st=frontend(text,morph)
    assert not st.frames


def test_known_missing_object_is_not_bypassed_by_open(morph):
    core=AHCore(); release=with_components(test_release(core,[('READ','читать','VERB',[role('SUBJECT'),role('OBJECT',('acc',))],'EVENT')]))
    st=frontend('Читал.',morph,release=release)
    assert st.frames
    assert all(f.semantic['structural_unresolved'] for f in st.frames)
    assert all(f.semantic['missing_required_roles']==['OBJECT'] for f in st.frames)
    assert all(any(q['kind']=='MISSING_REQUIRED_ROLE' and q['role']=='OBJECT'
                   for q in f.semantic['component_questions']) for f in st.frames)
    assert not st.observation['implicit_bindings']


def test_component_policy_is_opt_in(morph):
    st=frontend('Купались.',morph,release=test_release(AHCore()))
    assert not st.frames


def test_policy_rejects_unregistered_roles():
    manifest=deepcopy(with_components(test_release(AHCore())).manifest)
    next(r for r in manifest['entries'] if r['kind']=='ProposalPolicy')['entries'][0]['composition']['subject_role']='MADE_UP_ROLE'
    manifest.pop('coverage_report');manifest.pop('signed_review_id')
    with pytest.raises(ResourceMissing,match='invalid composition'):
        ResourceRelease(manifest,require_review=False)


def test_repeated_pronoun_spelling_has_distinct_source_ids(morph):
    st=frontend('Мария купалась. Она плавала. Анна гуляла. Она отдыхала.',morph)
    refs=st.reference_candidates
    assert len(refs)>=2
    assert len({r.mention_id for r in refs})==len(refs)
    assert all(r.mention_id.startswith('tok:') for r in refs)
    assert st.structural_closed


def test_implicit_context_receipts_replay_without_new_ticks(tmp_path,morph):
    from ah.ignition import IgnitionEngine
    from ah.config import IgnitionSettings, WorkspaceSettings
    core=AHCore()
    from tools.formalizer_v7_native_binding import fixture
    release,_=fixture(core,'known');release=with_components(release)
    journal=JournalChannel(tmp_path/'journal');store=AHStoreAdapter(core.store,journal,core)
    binding=InterpretationRunBinding(journal)
    ignition=IgnitionEngine(core,IgnitionSettings(),WorkspaceSettings(.02))
    text='Занимался. Купались.'
    from ah.formalizer.real_backend import RealBackendSelector
    class Backend:
        model='scripted-contract-fixture'
        calls=0
        def generate(self,prompt,**kwargs):
            self.calls+=1
            return '1'
    backend=Backend();selector=RealBackendSelector(backend,journal=journal)
    kwargs=dict(release=release,morph=morph,ignition=ignition,run_id='implicit-context',observation_id='O-implicit')
    st,report=interpret_full(text,None,selector,store,binding,**kwargs)
    assert report.applied,report
    requests=[r['request'] for r in st.context_reads]
    assert [r['kind'] for r in requests]==['IMPLICIT_ARGUMENT','IMPLICIT_ARGUMENT','READ_REMAINDER']
    assert [r['source_range'][1] for r in requests]==sorted(r['source_range'][1] for r in requests)
    tick=ignition.tick_index
    again,report2=interpret_full(text,None,selector,store,binding,**kwargs)
    assert report2.batch_hash==report.batch_hash
    assert ignition.tick_index==tick
    assert again.context_reads==st.context_reads
    assert backend.calls==2
