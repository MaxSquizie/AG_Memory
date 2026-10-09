"""Validate declared symbolic ordering without inventing calendar dates."""


def validate_order_constraints(edges, *, limit=8192):
    graph = {}
    for index, edge in enumerate(edges):
        if index >= limit:
            raise ValueError('COMPUTATION_LIMIT')
        if not isinstance(edge, (list, tuple)) or len(edge) != 3:
            raise ValueError('TEMPORAL_CONSTRAINT_INVALID')
        left, operator, right = edge
        if not isinstance(left, str) or not left or not isinstance(right, str) or not right:
            raise ValueError('TEMPORAL_CONSTRAINT_INVALID')
        if operator == 'AFTER':
            left, right = right, left
        elif operator != 'BEFORE':
            raise ValueError('REGISTRY_REJECT')
        graph.setdefault(left, set()).add(right)
        graph.setdefault(right, set())
    indegree = {node: 0 for node in graph}
    for targets in graph.values():
        for target in targets:
            indegree[target] += 1
    ready = sorted(node for node, degree in indegree.items() if degree == 0)
    order = []
    while ready:
        node = ready.pop(0)
        order.append(node)
        for target in sorted(graph[node]):
            indegree[target] -= 1
            if indegree[target] == 0:
                ready.append(target)
                ready.sort()
    if len(order) != len(graph):
        raise ValueError('CONSTRAINT_CONFLICT')
    return tuple(order)


def derive_declared_region(rule, premise_regions, declared_result_region):
    """Validate a registered extension's explicit temporal conclusion region.

This helper licenses no logical conclusion by itself. The registered inference
rule still has to check its typed premises and produce its own proof. It only
prevents an extension from silently inventing a result interval by intersecting
unrelated evidence, or treating an absent result declaration as timelessness.
"""
    from .temporal_license import covers, normalize
    if getattr(rule, 'license_kind', None) != 'DECLARED':
        raise ValueError('INFERENCE_RULE_TEMPORAL_CONTRACT_INVALID')
    regions = tuple(premise_regions)
    if not regions or declared_result_region is None:
        raise ValueError('INFERENCE_TEMPORAL_MISMATCH')
    result = normalize(declared_result_region)
    if result.kind == 'UNDATED':
        if any(region.kind != 'UNDATED' for region in regions):
            raise ValueError('INFERENCE_TEMPORAL_MISMATCH')
        return result
    if result.kind not in {'POINT', 'CONTINUOUS', 'EXISTENTIAL'}:
        raise ValueError('INFERENCE_TEMPORAL_MISMATCH')
    if any(covers(normalize(region), result) is not True for region in regions):
        raise ValueError('INFERENCE_TEMPORAL_MISMATCH')
    return result
