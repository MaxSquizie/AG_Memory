from __future__ import annotations

from ah.agent.interaction_context import AssociationDiscourseSession, InteractionContext
from ah.config import ContextSettings
from ah.core import AHCore, SequentialUidGenerator
from ah.inference.association_goal import _EndpointResolution
from ah.inference.association_session_goal import AssociationSessionTurnGoalCompiler
from ah.integration.contracts import IntegrationCommit
from ah.model import ActantRole, Domain
from ah.perception.association_semantics import AssociationActRelationCandidate
from ah.perception.contracts import ActantCandidate, PredicateCandidate, QueryCandidate, QueryMode
from ah.projection.association_context import AssociationContextProjector


def _ref(core: AHCore, element):
    return core.ref(element.uid)


def test_unresolved_new_scope_closes_previous_association_session() -> None:
    core = AHCore(uid_generator=SequentialUidGenerator())
    crow = core.add_entity(Domain.C)
    table = core.add_entity(Domain.C)
    left = _ref(core, crow)
    right = _ref(core, table)

    class Compiler(AssociationSessionTurnGoalCompiler):
        def _resolve_endpoint(self, candidate, *args, **kwargs):
            key = candidate.normalized_hint or candidate.mention
            if key == "ворона":
                return _EndpointResolution(left, ())
            if key == "стол":
                return _EndpointResolution(right, ())
            # Explicit LOCATION cannot be represented canonically.
            return _EndpointResolution(
                None,
                diagnostic="semantic:association_endpoint_not_found",
            )

    compiler = Compiler(core)
    compiler._association_integration = IntegrationCommit((), left, ())
    context = InteractionContext(
        association_session=AssociationDiscourseSession(left, right)
    )
    query = QueryCandidate(
        predicate=PredicateCandidate("быть", normalized_hint="быть"),
        actants=(
            ActantCandidate(ActantRole.STATE, mention="общего", normalized_hint="общий"),
            ActantCandidate(ActantRole.SUBJECT, mention="вороны", normalized_hint="ворона"),
            ActantCandidate(ActantRole.OBJECT, mention="стола", normalized_hint="стол"),
            ActantCandidate(ActantRole.LOCATION, mention="во дворе", normalized_hint="двор"),
        ),
        query_mode=QueryMode.EXISTS,
        local_id="Q1",
    )
    relation = AssociationActRelationCandidate(
        "ASSOCIATION", "Q1", ActantRole.SUBJECT, ActantRole.OBJECT
    )

    built = compiler._resolve_association_root(query, relation, context)

    assert built.association_goal is None
    assert context.association_session is None
    assert any("constraint:LOCATION" in item for item in built.diagnostics)


def test_unresolved_association_projection_does_not_expose_workspace() -> None:
    core = AHCore(uid_generator=SequentialUidGenerator())
    warm = core.add_entity(Domain.C)
    projector = AssociationContextProjector(core, ContextSettings())

    context = projector.project_with_associations(
        "Что общего у вороны и стола во дворе?",
        (_ref(core, warm),),
        unresolved_goal_diagnostics=((
            "semantic:association_goal",
            "semantic:association_endpoint_not_found:constraint:LOCATION",
        ),),
    )

    assert "# ACTIVE MEMORY" not in context.rendered
    assert "UNRESOLVED" in context.rendered
