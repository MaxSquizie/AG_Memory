from copy import deepcopy
from ah.formalizer.attention_context import AttentionContextReader,freeze_attention_base,attention_snapshot
from ah.formalizer.pipeline import t0
from ah.formalizer.v7_pipeline import interpret_full
from ah.formalizer.canonical_ledger import digest
from tools.formalizer_v7_test_support import native_fixture,FixtureMorph,NativeSelector,sign_test_release
from test_region_attention import engine


def test_forks_isolate_nonempty_attention_and_replay(tmp_path):
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
    from tools.formalizer_component_fixture import with_components
    release=with_components(release)
    live_engine=engine(store._core,event_transfer=0)
    _,report=interpret_full('У Ивана есть книга.',None,NativeSelector(),store,binding,
        morph=FixtureMorph(),release=release,ignition=live_engine,structure_mode='region_probes',observation_id='prior')
    assert report.applied
    entity=next(b['target_ref'] for b in store.ledger.data['bindings'].values()
        if store._store.get_element_any_domain(b['target_ref']).properties['name'].value=='Ивана')
    live_engine.seed(store._core.ref(entity),.8)
    parent=AttentionContextReader(store,release,live_engine,'fork-test',freeze_attention_base(store,live_engine))
    before=attention_snapshot(parent.engine);live_before=attention_snapshot(live_engine)
    left=parent.fork('AND');right=parent.fork('OR')
    state=t0('Ивана');state.observation={}
    request={'kind':'STRUCTURE','decision_ref':'test-goal','source_range':(0,len(state.text)),
        'region_ref':'root','cue_token_refs':[e.token_id for e in state.evidence],'proof_goals':[]}
    result=left.read(state,request)
    assert entity in {r['entity_ref'] for r in result['rows']}
    wal_before=store._journal.path.read_bytes();ordinal=left.ordinal
    branch_before=attention_snapshot(left.engine)
    assert left.validate_context_receipts(state.context_reads)['status']=='CURRENT'
    assert left.ordinal==ordinal and attention_snapshot(left.engine)==branch_before
    assert store._journal.path.read_bytes()==wal_before
    assert right.validate_context_receipts(state.context_reads)['status']=='STALE'
    assert attention_snapshot(parent.engine)==before==attention_snapshot(right.engine)
    assert attention_snapshot(live_engine)==live_before
    assert parent.ordinal==right.ordinal==0 and not parent.read_token_refs
    replay=parent.fork('AND');fresh=t0(state.text);fresh.observation={}
    assert replay.read(fresh,request)==result
    sibling=t0(state.text);sibling.observation={}
    assert right.read(sibling,request)==result
    assert left.run_id==replay.run_id and left.run_id!=right.run_id
    reads=[r for r in store._journal.scan_unprocessed() if r.get('run_id') in {left.run_id,right.run_id}]
    assert len(reads)==2
    assert attention_snapshot(live_engine)==live_before
