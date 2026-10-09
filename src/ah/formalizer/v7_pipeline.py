"""One production observation pipeline: bind -> T0..T4 -> typed C/T5 -> T6."""
from __future__ import annotations
from dataclasses import dataclass,field
from uuid import uuid4
from .canonical_ledger import digest
from .native_frontend import run_native
from .native_plan import build_plan
from .commit_stage import commit
from .pipeline import t0

@dataclass
class InterpretationReport:
    observation_id: str
    version: int
    run_id: str
    binding_ok: bool
    t5_eligibility: str
    committed_fragments: tuple[str,...]=()
    applied: bool=False
    terminal: str=''
    batch_hash: str=''
    diagnostics: tuple[str,...]=field(default_factory=tuple)
    node_refs: tuple[str,...]=()


def _observation(text,*,version,observation_id=None,raw_input=None,context_facts=()):
    raw=dict(raw_input or {})
    if type(version) is not int or version<1: raise ValueError('INVALID_INTERPRETATION_VERSION')
    links=raw.get('open_template_links',[])
    if not isinstance(links,list) or len(links)>32: raise ValueError('MIGRATION_LINK_INVALID')
    for link in links:
        if (not isinstance(link,dict) or set(link)!={'source_t_ref','canonical_t_ref','evidence_refs'}
            or any(not isinstance(link[k],str) or not link[k] for k in ('source_t_ref','canonical_t_ref'))
            or not isinstance(link['evidence_refs'],list) or not 1<=len(link['evidence_refs'])<=64
            or any(not isinstance(s,str) or not s for s in link['evidence_refs'])
            or len(set(link['evidence_refs']))!=len(link['evidence_refs'])):
            raise ValueError('MIGRATION_LINK_INVALID')
    if links and raw.get('supersedes_version') is None: raise ValueError('DECLARED_TRIGGER_REQUIRED')
    source_scope=raw.get('query_source_scope',[])
    if not isinstance(source_scope,list) or len(source_scope)>16 or any(not isinstance(s,str) or not s for s in source_scope): raise ValueError('QUERY_SOURCE_SCOPE_INVALID')
    if 'goal_request' in raw and not isinstance(raw['goal_request'],dict): raise ValueError('QUERY_REQUEST_INVALID')
    sources=raw.get('coreference_sources',[])
    if (not isinstance(sources,list) or len(sources)>128
            or any(not isinstance(t,list) or len(t)!=2 or not isinstance(t[0],str) or not t[0] or type(t[1]) is not int or t[1]<1 for t in sources)
            or len({tuple(t) for t in sources})!=len(sources)):
        raise ValueError('COREF_SOURCE_INVALID')
    raw.pop('coreference_context',None)  # Only the canonical reader may freeze it.
    raw.pop('event_bindings',None)  # Produced only by grounded TD reference selection.
    raw.setdefault('text',text)
    if raw['text']!=text: raise ValueError('INPUT_TEXT_MISMATCH')
    raw.setdefault('range',[0,len(text)])
    if raw.get('source_id') is not None:
        raw.setdefault('revision',1)
        oid='observation:'+digest([raw['source_id'],raw['revision'],raw['range']])
        if observation_id and observation_id!=oid: raise ValueError('OBSERVATION_ID_MISMATCH')
    else: oid=observation_id or 'observation:'+uuid4().hex
    raw.update(observation_id=oid,interpretation_version=version,context_facts=list(context_facts or raw.get('context_facts',())))
    return raw


def run_from_state(state,store,binding,*,schema=None,run_id=None,version=1,observation_id=None,template_map=None,registry=None,policy=None,release=None,input_observation=None):
    original=state.observation if input_observation is None else input_observation
    obs=observation_id or state.source_uid; run_id=run_id or binding.holder(obs,version) or 'run:'+uuid4().hex
    if not binding.acquire(run_id,obs,version,snapshot_hash=digest([original,state.resource_snapshot]),snapshot_data=original):
        return InterpretationReport(obs,version,run_id,False,'INTEGRITY_ERROR',diagnostics=('RUN_BINDING_FOREIGN_OWNER',))
    if release is None:
        return InterpretationReport(obs,version,run_id,True,'RESOURCE_MISSING',diagnostics=('RESOURCE_MISSING: signed resource release required',))
    release.assert_integrity()
    ops,fragments,diagnostics,nodes=build_plan(state,release,store)
    for d in diagnostics: state.diag(d.split(':',1)[0],d)
    rep=commit(state,store,run_id=run_id,plan_ops=ops,committed_fragments=fragments)
    D=store.ledger.data['decisions'].get(rep.batch_hash,{})
    actual=set(D.get('committed',()))
    node_refs=tuple(sorted({op.payload['node_ref'] for op in ops if op.op_type=='DECLARE_FRAGMENT' and op.payload['fragment_id'] in actual}))
    return InterpretationReport(obs,version,run_id,True,'OK',rep.committed_fragments,rep.applied,rep.terminal.value,rep.batch_hash,tuple(diagnostics),node_refs)


