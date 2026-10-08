"""Replaceable record indexes; append identities index once, liveness reads fresh."""
from collections import defaultdict


def record_index(core,ledger):
    supports_map=ledger.data['supports']; assertions_map=ledger.data['assertions']
    # Hypothetical views mask statuses, while sharing immutable record IDs.
    key=(id(getattr(supports_map,'records',supports_map)),
         id(getattr(assertions_map,'records',assertions_map)),len(supports_map),len(assertions_map))
    cached=getattr(core,'_native_query_records',None)
    if cached is not None and cached[0]==key:
        return cached[1]
    supports=defaultdict(list); assertions=defaultdict(list); targets=defaultdict(list)
    for sid,s in ledger.data['supports'].items(): supports[s['conclusion_ref']].append(sid)
    for aid,a in ledger.data['assertions'].items():
        assertions[a['support_record_id']].append(aid); targets[a['target_ref']].append(aid)
    result={'supports':supports,'assertions':assertions,'targets':targets}
    core._native_query_records=(key,result)
    return result
