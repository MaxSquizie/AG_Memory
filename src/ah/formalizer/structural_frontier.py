"""Session-owned breadth-first structural window; no pruning or publication."""
from copy import deepcopy
from dataclasses import replace
from .canonical_ledger import digest
from .composition_dispatcher import DispatchBlocked,canonical
from .composition_tree import InputSlot
from .structural_conditions import child_scope,execution_basis
from .structural_shells import produce,live,evidence_state

REGISTRIES=('structural_condition_registry','structural_condition_evidence','structural_shell_registry')
RESOURCE_CODES={'COMPOSITION_DISPATCH_INCOMPLETE','COMPUTATION_LIMIT','STRUCTURAL_TASK_SEARCH_INCOMPLETE'}


def order(jobs):
    return sorted(jobs,key=lambda j:(j['depth'],j['job_ref']))


def one_level(state,runtime,region,tokens,cfg,request):
    from .relation_composition import select_relation
    from .partial_readings import SupportedDomain
    from .structural_forest import retain
    result=select_relation(state,runtime.release,runtime.selector,region,tokens,cfg,request)
    if result is None:return None
    if not isinstance(result,SupportedDomain):
        value,proof=result
        result=SupportedDomain((value,),proof['decision_ref'],proof['domain_ref'])
    return retain(state,region,tokens,request,cfg,result)


