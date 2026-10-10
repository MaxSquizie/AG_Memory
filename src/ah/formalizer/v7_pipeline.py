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
    if not isinstance(text,str): raise ValueError('INPUT_REJECTED: text must be a string')
    try: text.encode('utf-8',errors='strict')
    except UnicodeError as exc: raise ValueError('INPUT_REJECTED: invalid UTF-8') from exc
    if type(version) is not int or version<1: raise ValueError('INVALID_INTERPRETATION_VERSION')
    # RawInput is validated before durable run binding or resource reads. Legacy
    # host calls without a source_id retain generated observation identities.
    if 'source_id' in raw and (not isinstance(raw['source_id'],str) or not raw['source_id']):
        raise ValueError('INPUT_REJECTED: empty source_id')
    revision=raw.get('source_revision',raw.get('revision',1))
    if type(revision) is not int or revision<1: raise ValueError('INPUT_REJECTED: invalid source revision')
    if 'source_revision' in raw and 'revision' in raw and raw['source_revision']!=raw['revision']:
        raise ValueError('INPUT_REJECTED: conflicting source revision aliases')
    if raw.get('language','ru')!='ru': raise ValueError('INPUT_REJECTED: unsupported language')
    if raw.get('batch_kind','MESSAGE') not in {'MESSAGE','DOCUMENT'}: raise ValueError('INPUT_REJECTED: unknown batch kind')
    if raw.get('request_kind')=='STATEMENT':raw['request_kind']='ASSERTION'
    if raw.get('request_kind','ASSERTION') not in {'ASSERTION','QUERY','COMMAND','MIXED'}:
        raise ValueError('INPUT_REJECTED: unknown request kind')
    span=raw.get('range',[0,len(text)])
    if (not isinstance(span,(list,tuple)) or len(span)!=2
            or any(type(v) is not int or v<0 for v in span) or span[0]>span[1]):
        raise ValueError('INPUT_REJECTED: invalid source range')
    if raw.get('source_timestamp') is not None:
        from datetime import datetime
        try:
            stamp=datetime.fromisoformat(raw['source_timestamp'].replace('Z','+00:00'))
            if stamp.tzinfo is None: raise ValueError('timestamp requires offset')
        except (ValueError,TypeError,AttributeError) as exc:
            raise ValueError('INPUT_REJECTED: invalid source timestamp') from exc
    for field in ('contextual_statements','hypotheses'):
        values=raw.get(field,[])
        if not isinstance(values,(list,tuple)) or any(not isinstance(v,str) for v in values):
            raise ValueError('INPUT_REJECTED: invalid '+field)
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
    for field,default in (('language','ru'),('batch_kind','MESSAGE'),('request_kind','ASSERTION')):
        raw.setdefault(field,default)
    # Canonicalize the accepted legacy revision alias before hashing snapshots.
    raw['source_revision']=revision
    raw['revision']=revision
    raw.pop('coreference_context',None)  # Only the canonical reader may freeze it.
    raw.pop('attention_context_base',None)
    raw.pop('coreference_context_by_mention',None)
    raw.pop('event_bindings',None)  # Produced only by grounded TD reference selection.
    raw.setdefault('text',text)
    if raw['text']!=text: raise ValueError('INPUT_TEXT_MISMATCH')
    raw.setdefault('range',[0,len(text)])
    if raw.get('source_id') is not None:
        raw.setdefault('revision',revision)
        # Source revision identifies an interpretation input, not the observation.
        oid='observation:'+digest([raw['source_id'],raw['range']])
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
    from .telemetry import emit
    emit("stage", stage="T5_PLAN")
    ops,fragments,diagnostics,nodes=build_plan(state,release,store)
    for d in diagnostics: state.diag(d.split(':',1)[0],d)
    emit("stage", stage="T6_ADMISSION", fragments=len(fragments), operations=len(ops))
    rep=commit(state,store,run_id=run_id,plan_ops=ops,committed_fragments=fragments)
    D=store.ledger.data['decisions'].get(rep.batch_hash,{})
    actual=set(D.get('committed',()))
    node_refs=tuple(sorted({op.payload['node_ref'] for op in ops if op.op_type=='DECLARE_FRAGMENT' and op.payload['fragment_id'] in actual}))
    return InterpretationReport(obs,version,run_id,True,'OK',rep.committed_fragments,rep.applied,rep.terminal.value,rep.batch_hash,tuple(diagnostics),node_refs)


