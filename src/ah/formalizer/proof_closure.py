"""Audit closure of concrete proof paths, separate from their visibility.

O/C/W sources create factual dependence. Resource and inference rules are
reported separately and do not make two observations dependent. The traversal
uses record IDs, includes reference-binding premises, and rejects missing or
cyclic records instead of assuming independence.
"""
from .canonical_ledger import digest


def source_premise_closure(ledger, support_id, *, limit=8192):
    factual = set()
    rules = set()
    visited = set()
    visiting = set()

    def visit(sid):
        if sid in visited:
            return
        if sid in visiting:
            raise ValueError('INTEGRITY_ERROR: cyclic support closure')
        if len(visited) + len(visiting) >= limit:
            raise ValueError('COMPUTATION_LIMIT')
        support = ledger.data['supports'].get(sid)
        if support is None:
            raise ValueError('INTEGRITY_ERROR: missing support closure record')
        visiting.add(sid)
        if support['kind'] == 'ROOT':
            ground = support.get('ground_type')
            if ground not in {'O', 'C', 'W'}:
                raise ValueError('INVALID_FACT_GROUND')
            source = support.get('ground_ref')
            if source is None:
                source = support.get('source_tag') if ground == 'O' else support.get('ground_record_id', sid)
            factual.add(digest({'kind': ground, 'source': source}))
        for ground in support.get('factual_ground_refs', ()):
            if ground.get('kind') not in {'O', 'C', 'W'} or 'source' not in ground:
                raise ValueError('INVALID_FACT_GROUND')
            factual.add(digest(ground))
        rules.update(digest(value) for value in support.get('rule_refs', ()))
        if support.get('rule_id'):
            rules.add(digest({'rule_id': support['rule_id']}))
        for premise in support.get('premise_support_refs', ()):
            visit(premise)
        for bid in support.get('binding_refs', ()):
            binding = ledger.data['bindings'].get(bid)
            if binding is None:
                raise ValueError('INTEGRITY_ERROR: missing binding closure record')
            for premise in binding.get('premise_support_refs', ()):
                visit(premise)
        visiting.remove(sid)
        visited.add(sid)

    visit(support_id)
    return {'factual_sources': sorted(factual), 'rule_refs': sorted(rules)}


def independent(ledger, left_support_id, right_support_id):
    left = source_premise_closure(ledger, left_support_id)
    right = source_premise_closure(ledger, right_support_id)
    return not (set(left['factual_sources']) & set(right['factual_sources']))
