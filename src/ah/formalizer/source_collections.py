"""A jointly collected occurrence set is not a domain of alternative readings."""
from copy import deepcopy
from dataclasses import dataclass,asdict


@dataclass(frozen=True)
class CollectionReceipt:
    source_refs: tuple
    selected_refs: tuple
    excluded_refs: tuple
    proofs: tuple
    completion_reason: str
    completion_proof: dict | None = None
    multiplicity: str = 'COMPATIBLE_OCCURRENCES'
    completion_scope: str = 'SELECTED_SOURCE_SET'
    selected_set_complete: bool = True
    search_complete: bool = False
    interpretation_complete: bool = False

    def record(self):return deepcopy(asdict(self))


def valid(state,row):
    from .structural_tasks import licensed_in_scope as licensed
    from .task_contracts import SelectionPurpose
    source=row.get('source_refs',());selected=row.get('selected_refs',());excluded=row.get('excluded_refs',())
    if (row.get('multiplicity')!='COMPATIBLE_OCCURRENCES'
            or row.get('completion_scope')!='SELECTED_SOURCE_SET'
            or row.get('selected_set_complete') is not True
            or row.get('search_complete') is not False
            or row.get('interpretation_complete') is not False):return False
    if (not selected or len(set(source))!=len(source) or len(set(selected))!=len(selected)
            or len(set(excluded))!=len(excluded) or not set(selected)|set(excluded)<=set(source)
            or set(selected)&set(excluded)):return False
    if not set(source)<={t.token_id for t in state.evidence}:return False
    proofs=row.get('proofs',())
    if not proofs or not all(licensed(state,p) for p in proofs):return False
    if row.get('completion_reason')=='ALL_AVAILABLE_OCCURRENCES':
        return set(selected)==set(source)-set(excluded) and row.get('completion_proof') is None
    if row.get('completion_reason')=='NO_SUPPORTED_ADDITION':
        proof=row.get('completion_proof')
        return (proof in proofs and proof.get('candidate_id')=='DONE'
            and proof.get('selection_purpose')==SelectionPurpose.NEXT.value
            and licensed(state,proof))
    return False


def choose_with_dependent(state, release, selector, region, tokens, cfg, *, slot,
                          dependent_slot, empty_id, select_dependent, question,
                          exclude=(), prerequisites=()):
    """Revise one collected set when its dependent returns a licensed empty result."""
    from .probe_prerequisites import accepted
    from .structural_tasks import choose, licensed_in_scope, source_set

    exhausted = set()
    premises = prerequisites

    while True:
        material = source_set(state, release, selector, region, tokens, cfg, slot, question,
                              exclude=exclude, prerequisites=premises)
        if material is None:
            return None
        words, proofs = material
        refs = [word.token_id for word in words]
        exact_set = frozenset(refs)
        # A rejected whole set may still be the first piece of a valid union.
        # Detect repetition only after the collection has completed.
        if exact_set in exhausted:
            state.diag('STRUCTURAL_REVISION_NO_PROGRESS', region.region_id)
            return None
        dependent = select_dependent(words, proofs)
        if dependent is None:
            return None
        value, proof = dependent
        if value['candidate_id'] != empty_id:
            return words, proofs, dependent
        if not licensed_in_scope(state, proof, **value):
            return None
        exhausted.add(exact_set)
        addressed = ', '.join(f'«{word.span}» @{word.start}' for word in words)
        option = {'candidate_id': 'REVISE', 'source_slot': slot, 'source_refs': refs,
                  'dependent_slot': dependent_slot,
                  'label': f'Reconsider the source words {addressed}. Select a different expression.'}
        revision = choose(
            state, release, selector, region, cfg, 'structural_ownership_revision', [option],
            'Does the source support revising the selected words? The earlier choice has no '
            'supported continuation under its current boundaries. A different expression can '
            'overlap those words. A failed search alone does not justify a correction.',
            prerequisites=(*prerequisites, accepted(dependent_slot, dependent)))
        if revision is None:
            return None
        premises = (*prerequisites, accepted('structural_ownership_revision', revision))
