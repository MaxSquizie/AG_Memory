from __future__ import annotations

from ah.config import ContextSettings
from ah.core import AHCore
from ah.model import Domain, Property
from ah.projection.event_context import EventAwareContextProjector


def _projector_with_active_entity():
    core = AHCore()
    entity = core.add_entity(
        Domain.P,
        {"name": Property("name", "чай", "str")},
        {"gc_auto_created": True},
    )
    return EventAwareContextProjector(core, ContextSettings()), core.ref(entity.uid)


def test_ordinary_non_query_projection_keeps_active_memory() -> None:
    projector, ref = _projector_with_active_entity()

    context = projector.project("Я пил чай", (ref,))

    assert context.workspace_blocks
    assert context.source_workspace_refs == (ref,)
    assert "# ACTIVE MEMORY" in context.rendered


def test_formal_goal_projection_hides_unproved_active_memory_from_main_llm() -> None:
    projector, ref = _projector_with_active_entity()

    context = projector.project(
        "Что вчера делал Илья?",
        (ref,),
        (),
        (("event_query_temporal_not_found",),),
    )

    # The operator/debug channel still sees the true Workspace snapshot.
    assert context.source_workspace_refs == (ref,)
    # The Main LLM cannot append the active entity/fact to a formally constrained
    # answer when the reasoner did not prove it for that goal.
    assert context.workspace_blocks == ()
    assert "# ACTIVE MEMORY" not in context.rendered
    assert "# INFERENCE RESULTS" in context.rendered
    assert "чай" not in context.rendered
