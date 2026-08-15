from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from ah.agent.interaction_context import InteractionContext
from ah.agent.orchestrator import AgentOrchestrator
from ah.config import (
    ContextSettings,
    IgnitionSettings,
    InferenceSettings,
    IntegrationSettings,
    LifecycleSettings,
    OrchestratorSettings,
    PersistenceSettings,
    WorkspaceSettings,
)
from ah.core import AHCore, JsonPersistence, SequentialUidGenerator
from ah.ignition import IgnitionEngine, LifecycleStage
from ah.inference import InferenceEngine, InferenceMaterializer, QueryGoalBuilder
from ah.integration import CandidateValidationError, IntegrationConfig, IntegrationService
from ah.integration.contracts import SeedReason
from ah.model import ActantRole, Domain, Hypernode, Property
from ah.perception import (
    ActantCandidate,
    AssertionCandidate,
    LLMPerceptionService,
    LLMPerceptionSettings,
    PerceptionResult,
    PredicateCandidate,
    PerceptionParseError,
    TemplateCandidate,
    TextSensoryService,
)
from ah.projection import ContextProjector


class FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text


class FakeLLMBackend:
    def __init__(self, outputs: list[str]) -> None:
        self.outputs = list(outputs)

    def generate(self, prompt: str, *, system: str = "", override=None, role: str = "generic"):
        return FakeResponse(self.outputs.pop(0))


class FakePerception:
    def __init__(self, user: PerceptionResult, response: PerceptionResult) -> None:
        self.user = user
        self.response = response
        self.calls = 0

    def parse(self, text: str, interaction_context: InteractionContext) -> PerceptionResult:
        self.calls += 1
        return self.user if self.calls == 1 else self.response


class FailingPerception:
    def parse(self, text: str, interaction_context: InteractionContext) -> PerceptionResult:
        raise PerceptionParseError("semantic parse failed")


class FakeAgent:
    def __init__(self, text: str) -> None:
        self.text = text

    def respond(self, context) -> str:
        return self.text


