"""Snapshot of the produced reference union, not a language-completeness claim."""
from .canonical_ledger import digest


def snapshot(state, constraint, decision):
    rows,receipt=inspect(state,constraint,decision)
    return rows, not receipt['enumeration_complete'], digest([constraint,rows,receipt])


def inspect(state, constraint, decision):
    from .nominal_reference_source import rows as entities
    from .nominal_reference_local import rows as places
    read=state.observation.get('nominal_reference_reads',{}).get(decision,{})
    from .nominal_group_source import domain as groups
    source=entities(state,constraint)
    from .nominal_reference_chain import rows as mentions
    group_rows,obligations=groups(state,constraint,source)
    rows=[*source,*group_rows,*places(state,constraint),*read.get('rows',[]),*mentions(state,constraint)]
    obligations=[{'producer':'LOCAL_GROUP',**row} for row in obligations]
    if not read or read.get('search_incomplete'):
        obligations.append({'producer':'ACTIVE_MEMORY','decision_ref':decision,
            'reason':'SOURCE_UNAVAILABLE' if not read else 'SOURCE_SEARCH_INCOMPLETE'})
    return rows,{'enumeration_scope':'PRODUCED_REFERENCE_UNION_ONLY',
        'enumeration_complete':not obligations,'obligations':obligations,
        'memory_read':read,'language_complete':False}
