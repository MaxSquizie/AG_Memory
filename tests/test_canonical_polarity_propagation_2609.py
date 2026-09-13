from __future__ import annotations

from ah.agent import InteractionContext
from ah.core import AHCore, SequentialUidGenerator
from ah.integration import IntegrationConfig, IntegrationService
from ah.model import ActantRole, Domain, FunctionSymbol, Hypernode, Property
from ah.perception import (
    ActantCandidate,
    AssertionCandidate,
    AssertionStatus,
    PerceptionResult,
    PredicateCandidate,
    TemplateCandidate,
)


def _runtime() -> tuple[AHCore, InteractionContext, IntegrationService]:
    core = AHCore(uid_generator=SequentialUidGenerator())
    user = core.add_entity(Domain.P, {"name": Property("name", "user", "str")})
    agent = core.add_entity(Domain.P, {"name": Property("name", "agent", "str")})
    context = InteractionContext(user_ref=core.ref(user.uid), self_ref=core.ref(agent.uid))
    integration = IntegrationService(core, IntegrationConfig(0.4, 0.3, 0.02))
    return core, context, integration


def _candidate(*, status: AssertionStatus = AssertionStatus.ASSERTED) -> AssertionCandidate:
    return AssertionCandidate(
        "A1",
        PredicateCandidate(
            "работает",
            "работать",
            template_candidate=TemplateCandidate((ActantRole.SUBJECT,)),
        ),
        (ActantCandidate(ActantRole.SUBJECT, mention="сервер"),),
        negated=True,
        status=status,
    )


def _not_operand(core: AHCore, ref):
    wrapper = core.store.get_element_any_domain(ref.uid)
    assert isinstance(wrapper, FunctionSymbol)
    assert wrapper.function_id == "NOT"
    assert len(wrapper.operands) == 1
    operand = core.store.get_element_any_domain(wrapper.operands[0].uid)
    assert isinstance(operand, Hypernode)
    return operand


def test_asserted_negation_survives_integration_as_object_level_not() -> None:
    core, context, integration = _runtime()
    commit = integration.integrate_external(
        PerceptionResult("Сервер не работает.", assertions=(_candidate(),)), context
    )
    assert len(commit.assertions) == 1
    operand = _not_operand(core, commit.assertions[0].ref)
    assert operand.meta.get("semantic_scope") is None
    assert commit.assertions[0].semantic_scope is None


def test_embedded_negation_keeps_scope_and_does_not_become_asserted_positive_fact() -> None:
    core, context, integration = _runtime()
    commit = integration.integrate_external(
        PerceptionResult(
            "Вложенное содержание: сервер не работает.",
            assertions=(_candidate(status=AssertionStatus.EMBEDDED),),
        ),
        context,
    )
    assert len(commit.assertions) == 1
    integrated = commit.assertions[0]
    operand = _not_operand(core, integrated.ref)
    assert operand.meta.get("semantic_scope") == AssertionStatus.EMBEDDED.value
    assert integrated.semantic_scope == AssertionStatus.EMBEDDED.value
    assert all(seed.ref.uid != operand.uid for seed in commit.activation_seeds)
