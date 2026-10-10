"""Immutable durable ownership of an observation/interpretation pair."""
from contextlib import nullcontext
from threading import RLock
from copy import deepcopy
from .canonical_ledger import digest

class InputConflict(ValueError):
    """An immutable source revision was reused for different input bytes."""
    def __init__(self, reason):
        self.reason=reason
        super().__init__('INPUT_CONFLICT: '+reason)


class InterpretationRunBinding:
    def __init__(self, journal=None):
        self._journal = journal
        self._bindings = {}
        self._snapshots = {}
        self._inputs = {}
        self._reservations = {}
        self._lock = RLock()
        self._refresh()

    def _refresh(self):
        if self._journal is None: return
        for rec in self._journal.scan_unprocessed(payload_kinds={'CLARIFICATION_SELECTED','MIGRATION_PLANNED','run_bind'}):
            p = rec['payload']
            if p.get('kind') == 'CLARIFICATION_SELECTED':
                key = (p['observation_id'], p['target_version'])
                old = self._reservations.get(key)
                if old is not None and old != p['run_id']:
                    raise RuntimeError('INTEGRITY_ERROR: clarification reservation conflict')
                self._reservations[key] = p['run_id']
            if p.get('kind') == 'MIGRATION_PLANNED':
                for item in p['items']:
                    key=(item['observation_id'],item['target_version'])
                    old=self._reservations.get(key)
                    if old is not None and old!=item['run_id']:
                        raise RuntimeError('INTEGRITY_ERROR: migration reservation conflict')
                    self._reservations[key]=item['run_id']
            if p.get('kind') == 'run_bind':
                key = (p['observation_id'],p['version'])
                current = self._bindings.get(key)
                if current is not None and current != p['owner']:
                    raise RuntimeError('INTEGRITY_ERROR: conflicting durable run bindings')
                if current is not None and self._snapshots[key]!=p.get('snapshot_hash',''):
                    raise RuntimeError('INTEGRITY_ERROR: durable run snapshot changed')
                if current is not None and digest(self._inputs.get(key))!=digest(p.get('snapshot_data')):
                    raise RuntimeError('INTEGRITY_ERROR: durable input snapshot changed')
                self._bindings[key] = p['owner']
                self._snapshots[key] = p.get('snapshot_hash','')
                self._inputs[key] = deepcopy(p.get('snapshot_data'))

    def acquire(self, owner, observation_id, version, snapshot_hash='', snapshot_data=None):
        with self._lock, (self._journal.atomic() if self._journal else nullcontext()):
            self._refresh(); key=(observation_id,version)
            # The cross-version source check shares the durable append lock.
            # Checking it only in interpret_full would race when two fresh
            # interpretation versions claim one revision with different text.
            if isinstance(snapshot_data,dict) and 'text' in snapshot_data:
                revision=snapshot_data.get('source_revision',snapshot_data.get('revision',1))
                prior=[value for (oid,_),value in self._inputs.items()
                       if oid==observation_id and isinstance(value,dict) and 'text' in value]
                if any(value.get('source_revision',value.get('revision',1))==revision
                       and value['text']!=snapshot_data['text'] for value in prior):
                    raise InputConflict('SOURCE_REVISION_TEXT_CHANGED')
                if key not in self._bindings and prior and revision<max(
                        value.get('source_revision',value.get('revision',1)) for value in prior):
                    raise InputConflict('SOURCE_REVISION_REGRESSED')
            if key in self._reservations and self._reservations[key]!=owner: return False
            current=self._bindings.get(key)
            if current is not None:
                if current != owner: return False
                if snapshot_hash and self._snapshots.get(key,'') != snapshot_hash:
                    raise RuntimeError('INTEGRITY_ERROR: run snapshot changed')
                return True
            if self._journal:
                self._journal.append('resolution_log',{'kind':'run_bind','observation_id':observation_id,
                    'version':version,'owner':owner,'snapshot_hash':snapshot_hash,'snapshot_data':deepcopy(snapshot_data),'run_marker':{'run_id':owner,'state':'RUN_STARTED'}},run_id=owner)
            self._bindings[key]=owner; self._snapshots[key]=snapshot_hash
            self._inputs[key]=deepcopy(snapshot_data)
            return True

    def release(self, owner, observation_id, version):
        # Ownership is historical. A declared reinterpretation requires a new version.
        return False

    def holder(self, observation_id, version):
        with self._lock:
            self._refresh()
            return self._bindings.get((observation_id,version))

    def input_snapshot(self,observation_id,version):
        with self._lock:
            self._refresh()
            return deepcopy(self._inputs.get((observation_id,version)))

    def versions(self, observation_id):
        with self._lock:
            self._refresh()
            return tuple(sorted({v for o,v in {*self._bindings,*self._reservations} if o==observation_id}))
