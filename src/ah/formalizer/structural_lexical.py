"""Private lexical source outcomes. No scalar selection or publication license.

This stage exposes real producer output and suspended child requests. Source
closure and downstream consumption remain explicit obligations, not inferred
from a return, frame count, or absence of diagnostics.
"""
from copy import deepcopy
from dataclasses import asdict
from .canonical_ledger import digest
from .composition_dispatcher import canonical,DispatchBlocked
from .structural_conditions import active,applicable,branch,inherit_scope,registry
from .lexical_demands import capture,ChildDemand


def bundles(frames):
    from .composition_tree import roots
    grouped={}
    for frame in frames:
        key=frame.semantic.get('composition_bundle_root',frame.semantic.get('composition_group_root',frame.frame_id))
        grouped.setdefault(key,[]).append(frame.frame_id)
    for frame in frames:
        domain=frame.semantic.get('composition_domain') or frame.semantic.get('lexical_bundle')
        if domain:grouped[frame.frame_id]=list(domain['frame_refs'])
    return [{'root_ref':key,'frame_refs':refs,'status':'PENDING_VALIDATION'} for key,refs in grouped.items()]


def produce(state,release,selector,region,tokens,cfg,request,forest):
    from .composition_session import current,CompositionSession,activate
    from .structural_resume import synchronize
    parent=current(state);inherited=active(state)
    if parent is None or not applicable(state,forest,cfg):return []
    results=[]
    for hypothesis in forest['hypotheses']:
        if hypothesis['candidate']['relation']!='LEXICAL':continue
        if parent.reader is not None and not callable(getattr(parent.reader,'fork',None)):
            state.syntax_trace.append({'kind':'STRUCTURAL_LEXICAL_PENDING',
                'hypothesis_ref':hypothesis['hypothesis_ref'],'reason':'CONTEXT_READER_FORK_UNAVAILABLE'})
            continue
        key=digest([forest['receipt_digest'],hypothesis['hypothesis_ref']])
        task=parent.structural_lexical_tasks.get(key)
        if task is None:
            local=deepcopy(state);local.budget=state.budget
            reader=parent.reader.fork(hypothesis['hypothesis_ref']) if parent.reader else None
            runtime=CompositionSession(local,release,reader,selector,parent.morph)
            runtime.original=deepcopy(parent.original);runtime.restore_context(parent.capture_context())
            runtime.tasks.feedback=deepcopy(parent.tasks.feedback)
            runtime.structural_child_edge=getattr(parent,'structural_child_edge',None)
            task={'state':local,'runtime':runtime,'sources':{},'begin':len(local.syntax_trace),
                  'diagnostics_begin':len(local.diagnostics),'result':None,'demands':{}}
            parent.structural_lexical_tasks[key]=task
        local=task['state'];runtime=task['runtime'];synchronize(state,local)
        for name in ('structural_condition_registry','structural_condition_evidence','structural_shell_registry'):
            local.observation.setdefault(name,{}).update(deepcopy(state.observation.get(name,{})))
        before=runtime.dispatcher.spent
        runtime.dispatcher.limit=before+max(0,parent.dispatcher.limit-parent.dispatcher.spent)
        with activate(runtime):
            try:
                with inherit_scope(state,local,cfg,inherited),branch(local,forest,hypothesis,cfg) as condition:
                    runtime.area_inputs=(region,tokens,request)
                    with runtime.area(region,tokens,request):
                        from .lexical_component import produce as component
                        from .component_area_scope import allowed
                        def component_source():
                            literal={**cfg,'_literal_relation':True,'_retain_lexical_bundles':True}
                            if not allowed(local,release,region,tokens,conjunction=True,
                                    inside_attitude=bool(request and request.inside_attitude),literal_scope=True):
                                local.diag('COMPONENT_SCOPE_UNRESOLVED',region.region_id);return []
                            return component(local,release,selector,region,tokens,literal,request=request)
                        sources={'GRAMMAR':lambda:runtime.sources.reuse(region,tokens,None,None,request),
                                 'COMPONENT':component_source}
                        for source,compute in sources.items():
                            # The dispatcher still owns probe replay. A source
                            # snapshot itself is not a reusable completion proof.
                            start=len(local.diagnostics);obligations=[];frames=[];returned=False
                            try:
                                with capture(local,{'hypothesis_ref':hypothesis['hypothesis_ref'],'source':source}):
                                    frames=list(compute() or ());returned=True
                            except ChildDemand as demand:
                                obligations.append(demand.obligation)
                                task['demands'][demand.obligation['obligation_ref']]=demand.invocation
                            except DispatchBlocked:
                                obligations.append({'kind':'RESOURCE_PENDING','source':source})
                            diagnostics=[asdict(d) for d in local.diagnostics[start:]]
                            task['sources'][source]={'source':source,'execution_complete':returned,
                                'producer_complete':False,'structure_complete':False,
                                'frames':[asdict(f) for f in frames],'bundles':bundles(frames),
                                'diagnostics':diagnostics,'obligations':obligations+[
                                    {'kind':'SOURCE_CLOSURE_UNESTABLISHED','source':source}]}
            finally:parent.dispatcher.spent+=runtime.dispatcher.spent-before
        registry(state).update(deepcopy(registry(local)))
        state.observation.setdefault('structural_condition_evidence',{}).update(
            deepcopy(local.observation.get('structural_condition_evidence',{})))
        row={'kind':'STRUCTURAL_CONDITIONAL_LEXICAL','hypothesis_ref':hypothesis['hypothesis_ref'],
             'forest_ref':forest['forest_ref'],'condition':condition.record(),
             'token_refs':[t.token_id for t in tokens],'source_range':list(region.source_range),
             'input_slot':canonical(request),'sources':deepcopy(list(task['sources'].values())),
             'status':'PENDING_VALIDATION','producer_complete':False,'structure_complete':False,
             'write_eligible':False,'obligations':[{'kind':'LEXICAL_EVIDENCE_VALIDATION_PENDING'}],
             'evidence':{'trace':deepcopy(local.syntax_trace[task['begin']:]),
                 'decisions':{k:asdict(v) for k,v in local.decisions.items()},
                 'probes':deepcopy(local.component_probe_records),
                 'diagnostics':[asdict(d) for d in local.diagnostics[task['diagnostics_begin']:]],
                 'context_reads':deepcopy(local.context_reads)}}
        row['execution_complete']=all(s['execution_complete'] for s in row['sources'])
        row['result_ref']='structural-lexical:'+digest([key,row['condition']])
        row['receipt_digest']=digest(row)
        task['result']=deepcopy(row);results.append(row)
        state.observation.setdefault('structural_lexical_results',{})[row['result_ref']]=deepcopy(row)
    return results
