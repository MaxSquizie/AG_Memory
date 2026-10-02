from __future__ import annotations

from types import SimpleNamespace

from ah.documents import DocumentProcessor


def _assertion(*anchors: tuple[str, int]):
    return SimpleNamespace(
        alternatives=(),
        actants=tuple(
            SimpleNamespace(entity_ref=entity_ref, evidence=SimpleNamespace(start=start))
            for entity_ref, start in anchors
        ),
    )


def _plan(*, anchors, candidates, ref_start=50):
    ref = SimpleNamespace(
        local_id="D1",
        candidate_entity_refs=tuple(candidates),
        source_start=ref_start,
    )
    return SimpleNamespace(
        candidate_ir=SimpleNamespace(discourse_refs=(ref,)),
        perception=SimpleNamespace(assertions=(_assertion(*anchors),)),
    )


class _Integration:
    def __init__(self):
        self.calls = []

    def bind_discourse_ref(self, plan, local_id, entity_ref, *, context=None):
        self.calls.append((local_id, entity_ref, context))
        return SimpleNamespace(
            candidate_ir=SimpleNamespace(discourse_refs=()),
            perception=plan.perception,
        )


def _processor():
    integration = _Integration()
    context = object()
    services = SimpleNamespace(integration=integration, context=context)
    return DocumentProcessor(services), integration, context


def test_unique_backward_antecedent_is_bound_with_keyword_only_context():
    processor, integration, context = _processor()
    plan = _plan(
        anchors=(("earlier", 10), ("future", 80)),
        candidates=("earlier", "future"),
        ref_start=50,
    )

    resolved = processor._resolve_batch_discourse_refs(plan)

    assert resolved.candidate_ir.discourse_refs == ()
    assert integration.calls == [("D1", "earlier", context)]


def test_future_only_candidate_is_never_used_as_antecedent():
    processor, integration, _context = _processor()
    plan = _plan(
        anchors=(("future", 80),),
        candidates=("future",),
        ref_start=50,
    )

    unresolved = processor._resolve_batch_discourse_refs(plan)

    assert unresolved is plan
    assert integration.calls == []
    assert unresolved.candidate_ir.discourse_refs[0].candidate_entity_refs == ("future",)


def test_multiple_backward_candidates_remain_explicitly_ambiguous():
    processor, integration, _context = _processor()
    plan = _plan(
        anchors=(("first", 10), ("second", 30)),
        candidates=("first", "second"),
        ref_start=50,
    )

    unresolved = processor._resolve_batch_discourse_refs(plan)

    assert unresolved is plan
    assert integration.calls == []
    assert unresolved.candidate_ir.discourse_refs[0].candidate_entity_refs == (
        "first",
        "second",
    )
