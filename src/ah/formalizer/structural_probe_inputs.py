"""Checked page obligations shared by addressed structural selectors.

This contract covers the page boundary. Slot-specific semantic obligations and
language-domain coverage remain separate; they are not certified by this type.
"""
from dataclasses import dataclass, asdict
from copy import deepcopy
from .canonical_ledger import digest


def source_signature(state):
    from .composition_dispatcher import canonical
    return digest(canonical([state.source_uid,state.interpretation_version,state.text,
                             state.evidence]))


def parent_signature(state):
    from .composition_session import current
    runtime=current(state)
    return runtime.input_signature() if runtime else None


@dataclass(frozen=True)
class StructuralProbeInputs:
    slot: str
    target_range: tuple
    target_refs: tuple
    source_text: str
    source_signature: str
    parent_signature: str | None
    candidate_payloads: tuple
    question: str
    page: int
    source_selection: object = None
    family: str = 'STRUCTURAL_PAGE'
    multiplicity: str = 'ALTERNATIVE_READINGS'
    negative_scope: str = 'DISPLAYED_PAGE'
    enumeration_scope: str = 'CALLER_GENERATOR'
    declaration_status: str = 'PAGE_DECLARED'

    def record(self):return asdict(self)

    def errors(self,state,slot,options,target_range):
        errors=[]
        if self.family!='STRUCTURAL_PAGE':errors.append('TASK_FAMILY_MISMATCH')
        if not self.source_text.strip():errors.append('SOURCE_MISSING')
        if slot!=self.slot:errors.append('TASK_SLOT_MISMATCH')
        if tuple(target_range)!=self.target_range:errors.append('TARGET_RANGE_MISMATCH')
        if self.source_signature!=source_signature(state):errors.append('SOURCE_CHANGED')
        if self.parent_signature!=parent_signature(state):errors.append('PARENT_CONSTRAINT_CHANGED')
        evidence={t.token_id:t for t in state.evidence}
        lo,hi=self.target_range
        if not self.target_refs or len(set(self.target_refs))!=len(self.target_refs):errors.append('TARGET_MISSING_OR_DUPLICATE')
        for ref in self.target_refs:
            token=evidence.get(ref)
            if token is None or not lo<=token.start<token.end<=hi:errors.append('TARGET_NOT_ADDRESSED')
        presented=[{'candidate_id':v['candidate_id'],'label':v['label']} for v in self.candidate_payloads]
        if presented!=options:errors.append('PAGE_DOMAIN_MISMATCH')
        if not self.question.strip():errors.append('QUESTION_MISSING')
        if self.page<0:errors.append('PAGE_ADDRESS_INVALID')
        if (self.multiplicity!='ALTERNATIVE_READINGS' or self.negative_scope!='DISPLAYED_PAGE'
                or self.enumeration_scope!='CALLER_GENERATOR'):errors.append('PAGE_RESULT_CONTRACT_MISMATCH')
        if self.source_selection is not None:errors.extend(self.source_selection.errors(state,self.candidate_payloads,self.target_refs))
        return tuple(dict.fromkeys(errors))

    def wording(self):
        text=('This is one page of the stated choice. Several numbers express alternative readings '
                'of that same choice, never a jointly selected set. 0 rejects only the displayed page; '
                '? means the evidence is insufficient to decide among these options.')
        return text+(self.source_selection.wording() if self.source_selection is not None else '')


def inputs(state,region,slot,values,question,context,page,source_selection=None):
    return StructuralProbeInputs(slot,tuple(region.source_range),tuple(region.token_refs),context,
        source_signature(state),parent_signature(state),tuple(deepcopy(values)),question,page,source_selection)


@dataclass(frozen=True)
class SourceSelection:
    operation: str
    source_refs: tuple
    selected_refs: tuple
    excluded_refs: tuple
    start_ref: str | None
    descriptions: tuple

    def errors(self,state,values,target_refs):
        domain=set(self.source_refs);selected=set(self.selected_refs);excluded=set(self.excluded_refs)
        errors=[]
        evidence={t.token_id:t for t in state.evidence}
        expected=tuple((ref,'«'+evidence[ref].span+'» at characters '+str(evidence[ref].start)+':'+str(evidence[ref].end))
                       for ref in self.source_refs if ref in evidence)
        if expected!=self.descriptions or not domain<=set(evidence):errors.append('SOURCE_OCCURRENCE_CHANGED')
        if self.operation not in {'START','END','CONTINUE','PIECE_END'}:errors.append('SOURCE_OPERATION_UNKNOWN')
        if len(domain)!=len(self.source_refs):errors.append('SOURCE_DOMAIN_DUPLICATE')
        if not domain<=set(target_refs) or not (selected|excluded)<=domain:errors.append('SOURCE_SCOPE_MISMATCH')
        if selected & excluded:errors.append('SOURCE_OWNERSHIP_CONFLICT')
        if self.operation in {'END','PIECE_END'} and self.start_ref not in domain-selected-excluded:
            errors.append('SOURCE_START_UNAVAILABLE')
        for value in values:
            ref=value.get('token_ref')
            if ref not in domain-selected-excluded:errors.append('SOURCE_CANDIDATE_OUTSIDE_DOMAIN')
            if ref in domain:
                index=self.source_refs.index(ref)
                field='index' if self.operation in {'START','END'} else 'end' if self.operation=='PIECE_END' else None
                if field and value.get(field)!=(index if self.operation=='START' else index+1):
                    errors.append('SOURCE_BOUNDARY_PAYLOAD_MISMATCH')
            if self.operation in {'END','PIECE_END'} and self.start_ref in domain and ref in domain:
                a,b=self.source_refs.index(self.start_ref),self.source_refs.index(ref)
                if b<a or set(self.source_refs[a:b+1]) & (selected|excluded):
                    errors.append('SOURCE_INTERVAL_OUTSIDE_DOMAIN')
        return errors

    def wording(self):
        labels=dict(self.descriptions)
        show=lambda refs:', '.join(labels[r] for r in refs)
        text='\nEach option names one boundary of the SAME expression. Several numbers remain alternative boundary choices; they do not add several fragments at once. '
        if self.selected_refs:text+='Already included occurrences: '+show(self.selected_refs)+'. Preserve them. '
        if self.excluded_refs:text+='Not selectable in this hypothesis: '+show(self.excluded_refs)+'. They remain readable context. '
        if self.start_ref:text+='The current piece starts at '+labels[self.start_ref]+'. '
        return text


def collection(operation,tokens,selected=(),exclude=(),start=None):
    refs=tuple(t.token_id for t in tokens);excluded=set(exclude)
    return SourceSelection(operation,refs,tuple(t.token_id for t in selected),
        tuple(r for r in refs if r in excluded),start,
        tuple((t.token_id,'«'+t.span+'» at characters '+str(t.start)+':'+str(t.end)) for t in tokens))
