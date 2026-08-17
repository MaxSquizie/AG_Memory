from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from ah.agent.interaction_context import InteractionContext
from ah.agent.llm_agent import LLMAgent, LLMAgentSettings
from ah.agent.orchestrator import AgentOrchestrator
from ah.config import (
    ContextSettings,
    IgnitionSettings,
    InferenceSettings,
    IntegrationSettings,
    LLMRoleSettings,
    OrchestratorSettings,
    PersistenceSettings,
    WorkspaceSettings,
)
from ah.core import AHCore, JsonPersistence, SequentialUidGenerator
from ah.ignition import IgnitionEngine
from ah.inference import InferenceEngine, InferenceMaterializer, QueryGoalBuilder
from ah.integration import IntegrationConfig, IntegrationService
from ah.integration.contracts import ClarificationOption, ClarificationRequest
from ah.llm import LLMResponse
from ah.model import ActantRole, Domain, Group, Hypernode, Property, RefKind
from ah.perception import (
    ActantCandidate,
    AssertionCandidate,
    LLMPerceptionService,
    LLMPerceptionSettings,
    PerceptionClarificationRequired,
    PerceptionResult,
    PredicateCandidate,
    StructuralClarificationOption,
    StructuralClarificationSpec,
    TemplateCandidate,
    TextSensoryService,
)
from ah.projection import ContextProjector

PROJECT = Path(__file__).resolve().parents[1]


class StaticPerception:
    def __init__(self, result: PerceptionResult) -> None:
        self.result = result
        self.parse_calls = 0
        self.answer_calls = 0

    def parse(self, text, interaction_context):
        self.parse_calls += 1
        return self.result

    def interpret_clarification_answer(self, answer_text, option_labels):
        self.answer_calls += 1
        return None


class StructuralPerception:
    def __init__(self) -> None:
        self.source = "Иван увидел Петра с биноклем."
        self.parse_calls = 0
        self.resolve_calls: list[tuple[str, str]] = []

    def parse(self, text, interaction_context):
        self.parse_calls += 1
        raise PerceptionClarificationRequired(
            StructuralClarificationSpec(
                ambiguity_type="WITH_ATTACHMENT",
                mention="с биноклем",
                source_text=self.source,
                options=(
                    StructuralClarificationOption(
                        "PREDICATE_ATTACHMENT",
                        "«с биноклем» относится к действию «увидел»",
                    ),
                    StructuralClarificationOption(
                        "OBJECT_ATTACHMENT",
                        "«с биноклем» описывает «Петра»",
                    ),
                ),
            )
        )

    def parse_with_structural_resolution(self, text, interaction_context, resolution_key):
        self.resolve_calls.append((text, resolution_key))
        if resolution_key == "PREDICATE_ATTACHMENT":
            return PerceptionResult(
                source_text=text,
                assertions=(
                    AssertionCandidate(
                        "A1",
                        PredicateCandidate(
                            "увидел", "увидеть",
                            template_candidate=TemplateCandidate((
                                ActantRole.SUBJECT, ActantRole.OBJECT, ActantRole.TOOL,
                            )),
                        ),
                        (
                            ActantCandidate(ActantRole.SUBJECT, mention="Иван"),
                            ActantCandidate(ActantRole.OBJECT, mention="Пётр", entity_ref="E_PETR"),
                            ActantCandidate(ActantRole.TOOL, mention="бинокль"),
                        ),
                    ),
                ),
            )
        if resolution_key == "OBJECT_ATTACHMENT":
            return PerceptionResult(
                source_text=text,
                assertions=(
                    AssertionCandidate(
                        "A1",
                        PredicateCandidate(
                            "увидел", "увидеть",
                            template_candidate=TemplateCandidate((ActantRole.SUBJECT, ActantRole.OBJECT)),
                        ),
                        (
                            ActantCandidate(ActantRole.SUBJECT, mention="Иван"),
                            ActantCandidate(ActantRole.OBJECT, mention="Пётр", entity_ref="E_PETR"),
                        ),
                    ),
                    AssertionCandidate(
                        "A2",
                        PredicateCandidate(
                            "с", "с",
                            template_candidate=TemplateCandidate((ActantRole.SUBJECT, ActantRole.OBJECT)),
                        ),
                        (
                            ActantCandidate(ActantRole.SUBJECT, mention="Пётр", entity_ref="E_PETR"),
                            ActantCandidate(ActantRole.OBJECT, mention="бинокль"),
                        ),
                    ),
                ),
            )
        raise AssertionError(f"unexpected structural key: {resolution_key}")

    def propose_template_candidate(self, source_text, predicate, filled_roles, role_bindings=()):
        return TemplateCandidate(tuple(filled_roles))

    def interpret_clarification_answer(self, answer_text, option_labels):
        return None


