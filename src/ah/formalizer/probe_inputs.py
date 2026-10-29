"""Explicit semantic inputs at a probe boundary, independent of reply transport.

A declaration verifies supplied evidence and task identity, not the truth of a
model answer or the completeness of a language-domain generator.
"""
from dataclasses import dataclass, asdict
from .canonical_ledger import digest


FOCUS_FAMILIES={'predicate_value':'LEXICAL_READING','spatial_reference':'SPATIAL_REFERENCE',
    'speech_act':'DISCOURSE_ACT','discourse_addressee':'ADDRESSEE','source_assertion':'ASSERTION_SCOPE'}
TASK_SLOTS={'REFERENCE':'reference','IMPLICIT_ARGUMENT':'implicit_argument',
            **{family:slot for slot,family in FOCUS_FAMILIES.items()}}
FOCUS_WORDING={
    'LEXICAL_READING':'Choose only the lexical use of the addressed predicate; preserve its participants, content, negation and modality.',
    'SPATIAL_REFERENCE':'Choose only the antecedent place of the addressed occurrence; preserve its spatial role and surrounding scope.',
    'DISCOURSE_ACT':'Choose only the outer speech act of the displayed accepted expression. Its internal content is fixed, not separately asserted.',
    'ADDRESSEE':'Choose only who is addressed by the specified quoted content; preserve its owner and speaker.',
    'ASSERTION_SCOPE':'Choose only whether the stated dependent content is independently asserted; preserve its accepted internal structure.'}

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
    target_descriptions: tuple = ()

    def record(self):
        return asdict(self)

    def errors(self, state, slot, options, target_range):
        errors=list(self.missing)
        if TASK_SLOTS.get(self.family)!=slot:
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
        if self.family in FOCUS_WORDING:
            expected=tuple('«'+evidence[r].span+'» at characters '+str(evidence[r].start)+':'+str(evidence[r].end)
                           for r in self.target_refs if r in evidence)
            if not self.target_descriptions or self.target_descriptions!=expected:errors.append('TARGET_VIEW_MISMATCH')
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
        if self.family in FOCUS_WORDING:
            return ('Addressed occurrences: '+'; '.join(self.target_descriptions)+'.\nEstablished interpretation (preserve roles and scopes):\n'+self.established+'\n'+FOCUS_WORDING[self.family]+
                ' Several numbers are alternative readings, not a jointly selected group. 0 rejects this page; ? means insufficient evidence.')
        return ('Established interpretation (preserve roles and scopes; it does not assert inner events):\n'+
                self.established+'\n'+('Choose only the participant for the stated omitted role of the addressed predicate. '
                if self.family=='IMPLICIT_ARGUMENT' else 'Choose only the referent of the addressed occurrence. ')+
                'Several numbers mean alternative referents, not a group formed from those individuals. '
                '0 rejects the displayed candidates only; ? means insufficient evidence. ')
