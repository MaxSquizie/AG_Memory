"""Closed short component questions; never model-generated structures."""
from .state import Decision, Ground
from .selection_protocol import DecisionSchema, Relation
from .selector_wire import build_selector_prompt, validate_selector_reply
from .provider_adapter import BudgetExceeded, IntegrityError

def _live_probe(state, selector, release, key, slot, options, context, source_range, *, equivalent_targets=None, question=None):
    from .probe_windows import enter
    enter(state,selector,source_range)
    ids = tuple(o['candidate_id'] for o in options)
    d = Decision(slot, key, ids)
    state.decisions[key] = d
    if not ids or state.budget.llm_exhausted:
        d.outcome = 'UNRESOLVED'
        state.diag('COMPUTATION_LIMIT' if ids else 'NO_GROUNDED_CANDIDATE', key)
        return None
    from .clarifications import choice
    chosen = choice(state, key, ids)
    if chosen is not None:
        d.selected, d.outcome, d.lifecycle = (chosen,), 'RESOLVED', 'PROVISIONAL'
        d.grounds.append(Ground('C', 'explicit clarification selection', chosen))
        return chosen
    schema = DecisionSchema(release.sha256, {
        o['candidate_id']: Relation(o['candidate_id'], o['label'], 0, (), o['label']) for o in options})
    prompt = build_selector_prompt(selector, slot_id=slot, frame_id=key,
        context_span=context, mentions={}, schema=schema, candidates=ids,
        contextual_statements=())
    prompt = ('Choose only interpretations positively supported by this source and supplied context. '
        'Generated alternatives are not evidence. Multiple choices need support for EACH. '
        'If context cannot discriminate and no applicable declared preference is supplied, answer ?. '
        'An explicitly supplied preference may resolve ordinary pragmatic underspecification; '
        'it never overrides incompatible grammar, missing candidate coverage or a semantic scope barrier. '
        'Do not invent context, identities or facts. Interpret what the SOURCE SAYS, not whether it is true in memory. '
        'An UNKNOWN memory lookup does not make explicit source syntax unknown.\n'+
        ((question+'\n\n') if question else '')+prompt)
    try:
        d.last_prompt = prompt
        state.budget.spend_llm()
        raw = selector.select(prompt)
        d.raw_response = raw
        reply = validate_selector_reply(selector, raw, schema, ids, allowed=frozenset(ids))
        d.selector_outcome = reply.outcome
    except IntegrityError:
        raise
    except BudgetExceeded as exc:
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
            d.selected, d.outcome, d.lifecycle = (chosen,), 'RESOLVED', 'PROVISIONAL'
            d.grounds.extend(Ground('M', 'admissible source reference', cid) for cid in reply.selected)
            d.grounds.append(Ground('D', 'selected references have the same established entity_ref: '+next(iter(targets)), chosen))
            d.history.append({'kind':'EQUIVALENT_REFERENCE_SELECTION', 'selected_refs':list(reply.selected),
                              'entity_ref':next(iter(targets)), 'representative':chosen})
            return chosen
    if reply.outcome != 'ONE_SELECTED':
        d.history.append({'kind':'CLOSED_PROBE_ALTERNATIVES','outcome':reply.outcome,
                          'selected':list(reply.selected)})
        d.outcome = 'INSUFFICIENT_CONTEXT' if reply.outcome == 'INSUFFICIENT_CONTEXT' else 'UNRESOLVED'
        from .clarifications import offer
        offer(state,key,'IMPLICIT_ARGUMENT' if slot=='implicit_argument' else 'COMPONENT',context,options)
        return None
    chosen = reply.selected[0]
    d.selected, d.outcome, d.lifecycle = (chosen,), 'RESOLVED', 'PROVISIONAL'
    d.grounds.append(Ground('M', 'closed source-grounded component question', chosen))
    return chosen


def _probe(state, selector, release, key, slot, options, context, source_range, *, equivalent_targets=None, question=None):
    from .canonical_ledger import digest
    dependency_signature=digest([release.sha256,slot,options,context,source_range,equivalent_targets,question])
    from .composition_session import current
    runtime=current(state)
    if runtime is not None:
        runtime.tasks.record_probe(key)
        from .component_policy import policy
        prior=state.component_probe_records.get(key)
        unchanged=bool(prior and prior['decision']['outcome']=='RESOLVED'
                       and prior.get('dependency_signature')==dependency_signature)
        memory='' if unchanged else runtime.memory(slot,options,source_range,policy(release))
        question=(question or '')+memory+runtime.tasks.question(key)
    from .component_probe_replay import execute
    return execute(_live_probe,state,selector,release,key,slot,options,context,source_range,
                   equivalent_targets=equivalent_targets,question=question,dependency_signature=dependency_signature)
