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


class PartitionDomain:
    def __init__(self,state,release,selector,region,tokens,cfg,kind,proof):
        self.state,self.release,self.selector=state,release,selector
        self.region,self.tokens,self.cfg=region,tokens,cfg
        self.kind,self.proof=kind,proof
        self.constraints=[]

    @property
    def required(self):
        return {ref for c in self.constraints for ref in c.token_refs}

    def span(self,tokens,slot,question,*,marker=False,covered=(),remaining_parts=0,
             remaining_contiguous=False,**kwargs):
        required=self.required-set(covered)
        admissible=None
        if required:
            words=', '.join('«'+t.span+'» @'+str(t.start) for t in self.tokens if t.token_id in self.required)
            question+=' For this '+self.kind+' reading, the local ownership check keeps '+words+' in the content. Select boundaries consistent with that choice.'
            excluded=set(kwargs.get('exclude',()))
            def admissible(part):
                selected={t.token_id for t in part}
                if marker:return not (required & selected)
                missing=required-selected
                if not remaining_parts:return not missing
                if not remaining_contiguous:
                    rest={t.token_id for t in tokens}-selected-excluded
                    return bool(rest) and missing<=rest
                # These producers have two parts. The remaining one must be
                # a nonempty span that can own every still required token.
                # No meaning or preferred boundary is inferred here.
                run=set()
                for token in tokens:
                    if token.token_id in selected or token.token_id in excluded:
                        if run and missing<=run:return True
                        run=set()
                    else:run.add(token.token_id)
                return bool(run) and missing<=run
        return span(self.state,self.release,self.selector,self.region,tokens,self.cfg,slot,question,
                    admissible=admissible,**kwargs)

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
                proposal=propose(self)
                if proposal is None:return None
                if not self.required<={t.token_id for g in proposal.groups for t in g}:
                    self.state.diag('INTEGRITY_ERROR','partition producer lost required content')
                    return None
                result=confirm_partition(self.state,self.release,self.selector,self.region,
                    self.tokens,self.cfg,self.kind,proposal.groups,self.proof,shared_functions=proposal.shared_functions)
                if on_check:on_check(proposal,result)
                return proposal,result
            if runtime:
                def dispatched():
                    begin=len(self.state.syntax_trace)
                    value=compute()
                    probes=[r['decision_ref'] for r in self.state.syntax_trace[begin:]
                            if r.get('kind')=='STRUCTURAL_TASK' and r.get('decision_ref')]
                    return value,probes
                result,probes=runtime.dispatcher.run(key,
                    [self.tokens,self.cfg,runtime.input_signature(),runtime.context_signature(),
                     runtime.tasks.feedback,runtime.domain_feedback,self.proof,self.constraints],dispatched,
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
                if self.constraints:
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
            'decision_ref':decision_ref,'selection_provisional':True})
