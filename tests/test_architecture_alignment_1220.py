from __future__ import annotations

from pathlib import Path
import unittest

from ah.agent import InteractionContext
from ah.agent.orchestrator import AgentOrchestrator
from ah.config import (
    ContextSettings,
    InferenceSettings,
    IntegrationSettings,
    LLMRoleSettings,
    OrchestratorSettings,
    WorkspaceSettings,
    IgnitionSettings,
)
from ah.core import AHCore, SequentialUidGenerator
from ah.ignition import IgnitionEngine
from ah.inference import InferenceEngine, InferenceMaterializer, QueryGoalBuilder
from ah.integration import IntegrationConfig, IntegrationService
from ah.integration.errors import TemplateResolutionError
from ah.llm import LLMResponse
from ah.model import ActantRole, Domain, Property, RefKind
from ah.perception import (
    ActantCandidate,
    AssertionCandidate,
    PerceptionResult,
    PredicateCandidate,
    QueryCandidate,
    QueryMode,
    TemplateCandidate,
    TextSensoryService,
)
from ah.perception.adaptive_parser import (
    AdaptivePerceptionParser, AdaptiveSettings, _EVENT_RECIPIENT_COMPLETION,
)
from ah.perception.llm_parser import LLMPerceptionService, LLMPerceptionSettings
from ah.projection import ContextProjector

from test_acceptance_regressions_1218 import AcceptanceMorphology, RequestMorphology

PROJECT = Path(__file__).resolve().parents[1]


class FiniteBackend:
    def __init__(self, answers: dict[str, list[int | str | tuple[str, float]]]):
        self.answers = {key: list(values) for key, values in answers.items()}
        self.calls: list[tuple[str, str, dict | None]] = []

    def generate(self, prompt, *, system="", override=None, role="generic"):
        self.calls.append((role, prompt, override))
        values = self.answers.get(role)
        if not values:
            raise AssertionError(f"unexpected LLM call: {role}\n{prompt}")
        item = values.pop(0)
        if isinstance(item, tuple):
            text, margin = item
            return LLMResponse(str(text), {"choice_margin": margin})
        return LLMResponse(str(item), {})


