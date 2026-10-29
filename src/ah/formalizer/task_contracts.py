"""Provider-neutral receipts. Search completeness is independent of a reply.

These contracts contain only source/candidate data; no store, model, GUI or
network handles. A selected page is evidence, never a closed-domain result.
"""
from dataclasses import dataclass
from enum import Enum
from typing import Any


class TaskOutcome(str, Enum):
    SUPPORTED = 'SUPPORTED'
    PARTIAL = 'PARTIAL'
    MULTIPLE = 'MULTIPLE'
    NONE_FIT = 'NONE_FIT_IN_COMPLETE_DOMAIN'
    GENERATOR_NONE_FIT = 'NONE_FIT_IN_ENUMERATED_GENERATOR'
    PAGE_NONE_FIT = 'NONE_FIT_ON_PAGE'
    UNKNOWN = 'UNKNOWN'
    NOT_APPLICABLE = 'NOT_APPLICABLE'
    INCOMPLETE = 'SEARCH_INCOMPLETE'
    BLOCKED = 'RESOURCE_BLOCKED'


class SelectionPurpose(str, Enum):
    ALTERNATIVE = 'ALTERNATIVE_READING'
    NEXT = 'NEXT_COLLECTION_STEP'
    CONFIRM = 'CONFIRM_PROPOSED_RELATION'

    def wording(self):
        return {
            self.ALTERNATIVE: 'Choose a reading of this one addressed question.',
            self.NEXT: 'Choose the next step of this collection. Several numbers are alternative next steps, not several objects to add together.',
            self.CONFIRM: 'Confirm or reject the single proposed relation. This does not enumerate other possible relations.',
        }[self]


def required_selection_purpose(slot, source_selection=None):
    """Declared consumer obligations, never inferred from question wording."""
    if getattr(source_selection,'operation',None)=='CONTINUE':return SelectionPurpose.NEXT
    if slot in {'nominal_function','temporal_function','structural_function_owner','nominal_coordination_discovery'}:
        return SelectionPurpose.NEXT
    if slot=='structural_partition':return SelectionPurpose.CONFIRM
    return None


@dataclass(frozen=True)
class SelectionReceipt:
    candidates: tuple[str, ...]
    supported: tuple[str, ...]
    search_complete: bool
    source_complete: bool = True
    purpose: SelectionPurpose = SelectionPurpose.ALTERNATIVE

    @property
    def outcome(self):
        if not self.source_complete:return TaskOutcome.BLOCKED
        if not self.search_complete:return TaskOutcome.INCOMPLETE
        if not self.supported:return TaskOutcome.GENERATOR_NONE_FIT
        return TaskOutcome.SUPPORTED if len(self.supported)==1 else TaskOutcome.MULTIPLE

    def record(self):
        return {'candidate_ids':list(self.candidates),'supported_ids':list(self.supported),
                'search_complete':self.search_complete,'source_complete':self.source_complete,
                'enumeration_complete':self.search_complete,
                'enumeration_scope':'CALLER_GENERATOR','interpretation_complete':False,
                'selection_purpose':self.purpose.value,'multiplicity':'ALTERNATIVE_READINGS',
                'task_outcome':self.outcome.value}


@dataclass(frozen=True)
class ProducerContract:
    kind: str
    level: str
    input_sort: str
    output_sort: str
    applicability: str
    completion: str


CONTRACTS={kind:ProducerContract(kind,level,source,target,domain,completion) for kind,level,source,target,domain,completion in [
    ('COMPOSITION','T2','SOURCE_SET_AND_PARENT_SLOT','FRAME_DOMAIN','source functions; bounded recursive search','one globally closed root or retained alternatives'),
    ('GRAMMAR','T2','SOURCE_READINGS','FRAME_DOMAIN','released grammar proposals; not a complete language domain','all rules searched within declared budget'),
    ('MORPHOLOGY','T1_T2','SOURCE_READINGS_AND_USE','READING_DOMAIN','whole source readings and contextual function proposals','unknown features remain unknown'),
    ('AGREEMENT','T1_T2','SOURCE_READINGS_AND_USE','READING_DOMAIN','released form recovery proposals','every proposed replacement needs a source-use proof'),
    ('PARTITION','T2','RELATION_AND_SOURCE_SET','OWNERSHIP_DOMAIN','finite occurrence/function assignments','all required content owned; compatible sharing licensed'),
    ('GOAL_CONTEXT','TD','ADDRESSED_READ','CONTEXT_EVIDENCE','declared frozen context window','read receipt complete independently of candidate count'),
    ('PROBE','T2_TP','CLOSED_OPTIONS_AND_SOURCE','SELECTION','provided options only; page receipt is provisional','validated reply and separate domain completion'),
]}


def probe_contract(slot,closed=False,inputs=None):
    from dataclasses import replace
    from .probe_families import contract
    spec=contract(slot,inputs)
    if spec is not None:
        return replace(CONTRACTS['PROBE'],level=spec.level,input_sort=spec.family+'_INPUT',
                       applicability=spec.object_of_choice,completion=spec.permission+'; '+spec.negative_scope)
    level='T4' if closed else 'TD' if slot in {
        'reference','implicit_argument','discourse_addressee','spatial_reference','nominal_reference'} else 'T1_T2' if slot in {
        'structural_oov_function','predicate_argument_reading','structural_marker_reading','agreement_recovery'} else 'T2_TP'
    return replace(CONTRACTS['PROBE'],level=level)


@dataclass(frozen=True)
class TaskResult:
    value: Any
    outcome: TaskOutcome
    search_complete: bool
    source_complete: bool
    alternatives: tuple = ()
    structure_complete: bool = False
    write_eligible: bool = False


def produced(kind,value,diagnostics=()):
    if isinstance(value,TaskResult):return value
    codes={d.code for d in diagnostics}
    if codes & {'RESOURCE_MISSING','VALENCY_UNKNOWN','INTEGRITY_ERROR','PROVIDER_UNAVAILABLE','COMPONENT_PROBE_FAILED'}:
        return TaskResult(value,TaskOutcome.BLOCKED,False,False)
    if any('INCOMPLETE' in c or c=='COMPUTATION_LIMIT' for c in codes):
        return TaskResult(value,TaskOutcome.INCOMPLETE,False,True)
    if kind=='COMPOSITION' and isinstance(value,list):
        from .composition_tree import roots
        partial=[f for f in roots(value) if f.semantic.get('partial_composition')]
        if len(partial)==1:
            record=partial[0].semantic['partial_composition']
            return TaskResult(value,TaskOutcome.PARTIAL,True,True,tuple(record['choices']),True,False)
        alternatives=tuple(f.frame_id for f in value if f.semantic.get('composition_domain'))
        if alternatives:return TaskResult(value,TaskOutcome.MULTIPLE,True,True,alternatives)
        from .composition_tree import roots
        if len(roots(value))!=1:return TaskResult(value,TaskOutcome.UNKNOWN,False,True)
        return TaskResult(value,TaskOutcome.SUPPORTED,True,True,structure_complete=True)
    if value is None or value is False:return TaskResult(value,TaskOutcome.UNKNOWN,False,True)
    return TaskResult(value,TaskOutcome.SUPPORTED,True,True)
