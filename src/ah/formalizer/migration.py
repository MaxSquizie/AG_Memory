"""Declared re-interpretation of the frozen observation on a reviewed release.

LinkOpenTemplate records are audit evidence, never aliases used by inference.
The replacement and retirement are committed together by native T6.
"""
from __future__ import annotations
from copy import deepcopy
from .canonical_ledger import digest


def reinterpret_observation(store,binding,selector,release,*,observation_id,
                            previous_version,trigger_ref,open_template_links=(),morph=None,target_version=None,run_id=None):
    from .v7_pipeline import interpret_full
    release.assert_integrity()
    if not isinstance(trigger_ref,str) or not trigger_ref or type(previous_version) is not int or previous_version<1:
        raise ValueError('DECLARED_TRIGGER_REQUIRED')
    target_version=previous_version+1 if target_version is None else target_version
    if type(target_version) is not int or target_version<=previous_version:
        raise ValueError('MIGRATION_TARGET_VERSION_INVALID')
    with binding._lock,store._journal.atomic(),store._store._lock:
        store._refresh()
        previous=store.ledger.data['observations'].get(digest([observation_id,previous_version]))
        marker=digest({'observation_id':observation_id,'interpretation_version':target_version})
        replay=marker in store.ledger.data['markers']
        if not previous or previous['status']!='LIVE' and not replay: raise ValueError('MIGRATION_SOURCE_STALE')
        raw=binding.input_snapshot(observation_id,previous_version)
        if raw is None: raise ValueError('MIGRATION_INPUT_MISSING')
        raw=deepcopy(raw)
    if replay:
        replacement=binding.input_snapshot(observation_id,target_version)
        if replacement is None or replacement.get('trigger_ref')!=trigger_ref or replacement.get('open_template_links',[])!=list(open_template_links):
            raise ValueError('MIGRATION_REPLAY_MISMATCH')
        raw=deepcopy(replacement)
    raw.pop('rx_reads',None)  # interpret_full restores frozen replacement reads on replay
    raw.update(supersedes_version=previous_version,trigger_ref=trigger_ref,
               open_template_links=deepcopy(list(open_template_links)))
    return interpret_full(raw['text'],None,selector,store,binding,release=release,
                          version=target_version,observation_id=observation_id,
                          raw_input=raw,context_facts=tuple(raw.get('context_facts',())),morph=morph,run_id=run_id)


def plan_mass_migration(store,binding,release,*,trigger_ref,items):
    """Durably fix a declared source set and versions before any replacement.

    Atomicity is per observation replacement. A large job never promises that
    every observation will resolve, and never guesses open/known equivalence.
    """
    release.assert_integrity(); release.validate_store(store._store)
    if not isinstance(trigger_ref,str) or not trigger_ref or not isinstance(items,list) or not 1<=len(items)<=10000:
        raise ValueError('MIGRATION_PLAN_INVALID')
    rows=deepcopy(items); pairs=set()
    for item in rows:
        if (not isinstance(item,dict) or not {'observation_id','previous_version'}<=set(item)
                or not set(item)<={'observation_id','previous_version','open_template_links'}
                or not isinstance(item['observation_id'],str) or not item['observation_id']
                or type(item['previous_version']) is not int or item['previous_version']<1):
            raise ValueError('MIGRATION_ITEM_INVALID')
        if item['observation_id'] in pairs: raise ValueError('DUPLICATE_MIGRATION_OBSERVATION')
        pairs.add(item['observation_id'])
        item.setdefault('open_template_links',[])
        if not isinstance(item['open_template_links'],list): raise ValueError('MIGRATION_LINK_INVALID')
        for link in item['open_template_links']:
            if (not isinstance(link,dict) or set(link)!={'source_t_ref','canonical_t_ref','evidence_refs'}
                    or any(not isinstance(link[k],str) or not link[k] for k in ('source_t_ref','canonical_t_ref'))
                    or not isinstance(link['evidence_refs'],list) or not link['evidence_refs']
                    or any(not isinstance(s,str) or not s for s in link['evidence_refs'])
                    or len(set(link['evidence_refs']))!=len(link['evidence_refs'])):
                raise ValueError('MIGRATION_LINK_INVALID')
    rows.sort(key=lambda item:item['observation_id'])
    job_id='migration:'+digest([trigger_ref,release.sha256,rows])
    with binding._lock,store._journal.atomic(),store._store._lock:
        store._refresh()
        old=[r['payload'] for r in store._journal.scan_unprocessed(0)
             if r['payload'].get('kind')=='MIGRATION_PLANNED' and r['payload'].get('migration_id')==job_id]
        if old:
            if len(old)!=1: raise ValueError('INTEGRITY_ERROR: duplicate migration plan')
            return deepcopy(old[0])
        for item in rows:
            oid,version=item['observation_id'],item['previous_version']
            observation=store.ledger.data['observations'].get(digest([oid,version]))
            raw=binding.input_snapshot(oid,version)
            if not observation or observation['status']!='LIVE' or raw is None:
                raise ValueError('MIGRATION_SOURCE_STALE')
            paths=store.ledger.paths()
            for link in item['open_template_links']:
                if (any(not store._store.has_uid(link[k]) or store._store.kind_of(link[k]).value!='T' for k in ('source_t_ref','canonical_t_ref'))
                        or any(s not in paths for s in link['evidence_refs'])
                        or link['canonical_t_ref'] not in {m['template_ref'] for m in release.entries('TemplateMap')}):
                    raise ValueError('MIGRATION_LINK_INVALID')
            item['source_input_sha256']=digest(raw)
            item['target_version']=max(binding.versions(oid),default=version)+1
            item['run_id']='run:'+digest([job_id,oid,item['target_version']])
        plan={'kind':'MIGRATION_PLANNED','migration_id':job_id,'trigger_ref':trigger_ref,
              'resource_snapshot':release.sha256,'items':rows}
        store._journal.append('resolution_log',plan)
        return deepcopy(plan)