class ArchitectureAlignment1220Tests(unittest.TestCase):
    def setUp(self) -> None:
        self.core = AHCore(uid_generator=SequentialUidGenerator())
        self.self_entity = self.core.add_entity(
            Domain.P, properties={"name": Property("name", "Агент", "str")}, uid="M_SELF"
        )
        self.user_entity = self.core.add_entity(
            Domain.P, properties={"name": Property("name", "Пользователь", "str")}, uid="M_USER"
        )
        self.context = InteractionContext(
            self_ref=self.core.ref(self.self_entity.uid),
            user_ref=self.core.ref(self.user_entity.uid),
        )
        self.integration = IntegrationService(
            self.core, IntegrationConfig(0.4, 0.3, 0.2, 0.18)
        )

    def test_raw_perception_does_not_invent_template_from_occurrence_roles(self):
        parser = AdaptivePerceptionParser(
            FiniteBackend({
                "perception_actant_start": [1, 2, 0],
                "perception_role_cue": ["ACTOR_OR_EXPERIENCER", "AFFECTED_OR_CONTENT"],
            }),
            AdaptiveSettings(
                prompt_dir=PROJECT / "prompts/perception",
                generation=LLMRoleSettings(max_new_tokens=24, temperature=0.0),
                retry_attempts=0,
                morphology_backend="none",
                verify_predicate_symbol=True,
            ),
            morphology=AcceptanceMorphology(),
        )
        assertion = parser.parse("Иван подарил книгу.").perception.assertions[0]
        self.assertIsNone(assertion.predicate.template_candidate)


    def test_template_preflight_requests_only_unknown_predicates(self):
        result = PerceptionResult(
            "Иван подарил книгу",
            assertions=(
                AssertionCandidate(
                    "A1",
                    PredicateCandidate("подарил", "подарить"),
                    (
                        ActantCandidate(ActantRole.SUBJECT, mention="Иван"),
                        ActantCandidate(ActantRole.OBJECT, mention="книга"),
                    ),
                ),
            ),
        )
        requests = self.integration.template_requests(result)
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0].filled_roles, (ActantRole.SUBJECT, ActantRole.OBJECT))

        symbol = self.core.add_abstract_symbol({"подарить", "подарил"})
        self.core.add_template(
            Domain.C,
            self.core.ref(symbol.uid),
            (ActantRole.SUBJECT, ActantRole.OBJECT, ActantRole.RECIPIENT),
        )
        requests = self.integration.template_requests(result)
        self.assertEqual(len(requests), 1)
        self.assertEqual([option.label for option in requests[0].sense_options], ["C1"])
        self.assertEqual(requests[0].sense_options[0].template_uid, self.core.store.find_templates_by_predicate(symbol.uid)[0].uid)

    def test_query_only_act_can_register_validated_template_without_creating_fact(self):
        predicate = PredicateCandidate(
            "любит", "любить",
            template_candidate=TemplateCandidate((ActantRole.SUBJECT, ActantRole.OBJECT)),
        )
        result = PerceptionResult(
            "Кто любит чай?",
            queries=(
                QueryCandidate(
                    predicate=predicate,
                    actants=(ActantCandidate(ActantRole.OBJECT, mention="чай"),),
                    requested_role=ActantRole.SUBJECT,
                    query_mode=QueryMode.FILL_ROLE,
                ),
            ),
        )
        commit = self.integration.integrate_external(result, self.context)
        symbol = self.core.store.find_symbol_by_form("любить")
        self.assertIsNotNone(symbol)
        templates = self.core.store.find_templates_by_predicate(symbol.uid)
        self.assertEqual(len(templates), 1)
        self.assertEqual(set(templates[0].roles), {ActantRole.SUBJECT, ActantRole.OBJECT})
        self.assertEqual(commit.assertions, ())
        self.assertEqual(len(commit.unresolved_queries), 1)
        unresolved = commit.unresolved_queries[0]
        self.assertEqual(unresolved.predicate.lookup_form, result.queries[0].predicate.lookup_form)
        self.assertEqual(unresolved.actants, result.queries[0].actants)
        self.assertEqual(unresolved.requested_roles, result.queries[0].requested_roles)
        self.assertIsNotNone(unresolved.predicate.template_selection)


    def test_runtime_entity_alternatives_become_canonical_ambiguity_group_in_integration(self):
        predicate = PredicateCandidate(
            "улыбнулась", "улыбнуться",
            template_candidate=TemplateCandidate((ActantRole.SUBJECT,)),
        )
        main = AssertionCandidate(
            "A1",
            predicate,
            (ActantCandidate(ActantRole.SUBJECT, mention="она"),),
            alternatives=(
                AssertionCandidate(
                    "A1", predicate,
                    (ActantCandidate(ActantRole.SUBJECT, mention="Анна", entity_ref="E1"),),
                ),
                AssertionCandidate(
                    "A1", predicate,
                    (ActantCandidate(ActantRole.SUBJECT, mention="Мария", entity_ref="E2"),),
                ),
            ),
        )
        commit = self.integration.integrate_external(
            PerceptionResult("Она улыбнулась.", assertions=(main,)), self.context
        )
        self.assertTrue(commit.clarification_required)
        node = self.core.store.get_hypernode(commit.assertions[0].ref.uid)
        subject_ref = node.actants[ActantRole.SUBJECT]
        self.assertEqual(subject_ref.kind, RefKind.K)
        group = self.core.store.get_element_any_domain(subject_ref.uid)
        self.assertEqual(group.meta["TYPE"], "AMBIGUOUS_REFERENCE")
        self.assertEqual(group.meta["mention"], "она")
        self.assertEqual(len(group.members), 2)

    def test_request_content_controller_is_semantically_resolved_before_integration(self):
        backend = FiniteBackend({
            "perception_actant_start": [1, 2, 0, 1, 0],
            "perception_role_cue": [
                "ACTOR_OR_EXPERIENCER",
                "RECEIVER_OR_ADDRESSEE",
                "AFFECTED_OR_CONTENT",
            ],
            "perception_content_addressee": ["CONTENT_ADDRESSEE"],
            "perception_frame_relation": ["CONTENT_LINK"],
            "perception_control_subject": ["SECOND"],
            "semantic_nonfinite_assertion_status": ["NONASSERTED_CONTENT"],
        })
        parser = AdaptivePerceptionParser(
            backend,
            AdaptiveSettings(
                prompt_dir=PROJECT / "prompts/perception",
                generation=LLMRoleSettings(max_new_tokens=24, temperature=0.0),
                retry_attempts=0,
                morphology_backend="none",
            ),
            morphology=RequestMorphology(),
        )
        result = parser.parse("Иван попросил Марию прочитать книгу.").perception
        parent, child = result.assertions
        recipient = next(a for a in parent.actants if a.role == ActantRole.RECIPIENT)
        content = next(a for a in parent.actants if a.role == ActantRole.OBJECT)
        child_subject = next(a for a in child.actants if a.role == ActantRole.SUBJECT)
        self.assertEqual(content.candidate_ref, child.local_id)
        self.assertEqual(child_subject.entity_ref, recipient.entity_ref)



if __name__ == "__main__":
    unittest.main()
