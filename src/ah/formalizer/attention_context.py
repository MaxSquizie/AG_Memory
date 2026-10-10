"""Pre-seal, replayable context reads through the actual AH's Ignition routes.

Canonical data stays in AH. Only transient activation is evaluated in an overlay
so a crash before the read receipt cannot consume a second attention event.
"""
from collections import defaultdict
from copy import deepcopy
from dataclasses import asdict, is_dataclass
from enum import Enum
from datetime import date, datetime
import json
from types import SimpleNamespace

from ah.config import IgnitionSettings, ActivationSettings, PlasticitySettings, WorkspaceSettings
from ah.ignition.engine import IgnitionEngine
from ah.model import RuntimeState
from .canonical_ledger import digest


class ContextReadError(ValueError):
    """A typed, non-committing failure of the frozen reading session."""


def attention_snapshot(engine):
    with engine._lock:
        cfg = engine.settings
        return {'policy': {k: getattr(cfg, k) for k in ('event_retention', 'event_transfer',
                    'event_input_budget', 'context_query_ticks', 'x_max')},
                'threshold': engine.workspace_settings.threshold,
                'epsilon': cfg.activation.epsilon,
                'tick': engine.tick_index,
                'runtime': {uid: asdict(engine.core.store.runtime_state(uid))
                            for uid in sorted(engine._active_uids | engine._incoming.keys())
                            if engine.core.store.has_uid(uid)},
                'incoming': dict(engine._incoming), 'external': dict(engine._event_external)}


def freeze_attention_base(store, engine):
    with store._journal.atomic(), store._store._lock:
        store._refresh()
        return {'schema': 'attention-context-1', 'memory_hash': memory_hash(store),
                'attention': attention_snapshot(engine)}


def memory_hash(store):
    # Journal-only provider/read records do not change this identity.
    def canonical(value):
        if is_dataclass(value): return canonical(asdict(value))
        if isinstance(value, Enum): return value.value
        if isinstance(value,(date,datetime)):
            return {'type':type(value).__name__,'value':value.isoformat()}
        if isinstance(value, dict): return {str(k):canonical(v) for k,v in value.items()}
        if isinstance(value, (set,frozenset)):
            return sorted((canonical(v) for v in value),key=lambda v:json.dumps(v,sort_keys=True))
        if isinstance(value, (list,tuple)): return [canonical(v) for v in value]
        return value
    core=store._store
    return digest({'ledger':{k:v for k,v in store.ledger.data.items() if k!='wal_seq'},
        'graph':[canonical(core.get_link(uid) if core.kind_of(uid).value=='L'
                           else core.get_symbol(uid) if core.kind_of(uid).value=='S'
                           else core.get_element_any_domain(uid)) for uid in sorted(core.all_uids())]})


class _RuntimeOverlay:
    def __init__(self, base, runtime):
        self.base = base
        self.runtime = {uid: RuntimeState(**row) for uid, row in runtime.items()}

    def __getattr__(self, name):
        return getattr(self.base, name)

    def runtime_state(self, uid):
        return self.runtime.setdefault(uid, RuntimeState())

    def runtime_items(self):
        return tuple(self.runtime.items())

    def _update_runtime_states(self, updates):
        self.runtime.update(updates)

    def enable_lifetime_tracking(self, tick):
        pass


