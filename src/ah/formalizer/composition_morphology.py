"""Scoped morphology tasks: immutable source, revisable local domains."""
from copy import deepcopy
from .canonical_ledger import digest
from .composition_dispatcher import canonical


def prepare(runtime,region,tokens,request,cfg):
    from .contextual_agreement import resolve as agreement
    from .contextual_oov import resolve as oov
    from .morphology_domain import project
    from .component_policy import _morph
    state=runtime.state
    parent_scope=runtime.morphology_scope
    # Never start from a previous contextual restriction or spelling repair.
    source=[deepcopy(runtime.original[t.token_id]) for t in tokens]
    owner=digest([region.region_id,region.source_range,[t.token_id for t in tokens]])
    from .morphology_domain import function_restrictions,function_support
    inherited=[];providers={};origins={}
    parent_task=parent_scope.rsplit(':',1)[0] if parent_scope else None
    old_imports={r['function_ref']:r for r in state.syntax_trace
        if r.get('kind')=='MORPHOLOGY_FUNCTION_IMPORT' and r.get('task_scope')==parent_scope}
    for token in source:
        rows=function_restrictions(state,token.token_id) if parent_task else []
        if not rows:continue
        row=rows[-1];ref=digest(row)
        if parent_task=='morphology:'+owner:
            # A local revision may reconsider its OWN guesses, but cannot
            # silently drop an occurrence restriction inherited from its parent.
            old=old_imports.get(ref)
            if not old:continue
            provider,version=old['parent_task'],old['parent_revision']
        else:
            provider=parent_task;version=runtime.dispatcher.nodes[provider]['revision']
        if not function_support(state,token,row):raise ValueError('MORPHOLOGY_FUNCTION_UNGROUNDED')
        inherited.append(row);providers[provider]=version;origins[ref]=(provider,version)
    # Execution version validates the use record, not the semantic input key.
    # Rebuilding after clarification must still reuse unchanged probe evidence.
    inputs=canonical([source,request,runtime.tasks.feedback,cfg.get('_task_constraints'),runtime.context_signature(),
                      [{k:v for k,v in r.items() if k!='interpretation_version'} for r in inherited],providers])
    runtime.morphology_scope='morphology:'+owner+':'+digest(inputs)
    scope=runtime.morphology_scope
    for row in inherited:
        ref=digest(row);provider,version=origins[ref]
        state.syntax_trace.append({'kind':'MORPHOLOGY_FUNCTION_IMPORT','task_scope':scope,
            'token_ref':row['token_ref'],'function_ref':ref,'via_scope':parent_scope,
            'parent_task':provider,'parent_revision':version})
    area={'source_range':region.source_range,'token_refs':[t.token_id for t in tokens]}
    def recover():
        local=deepcopy(source)
        with runtime.morphology_feedback(cfg.get('_task_constraints_text')):
            agreement(state,runtime.release,runtime.selector,runtime.morph,areas=[(region,local)])
        return local
    recovered=runtime.dispatcher.run('agreement:'+owner,inputs,recover,kind='AGREEMENT',**area)
    def select():
        local=deepcopy(recovered)
        with runtime.morphology_feedback(cfg.get('_task_constraints_text')):
            oov(state,runtime.release,runtime.selector,areas=[(region,local)])
        return project(state,local)
    # Link the two producers explicitly, including reused recovery results.
    def domain():
        for provider,version in providers.items():runtime.dispatcher.read(provider,version)
        runtime.dispatcher.run('agreement:'+owner,inputs,recover,kind='AGREEMENT',**area)
        return select()
    result=runtime.dispatcher.run('morphology:'+owner,[inputs,[_morph(v) for t in recovered for v in t.variants]],
        domain,kind='MORPHOLOGY',**area)
    state.syntax_trace.append({'kind':'DISPATCH_MORPHOLOGY','task_ref':'morphology:'+owner,
        'task_scope':scope,'source_range':list(region.source_range),
        'token_refs':[t.token_id for t in tokens], 'input_contract':canonical(request)})
    return result


def publish_recoveries(state,frames):
    """Expose only corrections used by the final composition to downstream T3.

    Parsing itself uses scoped copies. Rejected alternative repairs never mutate
    the evidence used to propose another interpretation.
    """
    from .morphology_domain import frame_readings,clean
    from .nominal_readings import variant
    selected={}
    for frame in frames:
        if frame.semantic.get('structural_unresolved'):continue
        for _,tid,reading in frame_readings(frame):
            if reading.get('origin')=='RECOVERED':selected.setdefault(tid,{})[digest(clean(reading))]=reading
    for token in state.evidence:
        readings=selected.get(token.token_id,{})
        if len(readings)!=1:continue
        reading=next(iter(readings.values()))
        for row in reversed(state.syntax_trace):
            if row.get('kind')!='AGREEMENT_RECOVERY' or row['token_ref']!=token.token_id:continue
            if row.get('recovered_reading')!=clean(reading):continue
            token.variants=(variant(reading),);token.lemma=reading['lemma'];token.pos=reading['pos']
            token.cases=frozenset(reading['cases']);token.lex_status='RECOVERY_SELECTED'
            token.lexical_recovery=deepcopy(row['lexical_recovery']);break