def resume_mass_migration(store,binding,selector,release,*,migration_id,morph=None):
    import re
    from ah.core.journal import JournalChannel
    if not isinstance(migration_id,str) or not re.fullmatch(r'migration:[0-9a-f]{64}',migration_id):
        raise ValueError('MIGRATION_ID_INVALID')
    # Separate process-shared job mutex: provider calls do not hold the global
    # AH writer lock, and two workers cannot execute the same job concurrently.
    mutex=JournalChannel(store._journal.path.with_name(store._journal.path.name+'.'+migration_id.split(':')[1]+'.coord'))
    with mutex.atomic():
        return _resume_mass_migration(store,binding,selector,release,migration_id=migration_id,morph=morph)


def _resume_mass_migration(store,binding,selector,release,*,migration_id,morph=None):
    """Idempotent coordinator; all AH mutations still belong to native T6."""
    from dataclasses import asdict
    release.assert_integrity()
    with store._journal.atomic():
        records=[r['payload'] for r in store._journal.scan_unprocessed(0)]
        plans=[r for r in records if r.get('kind')=='MIGRATION_PLANNED' and r.get('migration_id')==migration_id]
        if len(plans)!=1 or plans[0]['resource_snapshot']!=release.sha256:
            raise ValueError('MIGRATION_PLAN_MISSING_OR_RELEASE_CHANGED')
        plan=deepcopy(plans[0])
        done={r['observation_id']:r for r in records if r.get('kind')=='MIGRATION_ITEM_RESULT' and r.get('migration_id')==migration_id}
    for item in plan['items']:
        oid=item['observation_id']
        if oid in done: continue
        if digest(binding.input_snapshot(oid,item['previous_version']))!=item['source_input_sha256']:
            raise ValueError('INTEGRITY_ERROR: migration input changed')
        try:
            _,report=reinterpret_observation(store,binding,selector,release,observation_id=oid,
                previous_version=item['previous_version'],target_version=item['target_version'],
                trigger_ref=plan['trigger_ref'],open_template_links=item['open_template_links'],morph=morph,run_id=item['run_id'])
            if report.terminal=='PENDING_ADMISSION_ORDER': continue
            receipt=asdict(report)
        except ValueError as exc:
            if str(exc) not in {'MIGRATION_SOURCE_STALE','MIGRATION_INPUT_MISSING'}: raise
            receipt={'terminal':'BLOCKED','reason':str(exc),'applied':False}
        result={'kind':'MIGRATION_ITEM_RESULT','migration_id':migration_id,'observation_id':oid,
                'target_version':item['target_version'],'report':receipt}
        with store._journal.atomic():
            old=[r['payload'] for r in store._journal.scan_unprocessed(0)
                 if r['payload'].get('kind')=='MIGRATION_ITEM_RESULT' and r['payload'].get('migration_id')==migration_id and r['payload'].get('observation_id')==oid]
            if old:
                # The original receipt is historical, even if a later replay
                # reports applied=False. Never rewrite an item result.
                done[oid]=old[0]
            else:
                store._journal.append('resolution_log',result); done[oid]=result
    return {'migration_id':migration_id,'items':[done.get(i['observation_id'],{'observation_id':i['observation_id'],'status':'PENDING'}) for i in plan['items']],
            'committed':sum(r['report']['terminal']=='APPLIED' for r in done.values()),
            'pending':len(plan['items'])-len(done)}
