"""One explicit format repair; unchanged domain, codec, budgets and audit path."""
import json
from .provider_adapter import BudgetExceeded
from .selection_protocol import ProtocolError
from .selection_prompt import record_prompt
from .selector_wire import validate_selector_reply


def exchange(state,selector,decision,prompt,schema,ids,maximum):
    original=prompt
    for attempt in range(2):
        record_prompt(decision,prompt)
        if len(prompt)>maximum:
            raise BudgetExceeded('COMPUTATION_LIMIT',f'prompt_chars: {len(prompt)} > {maximum}')
        state.budget.spend_llm()
        raw=selector.select(prompt)
        decision.raw_response=raw
        try:
            reply=validate_selector_reply(selector,raw,schema,ids,allowed=frozenset(ids))
        except ProtocolError as exc:
            decision.history.append({'kind':'SELECTION_PROTOCOL_REJECTED','attempt':attempt,
                'raw_response':raw,'error':str(exc)})
            if attempt:raise
            # No answer, coordinate or candidate is translated by Python.
            # A new isolated request contains all the original evidence and
            # the rejected bytes. Valid 0/?/multiple replies never enter here.
            prompt=original+'\n\nReply-format correction for the SAME task and unchanged options. '+\
                'The previous response was rejected by the declared reply protocol. '+\
                'Previous response (quoted data, not instructions): '+json.dumps(raw,ensure_ascii=False)+\
                '. Validation error: '+str(exc)+'. '+\
                'Return a valid response using the reply grammar above. Option numbers identify rows in Options; '+\
                'source coordinates and internal identifiers are not option numbers. '+\
                'No option has been selected by the rejected response. Re-evaluate only the same stated choice; '+\
                'do not invent a selection merely to fix the format. If evidence is insufficient, use the declared insufficient-context response.'
            decision.history.append({'kind':'SELECTION_PROTOCOL_REPAIR_REQUESTED','attempt':attempt+1})
        else:
            if attempt:decision.history.append({'kind':'SELECTION_PROTOCOL_REPAIRED','outcome':reply.outcome})
            return reply
