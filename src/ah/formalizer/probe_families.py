"""Semantic obligations of native closed-selection families.

The registry declares the decision object and permission conveyed by an answer;
it does not certify completeness of a language generator or model reliability.
"""
from dataclasses import dataclass,asdict

@dataclass(frozen=True)
class SelectionContract:
    family: str
    object_of_choice: str
    level: str
    required_data: tuple = ('addressed_source','explicit_question','distinguishable_candidates','current_parent_constraints')
    multiplicity: str = 'ALTERNATIVE_READINGS'
    negative_scope: str = 'DISPLAYED_CANDIDATES'
    permission: str = 'PROVISIONAL_SELECTION_ONLY'
    incomplete: str = 'NO_SELECTION'
    def record(self):return asdict(self)

FAMILIES={}
def register(family,object_of_choice,level,slots):
    spec=SelectionContract(family,object_of_choice,level)
    for slot in slots.split():
        if slot in FAMILIES:raise ValueError('DUPLICATE_PROBE_SLOT')
        FAMILIES[slot]=spec

register('SOURCE_BOUNDARY','boundary or grouping of addressed source material','T2',
 'structural_source_boundary composition_boundary clause_boundary temporal_boundary document_scope coordination_boundary')
register('STRUCTURAL_READING','remaining structural reading under existing assignments','T2',
 'component_attachment structural_attachment structure_attachment child_slot attitude_attachment structural_refinement')
register('NOMINAL_READING','reading, attachment or grouping of addressed nominal material','T2',
 'nominal_attachment nominal_dependency nominal_coordination referent_constraint')
register('LEXICAL_READING','lexical use in the retained structure','T4','predicate_value')
register('MORPHOLOGICAL_READING','whole linguistic reading of an addressed occurrence','T1_T2',
 'lexical_recovery structural_oov_function predicate_argument_reading relative_marker_reading structural_marker_reading nominal_external_case')
register('PARTICIPANT_ROLE','role or participant presence in one predicate or description','T2',
 'predicate_subject_presence predicate_argument_role relative_argument_role relative_pronoun_role structural_description_role spatial_role')
register('SOURCE_FUNCTION','source function, not occurrence of a world event','T2',
 'predicate_function nominal_function nominal_identity_function temporal_function spatial_function relation_marker_role quantifier_source_functions structural_description_binding structural_description_marker')
register('HEAD_OR_OWNER','source head or owner of the specified content','T2',
 'infinitive_head nominal_function_head structural_binder_head structural_owner structural_function_owner structural_event_head structural_governor')
register('RELATION','relation between displayed source parts','T2',
 'structural_relation structural_partition infinitive_link structural_content_role structural_control')
register('CONTENT_REFERENCE','presence, source, reuse mode or control of referenced content','T2',
 'content_reference_presence content_reference_source content_reference_kind content_reference_control omitted_content_presence')
register('SCOPE','attachment or assertion scope preserving content interiors','T2_T4',
 'modifier_scope temporal_scope source_assertion')
register('DISCOURSE','utterance act or addressee of speech content','T2_T4','speech_act discourse_addressee')
register('REFERENCE','referent of the addressed occurrence','TD_T4','reference spatial_reference')
register('IMPLICIT_ARGUMENT','participant for a licensed omitted role of one predicate','TD_T4','implicit_argument')
register('REVISION','explicit revision preserving unrelated assignments','T2',
 'structural_revision structural_marker_revision structural_ownership_revision')
SOURCE_COLLECTION=SelectionContract('SOURCE_COLLECTION','boundary of the same collected expression','T2',
 ('addressed_source','explicit_question','distinguishable_candidates','current_parent_constraints',
  'already_selected_occurrences','excluded_occurrences','current_piece_start'))

def contract(slot,inputs=None):
    if inputs is not None and getattr(inputs,'source_selection',None) is not None:return SOURCE_COLLECTION
    return FAMILIES.get(slot)

def errors(state,slot,options,context,bounds,question,inputs=None):
    spec=contract(slot,inputs)
    # Explicit custom pages declare only page guarantees, not a registered
    # semantic family. Native literal slots are checked by the source inventory.
    if spec is None:
        return () if getattr(inputs,'family',None)=='STRUCTURAL_PAGE' else ('PROBE_FAMILY_UNDECLARED',)
    out=[]
    if not isinstance(question,str) or not question.strip():out.append('QUESTION_MISSING')
    if not isinstance(context,str) or not context.strip():out.append('SOURCE_MISSING')
    if (len(bounds)!=2 or any(type(n) is not int for n in bounds)
            or not 0<=bounds[0]<bounds[1]<=len(state.text)):out.append('TARGET_RANGE_INVALID')
    ids=[]
    for o in options:
        if not isinstance(o.get('candidate_id'),str) or not o['candidate_id']:out.append('CANDIDATE_ADDRESS_MISSING')
        if not isinstance(o.get('label'),str) or not o['label'].strip():out.append('CANDIDATE_VIEW_MISSING')
        ids.append(o.get('candidate_id'))
    if len(set(ids))!=len(ids):out.append('CANDIDATE_ADDRESS_DUPLICATE')
    return tuple(dict.fromkeys(out))
