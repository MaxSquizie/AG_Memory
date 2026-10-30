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
    def __init__(self,state,dispatcher):
        self.state=state;self.dispatcher=dispatcher;self.cache={};self.active=set();self.tasks={}
        self.inputs={};self.areas={}
        self.feedback=None;self.attempted=set();self.reads=[]
        from .composition_expansion import ExpansionWindows
        self.expansion=ExpansionWindows(state)

    def child(self,key,compute,inputs=None):
        from .composition_expansion import ExpansionRequired
        previous=self.feedback
        if previous and previous.get('target_child',key)!=key:self.feedback=None
        outer=not self.expansion.path
        try:
            while True:
                try:
                    # Cycle handling belongs to the dispatcher, not expansion.
                    if key in self.active:return self._child(key,compute,inputs)
                    with self.expansion.enter(key,inputs if inputs is not None else self.inputs.get(key),self.feedback):
                        return self._child(key,compute,inputs)
                except ExpansionRequired as pending:
                    if not outer:raise
                    self.expansion.demand(pending)
        finally:self.feedback=previous

    def _child(self,key,compute,inputs=None):
        self.tasks[key]=compute
        if inputs is not None:self.inputs[key]=inputs
        feedback_key=digest(self.feedback) if self.feedback else None
        cache_key=(key,feedback_key)
        task_ref='child:'+key
        version=self.dispatcher.nodes.get(task_ref,{}).get('revision',0)
        result=self.dispatcher.run(task_ref,[self.inputs.get(key),self.feedback],
            lambda:self._compute(key,compute,cache_key),kind='COMPOSITION',**self.areas.get(key,{}))
        if self.dispatcher.nodes[task_ref]['revision']==version:
            cached=self.cache[cache_key]
            for reads in self.reads:
                reads['probes'].update(cached['pending'])
                reads['blocked'] |= cached['blocked']
            self.state.syntax_trace.append({'kind':'COMPOSITION_CHILD_REUSED','child_key':key})
        return ChildFrames(result,task_key=key)

    def _compute(self,key,compute,cache_key):
        if key in self.active:
            self.state.diag('COMPOSITION_CYCLE',key)
            return ChildFrames(task_key=key)
        self.active.add(key)
        reads={'probes':set(),'blocked':False};self.reads.append(reads)
        start=len(self.state.diagnostics)
        try:
            result=compute()
            records=self.state.component_probe_records
            pending=[k for k in sorted(reads['probes']) if k in records and not records[k].get('superseded_by') and records[k]['decision'].get('selector_outcome')
                     in {'MULTIPLE_ADMISSIBLE','INSUFFICIENT_CONTEXT'}]
            diagnostics=list(self.state.diagnostics[start:])
            blocked=reads['blocked'] or any('INCOMPLETE' in d.code or d.code in {
                'COMPUTATION_LIMIT','RESOURCE_MISSING','VALENCY_UNKNOWN','INTEGRITY_ERROR',
                'COMPONENT_PROBE_FAILED'} for d in diagnostics)
            from .task_contracts import child_result
            receipt=child_result(ChildFrames(result,task_key=key),diagnostics,pending=pending,blocked=blocked)
            self.cache[cache_key]={'frames':deepcopy(list(result)),
                'complete':receipt.structure_complete,
                'receipt':receipt,
                'pending':pending,'blocked':blocked,'diagnostics':diagnostics}
            return receipt
        finally:
            self.reads.pop();self.active.remove(key)

    def resume(self,frames,contract,context,parent_ref):
        key=getattr(frames,'task_key',None)
        if key not in self.tasks:return False
        feedback={'target_child':key,'parent_ref':parent_ref,'contract':contract,'context':context}
        attempt=(key,digest(feedback))
        base=self.cache.get((key,None))
        if not base or base['blocked'] or not base['pending'] or attempt in self.attempted:return False
        self.attempted.add(attempt)
        previous=self.feedback;self.feedback=feedback
        try:result=self.child(key,self.tasks[key])
        finally:self.feedback=previous
        frames[:]=result
        self.dispatcher.replace_read('child:'+key)
        from .composition_tree import roots
        selected=[f.frame_id for f in roots(result)]
        resumed=self.cache[(key,digest(feedback))]
        if resumed['complete']:
            retired={id(d) for d in base['diagnostics']}
            self.state.diagnostics[:]=[d for d in self.state.diagnostics if id(d) not in retired]
        else:
            # Dispatcher retires a previous execution's diagnostics before
            # recomputing. Parent feedback discharges them only on closure.
            node=self.dispatcher.nodes['child:'+key]
            for target in (self.state.diagnostics,resumed['diagnostics'],node['diagnostics']):
                present={id(d) for d in target}
                target.extend(d for d in base['diagnostics'] if id(d) not in present)
        self.state.syntax_trace.append({'kind':'COMPOSITION_CHILD_RESUMED','child_key':key,
            'parent_feedback':feedback,'previous_pending':base['pending'],'selected_refs':selected,
            'structure_complete':resumed['complete'],'search_complete':resumed['receipt'].search_complete,
            'previous_diagnostics':[{'code':d.code,'detail':d.detail} for d in base['diagnostics']]})
        return True

    def record_probe(self,key):
        for reads in self.reads:reads['probes'].add(key)

    def question(self,key):
        if self.feedback is None:return ''
        return ('\nParent slot constraint: '+self.feedback['contract']+'. '+self.feedback['context']+
                ' This supplies interpretation context only. The need to fill a slot is not evidence; '
                'do not guess a candidate or assert the child content.\n')
