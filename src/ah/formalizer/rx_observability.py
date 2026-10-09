"""Replaceable R-X retrieval index and session measurements, never truth grounds."""
from __future__ import annotations
from collections import defaultdict
from time import perf_counter_ns
from copy import deepcopy
import json
from .canonical_ledger import digest


def lexical_keys(text,morph=None):
    """R1 normalization supplies lookup seeds only, never selects a sense."""
    import re
    if morph is None:
        # Lazy singleton avoids loading a dictionary for every cache lookup.
        morph=_dictionary()
    words={w.casefold() for w in re.findall(r'\w+',text)}
    if hasattr(morph, 'analyze'):
        return words | {v.lemma.casefold() for word in words for v in morph.analyze(word) if v.lemma}
    return words|{p.normal_form.casefold() for word in words for p in morph.parse(word)}


from functools import lru_cache
@lru_cache(maxsize=1)
def _dictionary():
    import pymorphy3
    return pymorphy3.MorphAnalyzer()


class ExperienceIndex:
    def __init__(self):
        self.revision = None
        self.record_count = None
        self.keys = defaultdict(set)
        self.snapshots = defaultdict(set)
        self.metrics = {'lookups': 0, 'index_builds': 0, 'records_indexed': 0,
                        'records_considered': 0, 'records_returned': 0,
                        'stale_rejected': 0, 'budget_exhaustions': 0,
                        'lookup_ns': 0, 'liveness_ns': 0, 'index_build_ns': 0, 'payload_bytes': 0}

    def build(self, records, revision):
        # Canonical R-X content is immutable and append-only; status changes
        # are checked at read time and do not alter lexical index keys.
        if self.record_count == len(records):
            self.revision=revision
            return
        start = perf_counter_ns()
        self.keys.clear(); self.snapshots.clear()
        for rid, record in records.items():
            snapshot = digest(record['resource_snapshot'])
            self.snapshots[snapshot].add(rid)
            stages = record['stages']
            lexical = {x['surface'].casefold() for x in stages.get('T1', {}).get('morphological_priors', ())}
            lexical |= {v['lemma'].casefold() for x in stages.get('T1', {}).get('morphological_priors', ()) for v in x['variants'] if v.get('lemma')}
            lexical |= {x['lemma'].casefold() for x in stages.get('T3', {}).get('semantic_priors', ())}
            for key in lexical:
                self.keys[snapshot, key].add(rid)
        self.revision = revision
        self.record_count = len(records)
        self.metrics['index_builds'] += 1
        self.metrics['records_indexed'] = len(records)
        self.metrics['index_build_ns'] += perf_counter_ns() - start

    def read(self, ledger, snapshot, keys, limit):
        start = perf_counter_ns(); self.metrics['lookups'] += 1
        snapshot_key = digest(snapshot)
        ids = self.snapshots.get(snapshot_key,set()) if keys is None else set().union(*(self.keys.get((snapshot_key,k.casefold()),set()) for k in keys))
        out = {s: [] for s in ('T1', 'T2', 'T3')}
        # An incomplete retrieval does not seed the selector with an arbitrary
        # successful prefix. The optional prior read is empty and diagnosed.
        if len(ids) > limit:
            self.metrics['budget_exhaustions'] += 1
            diagnostics = ['RX_PRIOR_LIMIT']
        else:
            diagnostics = []
            path_start=perf_counter_ns()
            paths = ledger.paths() if ids else set()
            self.metrics['liveness_ns']+=perf_counter_ns()-path_start
            for rid in sorted(ids):
                self.metrics['records_considered'] += 1
                entry = ledger.data['rx_cache'][rid]
                if entry['status'] != 'LIVE' or entry['support_record_id'] not in paths:
                    self.metrics['stale_rejected'] += 1; continue
                for stage, payload in entry['stages'].items():
                    out[stage].append({'record_id': rid, 'payload': deepcopy(payload)})
                self.metrics['records_returned'] += 1
        self.metrics['payload_bytes'] += len(json.dumps(out, ensure_ascii=False).encode('utf-8'))
        self.metrics['lookup_ns'] += perf_counter_ns() - start
        return {s: tuple(rows) for s, rows in out.items()}, diagnostics

    def report(self):
        return {'kind': 'RX_SESSION_MEASUREMENTS', 'schema_version': 'rx-metrics-v1',
                'revision': self.revision, 'counters': deepcopy(self.metrics),
                'coverage_evidence': 'retrieval counters only; semantic benefit requires a fixed corpus'}
