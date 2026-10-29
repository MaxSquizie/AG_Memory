"""Explicit semantic inputs at a probe boundary, independent of reply transport.

A declaration verifies supplied evidence and task identity, not the truth of a
model answer or the completeness of a language-domain generator.
"""
from dataclasses import dataclass, asdict
from .canonical_ledger import digest


@dataclass(frozen=True)
class ProbeInputs:
    family: str
    target_refs: tuple
    source_range: tuple
    source_text: str
    candidate_ids: tuple
    established: str
    basis_signature: str
    missing: tuple = ()
    multiplicity: str = 'ALTERNATIVE_READINGS'
    owner_ref: str | None = None
    requested_role: str | None = None

    def record(self):
        return asdict(self)

    def errors(self, state, slot, options, target_range):
        errors=list(self.missing)
        if {'REFERENCE':'reference','IMPLICIT_ARGUMENT':'implicit_argument'}.get(self.family)!=slot:
            errors.append('TASK_FAMILY_MISMATCH')
        if self.family=='IMPLICIT_ARGUMENT':
            owner=next((f for f in state.frames if f.frame_id==self.owner_ref),None)
            if owner is None or self.requested_role not in owner.semantic.get('implicit_arguments',{}):
                errors.append('OMITTED_ROLE_NOT_ESTABLISHED')
            elif self.target_refs!=(owner.predicate_token_ref,):errors.append('OMITTED_ROLE_OWNER_MISMATCH')
            elif self.requested_role in owner.semantic.get('proposed_roles',{}).values():
                errors.append('OMITTED_ROLE_ALREADY_FILLED')
        if self.multiplicity!='ALTERNATIVE_READINGS':errors.append('UNSUPPORTED_MULTIPLICITY')
        evidence={t.token_id:t for t in state.evidence}
        if not self.target_refs:errors.append('TARGET_MISSING')
        lo,hi=self.source_range
        if not 0<=lo<hi<=len(state.text) or self.source_text!=state.text[lo:hi]:
            errors.append('SOURCE_MISMATCH')
        for ref in self.target_refs:
            t=evidence.get(ref)
            if t is None or not (lo<=t.start<t.end<=hi and target_range[0]<=t.start<t.end<=target_range[1]):
                errors.append('TARGET_NOT_ADDRESSED')
        if self.candidate_ids!=tuple(o['candidate_id'] for o in options):errors.append('DOMAIN_MISMATCH')
        from .reference_structure import signature
        if self.basis_signature!=signature(state):errors.append('STRUCTURE_CHANGED')
        if not self.established:errors.append('STRUCTURE_VIEW_MISSING')
        return tuple(dict.fromkeys(errors))

    def wording(self):
        return ('Established interpretation (preserve roles and scopes; it does not assert inner events):\n'+
                self.established+'\n'+('Choose only the participant for the stated omitted role of the addressed predicate. '
                if self.family=='IMPLICIT_ARGUMENT' else 'Choose only the referent of the addressed occurrence. ')+
                'Several numbers mean alternative referents, not a group formed from those individuals. '
                '0 rejects the displayed candidates only; ? means insufficient evidence. ')
