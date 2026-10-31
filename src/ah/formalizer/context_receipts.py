"""Read-only validation of delivered context against its full durable receipt."""
from copy import deepcopy
from .canonical_ledger import digest
from .composition_dispatcher import canonical


def project(request,result):
    return {'request':deepcopy(request),'result_hash':digest(result),
            'scope':result['scope'],'events':deepcopy(result['events']),
            'rows':deepcopy(result['rows']),'proof_results':deepcopy(result.get('proof_results',[])),
            'search_incomplete':result.get('search_incomplete',False),'global_search_complete':False}


def validate(reader,receipts):
    """Validate historical delivery and frozen canonical basis; never replay."""
    from ah.core.journal import JournalIntegrityError
    from .attention_context import memory_hash
    def outcome(status,reason=None):return {'status':status,'reason':reason}
    store=reader.store
    try:
        with store._journal.atomic(),store._store._lock:
            snapshot=store._journal.verified_snapshot(payload_kinds={'CONTEXT_READ','canonical_unit'})
            current=store._store._state.formalizer_state.get('wal_seq',0)
            if current>snapshot['head']:return outcome('UNAVAILABLE','SNAPSHOT_AHEAD_OF_JOURNAL')
            # Do not refresh/import canonical snapshots during a read-only
            # check. A concurrently committed unit requires normal refresh.
            if any(r['seq']>current and r['payload']['kind']=='canonical_unit' for r in snapshot['records']):
                return outcome('UNAVAILABLE','CANONICAL_REFRESH_REQUIRED')
            if memory_hash(store)!=reader.base['memory_hash']:return outcome('STALE','CONTEXT_SNAPSHOT_STALE')
            for receipt in receipts:
                request=receipt['request']
                if (request.get('run_id')!=reader.run_id or type(request.get('ordinal')) is not int
                        or request['ordinal']<0):return outcome('STALE','CONTEXT_READER_ADDRESS_CHANGED')
                if request.get('memory_hash')!=reader.base['memory_hash']:return outcome('STALE','CONTEXT_MEMORY_CHANGED')
                if request.get('release_hash')!=reader.release.sha256:return outcome('STALE','CONTEXT_RELEASE_CHANGED')
                rows=[r for r in snapshot['records'] if r['payload']['kind']=='CONTEXT_READ'
                      and r.get('run_id')==reader.run_id and r['payload'].get('ordinal')==request['ordinal']]
                if len(rows)!=1:return outcome('UNAVAILABLE','CONTEXT_RECEIPT_NOT_UNIQUE')
                row=rows[0];payload=row['payload'];stored=payload['request'];result=payload['result']
                if (row['channel']!='resolution_log' or stored.get('run_id')!=reader.run_id
                        or stored.get('ordinal')!=payload['ordinal']
                        or digest(stored)!=payload['request_hash']
                        or canonical(stored)!=canonical(request)
                        or digest(result)!=payload['result_hash']):
                    return outcome('STALE','CONTEXT_RECEIPT_CHANGED')
                if canonical(project(stored,result))!=canonical(receipt):return outcome('STALE','CONTEXT_DELIVERY_CHANGED')
                if result.get('scope')!='ACTIVE_WORKSPACE' or result.get('global_search_complete') is not False:
                    return outcome('STALE','CONTEXT_SCOPE_CHANGED')
            return outcome('CURRENT')
    except (JournalIntegrityError,OSError):return outcome('UNAVAILABLE','CONTEXT_JOURNAL_UNAVAILABLE')
    except (KeyError,TypeError,ValueError):return outcome('STALE','CONTEXT_RECEIPT_MALFORMED')


def associate(reader,contexts,receipts):
    """Associate cached goals only with the reader that actually served them."""
    mapped={};unmapped=[];owner=getattr(reader,'run_id',None)
    for context in contexts:
        found=[r for r in receipts if owner is not None and r.get('request',{}).get('run_id')==owner
               and ((context.startswith('goal:') and
                     r.get('request',{}).get('decision_ref')=='composition-context:'+context[5:])
                    or context=='context:'+digest(r))]
        if not found:unmapped.append(context)
        for receipt in found:mapped[digest(receipt)]=deepcopy(receipt)
    return list(mapped.values()),unmapped