def interpret_full(text,schema,selector,store,binding,*,morph=None,context_facts=(),run_id=None,version=1,observation_id=None,template_map=None,registry=None,policy=None,release=None,raw_input=None,ignition=None,structure_mode='region_probes'):
    if release is not None: release.assert_integrity()
    observation=_observation(text,version=version,observation_id=observation_id,raw_input=raw_input,context_facts=context_facts)
    if structure_mode not in {'region_probes','legacy_proposal'}: raise ValueError('STRUCTURAL_CONTRACT_INVALID')
    observation['structural_contract']=structure_mode
    from .clarifications import validate_input
    validate_input(store, observation)
    obs=observation['observation_id']; run_id=run_id or binding.holder(obs,version) or 'run:'+uuid4().hex
    frozen=binding.input_snapshot(obs,version)
    # Reject source edits before selector/cache activity. Reusing an immutable
    # source revision for different bytes is an input conflict, distinct from a
    # provider or resource replay-integrity error.
    previous=[binding.input_snapshot(obs,v) for v in binding.versions(obs)]
    previous=[p for p in previous if p is not None]
    revision=observation.get('source_revision',observation.get('revision',1))
    conflict=None
    for prior in previous:
        old_revision=prior.get('source_revision',prior.get('revision',1))
        if old_revision==revision and prior.get('text')!=text:
            conflict='SOURCE_REVISION_TEXT_CHANGED';break
    if conflict is None and previous:
        latest=max(prior.get('source_revision',prior.get('revision',1)) for prior in previous)
        if frozen is None and revision<latest:conflict='SOURCE_REVISION_REGRESSED'
        elif frozen is not None and frozen.get('source_revision',frozen.get('revision',1))!=revision:
            conflict='SOURCE_REVISION_REQUIRES_NEW_VERSION'
    def conflict_result(reason):
        from .store_interface import JournalRecord
        body={'kind':'InvestigationReport','code':'INPUT_CONFLICT','reason':reason,
              'observation_id':obs,'version':version,'source_revision':revision,
              'input_hash':digest(text)}
        with store._journal.atomic():
            if not any(r['payload']==body for r in store._journal.scan_unprocessed()):
                store.append_journal('resolution_log',JournalRecord('resolution_log',run_id,body))
        state=t0(text);state.source_uid=obs;state.observation=observation
        state.diag('INPUT_CONFLICT',reason)
        return state,InterpretationReport(obs,version,run_id,False,'INPUT_CONFLICT',diagnostics=('INPUT_CONFLICT',))
    if conflict is not None:return conflict_result(conflict)
    if frozen is not None:
        if 'rx_reads' in frozen: observation['rx_reads']=frozen['rx_reads']
        for key in ('rx_diagnostics','coreference_context','attention_context_base'):
            if key in frozen: observation[key]=frozen[key]
    elif release is not None:
        resource_snapshot={'snapshot_id':release.sha256,'release_version':release.manifest['version']}
        from .rx_observability import lexical_keys
        keys=lexical_keys(text,morph)
        observation['rx_reads']={stage:list(rows) for stage,rows in store.read_cache_snapshot(resource_snapshot,lexical_keys=keys).items()}
        observation['rx_diagnostics']=list(store.last_rx_diagnostics)
        if ignition is not None and ignition.settings.clock_mode=='event':
            from .attention_context import freeze_attention_base
            observation['attention_context_base']=freeze_attention_base(store,ignition)
        elif observation.get('coreference_sources'):
            from .coreference import freeze_context
            observation['coreference_context']=freeze_context(store,release,observation['coreference_sources'])
    snapshot=digest([observation,{'snapshot_id':release.sha256,'release_version':release.manifest['version']} if release else {}])
    from .run_binding import InputConflict
    try: acquired=binding.acquire(run_id,obs,version,snapshot_hash=snapshot,snapshot_data=observation)
    except InputConflict as exc:return conflict_result(exc.reason)
    if not acquired:
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
    context_reader=None
    if observation.get('attention_context_base'):
        if ignition is None: raise ValueError('CONTEXT_REPLAY_REQUIRES_IGNITION')
        from .attention_context import AttentionContextReader
        context_reader=AttentionContextReader(store,release,ignition,run_id,observation['attention_context_base'])
    from .attention_context import ContextReadError
    try:
        state=run_native(text,selector,release,observation,morph=morph,context_reader=context_reader)
    except ContextReadError as exc:
        code=str(exc)
        state=t0(text); state.source_uid=obs; state.observation=observation
        state.diag(code,'frozen context read failed; no T5/T6 write')
        return state,InterpretationReport(obs,version,run_id,True,code,diagnostics=(code,))
    report=run_from_state(state,store,binding,schema=schema,run_id=run_id,version=version,observation_id=obs,release=release,input_observation=observation)
    with store._journal.atomic():
        if not any(r['payload'].get('kind')=='RUN_COMPLETED' and r['payload'].get('run_id')==run_id for r in store._journal.scan_unprocessed(0)):
            store._journal.append('provider',{'kind':'RUN_COMPLETED','run_id':run_id,'outcome':report.terminal,'batch_hash':report.batch_hash},run_id=run_id)
    return state,report


def interpretation_run(*args,**kwargs): return interpret_full(*args,**kwargs)[1]
