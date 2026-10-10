"""Text regions, dissipative attention, durable pre-seal reads on real AH."""
from copy import deepcopy
from dataclasses import replace
from types import SimpleNamespace

import pytest

from ah.config import IgnitionSettings, WorkspaceSettings, PlasticitySettings
from ah.core import AHCore, SequentialUidGenerator
from ah.ignition import IgnitionEngine
from ah.ignition.clock import IgnitionClock
from ah.model import Domain
from ah.formalizer.regions import build_regions
from ah.formalizer.attention_context import AttentionContextReader, freeze_attention_base, ContextReadError
from ah.formalizer.pipeline import t0
from ah.formalizer.v7_pipeline import interpret_full
from tools.formalizer_v7_test_support import native_fixture, FixtureMorph, NativeSelector


def engine(core, **kw):
    return IgnitionEngine(core, IgnitionSettings(plasticity=PlasticitySettings(enabled=False), **kw),
                          WorkspaceSettings(.02))


def mass(e):
    return sum(s.excitation for _,s in e.core.store.runtime_items())+sum(e._incoming.values())


def test_fanout_cycles_have_finite_pool_and_die_without_input():
    core=AHCore(uid_generator=SequentialUidGenerator())
    refs=[core.ref(core.add_entity(Domain.C).uid) for _ in range(20)]
    for ref in refs[1:]:
        core.add_link('ASSOC',refs[0],ref,1)
        core.add_link('ASSOC',ref,refs[0],1)
    e=engine(core,event_input_budget=2)
    e.seed(refs[0],1000)
    e.tick()
    assert mass(e)<=e.settings.event_retention*2+1e-10
    for _ in range(200):
        before=mass(e);e.tick()
        assert mass(e)<=before*e.settings.event_retention+1e-10
    assert not e.workspace_refs()
    assert all(core.store.has_uid(ref.uid) for ref in refs)  # cooling isn't retraction/GC


def test_no_top_k_under_threshold_workspace_rule():
    core=AHCore(uid_generator=SequentialUidGenerator())
    refs=[core.ref(core.add_entity(Domain.C).uid) for _ in range(70)]
    e=engine(core,event_input_budget=20)
    for r in refs:e.seed(r,.1)
    e.tick()
    assert len(e.workspace_refs())==70


def test_structural_routes_transfer_attention_without_asserting_content():
    from ah.model import ActantRole
    core=AHCore(); e=engine(core)
    m=core.ref(core.add_entity(Domain.C).uid)
    s=core.add_abstract_symbol({'predicate'})
    t=core.add_template(Domain.C,core.ref(s.uid),(ActantRole.SUBJECT,))
    n,_=core.add_hypernode(Domain.C,core.ref(t.uid),{ActantRole.SUBJECT:m},1)
    g=core.add_function(Domain.C,'NOT',(core.ref(n.uid),))
    e.seed(core.ref(g.uid),0)  # a zero seed must not divide by zero
    e.tick()
    e.seed(core.ref(g.uid),1)
    for _ in range(3):e.tick()
    assert core.store.runtime_state(m.uid).excitation>0
    assert core.store._state.formalizer_state=={}  # attention creates no proof records


def test_event_mode_does_not_start_wall_clock_or_refresh_epoch():
    core=AHCore(); e=engine(core)
    clock=IgnitionClock(e,.001)
    clock.start()
    assert not clock.running
    before=e.export_snapshot()
    e.begin_prompt_epoch()
    assert e.export_snapshot()==before


def test_regions_keep_all_tokens_and_cross_boundary_candidates():
    state=t0('Он сказал: «Она пришла. Я ждал»; потом ушёл.\n\nНовая сцена.')
    forest=build_regions(state.text,state.evidence,'doc')
    leaves=[r for r in forest.regions if r.kind=='TOKEN']
    assert [tid for r in leaves for tid in r.token_refs]==[e.token_id for e in state.evidence]
    assert all(r.boundary_status=='PROVISIONAL' for r in forest.regions
               if r.kind not in {'DOCUMENT','TOKEN'})
    frames=[SimpleNamespace(frame_id=f'F{i}',source_range=(0,len(state.text)),
                            predicate_token_ref=state.evidence[0].token_id,
                            argument_token_refs=(),semantic={'hypothesis':str(i)}) for i in (1,2)]
    forest.attach_frames(frames)
    assert len(forest.candidates)==2
    assert {c['region_ref'] for c in forest.candidates}=={forest.regions[0].region_id}
    assert next(d for d in forest.dependencies if d['kind']=='SHARED_ANCHOR')['candidate_refs']==['F1','F2']
    assert forest.to_dict()==build_and_attach(state,frames)


