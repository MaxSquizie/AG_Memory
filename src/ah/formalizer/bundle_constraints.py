"""Addressed semantic requirements, independent of the active composition session.

Liveness, known disagreement and missing information are different outcomes.
The checker never selects a reading or excludes a generator domain.
"""
from copy import deepcopy
from .composition_dispatcher import canonical
from .canonical_ledger import digest

FIELDS=('lemma','pos','cases','number','gender','tense','person','mood','features')


def compare_reading(actual,expected):
    """Compare one WHOLE alternative; never combine features across alternatives."""
    if actual is None:return 'UNKNOWN'
    unknown=False
    for field in FIELDS:
        wanted=expected.get(field)
        if wanted in (None,'',[],(),set(),frozenset()):continue
        got=actual.get(field)
        if got in (None,'',[],(),set(),frozenset()):unknown=True;continue
        if field in {'cases','features'}:
            left,right=set(got),set(wanted)
            if left==right:continue
            if field=='cases' and left.isdisjoint(right):return 'CONFLICT'
            # Overlapping case domains or non-exhaustive feature sets do not
            # prove incompatible complete readings.
            unknown=True
        elif got!=wanted:return 'CONFLICT'
    return 'UNKNOWN' if unknown else 'SATISFIED'


def select_records(state,region_ref,task_scope,condition=None):
    # Latest declaration wins only at the same exact use address. Retirement
    # is checked later and cannot silently erase the obligation.
    records={}
    from .structural_conditions import resolve
    allowed={None};current=condition
    while current:
        ref=current['condition_ref']
        if ref in allowed:break
        allowed.add(ref)
        try:parent=resolve(state,current).parent_condition_ref
        except (KeyError,ValueError):break
        current={'condition_ref':parent} if parent else None
    declarations={r['task_ref']:r for r in state.syntax_trace if r.get('kind')=='TASK_DOMAIN'}
    for row in state.syntax_trace:
        if row.get('kind') not in {'ESTABLISHED_PREDICATE_ROLE','PARTIAL_READING_DOMAIN'}:continue
        if row.get('region_ref')!=region_ref or row.get('task_scope')!=task_scope:continue
        domain_ref=row.get('domain_ref') or row.get('proof',{}).get('domain_ref')
        branch=declarations.get(domain_ref,{}).get('branch_condition')
        if branch and branch.get('condition_ref') not in allowed:continue
        records[(row['kind'],row['predicate_ref'],row['token_ref'])]=row
    return list(records.values())


def required_inventory_refs(state,region_ref,task_scope,token_refs,frames,condition=None):
    required={ref for f in frames for ref in f.semantic.get('function_inventory_refs',())}
    for row in state.syntax_trace:
        if (row.get('kind')=='FUNCTION_INVENTORY' and row.get('inventory_kind')=='NOMINAL'
                and row.get('inventory_tokens')==list(token_refs)
                and row.get('region_ref')==region_ref and row.get('task_scope')==task_scope
                and row.get('branch_condition')==condition and not row.get('superseded')):
            required.add(row['inventory_ref'])
    return required


