"""Operator facade for native source/witness withdrawal and reinterpretation.

Selection is explicit. A node with independent observations is never treated
as one retractable source; all mutations stay in the V7 durable channels.
"""
from __future__ import annotations

from copy import deepcopy
from .canonical_ledger import digest


class NativeMemoryService:
    def __init__(self, runtime):
        self.runtime = runtime

    @property
    def adapter(self):
        perception = self.runtime.perception
        adapter = getattr(perception, '_formalizer', None)
        if adapter is None or not adapter.native_available or adapter._release is None:
            raise ValueError('V7_RUNTIME_UNAVAILABLE: configure the reviewed release and backend')
        return adapter

    def _save(self):
        runtime = self.runtime
        if runtime.config.persistence.enabled:
            runtime.persistence.save(runtime.core, ignition=runtime.ignition, context=runtime.context)

    def sources(self, node_ref=None):
        """Concrete source/witness IDs to choose, not a name-based identity read."""
        from .native_records import record_index
        a = self.adapter; store = a._store
        with self.runtime.operation_lock, store._journal.atomic(), store._store._lock:
            store._refresh(); ledger = store.ledger; paths = ledger.paths()
            if node_ref is not None and node_ref not in ledger.data['nodes']:
                raise ValueError('V7_NODE_NOT_FOUND')
            supports = [ledger.data['supports'][sid] for sid in record_index(store._core, ledger)['supports'].get(node_ref, ())] if node_ref is not None else list(ledger.data['supports'].values())
            return {'supports': [{**deepcopy(s), 'effectively_live': s['record_id'] in paths} for s in supports],
                    'assertions': [deepcopy(a) for a in ledger.data['assertions'].values()
                                   if node_ref is None or a['target_ref'] == node_ref],
                    'observations': deepcopy(list(ledger.data['observations'].values()))}

    def retract_observation(self, observation_id, version, *, trigger_ref):
        if not isinstance(observation_id, str) or not observation_id or type(version) is not int or version < 1 or not isinstance(trigger_ref, str) or not trigger_ref:
            raise ValueError('RETRACTION_SOURCE_INVALID')
        a = self.adapter; store = a._store
        with self.runtime.operation_lock, store._journal.atomic(), store._store._lock:
            store._refresh()
            tag = [observation_id, version]
            if digest(tag) not in store.ledger.data['observations'] and not any(
                    r['payload'].get('kind')=='run_bind' and r['payload'].get('observation_id')==observation_id
                    and r['payload'].get('version')==version for r in store._journal.scan_unprocessed()):
                raise ValueError('RETRACTION_SOURCE_NOT_FOUND')
            before = store.ledger.f_visible()
            store.retract_observation(observation_id, version, trigger_ref=trigger_ref)
            removed = before - store.ledger.f_visible()
            self.runtime.context.formalizer_sources = [t for t in self.runtime.context.formalizer_sources if list(t) != tag]
            self._save()
            return {'source_tag': tag, 'status': 'RETRACTED', 'lost_visibility': sorted(removed)}

    def retract_record(self, record_id, *, kind, trigger_ref):
        if kind not in {'TIME_ASSERTION', 'SUPPORT'} or not isinstance(trigger_ref, str) or not trigger_ref:
            raise ValueError('RETRACTION_TRIGGER_REQUIRED')
        a = self.adapter; store = a._store
        with self.runtime.operation_lock, store._journal.atomic(), store._store._lock:
            store._refresh()
            records = store.ledger.data['assertions' if kind == 'TIME_ASSERTION' else 'supports']
            if record_id not in records:
                raise ValueError('RETRACTION_RECORD_NOT_FOUND')
            before = store.ledger.f_visible()
            changed = store.retract(record_id, reason=trigger_ref)
            self._save()
            return {'record_id': record_id, 'kind': kind, 'changed': changed,
                    'lost_visibility': sorted(before - store.ledger.f_visible())}

    def reinterpret(self, observation_id, previous_version, *, trigger_ref, input_changes=None, open_template_links=()):
        from .migration import reinterpret_observation
        a = self.adapter
        # Provider calls don't hold the AH writer lock; admission revalidates
        # against current durable state and atomically retires the old version.
        state, report = reinterpret_observation(a._store, a._binding, a._selector, a._release,
            observation_id=observation_id, previous_version=previous_version, trigger_ref=trigger_ref,
            input_changes=input_changes, open_template_links=open_template_links, morph=a._morph)
        receipt = a._receipt(state, report)
        with self.runtime.operation_lock:
            if report.committed_fragments:
                self.runtime.context.remember_formalizer_source(observation_id, report.version)
            self._save()
        return receipt

    def plan_migration(self, items, *, trigger_ref):
        from .migration import plan_mass_migration
        a = self.adapter
        return plan_mass_migration(a._store, a._binding, a._release, trigger_ref=trigger_ref, items=items)

    def resume_migration(self, migration_id):
        from .migration import resume_mass_migration
        a = self.adapter
        result = resume_mass_migration(a._store, a._binding, a._selector, a._release,
                                       migration_id=migration_id, morph=a._morph)
        with self.runtime.operation_lock:
            self._save()
        return result

    def pending_clarifications(self):
        from .clarifications import request_current
        a = self.adapter
        out = []
        for row in a._store._journal.scan_unprocessed():
            p = row['payload']
            if p.get('kind') != 'CLARIFICATION_REQUEST': continue
            key = 'v7:' + p['request_id'] + ':' + digest(p['options'][0])
            if not request_current(a, key): continue
            out.append({**deepcopy(p), 'options': [{**o, 'resolution_key': 'v7:'+p['request_id']+':'+digest(o)} for o in p['options']]})
        return out

    def clarify(self, resolution_key):
        receipt = self.adapter.clarify(resolution_key)
        with self.runtime.operation_lock:
            if receipt.committed_fragments:
                self.runtime.context.remember_formalizer_source(receipt.observation_id, receipt.version)
            self._save()
        return receipt
