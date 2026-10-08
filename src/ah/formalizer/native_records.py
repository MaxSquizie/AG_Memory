"""Replaceable record indexes; append identities index once, liveness reads fresh."""
from collections import defaultdict


def record_index(core,ledger):
    supports_map=ledger.data['supports']; assertions_map=ledger.data['assertions']; nodes_map=ledger.data['nodes']
    reports_map=ledger.data['reports']
    # Hypothetical views mask statuses, while sharing immutable record IDs.
    key=(id(getattr(supports_map,'records',supports_map)),
         id(getattr(assertions_map,'records',assertions_map)),id(nodes_map),id(reports_map),
         len(supports_map),len(assertions_map),len(nodes_map),len(reports_map))
    owner=core if core is not None else ledger
    cached=getattr(owner,'_native_query_records',None)
    if cached is not None and cached[0]==key:
        return cached[1]
    supports=defaultdict(list); assertions=defaultdict(list); targets=defaultdict(list)
    for sid,s in ledger.data['supports'].items(): supports[s['conclusion_ref']].append(sid)
    for aid,a in ledger.data['assertions'].items():
        assertions[a['support_record_id']].append(aid); targets[a['target_ref']].append(aid)
    content=defaultdict(list); negations=defaultdict(list); source_supports=defaultdict(list)
    report_nodes=defaultdict(set); report_content=defaultdict(set)
    for uid,n in nodes_map.items():
        if n.get('content_key'): content[n['content_key']].append(uid)
        if n.get('function_id')=='NOT' and len(n.get('operands',()))==1 and isinstance(n['operands'][0],str): negations[n['operands'][0]].append(uid)
    for sid,s in supports_map.items():
        if s.get('source_tag'): source_supports[s['source_tag'][0]].append(sid)
    for rid,r in reports_map.items():
        for uid in r.get('node_refs',()): report_nodes[uid].add(rid)
        for candidate in r.get('candidates',()):
            if candidate.get('content_key'): report_content[candidate['content_key']].add(rid)
    result={'supports':supports,'assertions':assertions,'targets':targets,'content':content,
            'negations':negations,'sources':source_supports,'report_nodes':report_nodes,'report_content':report_content}
    owner._native_query_records=(key,result)
    return result
