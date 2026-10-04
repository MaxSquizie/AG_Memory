# -*- coding: utf-8 -*-
"""IF/hypothetical end-to-end verdict through the production GoalMode (V7 §6.2/§6.3).

Proves the text-level IF seam (:func:`ah.inference.if_bridge.if_to_perception`) drives the *existing* typed, non-lexical
counterfactual machinery to a real verdict starting purely from raw Russian text: bridge -> ``apply_speech_act_scoping`` ->
``integrate_external`` + ``SemanticGoalCompiler.build`` (CounterfactualGoal) -> ``InferenceEngine.solve``. The verdict is
memory-grounded (PROVED only when the IMPLIES rule exists), never guessed, and writes no canonical AH.
"""

from __future__ import annotations

import unittest

from ah.agent import InteractionContext
from ah.config import InferenceSettings, IntegrationSettings
from ah.core import AHCore, SequentialUidGenerator
from ah.inference import (
    CounterfactualGoal,
    InferenceEngine,
    LogicalStatus,
    SemanticGoalCompiler,
)
from ah.inference.if_bridge import if_to_perception
from ah.integration import IntegrationConfig, IntegrationService
from ah.integration.experience_mapper import ExperienceMapper
from ah.model import ActantRole, Domain, Property, Ref
from ah.perception import apply_speech_act_scoping

IF_TEXT = "Если сервер работает, сервис отвечает."


def _runtime():
    core = AHCore(uid_generator=SequentialUidGenerator())
    self_entity = core.add_entity(Domain.P, {"name": Property("name", "Агент", "str")}, uid="M_SELF")
    user_entity = core.add_entity(Domain.P, {"name": Property("name", "Пользователь", "str")}, uid="M_USER")
    context = InteractionContext(self_ref=core.ref(self_entity.uid), user_ref=core.ref(user_entity.uid))
    service = IntegrationService(core, IntegrationConfig.from_settings(IntegrationSettings()))
    engine = InferenceEngine(
        core,
        InferenceSettings(max_depth=12, max_expanded_states=512),
        schema_registry=service.schema_registry,
    )
    return core, context, service, engine


def _entity(core: AHCore, name: str) -> Ref:
    found = core.store.find_entities_by_name(name, Domain.C)
    if found:
        return core.ref(found[0].uid)
    item = core.add_entity(Domain.C, {"name": Property("name", name, "str")})
    return core.ref(item.uid)


def _template(core: AHCore, predicate: str) -> Ref:
    symbol = core.ensure_abstract_symbol(predicate)
    found = core.store.find_templates_by_predicate(symbol.uid)
    if found:
        return core.ref(found[0].uid)
    template = core.add_template(Domain.C, core.ref(symbol.uid), (ActantRole.SUBJECT,))
    return core.ref(template.uid)


def _atom(core: AHCore, predicate: str, subject: str) -> Ref:
    node, _ = core.add_hypernode(
        Domain.C, _template(core, predicate), {ActantRole.SUBJECT: _entity(core, subject)}, 0.4, count_occurrence=False
    )
    return core.ref(node.uid)


def _assert_implies_rule(core: AHCore, context: InteractionContext, left: Ref, right: Ref) -> None:
    rule, _ = core.ensure_function(Domain.C, "IMPLIES", (left, right))
    ExperienceMapper(core, event_weight=0.3, follow_weight=0.2).record_turn(
        source_text="rule",
        speaker_ref=context.user_ref,
        semantic_refs=(core.ref(rule.uid),),
        context=context,
        speech_act_kinds=("ASSERTION",),
    )


def _compile_counterfactual(core, context, service, text: str):
    """Raw IF text -> bridge -> scoping -> production compiler. Returns (built_result, goal_or_None)."""
    perception = if_to_perception(text)  # default TagSource; deterministic for the fixture words
    if perception is None:
        return None, None
    scoped = apply_speech_act_scoping(perception)
    commit = service.integrate_external(scoped, context)
    built = SemanticGoalCompiler(core).build(commit, context, scoped)
    assert len(built) == 1
    result = built[0]
    goal = result.goal.goal.target if result.goal is not None else None
    return result, goal


class TestIfVerdict(unittest.TestCase):
    def test_if_text_proves_counterfactual_end_to_end(self) -> None:
        core, context, service, engine = _runtime()
        p = _atom(core, "работает", "сервер")
        q = _atom(core, "отвечает", "сервис")
        _assert_implies_rule(core, context, p, q)

        result, goal = _compile_counterfactual(core, context, service, IF_TEXT)
        self.assertIsInstance(goal, CounterfactualGoal)
        # The compiler recognized the typed counterfactual scope (not a lexical guess).
        self.assertIn("semantic:counterfactual_formula_goal", result.diagnostics)

        before = set(core.store.all_uids())
        outcome = engine.solve(result.goal)
        # ANSWERED equivalent: the conditional holds because memory contains IMPLIES(antecedent, consequent).
        self.assertIs(outcome.status, LogicalStatus.PROVED)
        # Counterfactual solving is a read-only sandbox: no canonical AH mutation.
        self.assertEqual(set(core.store.all_uids()), before)

    def test_if_without_rule_is_not_proved(self) -> None:
        core, context, service, engine = _runtime()
        _atom(core, "работает", "сервер")
        _atom(core, "отвечает", "сервис")  # facts exist but NO IMPLIES rule links them

        result, goal = _compile_counterfactual(core, context, service, IF_TEXT)
        self.assertIsInstance(goal, CounterfactualGoal)
        before = set(core.store.all_uids())
        outcome = engine.solve(result.goal)
        # Honest: without the linking rule the consequent is not derivable -> never PROVED.
        self.assertIsNot(outcome.status, LogicalStatus.PROVED)
        self.assertEqual(set(core.store.all_uids()), before)

    def test_single_clause_text_yields_no_goal(self) -> None:
        core, context, service, _engine = _runtime()
        result, goal = _compile_counterfactual(core, context, service, "Вороны любят червей.")
        # No paired IF boundaries -> the bridge is honest UNBOUND; nothing to compile.
        self.assertIsNone(result)
        self.assertIsNone(goal)


if __name__ == "__main__":
    unittest.main()