class ClarifyingAgent:
    def __init__(self) -> None:
        self.clarify_calls = 0
        self.respond_calls = 0

    def clarify(self, request: ClarificationRequest) -> str:
        self.clarify_calls += 1
        labels = " или ".join(item.label for item in request.options)
        return f"Кого означает «{request.mention}»: {labels}?"

    def respond(self, context) -> str:
        self.respond_calls += 1
        return "Принято."


class ChoiceBackend:
    def __init__(self, answer: str) -> None:
        self.answer = answer
        self.calls = []

    def generate(self, prompt, *, system="", override=None, role="generic"):
        self.calls.append((role, prompt, system, dict(override or {})))
        return LLMResponse(self.answer, {})


class Clarification1221Tests(unittest.TestCase):
    def _runtime(self):
        core = AHCore(uid_generator=SequentialUidGenerator())
        self_e = core.add_entity(Domain.P, properties={"name": Property("name", "Agent", "str")})
        user_e = core.add_entity(Domain.P, properties={"name": Property("name", "User", "str")})
        context = InteractionContext(self_ref=core.ref(self_e.uid), user_ref=core.ref(user_e.uid))
        integration = IntegrationService(core, IntegrationConfig(0.4, 0.3, 0.2))
        return core, context, integration

    def _orchestrator(self, core, context, integration, perception, agent=None):
        agent = agent or ClarifyingAgent()
        ignition = IgnitionEngine(core, IgnitionSettings(), WorkspaceSettings(0.1))
        return AgentOrchestrator(
            context=context,
            sensory=TextSensoryService(core),
            perception=perception,
            integration=integration,
            ignition=ignition,
            query_builder=QueryGoalBuilder(core),
            inference=InferenceEngine(core, InferenceSettings()),
            materializer=InferenceMaterializer(core, IntegrationSettings()),
            projector=ContextProjector(core, ContextSettings(max_tokens=4096)),
            agent=agent,
            settings=OrchestratorSettings(),
            persistence=None,
        ), agent

    @staticmethod
    def _smile_result(mention: str = "Иван") -> PerceptionResult:
        return PerceptionResult(
            source_text=f"{mention} улыбнулся.",
            assertions=(
                AssertionCandidate(
                    "A1",
                    PredicateCandidate(
                        "улыбнулся",
                        "улыбнуться",
                        template_candidate=TemplateCandidate((ActantRole.SUBJECT,)),
                    ),
                    (ActantCandidate(ActantRole.SUBJECT, mention=mention),),
                ),
            ),
        )

    def test_structural_clarification_diagnostic_turn_is_safe_and_does_not_arm_pending_state(self):
        core, context, integration = self._runtime()
        perception = StructuralPerception()
        orchestrator, _agent = self._orchestrator(core, context, integration, perception)
        before_world = sum(
            isinstance(item, Hypernode)
            for domain in (Domain.C, Domain.P)
            for item in core.store.elements(domain)
        )

        turn = orchestrator.handle_user_text(perception.source, generate_response=False)

        self.assertTrue(turn.integration.clarification_required)
        self.assertEqual(turn.clarification_request.kind, "STRUCTURAL")
        self.assertEqual(context.pending_clarification_refs, [])
        after_world = sum(
            isinstance(item, Hypernode)
            for domain in (Domain.C, Domain.P)
            for item in core.store.elements(domain)
        )
        self.assertEqual(after_world, before_world)
        self.assertEqual(core.store.domain_of(turn.integration.experience_ref.uid), Domain.H)
        self.assertEqual(tuple(option.index for option in turn.clarification_request.options), (1, 2))

    def test_structural_clarification_live_resolution_attaches_semantics_to_original_experience(self):
        core, context, integration = self._runtime()
        perception = StructuralPerception()
        orchestrator, agent = self._orchestrator(core, context, integration, perception)

        first = orchestrator.handle_user_text(perception.source, generate_response=True)
        original_h = first.integration.experience_ref
        self.assertEqual(first.clarification_request.kind, "STRUCTURAL")
        self.assertEqual(context.pending_clarification_refs, [first.clarification_request.ambiguous_ref])
        self.assertEqual(agent.clarify_calls, 1)

        second = orchestrator.handle_user_text("1", generate_response=False)
        self.assertIsNotNone(second.clarification_resolution)
        self.assertEqual(context.pending_clarification_refs, [])
        self.assertEqual(
            perception.resolve_calls,
            [(perception.source, "PREDICATE_ATTACHMENT")],
        )

        original = core.store.get_hypernode(original_h.uid)
        self.assertIn(ActantRole.OBJECT, original.actants)
        semantic_ref = original.actants[ActantRole.OBJECT]
        semantic = core.store.get_hypernode(semantic_ref.uid)
        self.assertIn(ActantRole.TOOL, semantic.actants)
        self.assertEqual(
            core.store.get_element_any_domain(first.clarification_request.ambiguous_ref.uid).meta.get("resolved_to"),
            first.clarification_request.options[0].ref.uid,
        )

        matching_originals = [
            item for item in core.store.elements(Domain.H)
            if isinstance(item, Hypernode)
            and (item.properties.get("text") is not None)
            and item.properties["text"].value == perception.source
        ]
        self.assertEqual(len(matching_originals), 1)

    def test_structural_object_attachment_shares_object_identity_after_resolution(self):
        core, context, integration = self._runtime()
        perception = StructuralPerception()
        orchestrator, _agent = self._orchestrator(core, context, integration, perception)
        first = orchestrator.handle_user_text(perception.source, generate_response=True)
        orchestrator.handle_user_text("2", generate_response=False)

        seen_nodes = []
        with_nodes = []
        for item in core.store.elements(Domain.C):
            if not isinstance(item, Hypernode):
                continue
            template = core.store.get_template(item.template.uid)
            symbol = core.store.get_symbol(template.predicate.uid)
            if "увидеть" in symbol.forms:
                seen_nodes.append(item)
            if "с" in symbol.forms:
                with_nodes.append(item)
        self.assertEqual(len(seen_nodes), 1)
        self.assertEqual(len(with_nodes), 1)
        self.assertEqual(
            seen_nodes[0].actants[ActantRole.OBJECT],
            with_nodes[0].actants[ActantRole.SUBJECT],
        )
        self.assertEqual(
            core.store.get_element_any_domain(first.clarification_request.ambiguous_ref.uid).meta.get("resolved_to"),
            first.clarification_request.options[1].ref.uid,
        )

    def test_integration_exposes_structured_clarification_and_resolution_replaces_k(self):
        core, context, integration = self._runtime()
        first = core.add_entity(Domain.C, properties={"name": Property("name", "Иван", "str")})
        second = core.add_entity(Domain.C, properties={"name": Property("name", "Иван", "str")})

        commit = integration.integrate_external(self._smile_result(), context)
        self.assertTrue(commit.clarification_required)
        self.assertEqual(len(commit.clarifications), 1)
        request = commit.clarifications[0]
        self.assertEqual(request.ambiguous_ref.kind, RefKind.K)
        self.assertEqual(tuple(item.ref for item in request.options), (core.ref(first.uid), core.ref(second.uid)))
        self.assertEqual(tuple(item.index for item in request.options), (1, 2))
        self.assertTrue(all("Иван" in item.label for item in request.options))
        self.assertEqual(len(request.uses), 1)
        self.assertEqual(request.uses[0].roles, (ActantRole.SUBJECT,))

        resolution = integration.resolve_clarification(request.ambiguous_ref, core.ref(second.uid))
        self.assertEqual(resolution.selected_ref, core.ref(second.uid))
        node = core.store.get_hypernode(resolution.affected_facts[0].uid)
        self.assertEqual(node.actants[ActantRole.SUBJECT], core.ref(second.uid))
        self.assertTrue(core.store.has_uid(request.ambiguous_ref.uid))
        group = core.store.get_element_any_domain(request.ambiguous_ref.uid)
        self.assertIsInstance(group, Group)
        self.assertEqual(group.meta["TYPE"], "AMBIGUOUS_REFERENCE")
        self.assertEqual(core.store.hypernodes_for_actant(request.ambiguous_ref.uid), ())

    def test_resolution_preserves_domain_local_dedup_when_fact_becomes_existing_fact(self):
        core, context, integration = self._runtime()
        maria = core.add_entity(Domain.C, properties={"name": Property("name", "Мария", "str")})
        anna = core.add_entity(Domain.C, properties={"name": Property("name", "Анна", "str")})
        pred = core.ensure_abstract_symbol("улыбнуться")
        template = core.add_template(Domain.C, core.ref(pred.uid), (ActantRole.SUBJECT,))
        existing, _ = core.add_hypernode(
            Domain.C, core.ref(template.uid), {ActantRole.SUBJECT: core.ref(maria.uid)}, 0.4
        )

        result = PerceptionResult(
            "Она улыбнулась.",
            assertions=(
                AssertionCandidate(
                    "A1",
                    PredicateCandidate("улыбнулась", "улыбнуться"),
                    (ActantCandidate(ActantRole.SUBJECT, mention="она"),),
                    alternatives=(
                        AssertionCandidate(
                            "A1", PredicateCandidate("улыбнулась", "улыбнуться"),
                            (ActantCandidate(ActantRole.SUBJECT, mention="Анна"),),
                        ),
                        AssertionCandidate(
                            "A1", PredicateCandidate("улыбнулась", "улыбнуться"),
                            (ActantCandidate(ActantRole.SUBJECT, mention="Мария"),),
                        ),
                    ),
                ),
            ),
        )
        commit = integration.integrate_external(result, context)
        ambiguous_fact = commit.assertions[0].ref
        request = commit.clarifications[0]
        maria_option = next(item for item in request.options if item.ref == core.ref(maria.uid))

        resolution = integration.resolve_clarification(request.ambiguous_ref, maria_option.ref)
        self.assertEqual(resolution.affected_facts, (core.ref(existing.uid),))
        self.assertFalse(core.store.has_uid(ambiguous_fact.uid))
        smiles = [
            n for n in core.store.elements(Domain.C)
            if isinstance(n, Hypernode) and n.template.uid == template.uid
        ]
        self.assertEqual(len(smiles), 1)
        self.assertEqual(smiles[0].actants[ActantRole.SUBJECT], core.ref(maria.uid))

    def test_orchestrator_asks_clarification_then_resolves_explicit_answer(self):
        core, context, integration = self._runtime()
        anna = core.add_entity(Domain.C, properties={"name": Property("name", "Анна", "str")})
        maria = core.add_entity(Domain.C, properties={"name": Property("name", "Мария", "str")})
        result = PerceptionResult(
            "Она улыбнулась.",
            assertions=(
                AssertionCandidate(
                    "A1",
                    PredicateCandidate(
                        "улыбнулась", "улыбнуться",
                        template_candidate=TemplateCandidate((ActantRole.SUBJECT,)),
                    ),
                    (ActantCandidate(ActantRole.SUBJECT, mention="она"),),
                    alternatives=(
                        AssertionCandidate(
                            "A1", PredicateCandidate("улыбнулась", "улыбнуться"),
                            (ActantCandidate(ActantRole.SUBJECT, mention="Анна"),),
                        ),
                        AssertionCandidate(
                            "A1", PredicateCandidate("улыбнулась", "улыбнуться"),
                            (ActantCandidate(ActantRole.SUBJECT, mention="Мария"),),
                        ),
                    ),
                ),
            ),
        )
        perception = StaticPerception(result)
        agent = ClarifyingAgent()
        ignition = IgnitionEngine(core, IgnitionSettings(), WorkspaceSettings(0.1))
        orchestrator = AgentOrchestrator(
            context=context,
            sensory=TextSensoryService(core),
            perception=perception,
            integration=integration,
            ignition=ignition,
            query_builder=QueryGoalBuilder(core),
            inference=InferenceEngine(core, InferenceSettings()),
            materializer=InferenceMaterializer(core, IntegrationSettings()),
            projector=ContextProjector(core, ContextSettings(max_tokens=4096)),
            agent=agent,
            settings=OrchestratorSettings(),
            persistence=None,
        )

        first_turn = orchestrator.handle_user_text("Она улыбнулась.")
        self.assertIsNotNone(first_turn.clarification_request)
        self.assertEqual(agent.clarify_calls, 1)
        self.assertEqual(agent.respond_calls, 0)
        self.assertEqual(len(context.pending_clarification_refs), 1)
        ambiguous_ref = first_turn.clarification_request.ambiguous_ref

        second_turn = orchestrator.handle_user_text("Мария")
        self.assertIsNotNone(second_turn.clarification_resolution)
        self.assertEqual(second_turn.clarification_resolution.selected_ref, core.ref(maria.uid))
        self.assertEqual(context.pending_clarification_refs, [])
        self.assertEqual(perception.parse_calls, 1)  # clarification answer bypasses ordinary assertion parsing
        self.assertEqual(perception.answer_calls, 0)  # exact label was deterministic
        self.assertEqual(agent.respond_calls, 1)
        self.assertEqual(second_turn.response_text, "Принято.")
        self.assertEqual(core.store.hypernodes_for_actant(ambiguous_ref.uid), ())


    def test_orchestrator_can_use_perception_probe_to_interpret_nonliteral_clarification_answer(self):
        core, context, integration = self._runtime()
        anna = core.add_entity(Domain.C, properties={"name": Property("name", "Анна", "str")})
        maria = core.add_entity(Domain.C, properties={"name": Property("name", "Мария", "str")})
        result = PerceptionResult(
            "Она улыбнулась.",
            assertions=(
                AssertionCandidate(
                    "A1",
                    PredicateCandidate(
                        "улыбнулась", "улыбнуться",
                        template_candidate=TemplateCandidate((ActantRole.SUBJECT,)),
                    ),
                    (ActantCandidate(ActantRole.SUBJECT, mention="она"),),
                    alternatives=(
                        AssertionCandidate(
                            "A1", PredicateCandidate("улыбнулась", "улыбнуться"),
                            (ActantCandidate(ActantRole.SUBJECT, mention="Анна"),),
                        ),
                        AssertionCandidate(
                            "A1", PredicateCandidate("улыбнулась", "улыбнуться"),
                            (ActantCandidate(ActantRole.SUBJECT, mention="Мария"),),
                        ),
                    ),
                ),
            ),
        )

        class ProbePerception(StaticPerception):
            def interpret_clarification_answer(self, answer_text, option_labels):
                self.answer_calls += 1
                self.last_answer = (answer_text, option_labels)
                return 2

        perception = ProbePerception(result)
        agent = ClarifyingAgent()
        ignition = IgnitionEngine(core, IgnitionSettings(), WorkspaceSettings(0.1))
        orchestrator = AgentOrchestrator(
            context=context,
            sensory=TextSensoryService(core),
            perception=perception,
            integration=integration,
            ignition=ignition,
            query_builder=QueryGoalBuilder(core),
            inference=InferenceEngine(core, InferenceSettings()),
            materializer=InferenceMaterializer(core, IntegrationSettings()),
            projector=ContextProjector(core, ContextSettings(max_tokens=4096)),
            agent=agent,
            settings=OrchestratorSettings(),
            persistence=None,
        )
        orchestrator.handle_user_text("Она улыбнулась.")
        turn = orchestrator.handle_user_text("вторая")
        self.assertEqual(perception.answer_calls, 1)
        self.assertEqual(perception.last_answer, ("вторая", ("Анна", "Мария")))
        self.assertEqual(turn.clarification_resolution.selected_ref, core.ref(maria.uid))
        self.assertEqual(context.pending_clarification_refs, [])

    def test_diagnostic_turn_does_not_arm_pending_clarification(self):
        core, context, integration = self._runtime()
        core.add_entity(Domain.C, properties={"name": Property("name", "Иван", "str")})
        core.add_entity(Domain.C, properties={"name": Property("name", "Иван", "str")})
        perception = StaticPerception(self._smile_result())
        agent = ClarifyingAgent()
        ignition = IgnitionEngine(core, IgnitionSettings(), WorkspaceSettings(0.1))
        orchestrator = AgentOrchestrator(
            context=context,
            sensory=TextSensoryService(core),
            perception=perception,
            integration=integration,
            ignition=ignition,
            query_builder=QueryGoalBuilder(core),
            inference=InferenceEngine(core, InferenceSettings()),
            materializer=InferenceMaterializer(core, IntegrationSettings()),
            projector=ContextProjector(core, ContextSettings(max_tokens=4096)),
            agent=agent,
            settings=OrchestratorSettings(),
            persistence=None,
        )
        turn = orchestrator.handle_user_text("Иван улыбнулся.", generate_response=False)
        self.assertTrue(turn.integration.clarification_required)
        self.assertEqual(context.pending_clarification_refs, [])
        self.assertEqual(agent.clarify_calls, 0)

    def test_adaptive_clarification_probe_only_interprets_new_answer(self):
        backend = ChoiceBackend("SECOND")
        service = LLMPerceptionService(
            backend,
            LLMPerceptionSettings(
                protocol="adaptive_v3",
                probe_prompt_dir=PROJECT / "prompts/perception",
                probe_retry_attempts=0,
                generation=LLMRoleSettings(max_new_tokens=8, temperature=0.0, top_p=1.0, top_k=0),
                morphology_backend="none",
            ),
        )
        selected = service.interpret_clarification_answer("вторая", ("Анна", "Мария"))
        self.assertEqual(selected, 2)
        role, prompt, _system, override = backend.calls[0]
        self.assertEqual(role, "perception_clarification_answer")
        self.assertIn("CLARIFICATION ANSWER:\nвторая", prompt)
        self.assertIn("FIRST: Анна", prompt)
        self.assertIn("SECOND: Мария", prompt)
        self.assertNotIn("choice_outputs", override)

    def test_llm_agent_clarification_prompt_contains_labels_but_not_uids(self):
        backend = ChoiceBackend("Анна или Мария?")
        agent = LLMAgent(
            backend,
            LLMAgentSettings(generation=LLMRoleSettings(max_new_tokens=32, temperature=0.0)),
        )
        core = AHCore(uid_generator=SequentialUidGenerator())
        a = core.add_entity(Domain.C, properties={"name": Property("name", "Анна", "str")})
        m = core.add_entity(Domain.C, properties={"name": Property("name", "Мария", "str")})
        k = core.add_group(
            Domain.C, (core.ref(a.uid), core.ref(m.uid)),
            meta={"TYPE": "AMBIGUOUS_REFERENCE", "mention": "она"},
        )
        request = ClarificationRequest(
            core.ref(k.uid), "она",
            (
                ClarificationOption(1, core.ref(a.uid), "Анна"),
                ClarificationOption(2, core.ref(m.uid), "Мария"),
            ),
        )
        text = agent.clarify(request)
        self.assertEqual(text, "Анна или Мария?")
        role, prompt, _system, _override = backend.calls[0]
        self.assertEqual(role, "agent_clarification")
        self.assertIn("Анна", prompt)
        self.assertIn("Мария", prompt)
        self.assertNotIn(a.uid, prompt)
        self.assertNotIn(m.uid, prompt)
        self.assertNotIn(k.uid, prompt)

    def test_pending_structural_clarification_survives_persistence_roundtrip(self):
        with TemporaryDirectory() as td:
            core, context, integration = self._runtime()
            raw = integration.integrate_external(
                PerceptionResult(source_text="Иван увидел Петра с биноклем."), context
            )
            request = integration.register_structural_clarification(
                StructuralClarificationSpec(
                    ambiguity_type="WITH_ATTACHMENT",
                    mention="с биноклем",
                    source_text="Иван увидел Петра с биноклем.",
                    options=(
                        StructuralClarificationOption("PREDICATE_ATTACHMENT", "к действию"),
                        StructuralClarificationOption("OBJECT_ATTACHMENT", "к Петру"),
                    ),
                ),
                raw.experience_ref,
            )
            context.pending_clarification_refs = [request.ambiguous_ref]
            path = Path(td) / "memory.json"
            persistence = JsonPersistence(
                path,
                PersistenceSettings(enabled=True, load_on_start=True, save_runtime_state=False),
            )
            persistence.save(core, context=context)
            bundle = persistence.load(uid_generator=SequentialUidGenerator())
            loaded_context = bundle.interaction_context
            self.assertIsNotNone(loaded_context)
            self.assertEqual(
                loaded_context.pending_clarification_refs,
                [bundle.core.ref(request.ambiguous_ref.uid)],
            )
            loaded_integration = IntegrationService(bundle.core, IntegrationConfig(0.4, 0.3, 0.2))
            restored = loaded_integration.clarification_request(
                loaded_context.pending_clarification_refs[0]
            )
            self.assertEqual(restored.kind, "STRUCTURAL")
            self.assertEqual(tuple(item.label for item in restored.options), ("к действию", "к Петру"))
            self.assertEqual(restored.source_text, "Иван увидел Петра с биноклем.")

    def test_pending_clarification_context_survives_persistence_roundtrip(self):
        with TemporaryDirectory() as td:
            core = AHCore(uid_generator=SequentialUidGenerator())
            a = core.add_entity(Domain.C, properties={"name": Property("name", "Анна", "str")})
            m = core.add_entity(Domain.C, properties={"name": Property("name", "Мария", "str")})
            k = core.add_group(
                Domain.C, (core.ref(a.uid), core.ref(m.uid)),
                meta={"TYPE": "AMBIGUOUS_REFERENCE", "mention": "она"},
            )
            context = InteractionContext(pending_clarification_refs=[core.ref(k.uid)])
            path = Path(td) / "memory.json"
            persistence = JsonPersistence(
                path,
                PersistenceSettings(enabled=True, load_on_start=True, save_runtime_state=False),
            )
            persistence.save(core, context=context)
            bundle = persistence.load(uid_generator=SequentialUidGenerator())
            self.assertIsNotNone(bundle.interaction_context)
            self.assertEqual(bundle.interaction_context.pending_clarification_refs, [bundle.core.ref(k.uid)])


if __name__ == "__main__":
    unittest.main()