def build_and_attach(state,frames):
    f=build_regions(state.text,state.evidence,'doc');f.attach_frames(frames);return f.to_dict()


def read_request(state):
    return {'kind':'READ_REMAINDER','decision_ref':'end','source_range':(0,len(state.text)),
            'region_ref':'root','cue_token_refs':[e.token_id for e in state.evidence]}


def test_receipt_replay_repairs_focus_projection_without_double_ticks(tmp_path, monkeypatch):
    store,binding,release=native_fixture(tmp_path/'journal')
    e=engine(store._core)
    base=freeze_attention_base(store,e)
    state=t0('А Б В.'); state.observation={}
    reader=AttentionContextReader(store,release,e,'read-1',base)
    monkeypatch.setattr(reader,'_publish',lambda result:None)  # crash window after receipt
    result=reader.read(state,read_request(state))
    assert e.tick_index==0
    for _ in range(2):
        replay=AttentionContextReader(store,release,e,'read-1',base)
        fresh=t0(state.text);fresh.observation={}
        assert replay.read(fresh,read_request(fresh))==result
        assert e.tick_index==len(state.evidence)
    receipts=[r for r in store._journal.scan_unprocessed() if r['payload'].get('kind')=='CONTEXT_READ']
    assert len(receipts)==1


def test_unrecorded_read_rejects_changed_canonical_graph(tmp_path):
    store,binding,release=native_fixture(tmp_path/'journal')
    e=engine(store._core);base=freeze_attention_base(store,e)
    reader=AttentionContextReader(store,release,e,'read-2',base)
    store._core.add_entity(Domain.C)
    state=t0('А.');state.observation={}
    with pytest.raises(ContextReadError,match='CONTEXT_SNAPSHOT_STALE'):
        reader.read(state,read_request(state))
    assert e.tick_index==0


def test_region_pipeline_commits_and_replays_without_model_graphs(tmp_path):
    store,binding,release=native_fixture(tmp_path/'journal')
    e=engine(store._core)
    class ClosedSelector(NativeSelector):
        def propose(self,prompt):raise AssertionError('Graph proposal forbidden')
        def propose_local(self,*args):raise AssertionError('Graph proposal forbidden')
    kwargs=dict(morph=FixtureMorph(),release=release,observation_id='O1',run_id='R1',
                ignition=e,structure_mode='region_probes')
    state,report=interpret_full('У Ивана есть книга.',None,ClosedSelector(),store,binding,**kwargs)
    assert report.applied
    assert state.region_forest.candidates
    assert state.context_reads
    before=e.tick_index
    replay,again=interpret_full(state.text,None,ClosedSelector(),store,binding,**kwargs)
    assert e.tick_index==before
    assert replay.context_reads==state.context_reads
    assert again.batch_hash==report.batch_hash


def test_uncovered_structure_is_not_sent_to_graph_proposer(tmp_path):
    store,binding,release=native_fixture(tmp_path/'journal')
    class NoCalls:
        def __getattr__(self,name):
            if name in {'propose','propose_local','select'}:
                return lambda *args:pytest.fail('No licensed probe exists')
            raise AttributeError(name)
    state,report=interpret_full('...',None,NoCalls(),store,binding,morph=FixtureMorph(),
        release=release,observation_id='gap',structure_mode='region_probes')
    assert not report.committed_fragments
    assert any(d.code=='STRUCTURE_NOT_COVERED' for d in state.diagnostics)


def test_pending_external_budget_survives_disk_snapshot(tmp_path):
    from ah.core import JsonPersistence
    from ah.config import PersistenceSettings
    core=AHCore();e=engine(core,event_input_budget=2)
    uid=core.add_entity(Domain.C).uid
    e.seed(core.ref(uid),100)
    persistence=JsonPersistence(tmp_path/'memory.json',PersistenceSettings(save_pending_impulses=True))
    persistence.save(core,ignition=e)
    bundle=persistence.load()
    restored=engine(bundle.core,event_input_budget=2)
    restored.restore_snapshot(bundle.ignition_snapshot)
    restored.tick()
    assert mass(restored)<=1.8
    e.tick()
    assert mass(e)==mass(restored)


