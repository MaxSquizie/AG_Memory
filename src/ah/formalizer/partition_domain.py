"""Propagate content ownership inside one provisional relation hypothesis.

Constraints belong to this invocation, never to a word, lemma or child. They
expire with the selected relation and its input contract. Only an explicit
content choice (or CONTENT's lexical coverage contract) can narrow the domain;
unknown answers and failed child parsing cannot.
"""
from dataclasses import dataclass
from .canonical_ledger import digest
from .structural_tasks import source_set as span


@dataclass(frozen=True)
class ContentRequired:
    token_refs: tuple
    reason: str
    proof: dict | None = None


@dataclass
class PartitionProposal:
    groups: list
    data: object = None
    shared_functions: tuple = ()
    owner_choice: object = None
    shared_material: object = None
    grouping: object = None


class PartitionDomain:
    def __init__(self,state,release,selector,region,tokens,cfg,kind,proof):
        self.state,self.release,self.selector=state,release,selector
        self.region,self.tokens,self.cfg=region,tokens,cfg
        self.kind,self.proof=kind,proof
        self.constraints=[]
        self.markers={};self.revisions=set();self.trace_begin=len(state.syntax_trace)
        self.owner_choice=None
        # A rejected combination is relevant to its own boundary producer, but
        # proves no individual boundary wrong. Do not leak it into other
        # relations, child regions or unrelated lexical questions.
        self.rejected=[]

    def refresh_rejections(self):
        from .partition_exclusions import failure_receipt,applicable
        self.rejected=[]
        for failure in self.cfg.get('_partition_rejections',()):
            receipt=failure_receipt(self.state,failure)
            if receipt and applicable(self.state,receipt,self.region,self.tokens,self.cfg,self.kind):
                self.rejected.append(receipt['candidate']['offered_payload']['label'])

    @property
    def required(self):
        return {ref for c in self.constraints for ref in c.token_refs}

    def span(self,tokens,slot,question,*,marker=False,covered=(),remaining_parts=0,
             remaining_contiguous=False,must_include=(),open_parts=False,**kwargs):
        self.refresh_rejections()
        if self.rejected:
            question+=' Previously rejected COMBINATION for this same relation and source: '+'; '.join(self.rejected)+'. '
            question+='The complete assignment was rejected, not each boundary separately. '
            question+='An unchanged boundary is allowed if other assignments change. '
            question+='Select this boundary from the source while keeping that combination excluded; do not copy the rejected split.'
        required=self.required-set(covered)
        excluded=set(kwargs.get('exclude',()))
        if marker:
            # A proved content occurrence cannot be proposed as a marker again.
            # This is branch-local ownership, never a spelling/POS blacklist.
            excluded.update(required)
            kwargs['exclude']=excluded
        elif self.markers:
            excluded.update(self.markers);kwargs['exclude']=excluded
        if self.markers:
            words=', '.join('«'+t.span+'» @'+str(t.start) for t in self.tokens if t.token_id in self.markers)
            question+=' Established outer-relation occurrences: '+words+'. '+(
                'The complete outer wording must include them.' if marker else 'Keep these occurrences outside the content parts.')
        if required:
            words=', '.join('«'+t.span+'» @'+str(t.start) for t in self.tokens if t.token_id in required)
            if marker:
                question+=' Established ownership: '+words+' belongs to content, so exclude it from the outer relation wording.'
            elif remaining_parts or open_parts:
                question+=' Established ownership: '+words+' must belong to SOME content part, not the outer relation wording. '
                question+='It may belong to this part OR a remaining part; its particular part has not been selected.'
            else:
                question+=' Established ownership: the still unassigned '+words+' belongs to content. This last content part must include it.'
        def partial(part):
            selected={t.token_id for t in part}
            if selected & excluded:return False
            rest={t.token_id for t in tokens}-selected-excluded
            if not marker and not required <= selected|rest:return False
            if remaining_parts:
                # Each explicit operand needs source content. Punctuation alone
                # cannot fill a proposition. Do not choose the remaining split.
                if sum(t.token_id in rest and any(c.isalnum() for c in t.span)
                       for t in tokens)<remaining_parts:return False
            return True
        def complete(part):
            if not partial(part):return False
            selected={t.token_id for t in part}
            if not set(must_include)<=selected:return False
            if marker and not set(self.markers)<=selected:return False
            if remaining_parts and remaining_contiguous:
                # Check the remaining continuous operand only at completion:
                # further pieces of this operand may still consume required words.
                missing=required-selected;run=set()
                for token in tokens:
                    if token.token_id in selected|excluded:
                        if run and missing<=run:return True
                        run=set()
                    else:run.add(token.token_id)
                return bool(run) and missing<=run
            return bool(marker or remaining_parts or open_parts or required<=selected)
        return span(self.state,self.release,self.selector,self.region,tokens,self.cfg,slot,question,
                    admissible=complete,partial_admissible=partial,**kwargs)

    def resolve(self,propose,on_check=None):
        from .relation_composition import confirm_partition
        from .composition_session import current
        runtime=current(self.state)
        # Distinct typed child slots may inspect the same source concurrently.
        # They must retain separate provisional domains, just like child_key.
        key='partition:'+digest([self.region.region_id,self.kind,self.proof,
                                 runtime.input_signature() if runtime else None])
        coverage=[]
        # Each continuation adds a previously absent source occurrence. Thus
        # at most len(tokens) continuations are possible, within probe budgets.
        while True:
            trace_begin=len(self.state.syntax_trace)
            def compute():
                self.refresh_rejections()
                from .partition_role_revision import read_proof
                if self.owner_choice and not read_proof(self.state,self.owner_choice[1],owner_ref=self.owner_choice[0]['owner_ref']):return None
                if not all(read_proof(self.state,c.proof) for c in self.constraints if c.proof):return None
                if not all(read_proof(self.state,p,marker_relation_ref=ref) for ref,p in self.markers.items()):return None
                proposal=propose(self)
                if proposal is None:return None
                if proposal.owner_choice:self.owner_choice=proposal.owner_choice
                if not self.required<={t.token_id for g in proposal.groups for t in g}:
                    self.state.diag('INTEGRITY_ERROR','partition producer lost required content')
                    return None
                result=confirm_partition(self.state,self.release,self.selector,self.region,
                    self.tokens,self.cfg,self.kind,proposal.groups,self.proof,
                    shared_functions=proposal.shared_functions,owner_choice=proposal.owner_choice,marker_roles=self.markers,
                    shared_material=proposal.shared_material,grouping=proposal.grouping)
                if on_check:on_check(proposal,result)
                return proposal,result
            if runtime:
                def dispatched():
                    begin=len(self.state.syntax_trace);diagnostics_begin=len(self.state.diagnostics)
                    value=compute()
                    probes=[r['decision_ref'] for r in self.state.syntax_trace[begin:]
                            if r.get('kind')=='STRUCTURAL_TASK' and r.get('decision_ref')]
                    from .task_contracts import produced,TaskResult,TaskOutcome
                    checked=value[1] if value else None
                    ready=bool(checked) and not isinstance(checked,ContentRequired)
                    receipt=produced('PARTITION',True if ready else None,self.state.diagnostics[diagnostics_begin:])
                    return TaskResult((value,probes),receipt.outcome,ready and receipt.search_complete,
                                      receipt.source_complete,structure_complete=ready)
                result,probes=runtime.dispatcher.run(key,
                    [self.tokens,self.cfg,runtime.input_signature(),runtime.context_signature(),
                     runtime.tasks.feedback,runtime.domain_feedback,self.proof,self.constraints,self.markers,self.owner_choice],dispatched,
                    kind='PARTITION',source_range=self.region.source_range,token_refs=self.region.token_refs)
                for ref in probes:runtime.tasks.record_probe(ref)
                # The consumer deliberately replaces this provisional split;
                # it has not composed any children from the rejected one.
                runtime.dispatcher.replace_read(key)
            else:result=compute()
            checked=result[1] if result else None
            if not isinstance(checked,ContentRequired):
                if checked:
                    for row in coverage:
                        row.update(status='REPAIRED',replacement_decision_ref=checked[1]['decision_ref'])
                    self.trace('RESOLVED' if self.constraints else 'SELECTED',checked[1]['decision_ref'])
                    return result
                if self.constraints or self.markers:
                    from .partition_role_revision import revise
                    if revise(self,trace_begin):continue
                    self.trace('PENDING')
                    self.state.diag('STRUCTURAL_MARKER_CONTENT' if any(c.proof for c in self.constraints)
                                    else 'STRUCTURAL_CONTENT_UNCOVERED',self.region.region_id)
                return None
            fresh=set(checked.token_refs)-self.required
            if not fresh:
                # A producer ignoring its own propagated ownership is an
                # integrity failure, not an invitation to ask the model again.
                self.state.diag('INTEGRITY_ERROR','partition ownership constraint was not applied')
                return None
            self.constraints.append(checked)
            coverage.extend(r for r in self.state.syntax_trace[trace_begin:] if
                r.get('kind')=='STRUCTURAL_PARTITION_COVERAGE' and r.get('region_ref')==self.region.region_id
                and r.get('uncovered_token_refs')==list(checked.token_refs) and r not in coverage)
            self.trace('RESTRICTED',checked.proof.get('decision_ref') if checked.proof else None)

    def trace(self,status,decision_ref=None):
        self.state.syntax_trace.append({'kind':'STRUCTURAL_BOUNDARY_DOMAIN','region_ref':self.region.region_id,
            'source_range':list(self.region.source_range),'relation':self.kind,'relation_proof':self.proof,
            'status':status,'required_content_refs':[t.token_id for t in self.tokens if t.token_id in self.required],
            'constraint_proofs':[c.proof for c in self.constraints if c.proof],
            'required_marker_proofs':dict(self.markers),
            'owner_choice':self.owner_choice,
            'decision_ref':decision_ref,'selection_provisional':True})
