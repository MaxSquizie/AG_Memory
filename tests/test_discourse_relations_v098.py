from __future__ import annotations

from pathlib import Path

from ah.agent.discourse import DiscourseRelationRefiner
from ah.config import ContextSettings, LLMRoleSettings
from ah.core import AHCore, SequentialUidGenerator
from ah.integration import IntegrationConfig, IntegrationService
from ah.integration.contracts import IntegratedAssertion, IntegrationCommit
from ah.llm import LLMResponse
from ah.model import ActantRole, Domain, Property
from ah.perception import DiscourseRelationDecision
from ah.perception.adaptive_parser import AdaptivePerceptionParser, AdaptiveSettings
from ah.projection import ContextProjector

ROOT = Path(__file__).resolve().parents[1]


class ScriptedBackend:
    def __init__(self, answers):
        self.answers = {key: list(values) for key, values in answers.items()}
        self.calls = []

    def generate(self, prompt, *, system="", override=None, role="generic"):
        self.calls.append((role, prompt, dict(override or {})))
        queue = self.answers.get(role)
        if not queue:
            raise AssertionError(f"unexpected model call {role}:\n{prompt}")
        return LLMResponse(queue.pop(0), {})


def test_uid_free_discourse_probe_selects_prior_current_and_relation():
    backend = ScriptedBackend({
        "semantic_discourse_current_event": ["C1"],
        "semantic_discourse_prior_event": ["P2"],
        "semantic_discourse_relation": ["CAUSE"],
    })
    parser = AdaptivePerceptionParser(
        backend,
        AdaptiveSettings(
            prompt_dir=ROOT / "prompts/perception",
            generation=LLMRoleSettings(max_new_tokens=24, temperature=0.0),
            retry_attempts=0,
            morphology_backend="none",
        ),
    )
    decision = parser.classify_discourse_relation(
        "Матросы спорили. Потом они направились к люку.",
        ("спорить(SUBJECT=матрос)", "обсуждать(SUBJECT=матрос)"),
        ("направиться(SUBJECT=матрос, LOCATION=люк)",),
    )
    assert decision == DiscourseRelationDecision("CAUSE", 1, 0)
    assert [call[0] for call in backend.calls] == [
        "semantic_discourse_current_event",
        "semantic_discourse_prior_event",
        "semantic_discourse_relation",
    ]
    assert all(call[2].get("enable_thinking") is False for call in backend.calls)
    # Local labels and semantics are visible; canonical AH UIDs are not part of this API.
    assert all("N_" not in call[1] and "M_" not in call[1] for call in backend.calls)


class DecisionPerception:
    def __init__(self, decision):
        self.decision = decision
        self.calls = []

    def classify_discourse_relation(
        self,
        narrative_context,
        prior_events,
        current_events,
        *,
        excluded_pairs=(),
    ):
        self.calls.append((narrative_context, prior_events, current_events, excluded_pairs))
        value = self.decision
        self.decision = None
        return value


