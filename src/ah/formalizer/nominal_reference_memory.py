"""Frozen Ignition reads for referential noun groups; no global name matching."""
from copy import deepcopy
from .canonical_ledger import digest


def groups(state):
    result = {}
    for frame in state.frames:
        # A grounded noun-group reading can ask memory while its external
        # attachment is still unresolved. This does not license that fragment.
        for unit in frame.semantic.get('lexical_units',{}).values():
            row = unit.get('reference_constraint')
            if row:
                result.setdefault(row['decision_ref'], (unit['mention_ref'], row))
    return result


def requests(state):
    for key, (mention, row) in groups(state).items():
        yield {'kind':'NOMINAL_REFERENCE', 'decision_ref':key+'|referent',
               'source_range':row['source_range'], 'cue_token_refs':row['anchor_refs'],
               'mention_ref':mention, 'constraint':deepcopy(row)}


def read_active(store, release, active_refs, source_tags=()):
    from .coreference import freeze_context
    from .spatial_memory import read_active as places
    rows = freeze_context(store,release,source_tags,active_refs=active_refs)
    # This channel currently binds entity slots only; event references retain
    # their separately typed EVENT_REFERENCE contract.
    rows = [dict(r, memory_binding_ref=r['binding_ref']) for r in rows
            if r.get('reference_kind') != 'EVENT']
    spatial, incomplete = places(store,release,active_refs,source_tags)
    rows.extend(dict(r, label=r.get('memory_excerpt',r['raw']), features=[],
                     reference_kind='PLACE', premise_support_refs=[]) for r in spatial)
    if len(rows)>32:
        return [], True
    return rows, incomplete


def attach(state, request, result):
    state.observation.setdefault('nominal_reference_reads',{})[request['decision_ref']] = {
        'rows':deepcopy([r for r in result['rows'] if r['source_tag'][0]!=state.source_uid]), 'context_read_hash':digest(result),
        'search_incomplete':bool(result.get('search_incomplete'))}


def resolve(state, release, selector):
    from .component_probe import _probe
    # Bindings are derived results of THIS complete resolution pass. An earlier
    # successful selection must not survive a missing/ambiguous new result.
    current=groups(state)
    active={key+'|referent' for key in current}
    for old in state.observation.get('nominal_reference_bindings',{}).values():
        if old['interpretation_decision_ref'] not in active:
            unresolve(state,old['interpretation_decision_ref'],'REFERENCE_TASK_REMOVED')
    state.observation['nominal_reference_bindings']={}
    for key, (mention, constraint) in current.items():
        decision = key+'|referent'
        read = state.observation.get('nominal_reference_reads',{}).get(decision,{})
        from .nominal_reference_local import rows as local_rows
        rows = [*local_rows(state,constraint),*read.get('rows',[])]
        incomplete=not read or bool(read.get('search_incomplete')) or len(rows)>32
        from .reference_presentation import label
        options = [{'candidate_id':'antecedent:'+str(i),
            'label':label(state,[r])+
                    '; features='+str(r.get('features',[]))} for i,r in enumerate(rows)]
        chosen = None;probed=False
        if rows and not incomplete:
            start,end=constraint['source_range']
            from .regions import reference_goal
            goal=reference_goal(state,constraint['head_ref'])
            lo,hi=goal['source_range']
            context=state.text[lo:hi]
            if len(context)>2048:incomplete=True
            else:
                from .reference_structure import inputs
                probed=True
                chosen = _probe(state,selector,release,decision,'reference',options,context,(start,end),
                    inputs=inputs(state,(constraint['head_ref'],),options),
                    equivalent_targets={o['candidate_id']:r['entity_ref'] for o,r in zip(options,rows)},
                    question='Resolve «'+constraint['raw']+'» as one noun group. Constraint='+
                    constraint['identity_constraint']+'. Select only a compatible antecedent supported by these source excerpts. '+
                    'Proximity and name spelling alone do not prove identity. An already introduced unnamed or relative place is a valid antecedent: unknown coordinates/name do not make its reference unresolved. '
                    'Choose the existing referent, not a new object. If several antecedents fit, list their numbers; use ? when evidence is insufficient to assess them.')
        by_id={o['candidate_id']:r for o,r in zip(options,rows)}
        if chosen in by_id:
            row=by_id[chosen]
            from .state import Ground
            from .reference_structure import signature
            state.decisions[decision].grounds.append(Ground('D' if row.get('local_spatial_anchor') else 'P',
                'local source anchor: '+row['memory_binding_ref'] if row.get('local_spatial_anchor') else
                'frozen active-workspace binding: '+row['memory_binding_ref'],chosen))
            state.observation.setdefault('nominal_reference_bindings',{})[mention]={
                'target_ref':row['entity_ref'], 'anchor_binding_ref':row['memory_binding_ref'],
                'premise_support_refs':row.get('premise_support_refs',[])[:1],
                **({'local_spatial_anchor':deepcopy(row['local_spatial_anchor'])} if row.get('local_spatial_anchor') else {'context_read_hash':read['context_read_hash']}),
                'interpretation_decision_ref':decision, 'selected_candidate_id':chosen,
                'reference_domain_hash':digest(read),'structure_signature':signature(state),
                'reference_constraint':deepcopy(constraint)}
        else:
            if not probed:unresolve(state,decision,'DOMAIN_UNAVAILABLE' if incomplete else 'NO_CANDIDATES')
            state.diag('NOMINAL_REFERENCE_SEARCH_INCOMPLETE' if incomplete
                       else 'NOMINAL_REFERENCE_UNRESOLVED',decision)
            from .clarifications import offer
            offer(state,decision,'REFERENCE',constraint['raw'],options)
        state.syntax_trace.append({'kind':'NOMINAL_REFERENCE', 'decision_ref':decision,
            'mention_ref':mention, 'constraint':constraint, 'candidate_count':len(rows), 'selected':chosen})


def unresolve(state,decision_ref,reason):
    """A skipped probe cannot leave an earlier local success active."""
    decision=state.decisions.get(decision_ref)
    if decision is None:return
    decision.history.append({'kind':'NOMINAL_REFERENCE_RESULT_WITHDRAWN','reason':reason,
                             'previous_selected':list(decision.selected)})
    decision.selected=();decision.outcome='UNRESOLVED';decision.search_complete=False
    decision.machine_state='OPEN';decision.lifecycle='PROVISIONAL'
