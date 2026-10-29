"""Explicit source focus for direct choices over candidate hypotheses.

These are proposed readings, not an already accepted structure. Later semantic
choices use ProbeInputs instead. The caller must address its own question.
"""
from copy import deepcopy
from dataclasses import dataclass,asdict
from .structural_probe_inputs import source_signature,parent_signature
from .reference_structure import signature as structure_signature


@dataclass(frozen=True)
class DirectProbeInputs:
    slot: str
    target_refs: tuple
    target_range: tuple
    source_text: str
    source_basis: str
    parent_basis: str | None
    structure_basis: str
    candidate_payloads: tuple
    question: str
    descriptions: tuple
    declaration_status: str = 'ADDRESSED_SOURCE_DECLARED'
    family: str = 'DIRECT_SOURCE_CHOICE'

    def record(self):return asdict(self)

    def errors(self,state,slot,options,target_range):
        errors=[];evidence={e.token_id:e for e in state.evidence}
        if slot!=self.slot or tuple(target_range)!=self.target_range:errors.append('TASK_ADDRESS_MISMATCH')
        if not self.target_refs or len(set(self.target_refs))!=len(self.target_refs):errors.append('TARGET_MISSING_OR_DUPLICATE')
        for ref in self.target_refs:
            e=evidence.get(ref)
            # A copied content use retains its original source occurrences.
            # The use area and the read-only source focus are different axes;
            # this declaration grants no selection ownership outside the area.
            if e is None or not 0<=e.start<e.end<=len(state.text):errors.append('TARGET_NOT_ADDRESSED')
        expected=tuple('«'+evidence[r].span+'» at characters '+str(evidence[r].start)+':'+str(evidence[r].end) for r in self.target_refs if r in evidence)
        if expected!=self.descriptions:errors.append('TARGET_VIEW_MISMATCH')
        if self.source_text!=state.text or self.source_basis!=source_signature(state):errors.append('SOURCE_CHANGED')
        if self.parent_basis!=parent_signature(state):errors.append('PARENT_CONSTRAINT_CHANGED')
        if self.structure_basis!=structure_signature(state):errors.append('STRUCTURE_CHANGED')
        if list(self.candidate_payloads)!=options:errors.append('CANDIDATE_PAYLOAD_CHANGED')
        return tuple(dict.fromkeys(errors))

    def wording(self):
        return ('Interpretation area: characters '+str(self.target_range[0])+':'+str(self.target_range[1])+'. '
            'Question target source occurrences: '+'; '.join(self.descriptions)+'. '
            'Source focus can refer to reused content outside this use area; it grants no additional source ownership. '
            'The options are candidate interpretations of this addressed material, not established facts. '
            'Preserve separately supplied parent requirements. Several numbers mean alternative readings, '
            'not a combined set. 0 rejects the displayed candidates; ? means insufficient evidence.')


def inputs(state,slot,target_refs,options,source_range,question):
    refs=tuple(target_refs);evidence={e.token_id:e for e in state.evidence}
    descriptions=tuple('«'+evidence[r].span+'» at characters '+str(evidence[r].start)+':'+str(evidence[r].end)
                       for r in refs if r in evidence)
    return DirectProbeInputs(slot,refs,tuple(source_range),state.text,source_signature(state),parent_signature(state),
        structure_signature(state),tuple(deepcopy(options)),question,descriptions)