class AttentionContextReader:
    def __init__(self, store, release, engine, run_id, base):
        self.store, self.release, self.live_engine = store, release, engine
        self.run_id, self.base = run_id, base
        self.ordinal = 0
        self.read_token_refs = set()
        self.lexical_symbols = defaultdict(set)
        mappings = defaultdict(set)
        for row in release.entries('TemplateMap'):
            if store._store.has_uid(row['template_ref']):
                template=store._store.get_element_any_domain(row['template_ref'])
                mappings[row['sense_id']].add(template.predicate.uid)
        for row in release.entries('R-S'):
            self.lexical_symbols[(row['lemma'],row['POS'])].update(mappings[row['sense_id']])
        a = base['attention']
        overlay = _RuntimeOverlay(store._store, a['runtime'])
        cfg = IgnitionSettings(**a['policy'], activation=ActivationSettings(epsilon=a['epsilon']),
                               plasticity=PlasticitySettings(enabled=False))
        self.engine = IgnitionEngine(SimpleNamespace(store=overlay, ref=store._core.ref),
                                     cfg, WorkspaceSettings(a['threshold']))
        self.engine.tick_index = a['tick']
        self.engine._incoming = defaultdict(float, a['incoming'])
        self.engine._event_external = defaultdict(float, a['external'])
        self.expected_live_hash = digest(a)

    def _restore_result(self, result):
        a = result['attention_after']
        self.engine.core.store.runtime = {uid: RuntimeState(**row) for uid, row in a['runtime'].items()}
        self.engine._active_uids = {uid for uid, row in a['runtime'].items()
                                   if row['excitation'] > a['epsilon']}
        self.engine._incoming = defaultdict(float, a['incoming'])
        self.engine._event_external = defaultdict(float, a['external'])
        self.engine.tick_index = a['tick']
        self.read_token_refs.update(result['read_token_refs'])

    def read(self, state, request):
        state.require_structures_open('CONTEXT_GOAL')
        ordinal = self.ordinal
        self.ordinal += 1
        request = {**request, 'ordinal': ordinal, 'run_id': self.run_id,
                   'memory_hash': self.base['memory_hash'], 'release_hash': self.release.sha256}
        key = digest(request)
        store = self.store
        with store._journal.atomic(), store._store._lock:
            store._refresh()
            previous = [r['payload'] for r in store._journal.scan_unprocessed()
                        if r.get('run_id') == self.run_id and r['payload'].get('kind') == 'CONTEXT_READ'
                        and r['payload'].get('ordinal') == ordinal]
            if previous:
                if len(previous) != 1 or previous[0]['request_hash'] != key:
                    raise ContextReadError('CONTEXT_REPLAY_MISMATCH')
                result = deepcopy(previous[0]['result'])
                if digest(result) != previous[0]['result_hash']:
                    raise ContextReadError('CONTEXT_REPLAY_MISMATCH')
                self._restore_result(result)
                # A receipt may have committed just before a crash, with the
                # transient focus projection still at its previous state.
                self._publish(result)
                return self._deliver(state, request, result)
            if memory_hash(store) != self.base['memory_hash']:
                raise ContextReadError('CONTEXT_SNAPSHOT_STALE')
            evidence = {e.token_id: e for e in state.evidence}
            events = []
            # Token-addressed progression is independent of transport chunks,
            # hypothesis counts, model calls and their duration.
            frontier = request['source_range'][1]
            for tid in (e.token_id for e in state.evidence if e.end <= frontier):
                if tid in self.read_token_refs:
                    continue
                e = evidence[tid]
                forms = {e.span.casefold(), *(v.lemma for v in e.variants if v.lemma)}
                refs = {s.uid for form in sorted(forms) for s in store._store.find_symbols_by_form(form)}
                for variant in e.variants:
                    refs.update(self.lexical_symbols.get((variant.lemma,variant.pos),()))
                for uid in sorted(refs):
                    self.engine.seed(store._core.ref(uid), 1.0)
                self.engine.tick(include_pacemaker=False)
                self.read_token_refs.add(tid)
                events.append({'kind': 'READ_TOKEN', 'source_ref': tid})
            if request['kind'] == 'REFERENCE':
                # A goal redistributes existing excitation; it injects no new
                # semantic evidence and gives no fresh independent seed.
                for _ in range(self.engine.settings.context_query_ticks):
                    self.engine.tick(include_pacemaker=False)
                events.append({'kind': 'CONTEXT_GOAL', 'decision_ref': request['decision_ref']})
                from .coreference import freeze_context
                active = {r.uid for r in self.engine.workspace_refs()}
                try:
                    rows = freeze_context(store, self.release, state.observation.get('coreference_sources', []),
                                          active_refs=active)
                except ValueError as exc:
                    code=str(exc).split(':',1)[0]
                    if code not in {'RESOURCE_MISSING','COREF_WINDOW_LIMIT','COREF_CANDIDATE_LIMIT'}:
                        raise
                    raise ContextReadError(code) from exc
            else:
                rows = []
            result = {'rows': rows, 'events': events, 'scope': 'ACTIVE_WORKSPACE',
                      'global_search_complete': False, 'read_token_refs': sorted(self.read_token_refs),
                      'attention_after': attention_snapshot(self.engine)}
            store._journal.append('resolution_log', {'kind': 'CONTEXT_READ', 'ordinal': ordinal,
                'request_hash': key, 'request': request, 'result': result, 'result_hash': digest(result)},
                run_id=self.run_id)
            self._publish(result)
            return self._deliver(state, request, result)

    def _publish(self, result):
        engine = self.live_engine
        with engine._lock:
            current = digest(attention_snapshot(engine))
            target = digest(result['attention_after'])
            if current == target:
                self.expected_live_hash = target
                return
            if current != self.expected_live_hash:
                return  # Another explicit attention task owns the live focus.
            a = result['attention_after']
            engine.core.store._update_runtime_states(deepcopy(self.engine.core.store.runtime))
            engine._active_uids = set(self.engine._active_uids)
            engine._incoming = defaultdict(float, a['incoming'])
            engine._event_external = defaultdict(float, a['external'])
            engine._seed_reasons.clear()
            engine.tick_index = a['tick']
            self.expected_live_hash = digest(attention_snapshot(engine))

    @staticmethod
    def _deliver(state, request, result):
        state.context_reads.append({'request': request, 'result_hash': digest(result),
                                    'scope': result['scope'], 'events': result['events'],
                                    'rows': result['rows'], 'global_search_complete': False})
        return result
