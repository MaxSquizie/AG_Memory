"""Explicitly ignored question -> declared, journaled replacement interpretation."""
from copy import deepcopy
import re
from .canonical_ledger import digest


def ignore(adapter,resolution_key):
    from .migration import plan_mass_migration, reinterpret_observation
    match=re.fullmatch(r'v7:([0-9a-f]{64}):([0-9a-f]{64})',resolution_key)
    if match is None:raise ValueError('CLARIFICATION_KEY_INVALID')
    rid,option_hash=match.groups()
    store,binding,release=adapter._store,adapter._binding,adapter._release
    trigger='clarification-ignored:'+rid
    with binding._lock,store._journal.atomic(),store._store._lock:
        store._refresh()
        rows=[r['payload'] for r in store._journal.scan_unprocessed()]
        requests=[r for r in rows if r.get('kind')=='CLARIFICATION_REQUEST' and r.get('request_id')==rid]
        if len(requests)!=1:raise ValueError('CLARIFICATION_REQUEST_MISSING')
        request=requests[0]
        if request['resource_snapshot']!=release.sha256:raise ValueError('CLARIFICATION_RESOURCE_STALE')
        if not any(digest(o)==option_hash for o in request['options']):raise ValueError('CLARIFICATION_OPTION_INVALID')
        if not request['decision_ref'].endswith('|refinement-host') or not all('member_refs' in o for o in request['options']):
            raise ValueError('CLARIFICATION_DEFERRAL_UNSUPPORTED')
        oid,version=request['observation_id'],request['version']
        raw=binding.input_snapshot(oid,version)
        if raw is None or digest(raw)!=request['input_sha256']:raise ValueError('CLARIFICATION_INPUT_CHANGED')
        old=any(r.get('kind')=='MIGRATION_PLANNED' and r.get('trigger_ref')==trigger for r in rows)
        if not old and max(binding.versions(oid),default=version)!=version:
            raise ValueError('CLARIFICATION_VERSION_STALE')
        delivery=deepcopy(raw.get('clarification_delivery',{}));delivery[request['decision_ref']]='IGNORED'
        plan=plan_mass_migration(store,binding,release,trigger_ref=trigger,items=[{
            'observation_id':oid,'previous_version':version,'input_changes':{'clarification_delivery':delivery}}])
    item=plan['items'][0]
    # Re-evaluate on a new version; never fabricate a speaker-selected option.
    # Source generation may issue fresh short probes. Migration owns recovery.
    return reinterpret_observation(store,binding,adapter._selector,release,
        observation_id=oid,previous_version=version,target_version=item['target_version'],
        run_id=item['run_id'],trigger_ref=trigger,input_changes=item['input_changes'],morph=adapter._morph)
