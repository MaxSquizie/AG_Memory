"""One speaker choice for an exactly equal occurrence-reading uncertainty.

Producer domains remain distinct. A durable choice is projected to each only
through an explicit equality receipt, never by matching labels or spellings.
"""
from copy import deepcopy
from .canonical_ledger import digest
from .partial_readings import valid_domain,retired_refs


def merge_offers(state,record):
    from .probe_wording import reading as label
    from .clarifications import offer
    for reading in record['reading_domains']:
        scope={k:reading[k] for k in ('region_ref','task_scope','predicate_ref','token_ref','role')}
        readings={digest(v['reading']):v['reading'] for v in reading['alternatives']}
        domains={}
        offered={r['decision_ref'] for r in state.clarification_candidates}
        for row in state.syntax_trace:
            if row.get('kind')!='PARTIAL_READING_DOMAIN' or any(row.get(k)!=v for k,v in scope.items()):continue
            if row['decision_ref'] not in offered:continue
            # Equal reading text does not collapse two distinct alternatives
            # inside a producer. Projection must be a bijection of its domain.
            if len(row['alternatives'])!=len(readings):continue
            if {digest(v['reading']) for v in row['alternatives']}!=set(readings) or not valid_domain(state,row):continue
            domains[row['decision_ref']]=deepcopy(row)
        if len(domains)<2:continue
        key='reading-clarification:'+digest([scope,sorted(domains),readings])
        options=[]
        for rid,value in sorted(readings.items()):
            mapping={ref:next(v['candidate_id'] for v in domain['alternatives'] if digest(v['reading'])==rid)
                     for ref,domain in sorted(domains.items())}
            options.append({'candidate_id':rid,'label':label(value),'reading':deepcopy(value),
                            'equivalent_reading_choices':mapping})
        state.syntax_trace.append({'kind':'PARTIAL_READING_EQUIVALENCE','decision_ref':key,
            'scope':scope,'domains':list(domains.values()),'options':deepcopy(options)})
        state.clarification_candidates[:]=[r for r in state.clarification_candidates if r['decision_ref'] not in domains]
        token=next(t for t in state.evidence if t.token_id==scope['token_ref'])
        offer(state,key,'COMPONENT',token.span,options)


def project(request,option):
    mapping=option.get('equivalent_reading_choices')
    if mapping is None:return {}
    trace=request.get('generation_snapshot',{}).get('syntax_trace',())
    row=next((r for r in reversed(trace) if r.get('kind')=='PARTIAL_READING_EQUIVALENCE'
              and r['decision_ref']==request['decision_ref']),None)
    if row is None or option not in row['options']:
        raise ValueError('CLARIFICATION_READING_PROOF_INVALID')
    domains={d['decision_ref']:d for d in row['domains']}
    if set(domains)!=set(mapping):raise ValueError('CLARIFICATION_READING_PROOF_INVALID')
    retired=retired_refs(trace)
    if retired.intersection(domains):raise ValueError('CLARIFICATION_READING_PROOF_RETIRED')
    for ref,cid in mapping.items():
        domain=domains[ref]
        if any(domain.get(k)!=v for k,v in row['scope'].items()):raise ValueError('CLARIFICATION_READING_SCOPE_CHANGED')
        value=next((v for v in domain['alternatives'] if v['candidate_id']==cid),None)
        receipt=next((r for r in reversed(trace) if r.get('kind')=='TASK_DOMAIN' and r['task_ref']==domain['domain_ref']),None)
        if (value is None or digest(value['reading'])!=digest(option['reading']) or receipt is None
                or receipt.get('search_complete') is not True or receipt.get('source_complete') is not True
                or retired.intersection(receipt.get('page_refs',()))
                or receipt.get('supported_payloads',{}).get(cid)!=digest(value)):
            raise ValueError('CLARIFICATION_READING_PROOF_INVALID')
    return deepcopy(mapping)
