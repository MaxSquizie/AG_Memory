"""Run-local function inventories depend on addressed parent requirements.

Completed discovery can be reused only with the same source set and inputs.
A recomputation retires the previous inventory for that area, including partial
rows. Downstream consumers never read retired function proposals.
"""
from .canonical_ledger import digest


def identity(state,kind,tokens,constraints=None):
    from .composition_session import current
    runtime=current(state)
    refs=tuple(t.token_id for t in tokens)
    signature=digest([refs,constraints,runtime.input_signature() if runtime else None,
                      runtime.context_signature() if runtime else None,
                      runtime.domain_feedback if runtime else None])
    return kind,refs,signature


def begin(state,kind,tokens,constraints=None):
    kind,refs,signature=identity(state,kind,tokens,constraints)
    previous=[r for r in state.syntax_trace if r.get('inventory_kind')==kind and r.get('inventory_tokens')==list(refs)]
    if any(completed(r) and r['inventory_signature']==signature for r in previous):
        return None
    for row in previous:row['superseded']=True
    return {'inventory_kind':kind,'inventory_tokens':list(refs),'inventory_signature':signature}


def complete(state,metadata):
    state.syntax_trace.append({'kind':'FUNCTION_INVENTORY',**metadata,'inventory_complete':True,
        'multiplicity':'COMPATIBLE_FUNCTIONS','completion_scope':'DECLARED_FUNCTION_INVENTORY',
        'interpretation_complete':False})


def active(row):
    return not row.get('superseded',False)


def completed(row):
    return (row.get('kind')=='FUNCTION_INVENTORY' and row.get('inventory_complete') is True
        and row.get('multiplicity')=='COMPATIBLE_FUNCTIONS'
        and row.get('completion_scope')=='DECLARED_FUNCTION_INVENTORY'
        and row.get('interpretation_complete') is False and active(row))
