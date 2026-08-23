from __future__ import annotations

from dataclasses import replace

from .contracts import (
    ActDependencyKind,
    AssertionCandidate,
    AssertionStatus,
    PerceptionResult,
)


def apply_speech_act_scoping(result: PerceptionResult) -> PerceptionResult:
    """Mark assertion content embedded under live QUERY/COMMAND roots.

    Structural act dependencies preserve which clause/frame is embedded under a
    speech-act root.  Mentioning proposition ``P`` inside ``ask/command(P)`` does
    not assert ``P`` as a world fact.  This pass is deterministic and idempotent;
    quoted edges are separate scope boundaries and are therefore not traversed.
    """
    root_ids = {
        item.local_id
        for item in (*result.queries, *result.commands)
        if item.local_id is not None and not item.quoted
    }
    if not root_ids or not result.act_dependencies:
        return result

    adjacency: dict[str, list[str]] = {}
    for dependency in result.act_dependencies:
        if dependency.kind is ActDependencyKind.QUOTED:
            continue
        adjacency.setdefault(dependency.parent_ref, []).append(dependency.child_ref)

    embedded_ids: set[str] = set()
    queue = list(root_ids)
    visited = set(root_ids)
    while queue:
        parent = queue.pop()
        for child in adjacency.get(parent, ()):
            if child in visited:
                continue
            visited.add(child)
            embedded_ids.add(child)
            queue.append(child)

    if not embedded_ids:
        return result

    def mark(item: AssertionCandidate) -> AssertionCandidate:
        if item.local_id not in embedded_ids or item.status is not AssertionStatus.ASSERTED:
            return item
        alternatives = tuple(
            replace(alt, status=AssertionStatus.EMBEDDED)
            if alt.status is AssertionStatus.ASSERTED
            else alt
            for alt in item.alternatives
        )
        return replace(item, status=AssertionStatus.EMBEDDED, alternatives=alternatives)

    assertions = tuple(mark(item) for item in result.assertions)
    if assertions == result.assertions:
        return result
    return replace(result, assertions=assertions)
