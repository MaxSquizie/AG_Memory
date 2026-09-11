from __future__ import annotations

from dataclasses import replace

from .contracts import (
    ActDependencyCandidate,
    ActDependencyKind,
    AssertionCandidate,
    AssertionStatus,
    PerceptionResult,
    QueryMode,
)


_COUNTERFACTUAL_TARGET_SUFFIX = ":__CF_TARGET__"


def apply_speech_act_scoping(result: PerceptionResult) -> PerceptionResult:
    """Apply non-factual speech-act scope and expose counterfactual formula targets.

    Structural act dependencies preserve which clause/frame is embedded under a
    speech-act root. Mentioning proposition ``P`` inside ``ask/command(P)`` does
    not assert ``P`` as a world fact. Explicit ``HYPOTHETICAL`` status is stronger
    than ordinary embedding and is therefore preserved rather than overwritten.

    A direct polar counterfactual often arrives as ``QUERY(Q)`` with one or more
    ``HYPOTHETICAL`` descendants but no separate assertion node for Q itself. The
    existing CounterfactualGoal requires a canonical N/G formula target, while a
    QueryCandidate is intentionally not a canonical proposition. In that one typed
    situation this pass creates an EMBEDDED shadow assertion for the query target.
    Integration will canonicalize it with occurrence_count=0; it never becomes an
    ordinary factual premise. No surface marker such as "если бы" is inspected.

    The pass is deterministic and idempotent, including after document-local IDs
    are namespaced (``Q1:__CF_TARGET__`` -> ``B0:Q1:__CF_TARGET__``). Quoted edges
    are separate scope boundaries and are never traversed.
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

    def descendants(root_ref: str) -> set[str]:
        out: set[str] = set()
        queue = [root_ref]
        seen = {root_ref}
        while queue:
            parent = queue.pop()
            for child in adjacency.get(parent, ()):
                if child in seen:
                    continue
                seen.add(child)
                out.add(child)
                queue.append(child)
        return out

    embedded_ids: set[str] = set()
    for root_id in root_ids:
        embedded_ids.update(descendants(root_id))

    def mark(item: AssertionCandidate) -> AssertionCandidate:
        if (
            item.local_id not in embedded_ids
            or item.status is not AssertionStatus.ASSERTED
        ):
            return item
        alternatives = tuple(
            replace(alt, status=AssertionStatus.EMBEDDED)
            if alt.status is AssertionStatus.ASSERTED
            else alt
            for alt in item.alternatives
        )
        return replace(
            item,
            status=AssertionStatus.EMBEDDED,
            alternatives=alternatives,
        )

    assertions = list(mark(item) for item in result.assertions)
    dependencies = list(result.act_dependencies)
    assertion_by_id = {item.local_id: item for item in assertions}
    occupied_ids = set(root_ids) | set(assertion_by_id)
    relation_root_ids = {item.act_ref for item in result.act_relations}

    # Counterfactual assumptions are already semantic parser output. We only make
    # the direct query proposition addressable when there is no explicit EMBEDDED
    # target outside the hypothetical subtree. If an explicit target exists, it is
    # strictly better evidence and no shadow node is created.
    for query in result.queries:
        if query.local_id is None or query.quoted:
            continue
        qid = query.local_id
        q_descendants = descendants(qid)
        hypothetical_ids = {
            local_id
            for local_id in q_descendants
            if local_id in assertion_by_id
            and assertion_by_id[local_id].status is AssertionStatus.HYPOTHETICAL
            and not assertion_by_id[local_id].quoted
        }
        if not hypothetical_ids:
            continue

        hypothetical_scope: set[str] = set(hypothetical_ids)
        for local_id in hypothetical_ids:
            hypothetical_scope.update(descendants(local_id))
        explicit_targets = {
            local_id
            for local_id in q_descendants - hypothetical_scope
            if local_id in assertion_by_id
            and assertion_by_id[local_id].status is AssertionStatus.EMBEDDED
            and not assertion_by_id[local_id].quoted
        }
        if explicit_targets:
            continue

        # The existing CounterfactualGoal has a FormulaGoal target. Open-ended
        # FILL_ROLE questions and structural RelationGoal queries are deliberately
        # left without a shadow so GoalCompiler can fail closed rather than pretend
        # they are ordinary factual questions. Quantified+counterfactual composition
        # is likewise a separate feature; neither point 4 nor this pass owns it.
        if query.query_mode is not QueryMode.EXISTS:
            continue
        if qid in relation_root_ids:
            continue
        if getattr(query, "quantified", None) is not None:
            continue

        target_id = f"{qid}{_COUNTERFACTUAL_TARGET_SUFFIX}"
        if target_id in occupied_ids:
            # Idempotence: if a prior pass already created the exact shadow and its
            # dependency is present, there is nothing more to do. Any other use of
            # the reserved id is a malformed staging graph and must not be guessed.
            existing = assertion_by_id.get(target_id)
            if (
                existing is not None
                and existing.status is AssertionStatus.EMBEDDED
                and any(
                    edge.parent_ref == qid
                    and edge.child_ref == target_id
                    and edge.kind is ActDependencyKind.SUBORDINATE
                    for edge in dependencies
                )
            ):
                continue
            raise ValueError(
                f"Reserved counterfactual target id collision: {target_id}"
            )

        shadow = AssertionCandidate(
            local_id=target_id,
            predicate=query.predicate,
            actants=query.actants,
            status=AssertionStatus.EMBEDDED,
            quoted=False,
        )
        assertions.append(shadow)
        assertion_by_id[target_id] = shadow
        occupied_ids.add(target_id)
        dependencies.append(
            ActDependencyCandidate(
                qid,
                target_id,
                ActDependencyKind.SUBORDINATE,
            )
        )
        adjacency.setdefault(qid, []).append(target_id)

    final_assertions = tuple(assertions)
    final_dependencies = tuple(dependencies)
    if (
        final_assertions == result.assertions
        and final_dependencies == result.act_dependencies
    ):
        return result
    return replace(
        result,
        assertions=final_assertions,
        act_dependencies=final_dependencies,
    )
