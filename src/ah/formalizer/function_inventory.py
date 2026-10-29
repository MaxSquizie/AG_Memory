"""Function inventories retain task identity and positive/negative dependencies."""
from copy import deepcopy
from .canonical_ledger import digest


class InventoryUnavailable(ValueError):
    pass


def source_basis(state):
    return digest([state.source_uid,state.interpretation_version,state.text])


def identity(state,kind,tokens,constraints=None):
    from .composition_session import current
    runtime=current(state)
    refs=tuple(t.token_id for t in tokens)
    signature=digest([source_basis(state),refs,constraints,runtime.input_signature() if runtime else None,
                      runtime.context_signature() if runtime else None,
                      runtime.domain_feedback if runtime else None])
    return kind,refs,signature


def completed(row):
    return (row.get('kind')=='FUNCTION_INVENTORY' and row.get('inventory_complete') is True
        and row.get('multiplicity')=='COMPATIBLE_FUNCTIONS'
        and row.get('completion_scope')=='DECLARED_FUNCTION_INVENTORY'
        and row.get('interpretation_complete') is False and active(row))


def active(row):
    return not row.get('superseded',False)


def unit_hash(row):
    return digest({k:v for k,v in row.items() if k!='superseded'})


def live(state,row):
    from .structural_tasks import licensed
    if (not completed(row) or row.get('source_basis')!=source_basis(state)
            or 'inventory_ref' not in row or 'unit_hashes' not in row):return False
    units={r['unit_ref']:unit_hash(r) for r in state.syntax_trace
        if r.get('inventory_ref')==row['inventory_ref'] and r.get('kind') in {'NOMINAL_FUNCTION','TEMPORAL_FUNCTION'} and active(r)}
    return units==row['unit_hashes'] and all(licensed(state,p) for p in row.get('proofs',()))


def current(state,kind,tokens,constraints=None,*,require=False):
    kind,refs,signature=identity(state,kind,tokens,constraints)
    previous=[r for r in state.syntax_trace if r.get('inventory_kind')==kind and r.get('inventory_tokens')==list(refs)]
    match=next((r for r in reversed(previous) if r.get('inventory_signature')==signature and live(state,r)),None)
    if match is None and require and previous:
        raise InventoryUnavailable(kind+': function inventory inputs or dependencies changed')
    return match


def begin(state,kind,tokens,constraints=None):
    kind,refs,signature=identity(state,kind,tokens,constraints)
    if current(state,kind,tokens,constraints) is not None:return None
    previous=[r for r in state.syntax_trace if r.get('inventory_kind')==kind and r.get('inventory_tokens')==list(refs)]
    for row in previous:row['superseded']=True
    return {'inventory_kind':kind,'inventory_tokens':list(refs),'inventory_signature':signature,
        'source_basis':source_basis(state),'inventory_ref':'inventory:'+digest([kind,refs,signature,len(previous)])}


def complete(state,metadata,completion_proof=None):
    from .structural_tasks import licensed
    if metadata.get('source_basis')!=source_basis(state):
        state.diag('FUNCTION_INVENTORY_UNRESOLVED','source changed during inventory preparation');return False
    units=[r for r in state.syntax_trace if r.get('inventory_ref')==metadata['inventory_ref']
        and r.get('kind') in {'NOMINAL_FUNCTION','TEMPORAL_FUNCTION'} and active(r)]
    if completion_proof is None and (metadata['inventory_kind']!='TEMPORAL' or
            {ref for r in units for ref in r.get('token_refs',())}!=set(metadata['inventory_tokens'])):
        state.diag('FUNCTION_INVENTORY_UNRESOLVED','missing enumeration completion proof');return False
    proofs=[p for r in units for p in r.get('proofs',())]
    if completion_proof is not None:proofs.append(completion_proof)
    proofs=list({digest(p):deepcopy(p) for p in proofs}.values())
    if not all(licensed(state,p) for p in proofs):
        state.diag('FUNCTION_INVENTORY_UNRESOLVED',metadata['inventory_ref']);return False
    state.syntax_trace.append({'kind':'FUNCTION_INVENTORY',**metadata,'inventory_complete':True,
        'multiplicity':'COMPATIBLE_FUNCTIONS','completion_scope':'DECLARED_FUNCTION_INVENTORY',
        'interpretation_complete':False,'proofs':proofs,
        'completion_proof':deepcopy(completion_proof),
        'unit_hashes':{r['unit_ref']:unit_hash(r) for r in units}})
    return True


def unit_live(state,unit):
    if not active(unit) or not unit.get('inventory_ref'):return False
    receipt=next((r for r in reversed(state.syntax_trace) if r.get('inventory_ref')==unit['inventory_ref'] and completed(r)),None)
    return bool(receipt and live(state,receipt) and receipt['unit_hashes'].get(unit.get('unit_ref'))==unit_hash(unit))


def require_unit(state,unit):
    if not unit_live(state,unit):raise InventoryUnavailable('function snapshot is no longer licensed')


def attach(state,tokens,cfg,frames):
    refs=[]
    for kind in ('NOMINAL','TEMPORAL'):
        receipt=current(state,kind,tokens,cfg.get('_task_constraints'),require=True)
        if receipt:refs.append(receipt['inventory_ref'])
    for frame in frames:
        frame.semantic['function_inventory_refs']=list(dict.fromkeys([
            *frame.semantic.get('function_inventory_refs',()),*refs]))
    return frames


def frame_live(state,frame):
    receipts={r.get('inventory_ref'):r for r in state.syntax_trace if r.get('kind')=='FUNCTION_INVENTORY'}
    if any(ref not in receipts or not live(state,receipts[ref])
           for ref in frame.semantic.get('function_inventory_refs',())):return False
    return all(unit_live(state,u) for u in frame.semantic.get('temporal_functions',()))
