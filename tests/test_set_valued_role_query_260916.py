from __future__ import annotations

from ah.agent import InteractionContext
from ah.config import ContextSettings, InferenceSettings, IntegrationSettings
from ah.core import AHCore
from ah.inference import (
    CompositeConclusion,
    InferenceEngine,
    InferenceMaterializer,
    LogicalStatus,
    QueryGoalBuilder,
    RoleBindingConclusion,
)
from ah.model import ActantRole, Domain, Property
from ah.perception import (
    ActantCandidate,
    PredicateCandidate,
    QueryCandidate,
    QueryMode,
)
from ah.projection.association_context import AssociationContextProjector


def _entity(core: AHCore, domain: Domain, name: str):
    return core.add_entity(
        domain,
        {"name": Property("name", name, "str")},
    )


def test_user_wh_role_query_returns_every_matching_value() -> None:
    core = AHCore()
    user = _entity(core, Domain.P, "Пользователь")
    crow = _entity(core, Domain.C, "ворона")
    table = _entity(core, Domain.C, "стол")
    yard = _entity(core, Domain.C, "двор")
    context = InteractionContext(user_ref=core.ref(user.uid))

    symbol = core.add_abstract_symbol({"видеть", "видел"})
    template = core.add_template(
        Domain.C,
        core.ref(symbol.uid),
        (ActantRole.SUBJECT, ActantRole.OBJECT, ActantRole.LOCATION),
    )
    for value in (crow, table):
        core.add_hypernode(
            Domain.P,
            core.ref(template.uid),
            {
                ActantRole.SUBJECT: core.ref(user.uid),
                ActantRole.OBJECT: core.ref(value.uid),
                ActantRole.LOCATION: core.ref(yard.uid),
            },
            0.5,
        )

    query = QueryCandidate(
        predicate=PredicateCandidate("видел", normalized_hint="видеть"),
        actants=(
            ActantCandidate(
                ActantRole.SUBJECT,
                mention="я",
                normalized_hint="я",
            ),
            ActantCandidate(
                ActantRole.LOCATION,
                mention="двор",
                normalized_hint="двор",
            ),
        ),
        requested_roles=(ActantRole.OBJECT,),
        query_mode=QueryMode.FILL_ROLE,
        local_id="Q_WH_SET",
    )

    built = QueryGoalBuilder(core).build(query, context)
    assert built.goal is not None, built.diagnostics
    assert built.goal.goal.request_all_proofs is True

    outcome = InferenceEngine(core, InferenceSettings()).solve(built.goal)
    assert outcome.status is LogicalStatus.PROVED
    assert isinstance(outcome.conclusion, CompositeConclusion)
    assert all(
        isinstance(item, RoleBindingConclusion)
        for item in outcome.conclusion.conclusions
    )
    assert {
        item.value.uid
        for item in outcome.conclusion.conclusions
        if isinstance(item, RoleBindingConclusion)
    } == {crow.uid, table.uid}

    materialized = InferenceMaterializer(
        core,
        IntegrationSettings(),
    ).materialize(outcome)
    assert materialized.ref is None
    assert materialized.created is False

    projected = AssociationContextProjector(
        core,
        ContextSettings(),
    ).project_with_associations(
        "Что я видел во дворе?",
        (),
        (outcome,),
        (),
        (),
    )
    assert len(projected.inference_blocks) == 1
    semantic = projected.inference_blocks[0].semantic.casefold()
    assert "ворона" in semantic
    assert "стол" in semantic