class LifecyclePersistenceOrchestratorTests(unittest.TestCase):
    def _fact(self, core: AHCore, domain: Domain = Domain.C):
        pred = core.ensure_abstract_symbol("быть")
        t = core.add_template(domain, core.ref(pred.uid), (ActantRole.SUBJECT, ActantRole.STATE))
        a = core.add_entity(domain, properties={"name": Property("name", "A", "str")})
        b = core.add_entity(domain, properties={"name": Property("name", "B", "str")})
        n, _ = core.add_hypernode(
            domain,
            core.ref(t.uid),
            {ActantRole.SUBJECT: core.ref(a.uid), ActantRole.STATE: core.ref(b.uid)},
            0.4,
        )
        return core.ref(n.uid)

    def test_lifecycle_new_reinforced_consolidated(self) -> None:
        core = AHCore(uid_generator=SequentialUidGenerator())
        n = self._fact(core)
        engine = IgnitionEngine(
            core,
            IgnitionSettings(),
            WorkspaceSettings(threshold=0.1),
            LifecycleSettings(
                initial_lifetime_ticks=100,
                reinforced_lifetime_ticks=100,
                min_spacing_1_ticks=2,
                min_spacing_2_ticks=3,
            ),
        )
        engine.seed(n, 0.4, reason=SeedReason.NEW_FACT)
        engine.tick()  # tick 0, creation
        self.assertEqual(core.store.get_hypernode(n.uid).meta["lifecycle_state"], LifecycleStage.NEW.value)

        engine.tick()  # tick 1
        engine.seed(n, 0.4, reason=SeedReason.REACTIVATED_FACT)
        engine.tick()  # tick 2 -> reinforced
        self.assertEqual(core.store.get_hypernode(n.uid).meta["lifecycle_state"], LifecycleStage.REINFORCED.value)

        engine.tick()  # 3
        engine.tick()  # 4
        engine.seed(n, 0.4, reason=SeedReason.REACTIVATED_FACT)
        engine.tick()  # 5 -> consolidated
        self.assertEqual(core.store.get_hypernode(n.uid).meta["lifecycle_state"], LifecycleStage.CONSOLIDATED.value)
        self.assertNotIn("expires_tick", core.store.get_hypernode(n.uid).meta)

    def test_expired_unreferenced_new_n_is_gc_deleted(self) -> None:
        core = AHCore(uid_generator=SequentialUidGenerator())
        n = self._fact(core)
        engine = IgnitionEngine(
            core,
            IgnitionSettings(),
            WorkspaceSettings(threshold=0.1),
            LifecycleSettings(
                initial_lifetime_ticks=2,
                reinforced_lifetime_ticks=10,
                min_spacing_1_ticks=10,
                min_spacing_2_ticks=10,
            ),
        )
        engine.seed(n, 0.4, reason=SeedReason.NEW_FACT)
        engine.tick()
        engine.tick()
        result = engine.tick()
        self.assertFalse(core.store.has_uid(n.uid))
        self.assertIn(n.uid, set(result.gc.deleted))

    def test_h_structural_reference_protects_expired_c_fact(self) -> None:
        core = AHCore(uid_generator=SequentialUidGenerator())
        c_fact = self._fact(core, Domain.C)
        speaker = core.add_entity(Domain.P, properties={"name": Property("name", "User", "str")})
        say = core.ensure_abstract_symbol("сказать")
        t = core.add_template(Domain.H, core.ref(say.uid), (ActantRole.SUBJECT, ActantRole.OBJECT))
        core.add_hypernode(
            Domain.H,
            core.ref(t.uid),
            {ActantRole.SUBJECT: core.ref(speaker.uid), ActantRole.OBJECT: c_fact},
            0.3,
            deduplicate=False,
        )
        engine = IgnitionEngine(
            core,
            IgnitionSettings(),
            WorkspaceSettings(threshold=0.1),
            LifecycleSettings(2, 10, 10, 10),
        )
        engine.seed(c_fact, 0.4, reason=SeedReason.NEW_FACT)
        engine.tick(); engine.tick(); result = engine.tick()
        self.assertTrue(core.store.has_uid(c_fact.uid))
        self.assertIn(c_fact.uid, set(result.gc.protected))

    def test_json_persistence_roundtrip_rebuilds_indexes_and_runtime(self) -> None:
        with TemporaryDirectory() as td:
            path = Path(td) / "memory.json"
            settings = PersistenceSettings(
                enabled=True,
                load_on_start=True,
                autosave_every_ticks=2,
                save_runtime_state=True,
                save_pending_impulses=True,
            )
            core = AHCore(uid_generator=SequentialUidGenerator())
            a = core.add_entity(Domain.C, properties={"name": Property("name", "Alpha", "str")})
            b = core.add_entity(Domain.C, properties={"name": Property("name", "Beta", "str")})
            link = core.add_link("IS-A", core.ref(a.uid), core.ref(b.uid), 0.4)
            engine = IgnitionEngine(core, IgnitionSettings(), WorkspaceSettings(0.1))
            engine.seed(core.ref(a.uid), 0.6)
            engine.tick()
            engine.seed(core.ref(b.uid), 0.25)  # pending at save time
            expected_pending = engine.export_snapshot().incoming[b.uid]
            context = InteractionContext(self_ref=core.ref(a.uid), user_ref=core.ref(b.uid))

            persistence = JsonPersistence(path, settings)
            persistence.save(core, ignition=engine, context=context)
            bundle = persistence.load(uid_generator=SequentialUidGenerator())

            self.assertEqual(bundle.core.store.find_entities_by_name("Alpha")[0].uid, a.uid)
            self.assertEqual(bundle.core.store.find_link("IS-A", a.uid, b.uid).uid, link.uid)
            self.assertGreater(bundle.core.store.runtime_state(a.uid).excitation, 0)
            self.assertIsNotNone(bundle.ignition_snapshot)
            self.assertAlmostEqual(bundle.ignition_snapshot.incoming[b.uid], expected_pending)
            self.assertEqual(bundle.interaction_context.self_ref.uid, a.uid)

    def test_persistence_roundtrip_preserves_pacemaker_and_pending_refutation(self) -> None:
        with TemporaryDirectory() as td:
            path = Path(td) / "memory.json"
            settings = PersistenceSettings(
                enabled=True,
                load_on_start=True,
                autosave_every_ticks=10,
                save_runtime_state=True,
                save_pending_impulses=True,
            )
            core = AHCore(uid_generator=SequentialUidGenerator())
            target = self._fact(core, Domain.C)
            from ah.config import PacemakerSettings
            from ah.integration.contracts import RefutationRequest
            ignition_settings = IgnitionSettings(
                tick_interval_seconds=0.1,
                nu=2.0,
                pacemaker=PacemakerSettings(
                    enabled=True,
                    target_policy="round_robin",
                    include_symbols=False,
                ),
            )
            engine = IgnitionEngine(core, ignition_settings, WorkspaceSettings(0.1))
            for _ in range(3):
                engine.tick()
            engine.apply_refutation_requests((RefutationRequest(target),))
            before = engine.export_snapshot()

            persistence = JsonPersistence(path, settings)
            persistence.save(core, ignition=engine, context=InteractionContext())
            bundle = persistence.load(uid_generator=SequentialUidGenerator())

            self.assertIsNotNone(bundle.ignition_snapshot)
            restored = bundle.ignition_snapshot
            self.assertEqual(restored.pending_refutations, (target.uid,))
            self.assertAlmostEqual(restored.pacemaker.phase, before.pacemaker.phase)
            self.assertEqual(restored.pacemaker.cursor, before.pacemaker.cursor)
            self.assertEqual(restored.pacemaker.pulse_count, before.pacemaker.pulse_count)

    def test_llm_perception_json_parser_does_not_emit_uids(self) -> None:
        backend = FakeLLMBackend([
            '''{"assertions":[{"local_id":"A1","predicate":{"surface":"любит","normalized_hint":"любить"},"actants":[{"role":"SUBJECT","mention":"Маша"},{"role":"OBJECT","mention":"чай"}]}],"queries":[],"commands":[],"diagnostics":[]}'''
        ])
        service = LLMPerceptionService(backend, LLMPerceptionSettings(protocol="legacy_json", probe_retry_attempts=0))
        result = service.parse("Маша любит чай", InteractionContext())
        self.assertEqual(result.assertions[0].predicate.lookup_form, "любить")
        self.assertEqual(result.assertions[0].actants[0].role, ActantRole.SUBJECT)
        self.assertEqual(
            result.assertions[0].predicate.template_candidate.roles,
            (ActantRole.SUBJECT, ActantRole.OBJECT),
        )

    def test_full_orchestrator_records_response_only_in_h(self) -> None:
        core = AHCore(uid_generator=SequentialUidGenerator())
        self_e = core.add_entity(Domain.P, properties={"name": Property("name", "Agent", "str")})
        user_e = core.add_entity(Domain.P, properties={"name": Property("name", "User", "str")})
        context = InteractionContext(self_ref=core.ref(self_e.uid), user_ref=core.ref(user_e.uid))
        integration = IntegrationService(core, IntegrationConfig(0.4, 0.3, 0.2))
        ignition = IgnitionEngine(core, IgnitionSettings(), WorkspaceSettings(0.1))

        user_result = PerceptionResult(
            "Небо синее",
            assertions=(
                AssertionCandidate(
                    "A1",
                    PredicateCandidate(
                        "быть",
                        "быть",
                        template_candidate=TemplateCandidate(
                            (ActantRole.SUBJECT, ActantRole.STATE)
                        ),
                    ),
                    (
                        ActantCandidate(ActantRole.SUBJECT, mention="небо"),
                        ActantCandidate(ActantRole.STATE, mention="синее"),
                    ),
                ),
            ),
        )
        response_result = PerceptionResult(
            "Я сказал, что небо синее",
            assertions=(
                AssertionCandidate(
                    "R1",
                    PredicateCandidate(
                        "сказать",
                        "сказать",
                        template_candidate=TemplateCandidate((ActantRole.SUBJECT,)),
                    ),
                    (ActantCandidate(ActantRole.SUBJECT, mention="я"),),
                ),
            ),
        )
        orchestrator = AgentOrchestrator(
            context=context,
            sensory=TextSensoryService(core),
            perception=FakePerception(user_result, response_result),
            integration=integration,
            ignition=ignition,
            query_builder=QueryGoalBuilder(core),
            inference=InferenceEngine(core, InferenceSettings()),
            materializer=InferenceMaterializer(core, IntegrationSettings()),
            projector=ContextProjector(core, ContextSettings(max_tokens=4096)),
            agent=FakeAgent("Я сказал, что небо синее"),
            settings=OrchestratorSettings(1, 1, True, True),
            persistence=None,
        )
        turn = orchestrator.handle_user_text("Небо синее")
        self.assertIsNotNone(turn.response_integration)
        self.assertTrue(all(item.domain is Domain.H for item in turn.response_integration.assertions))
        # User semantic assertion is C, response semantic assertion is H-only.
        self.assertTrue(any(item.domain is Domain.C for item in turn.integration.assertions))

    def test_diagnostic_turn_can_stop_before_agent_generation_without_synthetic_response_h_event(self) -> None:
        class FailIfCalledAgent:
            def respond(self, context) -> str:
                raise AssertionError("agent generation must be skipped")

        core = AHCore(uid_generator=SequentialUidGenerator())
        self_e = core.add_entity(Domain.P, properties={"name": Property("name", "Agent", "str")})
        user_e = core.add_entity(Domain.P, properties={"name": Property("name", "User", "str")})
        context = InteractionContext(self_ref=core.ref(self_e.uid), user_ref=core.ref(user_e.uid))
        integration = IntegrationService(core, IntegrationConfig(0.4, 0.3, 0.2))
        ignition = IgnitionEngine(core, IgnitionSettings(), WorkspaceSettings(0.1))
        orchestrator = AgentOrchestrator(
            context=context,
            sensory=TextSensoryService(core),
            perception=FakePerception(PerceptionResult("Привет"), PerceptionResult("unused")),
            integration=integration,
            ignition=ignition,
            query_builder=QueryGoalBuilder(core),
            inference=InferenceEngine(core, InferenceSettings()),
            materializer=InferenceMaterializer(core, IntegrationSettings()),
            projector=ContextProjector(core, ContextSettings(max_tokens=4096)),
            agent=FailIfCalledAgent(),
            settings=OrchestratorSettings(),
            persistence=None,
        )

        turn = orchestrator.handle_user_text("Привет", generate_response=False)

        self.assertIsNone(turn.response_text)
        self.assertIsNone(turn.response_perception)
        self.assertIsNone(turn.response_integration)
        self.assertEqual(turn.ticks_after_response, ())
        h_texts = [
            item.properties["text"].value
            for item in core.store.elements(Domain.H)
            if isinstance(item, Hypernode) and item.properties.get("text") is not None
        ]
        self.assertEqual(h_texts, ["Привет"])

    def test_perception_failure_is_raised_but_raw_user_turn_is_still_experienced_in_h(self) -> None:
        core = AHCore(uid_generator=SequentialUidGenerator())
        self_e = core.add_entity(Domain.P, properties={"name": Property("name", "Agent", "str")})
        user_e = core.add_entity(Domain.P, properties={"name": Property("name", "User", "str")})
        context = InteractionContext(self_ref=core.ref(self_e.uid), user_ref=core.ref(user_e.uid))
        integration = IntegrationService(core, IntegrationConfig(0.4, 0.3, 0.2))
        ignition = IgnitionEngine(core, IgnitionSettings(), WorkspaceSettings(0.1))
        orchestrator = AgentOrchestrator(
            context=context,
            sensory=TextSensoryService(core),
            perception=FailingPerception(),
            integration=integration,
            ignition=ignition,
            query_builder=QueryGoalBuilder(core),
            inference=InferenceEngine(core, InferenceSettings()),
            materializer=InferenceMaterializer(core, IntegrationSettings()),
            projector=ContextProjector(core, ContextSettings(max_tokens=4096)),
            agent=FakeAgent("unused"),
            settings=OrchestratorSettings(),
            persistence=None,
        )

        with self.assertRaises(PerceptionParseError):
            orchestrator.handle_user_text("Неразобранная реплика")

        h_events = [
            item
            for item in core.store.elements(Domain.H)
            if isinstance(item, Hypernode)
            and item.properties.get("text") is not None
            and item.properties["text"].value == "Неразобранная реплика"
        ]
        self.assertEqual(len(h_events), 1)
        self.assertEqual(context.last_experience_ref.uid, h_events[0].uid)




    def test_integration_validation_failure_still_records_raw_user_turn_in_h(self) -> None:
        core = AHCore(uid_generator=SequentialUidGenerator())
        self_e = core.add_entity(Domain.P, properties={"name": Property("name", "Agent", "str")})
        user_e = core.add_entity(Domain.P, properties={"name": Property("name", "User", "str")})
        context = InteractionContext(self_ref=core.ref(self_e.uid), user_ref=core.ref(user_e.uid))
        integration = IntegrationService(core, IntegrationConfig(0.4, 0.3, 0.2))
        ignition = IgnitionEngine(core, IgnitionSettings(), WorkspaceSettings(0.1))
        invalid = PerceptionResult(
            "Иван читает книгу",
            assertions=(
                AssertionCandidate(
                    "A1",
                    PredicateCandidate(
                        "читает",
                        "read",
                        template_candidate=TemplateCandidate((ActantRole.SUBJECT,)),
                    ),
                    (
                        ActantCandidate(ActantRole.SUBJECT, mention="Иван"),
                        ActantCandidate(ActantRole.OBJECT, mention="книгу"),
                    ),
                ),
            ),
        )
        orchestrator = AgentOrchestrator(
            context=context,
            sensory=TextSensoryService(core),
            perception=FakePerception(invalid, PerceptionResult("unused")),
            integration=integration,
            ignition=ignition,
            query_builder=QueryGoalBuilder(core),
            inference=InferenceEngine(core, InferenceSettings()),
            materializer=InferenceMaterializer(core, IntegrationSettings()),
            projector=ContextProjector(core, ContextSettings(max_tokens=4096)),
            agent=FakeAgent("unused"),
            settings=OrchestratorSettings(),
            persistence=None,
        )

        with self.assertRaises(CandidateValidationError):
            orchestrator.handle_user_text("Иван читает книгу", generate_response=False)

        h_events = [
            item for item in core.store.elements(Domain.H)
            if isinstance(item, Hypernode)
            and item.properties.get("text") is not None
            and item.properties["text"].value == "Иван читает книгу"
        ]
        self.assertEqual(len(h_events), 1)
        self.assertEqual(context.last_experience_ref.uid, h_events[0].uid)
        # The rejected semantic assertion itself must not leak into C.
        c_hypernodes = [item for item in core.store.elements(Domain.C) if isinstance(item, Hypernode)]
        self.assertEqual(c_hypernodes, [])

    def test_default_orchestrator_records_agent_text_in_h_without_second_parser_call(self) -> None:
        core = AHCore(uid_generator=SequentialUidGenerator())
        self_e = core.add_entity(Domain.P, properties={"name": Property("name", "Agent", "str")})
        user_e = core.add_entity(Domain.P, properties={"name": Property("name", "User", "str")})
        context = InteractionContext(self_ref=core.ref(self_e.uid), user_ref=core.ref(user_e.uid))
        integration = IntegrationService(core, IntegrationConfig(0.4, 0.3, 0.2))
        ignition = IgnitionEngine(core, IgnitionSettings(), WorkspaceSettings(0.1))
        user_result = PerceptionResult("Привет")
        perception = FakePerception(user_result, PerceptionResult("SHOULD NOT BE USED"))
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
            agent=FakeAgent("Привет в ответ"),
            settings=OrchestratorSettings(),
            persistence=None,
        )
        turn = orchestrator.handle_user_text("Привет")
        self.assertEqual(perception.calls, 1)
        self.assertIsNotNone(turn.response_integration)
        self.assertEqual(turn.response_perception.source_text, "Привет в ответ")
        self.assertIn("AGENT_H_TEXT_ONLY", turn.response_perception.diagnostics)
        event = core.store.get_hypernode(turn.response_integration.experience_ref.uid)
        self.assertEqual(event.properties["text"].value, "Привет в ответ")

    def test_llm_perception_parser_preserves_explicit_negation_flag(self) -> None:
        backend = FakeLLMBackend(['{"assertions":[{"local_id":"A1","predicate":{"surface":"спать","normalized_hint":"спать"},"actants":[{"role":"SUBJECT","mention":"кошка"}],"negated":true}],"queries":[],"commands":[],"diagnostics":[]}'])
        service = LLMPerceptionService(backend, LLMPerceptionSettings(protocol="legacy_json", probe_retry_attempts=0))
        parsed = service.parse("Кошка не спит", InteractionContext())
        self.assertTrue(parsed.assertions[0].negated)


if __name__ == "__main__":
    unittest.main()
