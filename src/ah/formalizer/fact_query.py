"""Fact queries require a concrete proof path, temporal coverage and admissibility."""
from dataclasses import dataclass
DEFAULT_FACT_KINDS=frozenset({'ASSERTED'})
ALL_KINDS=frozenset({'ASSERTED','HYPOTHETICAL','EMBEDDED','OBSERVATION_RECORD'})
@dataclass(frozen=True)
class FactRecord:
    record_id: str
    proposition: str
    kind: str
    status: str='LIVE'
    support_record_id: str | None=None
    node_ref: str | None=None

def answer_fact_goal(records,proposition,allow_kinds=DEFAULT_FACT_KINDS,*,ledger=None,point=None,window=None,bridging_rule=None):
    for r in records:
        if r.proposition!=proposition or r.status!='LIVE': continue
        # Widening allow_kinds is not a licence to turn reported content into truth.
        if r.kind!='ASSERTED' or r.kind not in allow_kinds or ledger is None or r.support_record_id not in ledger.paths(): continue
        if ledger.data['supports'][r.support_record_id]['conclusion_ref']!=r.node_ref: continue
        answer=ledger.query_support(r.support_record_id,point=point,window=window)
        if answer['answer']=='YES': return {**answer,'satisfied_by':r.record_id,'kind':r.kind}
    return {'answer':'UNKNOWN','reason':'NO_ADMISSIBLE_PROOF'}
