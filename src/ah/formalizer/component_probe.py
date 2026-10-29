"""Closed short component questions; never model-generated structures."""
from .state import Decision, Ground
from .selection_evidence import selected_candidate
from .selection_protocol import DecisionSchema, Relation
from .selector_wire import build_selector_prompt
from .provider_adapter import BudgetExceeded, IntegrityError

def _live_probe(state, selector, release, key, slot, options, context, source_range, *, equivalent_targets=None, question=None, offer_clarification=True):
    from .probe_windows import enter
    enter(state,selector,source_range)
    ids = tuple(o['candidate_id'] for o in options)
    d = Decision(slot, key, ids, search_complete=False)
    state.decisions[key] = d
    if not ids:
        d.outcome = 'UNRESOLVED'
        state.diag('NO_GROUNDED_CANDIDATE', key)
        return None
    from .clarifications import choice
    chosen = choice(state, key, ids)
    if chosen is not None:
        d.selected, d.outcome, d.lifecycle = (chosen,), None, 'PROVISIONAL'
        d.grounds.append(Ground('C', 'explicit clarification selection', chosen))
        return chosen
    if state.budget.llm_exhausted:
        d.outcome = 'UNRESOLVED'
        state.diag('COMPUTATION_LIMIT', key)
        return None
    if equivalent_targets:
        groups={}
        for option in options:groups.setdefault(option['label'],[]).append(option)
        retained=[]
        for group in groups.values():
            targets={equivalent_targets.get(o['candidate_id']) for o in group}
            if len(group)>1 and len(targets)==1 and None not in targets:
                representative=min(group,key=lambda o:o['candidate_id'])
                retained.append(representative)
                d.history.append({'kind':'EQUIVALENT_REFERENCE_OPTIONS','representative':representative['candidate_id'],
                    'equivalent_refs':[o['candidate_id'] for o in group],'entity_ref':next(iter(targets))})
            else:retained.extend(group)
        options=retained;ids=tuple(o['candidate_id'] for o in options);d.candidates=ids
    # A number cannot disambiguate an invisible distinction. Keep the domain
    # unresolved instead of asking the model to pick a producer or hidden ID.
    labels=[o['label'] for o in options]
    if len(set(labels)) != len(labels):
        d.outcome='UNRESOLVED'
        d.history.append({'kind':'UNREPRESENTED_CANDIDATE_DIFFERENCE','candidates':list(ids)})
        state.diag('PROBE_OPTIONS_INDISTINGUISHABLE',key)
        return None
    from .probe_presentation import factor_options
    options,common=factor_options(options)
    if common:question=(question or '')+'\nShared by all proposed options (0 rejects this too): '+common
    schema = DecisionSchema(release.sha256, {
        o['candidate_id']: Relation(o['candidate_id'], o['label'], 0, (), o['label']) for o in options})
    prompt = build_selector_prompt(selector, slot_id=slot, frame_id=key,
        context_span=context, mentions={}, schema=schema, candidates=ids,
        contextual_statements=())
    revising=slot in {'structural_revision','structural_ownership_revision','structural_marker_revision'}
    prompt = ('Interpret the supplied text. Options are proposed readings, not world facts. '
        +('Answer only the stated revision question. The named earlier assignments may be replaced; '
          'preserve all other established constraints.\n' if revising else
          'Answer only the stated question; preserve established constraints.\n')+
        ((question+'\n\n') if question else '')+prompt)
    try:
        limits=state.observation.get('probe_limits',{})
        maximum=getattr(getattr(selector,'limits',None),'max_prompt_chars',limits.get('max_prompt_chars',8192))
        if type(maximum) is not int or maximum<1:raise ValueError('PROBE_LIMIT_INVALID')
        from .selection_exchange import exchange
        reply=exchange(state,selector,d,prompt,schema,ids,maximum)
        d.selector_outcome = reply.outcome
    except IntegrityError:
        raise
    except BudgetExceeded as exc:
        d.history.append({'kind':'PROBE_LIMIT','code':exc.code,'detail':str(exc)})
        d.outcome = 'UNRESOLVED'
        state.diag(exc.code, key)
        return None
    except Exception as exc:
        d.outcome = 'UNRESOLVED'
        d.history.append({'kind':'PROBE_FAILURE','error_type':type(exc).__name__,
                          'message':str(exc)})
        state.diag('COMPONENT_PROBE_FAILED', type(exc).__name__ + ': ' + str(exc))
        return None
    if reply.outcome == 'MULTIPLE_ADMISSIBLE' and equivalent_targets:
        targets = {equivalent_targets.get(cid) for cid in reply.selected}
        if len(targets) == 1 and None not in targets:
            # Choose a proof representative, never a different entity. Frozen
            # candidates and the raw multi-answer remain in the audit trail.
            chosen = min(reply.selected)
            d.selected, d.outcome, d.lifecycle = (chosen,), None, 'PROVISIONAL'
            d.grounds.extend(Ground('M', 'admissible source reference', cid) for cid in reply.selected)
            d.grounds.append(Ground('D', 'selected references have the same established entity_ref: '+next(iter(targets)), chosen))
            d.history.append({'kind':'EQUIVALENT_REFERENCE_SELECTION', 'selected_refs':list(reply.selected),
                              'entity_ref':next(iter(targets)), 'representative':chosen})
            return chosen
    if reply.outcome != 'ONE_SELECTED':
        d.selected=tuple(reply.selected)
        d.history.append({'kind':'CLOSED_PROBE_ALTERNATIVES','outcome':reply.outcome,
                          'selected':list(reply.selected)})
        d.outcome = 'INSUFFICIENT_CONTEXT' if reply.outcome == 'INSUFFICIENT_CONTEXT' else 'UNRESOLVED'
        return None
    chosen = reply.selected[0]
    d.selected, d.outcome, d.lifecycle = (chosen,), None, 'PROVISIONAL'
    d.grounds.append(Ground('M', 'closed source-grounded component question', chosen))
    return chosen


