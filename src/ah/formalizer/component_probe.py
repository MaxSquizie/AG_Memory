"""Closed short component questions; never model-generated structures."""
from .state import Decision, Ground
from .selection_protocol import DecisionSchema, Relation
from .selector_wire import build_selector_prompt, validate_selector_reply
from .provider_adapter import BudgetExceeded, IntegrityError

def _probe(state, selector, release, key, slot, options, context, source_range, *, equivalent_targets=None, question=None):
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
    if question:
        prompt = question+'\n\n'+prompt
    try:
        state.budget.spend_llm()
        raw = selector.select(prompt)
        reply = validate_selector_reply(selector, raw, schema, ids, allowed=frozenset(ids))
        d.last_prompt, d.raw_response, d.selector_outcome = prompt, raw, reply.outcome
    except IntegrityError:
        raise
    except BudgetExceeded as exc:
        d.outcome = 'UNRESOLVED'
        state.diag(exc.code, key)
        return None
    except Exception as exc:
        d.outcome = 'UNRESOLVED'
        state.diag('COMPONENT_PROBE_FAILED', type(exc).__name__)
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
        d.outcome = 'INSUFFICIENT_CONTEXT' if reply.outcome == 'INSUFFICIENT_CONTEXT' else 'UNRESOLVED'
        from .clarifications import offer
        offer(state,key,'IMPLICIT_ARGUMENT' if slot=='implicit_argument' else 'COMPONENT',context,options)
        return None
    chosen = reply.selected[0]
    d.selected, d.outcome, d.lifecycle = (chosen,), 'RESOLVED', 'PROVISIONAL'
    d.grounds.append(Ground('M', 'closed source-grounded component question', chosen))
    return chosen


