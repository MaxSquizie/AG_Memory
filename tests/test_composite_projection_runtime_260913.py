from __future__ import annotations

from ah.config import ContextSettings
from ah.core import AHCore
from ah.inference import (
    CompositeConclusion,
    ExistingRefConclusion,
    InferenceOutcome,
    LogicalStatus,
    StopReason,
)
from ah.model import Domain, Property
from ah.projection.association_context import AssociationContextProjector


def test_association_projection_preserves_composite_event_results() -> None:
    core = AHCore()
    first = core.add_entity(
        Domain.P,
        {"name": Property("name", "первое событие", "str")},
    )
    second = core.add_entity(
        Domain.P,
        {"name": Property("name", "второе событие", "str")},
    )
    first_ref = core.ref(first.uid)
    second_ref = core.ref(second.uid)
    outcome = InferenceOutcome(
        LogicalStatus.PROVED,
        StopReason.GOAL_SATISFIED,
        CompositeConclusion(
            (
                ExistingRefConclusion(first_ref),
                ExistingRefConclusion(second_ref),
            )
        ),
        (first_ref, second_ref),
        (first_ref, second_ref),
        Domain.P,
        2,
    )

    projector = AssociationContextProjector(core, ContextSettings())
    context = projector.project_with_associations(
        "Что ещё сделал Илья?",
        (),
        (outcome,),
        (),
        (),
    )

    assert len(context.inference_blocks) == 1
    assert "Найденные события по формальным ограничениям" in context.inference_blocks[0].semantic
    assert "первое событие" in context.inference_blocks[0].semantic
    assert "второе событие" in context.inference_blocks[0].semantic