def interpret_full(text,schema,selector,store,binding,*,morph=None,context_facts=(),run_id=None,version=1,observation_id=None,template_map=None,registry=None,policy=None,release=None,raw_input=None):
    if release is not None: release.assert_integrity()
    observation=_observation(text,version=version,observation_id=observation_id,raw_input=raw_input,context_facts=context_facts)
    from .clarifications import validate_input
    validate_input(store, observation)
    obs=observation['observation_id']; run_id=run_id or binding.holder(obs,version) or 'run:'+uuid4().hex
    frozen=binding.input_snapshot(obs,version)
    if frozen is not None:
        observation['rx_reads']=frozen.get('rx_reads',{})
        for key in ('rx_diagnostics','coreference_context'):
            if key in frozen: observation[key]=frozen[key]
    elif release is not None:
        resource_snapshot={'snapshot_id':release.sha256,'release_version':release.manifest['version']}
        from .rx_observability import lexical_keys
        keys=lexical_keys(text,morph)
        observation['rx_reads']={stage:list(rows) for stage,rows in store.read_cache_snapshot(resource_snapshot,lexical_keys=keys).items()}
        observation['rx_diagnostics']=list(store.last_rx_diagnostics)
        if observation.get('coreference_sources'):
            from .coreference import freeze_context
            observation['coreference_context']=freeze_context(store,release,observation['coreference_sources'])
    snapshot=digest([observation,{'snapshot_id':release.sha256,'release_version':release.manifest['version']} if release else {}])
    if not binding.acquire(run_id,obs,version,snapshot_hash=snapshot,snapshot_data=observation):
        from .store_interface import JournalRecord
        store.append_journal('resolution_log',JournalRecord('resolution_log',run_id,{'kind':'InvestigationReport','code':'INTEGRITY_ERROR','reason':'RUN_BINDING_FOREIGN_OWNER','observation_id':obs,'version':version,'holder':binding.holder(obs,version)}))
        state=t0(text); state.source_uid=obs; state.observation=observation
        return state,InterpretationReport(obs,version,run_id,False,'INTEGRITY_ERROR',diagnostics=('RUN_BINDING_FOREIGN_OWNER',))
    if release is None:
        state=t0(text); state.source_uid=obs; state.observation=observation; state.diag('RESOURCE_MISSING','signed resource release required')
        return state,InterpretationReport(obs,version,run_id,True,'RESOURCE_MISSING',diagnostics=('RESOURCE_MISSING',))
    supersedes=observation.get('supersedes_version')
    if supersedes is not None:
        if type(supersedes) is not int or not 0<supersedes<version or not observation.get('trigger_ref'): raise ValueError('DECLARED_TRIGGER_REQUIRED')
        # Retirement is part of T6's replacement transaction. A failed T4/T5 or
        # an entirely rejected admission must leave the old version untouched.
    if hasattr(selector, 'for_run'): selector = selector.for_run(run_id)
    if hasattr(selector,'start_run'): selector.start_run(run_id)
    state=run_native(text,selector,release,observation,morph=morph)
    report=run_from_state(state,store,binding,schema=schema,run_id=run_id,version=version,observation_id=obs,release=release,input_observation=observation)
    with store._journal.atomic():
        if not any(r['payload'].get('kind')=='RUN_COMPLETED' and r['payload'].get('run_id')==run_id for r in store._journal.scan_unprocessed(0)):
            store._journal.append('provider',{'kind':'RUN_COMPLETED','run_id':run_id,'outcome':report.terminal,'batch_hash':report.batch_hash},run_id=run_id)
    return state,report


def interpretation_run(*args,**kwargs): return interpret_full(*args,**kwargs)[1]