def _memory_fixture():
    core = AHCore(uid_generator=SequentialUidGenerator())
    config = IntegrationConfig(
        initial_hypernode_weight=0.4,
        experience_hypernode_weight=0.3,
        follow_link_weight=0.2,
        cause_link_weight=0.2,
        is_a_link_weight=0.2,
        nominal_relation_link_weight=0.2,
    )
    integration = IntegrationService(core, config)
    projector = ContextProjector(core, ContextSettings(max_tokens=2048))

    actor = core.add_entity(Domain.C, {"name": Property("name", "матрос", "str")})
    prior_pred = core.add_abstract_symbol({"обсуждать"})
    current_pred = core.add_abstract_symbol({"направиться"})
    say_pred = core.add_abstract_symbol({"высказать"})
    prior_t = core.add_template(Domain.C, core.ref(prior_pred.uid), (ActantRole.SUBJECT,))
    current_t = core.add_template(Domain.C, core.ref(current_pred.uid), (ActantRole.SUBJECT,))
    say_t = core.add_template(Domain.H, core.ref(say_pred.uid), (ActantRole.OBJECT,))
    prior, _ = core.add_hypernode(
        Domain.C, core.ref(prior_t.uid), {ActantRole.SUBJECT: core.ref(actor.uid)}, 0.4
    )
    current, _ = core.add_hypernode(
        Domain.C, core.ref(current_t.uid), {ActantRole.SUBJECT: core.ref(actor.uid)}, 0.4
    )
    prior_exp, _ = core.add_hypernode(
        Domain.H,
        core.ref(say_t.uid),
        {ActantRole.OBJECT: core.ref(prior.uid)},
        0.3,
        properties={"text": Property("text", "Матросы обсуждали, что делать.", "str")},
        meta={"event_instance": True},
        deduplicate=False,
    )
    current_exp, _ = core.add_hypernode(
        Domain.H,
        core.ref(say_t.uid),
        {ActantRole.OBJECT: core.ref(current.uid)},
        0.3,
        properties={"text": Property("text", "Матросы направились к люку.", "str")},
        meta={"event_instance": True},
        deduplicate=False,
    )
    core.add_link("FOLLOW", core.ref(prior_exp.uid), core.ref(current_exp.uid), 0.2)
    commit = IntegrationCommit(
        assertions=(IntegratedAssertion("A1", core.ref(current.uid), Domain.C, True),),
        experience_ref=core.ref(current_exp.uid),
        activation_seeds=(),
    )
    return core, integration, projector, prior, current, prior_exp, current_exp, commit


def test_refiner_reads_only_active_h_history_and_materializes_through_integration():
    core, integration, projector, prior, current, prior_exp, _current_exp, commit = _memory_fixture()
    perception = DecisionPerception(DiscourseRelationDecision("FOLLOW", 0, 0))
    refiner = DiscourseRelationRefiner(integration, perception, projector)

    review = refiner.prepare(
        commit,
        (core.ref(prior_exp.uid), core.ref(prior.uid), core.ref(current.uid)),
        "Матросы направились к люку.",
    )
    assert review is not None
    assert review.prior_refs == (core.ref(prior.uid),)
    assert review.current_refs == (core.ref(current.uid),)
    assert "Матросы обсуждали" in review.narrative_text
    assert all("N_" not in text for text in (*review.prior_semantics, *review.current_semantics))

    decisions = refiner.decide(review)
    relations = refiner.integrate(review, decisions)
    assert len(relations) == 1
    assert relations[0].relation_id == "FOLLOW"
    link = core.store.find_link("FOLLOW", prior.uid, current.uid)
    assert link is not None


def test_refiner_does_not_globally_read_inactive_prior_experience():
    core, integration, projector, prior, current, _prior_exp, _current_exp, commit = _memory_fixture()
    perception = DecisionPerception(DiscourseRelationDecision("CAUSE", 0, 0))
    refiner = DiscourseRelationRefiner(integration, perception, projector)
    # Prior semantic N is active but the H experience that gives access to the
    # narrative path is not. The refiner must not jump around the global AH store.
    review = refiner.prepare(
        commit,
        (core.ref(prior.uid), core.ref(current.uid)),
        "Матросы направились к люку.",
    )
    assert review is None
    assert perception.calls == []


def test_integration_rejects_embedded_cross_turn_endpoint():
    core, integration, _projector, prior, current, _prior_exp, _current_exp, _commit = _memory_fixture()
    embedded = core.store.get_hypernode(prior.uid)
    from dataclasses import replace
    core.edit_element(Domain.C, replace(embedded, meta={**dict(embedded.meta), "semantic_scope": "EMBEDDED"}))
    import pytest
    with pytest.raises(Exception):
        integration.integrate_discourse_relation("CAUSE", core.ref(prior.uid), core.ref(current.uid))
