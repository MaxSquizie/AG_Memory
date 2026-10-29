"""Snapshot of the produced reference union, not a language-completeness claim."""
from .canonical_ledger import digest


def snapshot(state, constraint, decision):
    from .nominal_reference_source import rows as entities
    from .nominal_reference_local import rows as places
    read=state.observation.get('nominal_reference_reads',{}).get(decision,{})
    rows=[*entities(state,constraint),*places(state,constraint),*read.get('rows',[])]
    incomplete=not read or bool(read.get('search_incomplete'))
    return rows, bool(incomplete), digest([constraint,rows,read])
