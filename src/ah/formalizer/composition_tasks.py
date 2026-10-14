"""Resume addressed child domains while retaining completed probe evidence.

Tasks are ephemeral services, not a second serialized IR or a fact store.
Only changed parent input can resume a task; a retry is not a source-clock tick.
"""
from copy import deepcopy
from .canonical_ledger import digest


class ChildFrames(list):
    def __init__(self, values=(), *, task_key=None):
        super().__init__(values)
        self.task_key=task_key


class ChildTasks:
    def __init__(self,state):
        self.state=state;self.cache={};self.active=set();self.tasks={}
        self.feedback=None;self.attempted=set();self.reads=[]

    def child(self,key,compute):
        self.tasks.setdefault(key,compute)
        feedback_key=digest(self.feedback) if self.feedback else None
        cache_key=(key,feedback_key)
        base=self.cache.get((key,None))
        # Completed descendants stay reusable. Parent feedback is requested
        # only for unresolved domains, not a new interpretation version.
        cached=self.cache.get(cache_key)
        if cached is None and base and base['complete']:cached=base
        if cached is not None:
            for reads in self.reads:
                reads['probes'].update(cached['pending'])
                reads['blocked'] |= cached['blocked']
            self.state.syntax_trace.append({'kind':'COMPOSITION_CHILD_REUSED','child_key':key})
            return ChildFrames(deepcopy(cached['frames']),task_key=key)
        if key in self.active:
            self.state.diag('COMPOSITION_CYCLE',key)
            return ChildFrames(task_key=key)
        self.active.add(key)
        reads={'probes':set(),'blocked':False};self.reads.append(reads)
        start=len(self.state.diagnostics)
        try:
            result=compute()
            records=self.state.component_probe_records
            pending=[k for k in sorted(reads['probes']) if k in records and records[k]['decision'].get('selector_outcome')
                     in {'MULTIPLE_ADMISSIBLE','INSUFFICIENT_CONTEXT'}]
            diagnostics=list(self.state.diagnostics[start:])
            blocked=reads['blocked'] or any('INCOMPLETE' in d.code or d.code in {
                'COMPUTATION_LIMIT','RESOURCE_MISSING','VALENCY_UNKNOWN','INTEGRITY_ERROR',
                'COMPONENT_PROBE_FAILED'} for d in diagnostics)
            from .composition_tree import roots
            self.cache[cache_key]={'frames':deepcopy(list(result)),
                'complete':len(roots(result))==1 and not pending and not blocked,
                'pending':pending,'blocked':blocked,'diagnostics':diagnostics}
            return ChildFrames(result,task_key=key)
        finally:
            self.reads.pop();self.active.remove(key)

    def resume(self,frames,contract,context,parent_ref):
        key=getattr(frames,'task_key',None)
        if key not in self.tasks:return False
        feedback={'parent_ref':parent_ref,'contract':contract,'context':context}
        attempt=(key,digest(feedback))
        base=self.cache.get((key,None))
        if not base or base['blocked'] or not base['pending'] or attempt in self.attempted:return False
        self.attempted.add(attempt)
        previous=self.feedback;self.feedback=feedback
        try:result=self.child(key,self.tasks[key])
        finally:self.feedback=previous
        frames[:]=result
        from .composition_tree import roots
        selected=[f.frame_id for f in roots(result)]
        if len(selected)==1:
            retired={id(d) for d in base['diagnostics']}
            self.state.diagnostics[:]=[d for d in self.state.diagnostics if id(d) not in retired]
        self.state.syntax_trace.append({'kind':'COMPOSITION_CHILD_RESUMED','child_key':key,
            'parent_feedback':feedback,'previous_pending':base['pending'],'selected_refs':selected,
            'previous_diagnostics':[{'code':d.code,'detail':d.detail} for d in base['diagnostics']]})
        return True

    def record_probe(self,key):
        for reads in self.reads:reads['probes'].add(key)

    def question(self,key):
        if self.feedback is None:return ''
        previous=self.state.decisions.get(key)
        if previous and previous.outcome=='RESOLVED':return ''
        return ('\nParent slot constraint: '+self.feedback['contract']+'. '+self.feedback['context']+
                ' This supplies interpretation context only. The need to fill a slot is not evidence; '
                'do not guess a candidate or assert the child content.\n')
