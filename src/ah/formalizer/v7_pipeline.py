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


def run_from_state(state,store,binding,*,schema=None,run_id=None,version=1,observation_id=None,template_map=None,registry=None,policy=None,release=None):
    obs=observation_id or state.source_uid; run_id=run_id or binding.holder(obs,version) or 'run:'+uuid4().hex
    if not binding.acquire(run_id,obs,version,snapshot_hash=digest([state.observation,state.resource_snapshot]),snapshot_data=state.observation):
        return InterpretationReport(obs,version,run_id,False,'INTEGRITY_ERROR',diagnostics=('RUN_BINDING_FOREIGN_OWNER',))
    if release is None:
        return InterpretationReport(obs,version,run_id,True,'RESOURCE_MISSING',diagnostics=('RESOURCE_MISSING: signed resource release required',))
    ops,fragments,diagnostics,nodes=build_plan(state,release,store)
    for d in diagnostics: state.diag(d.split(':',1)[0],d)
    rep=commit(state,store,run_id=run_id,plan_ops=ops,committed_fragments=fragments)
    D=store.ledger.data['decisions'].get(rep.batch_hash,{})
    actual=set(D.get('committed',()))
    node_refs=tuple(sorted({op.payload['node_ref'] for op in ops if op.op_type=='DECLARE_FRAGMENT' and op.payload['fragment_id'] in actual}))
    return InterpretationReport(obs,version,run_id,True,'OK',rep.committed_fragments,rep.applied,rep.terminal.value,rep.batch_hash,tuple(diagnostics),node_refs)


def interpret_full(text,schema,selector,store,binding,*,morph=None,context_facts=(),run_id=None,version=1,observation_id=None,template_map=None,registry=None,policy=None,release=None,raw_input=None):
    observation=_observation(text,version=version,observation_id=observation_id,raw_input=raw_input,context_facts=context_facts)
    obs=observation['observation_id']; run_id=run_id or binding.holder(obs,version) or 'run:'+uuid4().hex
    frozen=binding.input_snapshot(obs,version)
    if frozen is not None:
        observation['rx_reads']=frozen.get('rx_reads',{})
    elif release is not None:
        resource_snapshot={'snapshot_id':release.sha256,'release_version':release.manifest['version']}
        observation['rx_reads']={stage:list(rows) for stage,rows in store.read_cache_snapshot(resource_snapshot).items()}
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
        if supersedes>=version or not observation.get('trigger_ref'): raise ValueError('DECLARED_TRIGGER_REQUIRED')
        store.supersede_observation(obs,supersedes,trigger_ref=observation['trigger_ref'])
    if hasattr(selector,'start_run'): selector.start_run(run_id)
    state=run_native(text,selector,release,observation,morph=morph)
    report=run_from_state(state,store,binding,schema=schema,run_id=run_id,version=version,observation_id=obs,release=release)
    with store._journal.atomic():
        if not any(r['payload'].get('kind')=='RUN_COMPLETED' and r['payload'].get('run_id')==run_id for r in store._journal.scan_unprocessed(0)):
            store._journal.append('provider',{'kind':'RUN_COMPLETED','run_id':run_id,'outcome':report.terminal,'batch_hash':report.batch_hash},run_id=run_id)
    return state,report


def interpretation_run(*args,**kwargs): return interpret_full(*args,**kwargs)[1]