@pytest.mark.parametrize('transfer',[0,.25])
def test_reference_read_uses_active_live_proof_and_requires_closed_choice(tmp_path,transfer):
    import json
    from ah.formalizer.canonical_ledger import digest
    from tools.formalizer_v7_test_support import sign_test_release
    from ah.formalizer.state import MorphVariant
    store,binding,release=native_fixture(tmp_path/'journal')
    m=deepcopy(release.manifest)
    m['entries'].append({'kind':'CorefPolicy','version':'test-v1','schema_version':'v7',
        'dependency_versions':{},'entries':[{'window_size':128,'hard_features':['gender','number'],
        'ranking_criteria':['EXPLICIT_REF'],'tie_policy':'KEEP_ALL','event_anaphora_rules':[]}]})
    m['dependency_versions']['CorefPolicy']='test-v1'
    m['coverage_report']['units_by_kind']['CorefPolicy']=1
    m['coverage_report']['resource_content_sha256']=digest({k:m[k] for k in
        ('kind','version','schema_version','entries','dependency_versions')})
    release,_=sign_test_release(m)
    class Morph(FixtureMorph):
        def analyze(self,word):
            if word.casefold()=='него':
                return (MorphVariant(lemma='он',pos='NPRO',cases=frozenset({'gen'})),)
            return super().analyze(word)
    class Selector(NativeSelector):
        refs=0
        def select(self,prompt):
            if 'reference:0' in prompt:
                self.refs+=1
                return json.dumps({'outcome':'NONE_FIT','selected':[]})
            return super().select(prompt)
    e=engine(store._core,event_transfer=transfer)
    common=dict(morph=Morph(),release=release,ignition=e,structure_mode='region_probes')
    _,report=interpret_full('У Ивана есть книга.',None,NativeSelector(),store,binding,
                           observation_id='prior',**common)
    assert report.applied
    entity=next(b['target_ref'] for b in store.ledger.data['bindings'].values()
                if store._store.get_element_any_domain(b['target_ref']).properties['name'].value=='Ивана')
    e.seed(store._core.ref(entity),.8)
    selector=Selector()
    state,report=interpret_full('У него есть книга.',None,selector,store,binding,
                                observation_id='pronoun',**common)
    read=next(r for r in state.context_reads if r['request']['kind']=='REFERENCE')
    assert entity in {r['entity_ref'] for r in read['rows']}
    if transfer==0:
        assert {r['entity_ref'] for r in read['rows']}=={entity}
    assert all(r['premise_support_refs'] for r in read['rows'])
    assert not read['global_search_complete']
    assert selector.refs==1  # one active candidate was NOT treated as unique identity
    assert state.observation['unresolved_references']
    assert not report.committed_fragments


def test_attachment_probe_can_only_choose_existing_alternative():
    from ah.formalizer.tp_proposer import TNode, TEdge, Hypothesis
    from ah.formalizer.region_probes import select_generated
    import json
    state=t0('А Б В')
    ids=tuple(e.token_id for e in state.evidence)
    state.region_forest=build_regions(state.text,state.evidence,'doc')
    nodes=(TNode('PREDICATE',(ids[0],)),TNode('ENTITY',(ids[1],)),TNode('ENTITY',(ids[2],)))
    alternatives=[Hypothesis(cid,nodes,(TEdge('ARGUMENT',0,i,'SUBJECT'),),alignment=ids)
                  for cid,i in [('left',1),('right',2)]]
    state.clarification_candidates=[{'kind':'STRUCTURE','decision_ref':'choose',
        'options':[{'candidate_id':h.local_id} for h in alternatives]}]
    class Selector:
        def select(self,prompt):
            assert 'А@0' in prompt and 'Б@2' in prompt
            return json.dumps({'outcome':'ONE_SELECTED','selected':['right']})
    result=select_generated(state,[(h,[]) for h in alternatives],Selector(),SimpleNamespace(sha256='release'))
    assert [h.local_id for h,_ in result]==['right']
    assert state.decisions['choose'].selected==('right',)
    assert state.rejections