def inspect(state,region_ref,task_scope,token_refs,frames,condition=None,*,nominal=True,require_nominal_projection=False):
    from .structural_tasks import _licensed
    from .partial_readings import valid_domain
    from .structural_conditions import historical,allows
    from .function_inventory import live as inventory_live,unit_hash
    conflicts=[];unknown=[];stale=[];invalid_outputs=[]
    def add(target,kind,row,frame=None,actual=None):
        target.append({'kind':kind,'region_ref':region_ref,'task_scope':task_scope,
            'frame_ref':frame.frame_id if frame else None,'predicate_ref':row.get('predicate_ref'),
            'token_ref':row.get('token_ref',row.get('head_ref')),
            'requirement':deepcopy(row),'actual':deepcopy(actual)})
    if condition is not None and not historical(state,condition):
        add(stale,'CONDITION_RETIRED',{'condition':condition})
    def relevant(row):
        token=row['token_ref']
        return [f for f in frames if f.predicate_token_ref==row['predicate_ref'] and
            (token in f.argument_token_refs or token in f.semantic.get('proposed_roles',{})
             or token in f.semantic.get('morph_bindings',{}))]
    for row in select_records(state,region_ref,task_scope,condition):
        domain=row.get('kind')=='PARTIAL_READING_DOMAIN'
        if domain:
            declaration=next((r for r in reversed(state.syntax_trace) if r.get('kind')=='TASK_DOMAIN'
                and r.get('task_ref')==row.get('domain_ref')),None)
            branch=declaration.get('branch_condition') if declaration else None
            licensed=(valid_domain(state,row) and (branch is None or condition is not None and allows(state,branch,condition))
                and all(v.get('predicate_ref')==row['predicate_ref'] and v.get('token_ref')==row['token_ref']
                        and v.get('role')==row['role'] for v in row.get('alternatives',())))
        else:
            licensed=_licensed(state,row['proof'],_branch=condition,predicate_ref=row['predicate_ref'],
                               token_ref=row['token_ref'],candidate_id=row['role'])
        if not licensed:
            add(stale,'READING_DOMAIN_RETIRED' if domain else 'ROLE_PROOF_RETIRED',row);continue
        used=relevant(row);expected=row['role']
        if not used and (expected!='NO_DIRECT_ROLE' or domain or row.get('reading')):add(unknown,'ROLE_USE_UNESTABLISHED',row)
        for frame in used:
            actual=frame.semantic.get('proposed_roles',{}).get(row['token_ref'])
            if expected=='NO_DIRECT_ROLE':
                if actual is not None:add(conflicts,'DIRECT_ROLE_FORBIDDEN',row,frame,actual)
            elif actual is None:add(unknown,'ROLE_UNESTABLISHED',row,frame)
            elif actual!=expected:add(conflicts,'ROLE_CONFLICT',row,frame,actual)
            if not domain and row.get('reading'):
                add(unknown,'READING_PROVENANCE_UNKNOWN',row,frame)
            readings=[v['reading'] for v in row['alternatives']] if domain else []
            if readings:
                actual_reading=frame.semantic.get('morph_bindings',{}).get(row['token_ref'])
                checks=[compare_reading(actual_reading,r) for r in readings]
                if all(c=='CONFLICT' for c in checks):add(conflicts,'WHOLE_READING_CONFLICT',row,frame,actual_reading)
                else:
                    from .morphology_domain import clean
                    if actual_reading is None or clean(actual_reading) not in [clean(r) for r in readings]:
                        add(unknown,'READING_UNESTABLISHED',row,frame,actual_reading)
    if nominal:
        inventories={r['inventory_ref']:r for r in state.syntax_trace if r.get('kind')=='FUNCTION_INVENTORY'}
        required=required_inventory_refs(state,region_ref,task_scope,token_refs,frames,condition)
        units={(r['inventory_ref'],r['unit_ref']):r for r in state.syntax_trace if r.get('kind')=='NOMINAL_FUNCTION'}
        for ref in sorted(required):
            inventory=inventories.get(ref)
            if inventory is None or not inventory_live(state,inventory,condition=condition):
                add(stale,'FUNCTION_INVENTORY_RETIRED',{'inventory_ref':ref});continue
            for unit_ref,stamp in inventory['unit_hashes'].items():
                unit=units.get((ref,unit_ref))
                if unit is None:
                    if inventory['inventory_kind']=='NOMINAL':add(stale,'NOMINAL_UNIT_MISSING',{'inventory_ref':ref,'unit_ref':unit_ref})
                    continue
                if unit.get('inventory_ref')!=ref or unit_hash(unit)!=stamp:
                    add(stale,'NOMINAL_UNIT_CHANGED',unit);continue
                kind=unit['function']
                if kind=='REFERENCE':
                    candidates=[(f,u.get('reference_constraint',{})) for f in frames
                        for u in f.semantic.get('lexical_units',{}).values()
                        if u.get('reference_constraint',{}).get('head_ref')==unit['head_ref']
                        and u.get('reference_constraint',{}).get('function_refs')==unit['function_refs']]
                    fields=('function_refs','identity_constraint')
                elif kind=='QUANTITY':
                    candidates=[(f,g) for f in frames for g in f.semantic.get('qualitative_groups',()) if g.get('head_ref')==unit['head_ref'] and g.get('quantity_token_refs')==unit['function_refs']]
                    fields=()
                else:
                    continue  # RELATION ownership is a separate contract family.
                if not candidates:
                    add(invalid_outputs if require_nominal_projection else unknown,
                        'NOMINAL_FUNCTION_PROJECTION_MISSING',unit)
                for frame,actual in candidates:
                    if kind=='REFERENCE':
                        for field in fields:
                            if actual.get(field) is None:add(unknown,'REFERENCE_FIELD_UNKNOWN',unit,frame,actual)
                            elif actual[field]!=unit[field]:add(conflicts,'REFERENCE_FUNCTION_CONFLICT',unit,frame,actual)
                    else:
                        if actual.get('quantity_token_refs') is None:add(unknown,'QUANTITY_SOURCE_UNKNOWN',unit,frame,actual)
                        elif actual['quantity_token_refs']!=unit['function_refs']:add(conflicts,'QUANTITY_FUNCTION_CONFLICT',unit,frame,actual)
                        cases=set(actual.get('external_cases') or ())
                        if not cases:add(unknown,'QUANTITY_CASE_UNKNOWN',unit,frame,actual)
                        elif unit.get('external_case') and unit['external_case'] not in cases:add(conflicts,'QUANTITY_CASE_CONFLICT',unit,frame,actual)
    status='STALE_EVIDENCE' if stale else 'CONTRACT_CONFLICT' if conflicts else 'OPEN_REQUIREMENTS' if unknown else 'INVALID_PRODUCER_OUTPUT' if invalid_outputs else 'REQUIREMENTS_SATISFIED'
    return {'status':status,'conflicts':conflicts,'unknowns':unknown,'stale':stale,'invalid_outputs':invalid_outputs}


def signature(result):return digest(canonical(result))