class StructuralFrontier:
    def __init__(self,runtime,region,tokens,cfg,request,forest):
        self.runtime=runtime;self.state=runtime.state;self.jobs={}
        self.generation_ref='structural-generation:'+digest([forest['receipt_digest'],execution_basis(self.state,cfg)])
        self.basis=execution_basis(self.state,cfg);self.context=runtime.capture_context()
        self.add({'job_ref':self.generation_ref+':root','depth':1,'state':self.state,
            'runtime':runtime,'region':region,'tokens':tokens,'cfg':deepcopy(cfg),'request':request,
            'forest':forest,'parent_shell':None,'child':None,'status':'QUEUED','results':[]})

    def event(self,job,event,**extra):
        self.state.syntax_trace.append({'kind':'STRUCTURAL_FRONTIER_EVENT','generation_ref':self.generation_ref,
            'job_ref':job['job_ref'],'depth':job['depth'],'event':event,
            'condition_ref':job['parent_shell']['condition']['condition_ref'] if job['parent_shell'] else None,
            **extra})

    def add(self,job):
        if job['job_ref'] in self.jobs:return
        self.jobs[job['job_ref']]=job;self.event(job,'enqueued')

    def sync(self,job):
        state=job['state']
        if state is self.state:return
        from .structural_resume import synchronize
        synchronize(self.state,state)
        for name in REGISTRIES:
            state.observation.setdefault(name,{}).update(deepcopy(self.state.observation.get(name,{})))
        for event in self.state.syntax_trace:
            if event.get('kind') in {'DEPENDENCY_REJECTED','COMPOSITION_PROBE_SUPERSEDED'} and event not in state.syntax_trace:
                state.syntax_trace.append(deepcopy(event))

    def publish_diagnostics(self,job,begin):
        state=job['state']
        if state is self.state:return
        for name in REGISTRIES:
            self.state.observation.setdefault(name,{}).update(deepcopy(state.observation.get(name,{})))
        for row in state.syntax_trace[begin:]:
            if row.get('kind') in {'STRUCTURAL_OPEN_DOMAIN','STRUCTURAL_CONDITIONAL_SHELL','STRUCTURAL_SHELL_PENDING'}:
                if row not in self.state.syntax_trace:self.state.syntax_trace.append(deepcopy(row))

    def enqueue_children(self,job,shell):
        from .composition_session import CompositionSession
        from .component_refinement import region_for
        # Reuse the exact private reader checkpoint that produced this shell.
        owner=next(t['runtime'] for t in job['runtime'].structural_shell_tasks.values()
                   if t.get('result',{}).get('shell_ref')==shell['shell_ref'])
        for child in shell['children']:
            if child['child_ref'] in self.jobs:continue
            local=evidence_state(job['state'],shell);local.budget=self.state.budget
            by_id={t.token_id:t for t in local.evidence};tokens=[by_id[r] for r in child['token_refs']]
            request=replace(job['request'] or InputSlot(),
                surrounding_relations=(*(job['request'] or InputSlot()).surrounding_relations,shell['relation']))
            if canonical(request)!=child['input_slot']:raise ValueError('STRUCTURAL_CHILD_CONTRACT_MISMATCH')
            cfg={k:v for k,v in job['cfg'].items() if k not in
                 {'_task_constraints','_task_constraints_text','_ownership_feedback','_partition_rejections'}}
            region=region_for(local,job['region'],tokens,child['child_ref'])
            can_fork=owner.reader is None or callable(getattr(owner.reader,'fork',None))
            reader=owner.reader.fork(child['child_ref']) if owner.reader is not None and can_fork else None
            runtime=CompositionSession(local,owner.release,reader,owner.selector,owner.morph)
            runtime.original=deepcopy(owner.original)
            # Retain the producing branch's context, then enter the derived slot.
            # Addressed feedback applies only to its recipient, as in ChildTasks.
            runtime.restore_context(owner.capture_context())
            feedback=owner.tasks.feedback
            if feedback and feedback.get('target_child',child['child_ref'])==child['child_ref']:
                runtime.tasks.feedback=deepcopy(feedback)
            runtime.area_inputs=(region,tokens,request)
            self.add({'job_ref':child['child_ref'],'depth':job['depth']+1,'state':local,
                'runtime':runtime,'region':region,'tokens':tokens,'cfg':cfg,'request':request,
                'forest':None,'parent_shell':deepcopy(shell),'child':deepcopy(child),
                'status':'QUEUED' if can_fork else 'PENDING_CAPABILITY','results':[]})

    def available(self):
        return self.runtime.dispatcher.spent<self.runtime.dispatcher.limit and not self.state.budget.llm_exhausted

    def run(self):
        from contextlib import nullcontext
        from .composition_session import activate
        from .structural_probe_inputs import source_signature
        from .structural_resume import reopen,resource_stamp
        # The source/meaning context is immutable for one frontier generation.
        stale=(canonical(self.runtime.capture_context())!=canonical(self.context)
               or canonical(self.runtime.tasks.feedback)!=self.basis['context']['parent_feedback']
               or source_signature(self.state)!=self.basis['source_basis']
               or self.state.context_version!=self.basis['context_version']
               or self.runtime.context_signature()!=self.basis['context']['memory_context'])
        for job in order(self.jobs.values()):
            self.sync(job)
            from .structural_forest import live as domain_live
            domain_stale=job['forest'] is not None and not domain_live(job['state'],job['forest'])
            if stale or domain_stale or (job['parent_shell'] is not None and not live(job['state'],job['parent_shell'])):
                if job['status']!='STALE':job['status']='STALE';self.event(job,'pending',reason='BASIS_RETIRED')
            elif job['status']=='PRODUCED' and any(not live(job['state'],r) for r in job['results']):
                job['status']='PENDING_EVIDENCE';self.event(job,'pending',reason='RESULT_BASIS_RETIRED')
        if any(j['status']=='PENDING_RESOURCE' and j.get('resource_stamp')==resource_stamp(self.runtime,j['cfg'])
               for j in self.jobs.values()):return self.save_snapshot()
        while True:
            candidates=order(j for j in self.jobs.values() if j['depth']<=3 and (j['status']=='QUEUED' or (j['status']=='PENDING_RESOURCE' and
                j.get('resource_stamp')!=resource_stamp(self.runtime,j['cfg']))))
            if not candidates:break
            job=candidates[0]
            if not self.available():
                job['status']='PENDING_RESOURCE';job['resource_stamp']=resource_stamp(self.runtime,job['cfg'])
                self.event(job,'pending',reason='RESOURCE_EXHAUSTED');break
            self.sync(job)
            if job['parent_shell'] is not None and not live(job['state'],job['parent_shell']):
                job['status']='STALE';self.event(job,'pending',reason='BASIS_RETIRED');continue
            state=job['state'];runtime=job['runtime'];before=runtime.dispatcher.spent
            if job['status']=='PENDING_RESOURCE':reopen(runtime)
            if runtime is not self.runtime:
                runtime.dispatcher.limit=before+max(0,self.runtime.dispatcher.limit-self.runtime.dispatcher.spent)
            begin=len(state.syntax_trace);diag_begin=len(state.diagnostics)
            job['status']='RUNNING';self.event(job,'started')
            try:
                with activate(runtime):
                    scope=child_scope(state,job['parent_shell'],job['child'],job['cfg']) if job['parent_shell'] else nullcontext()
                    with scope:
                        if job['forest'] is None:
                            job['forest']=one_level(state,runtime,job['region'],job['tokens'],job['cfg'],job['request'])
                        if job['forest'] is not None:
                            job['results']=produce(state,runtime.release,runtime.selector,job['region'],
                                job['tokens'],job['cfg'],job['request'],job['forest'])
                codes={d.code for d in state.diagnostics[diag_begin:]}
                codes.update(d['code'] for r in job['results'] for d in r['evidence']['diagnostics'])
                if codes & RESOURCE_CODES:job['status']='PENDING_RESOURCE'
                elif job['results'] and any(r['status']=='SHELL_PRODUCED' for r in job['results']):job['status']='PRODUCED'
                elif job['forest'] and all(h['candidate']['relation'] not in {'AND','OR'} for h in job['forest']['hypotheses']):
                    job['status']='PENDING_CAPABILITY'
                elif any(r.get('kind')=='STRUCTURAL_SHELL_PENDING' and r.get('reason')=='CONTEXT_READER_FORK_UNAVAILABLE'
                         for r in state.syntax_trace[begin:]):job['status']='PENDING_CAPABILITY'
                else:job['status']='PENDING_EVIDENCE'
            except DispatchBlocked:job['status']='PENDING_RESOURCE'
            finally:
                if runtime is not self.runtime:self.runtime.dispatcher.spent+=runtime.dispatcher.spent-before
            self.publish_diagnostics(job,begin)
            for shell in job['results']:
                if live(state,shell):self.enqueue_children(job,shell)
            self.event(job,'completed' if job['status']=='PRODUCED' else 'pending',status=job['status'],
                result_refs=[s['shell_ref'] for s in job['results']])
            if job['status']=='PENDING_RESOURCE':
                job['resource_stamp']=resource_stamp(self.runtime,job['cfg']);break
        return self.save_snapshot()

    def save_snapshot(self):
        snapshot=self.snapshot()
        self.state.observation.setdefault('structural_frontiers',{})[self.generation_ref]=snapshot
        return snapshot

    def snapshot(self):
        return {'generation_ref':self.generation_ref,'window_depth':3,'structure_complete':False,'write_eligible':False,
            'jobs':[{'job_ref':j['job_ref'],'depth':j['depth'],'status':j['status'],
                'parent_shell_ref':j['parent_shell']['shell_ref'] if j['parent_shell'] else None,
                'condition_ref':j['parent_shell']['condition']['condition_ref'] if j['parent_shell'] else None,
                'token_refs':[t.token_id for t in j['tokens']], 'input_slot':canonical(j['request']),
                'result_refs':[r['shell_ref'] for r in j['results'] if live(j['state'],r)] if j['status']!='STALE' else []}
                for j in order(self.jobs.values())]}


def start(runtime,region,tokens,cfg,request,forest):
    key=forest['receipt_digest']
    driver=runtime.structural_frontiers.get(key)
    if driver is None:
        driver=StructuralFrontier(runtime,region,tokens,cfg,request,forest)
        runtime.structural_frontiers[key]=driver
    return driver.run()
