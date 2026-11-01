"""Pure completion-receipt validation, independent of an active dispatcher.

Use explicit task revisions and iterative traversal. Lazy evidence revocation
must have the same effect before and after a runtime invalidation is recorded.
"""

def valid(state,task_ref,revision):
    from .dispatch_evidence import valid as evidence_valid,probe_stamp
    latest={}
    for row in state.syntax_trace:
        if row.get('kind')=='DISPATCH_COMPLETED':latest[row['task_ref']]=row
        elif row.get('kind')=='DISPATCH_INVALIDATED':latest[row['task_ref']]=None
    root=(task_ref,revision);results={};active=set();pending=[(root,False)]
    def children(row):
        hard=[(v['task_ref'],v['revision']) for v in row.get('dependencies',())]
        soft=[]
        for read in row.get('evidence_reads',()):
            transfer=read.get('value',{}).get('transfer') if read['kind']=='READING_USE' else None
            if transfer:
                imp=transfer['import'];soft.append((imp['parent_task'],imp['parent_revision']))
        return hard,soft
    while pending:
        key,leaving=pending.pop()
        if key in results:continue
        row=latest.get(key[0])
        if row is None or row.get('revision')!=key[1]:results[key]=False;continue
        hard,soft=children(row)
        if leaving:
            active.discard(key)
            ok=all(results.get(c,False) for c in hard)
            if row.get('task_kind')=='PROBE':
                ok=ok and row.get('probe_stamp') is not None and row['probe_stamp']==probe_stamp(state,key[0].removeprefix('probe:'))
            if ok:
                ok=all(evidence_valid(state,r['kind'],r['value'],provider_results=results)==r.get('expected',True)
                       for r in row.get('evidence_reads',()))
            results[key]=ok
        elif key in active:results[key]=False
        else:
            active.add(key);pending.append((key,True))
            pending.extend((c,False) for c in dict.fromkeys((*hard,*soft)) if c not in results)
    return results[root]