def _probe(state, selector, release, key, slot, options, context, source_range, *, equivalent_targets=None, question=None, offer_clarification=True, inputs=None):
    # The enclosing domain owns speaker choices; a page only supplies evidence.
    state.clarification_candidates[:]=[r for r in state.clarification_candidates if r['decision_ref']!=key]
    state.syntax_trace.append({'kind':'PROBE_PAGE','decision_ref':key,'slot':slot,
                              'source_range':list(source_range)})
    from .canonical_ledger import digest
    # Migrate semantic families explicitly. Unmigrated slots remain visible in
    # the audit; a transport-valid string is not a semantic input contract.
    input_record=inputs.record() if inputs is not None else None
    errors=inputs.errors(state,slot,options,source_range) if inputs is not None else (
        ('INPUT_CONTRACT_MISSING',) if slot in {'reference','implicit_argument'} else ())
    if inputs is not None and hasattr(inputs,'question') and question!=inputs.question:
        errors=(*errors,'QUESTION_MISMATCH')
    from .probe_families import contract as family_contract, errors as family_errors
    family=family_contract(slot,inputs)
    errors=tuple(dict.fromkeys((*errors,*family_errors(state,slot,options,context,source_range,question,inputs))))
    state.syntax_trace.append({'kind':'PROBE_INPUT_CONTRACT','decision_ref':key,
        'slot':slot,'status':'INVALID' if errors else getattr(inputs,'declaration_status','DECLARED') if inputs is not None else 'FAMILY_DECLARED',
        'inputs':input_record,'semantic_contract':family.record() if family else None,'errors':list(errors)})
    if errors:
        # Invalidate this cached evaluation, not the stable task address for
        # all future revisions. A repaired declaration may use the same key.
        record=state.component_probe_records.get(key)
        if record is not None:record['superseded_by']='blocked-input:'+digest([key,input_record,errors])
        from .composition_session import current
        runtime=current(state)
        if runtime is not None:runtime.dispatcher.invalidate('probe:'+key,'PROBE_INPUT_INCOMPLETE')
        d=Decision(slot,key,tuple(o['candidate_id'] for o in options),outcome='UNRESOLVED')
        d.history.append({'kind':'PROBE_INPUT_REJECTED','errors':list(errors)})
        state.decisions[key]=d
        state.diag('PROBE_INPUT_INCOMPLETE',key+': '+', '.join(errors))
        return None
    if inputs is not None:
        context=inputs.source_text
        question=(question or '')+'\n'+inputs.wording()
    # Direct producers as well as paged tasks must not lose later/earlier
    # evidence merely because their selection target is a smaller region.
    # This grants no ownership outside the declared target or candidate list.
    if state.text not in context:
        context+='\nFULL SOURCE (evidence only): '+state.text
        question+='\nThe target occupies characters '+str(source_range[0])+':'+str(source_range[1])+'. Broader source is readable evidence, not additional selectable material.'
    dependency_signature=digest([release.sha256,slot,options,context,source_range,equivalent_targets,question])
    if input_record is not None:dependency_signature=digest([dependency_signature,input_record])
    from .composition_session import current
    runtime=current(state)
    if runtime is not None:
        runtime.tasks.record_probe(key)
        from .component_policy import policy
        memory=runtime.memory(slot,options,source_range,policy(release)) if not state.structural_closed else ''
        question=(question or '')+memory+runtime.tasks.question(key)+runtime.input_question(slot)
        dependency_signature=digest([dependency_signature,runtime.input_signature(),question])
    from .component_probe_replay import execute
    def run():
        before=len(state.diagnostics)
        value=execute(_live_probe,state,selector,release,key,slot,options,context,source_range,
                      equivalent_targets=equivalent_targets,question=question,dependency_signature=dependency_signature,
                      offer_clarification=offer_clarification)
        from .task_contracts import TaskResult,TaskOutcome
        d=state.decisions[key]
        outcome={'ONE_SELECTED':TaskOutcome.SUPPORTED,'MULTIPLE_ADMISSIBLE':TaskOutcome.MULTIPLE,
                 'INSUFFICIENT_CONTEXT':TaskOutcome.UNKNOWN,'NONE_FIT':TaskOutcome.PAGE_NONE_FIT}.get(d.selector_outcome)
        if outcome is None:
            codes={x.code for x in state.diagnostics[before:]}
            outcome=(TaskOutcome.SUPPORTED if selected_candidate(d) is not None else
                     TaskOutcome.INCOMPLETE if any('LIMIT' in c or 'INCOMPLETE' in c for c in codes) else TaskOutcome.BLOCKED)
        return TaskResult(value,outcome,False,
                          outcome!=TaskOutcome.BLOCKED,tuple(d.selected))
    if runtime is None:return run().value
    from .task_contracts import probe_contract
    result=runtime.dispatcher.run('probe:'+key,[dependency_signature,state.observation.get('clarification_choices',{}).get(key)],
        run,kind='PROBE',source_range=source_range,contract=probe_contract(slot,state.structural_closed,inputs))
    # Dispatcher reuse returns a scalar; restore its immutable selection evidence too.
    from .component_probe_replay import restore_decision
    restore_decision(state,key,state.component_probe_records[key]['decision'])
    return result
