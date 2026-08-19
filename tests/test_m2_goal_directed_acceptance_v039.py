from __future__ import annotations

import unittest

from ah.config import (
    IgnitionSettings,
    InferenceSettings,
    LifecycleSettings,
    WorkspaceSettings,
)
from ah.core import AHCore, SequentialUidGenerator
from ah.ignition import IgnitionEngine
from ah.inference import (
    CauseEntailmentGoal,
    GoalSpec,
    IgnitionInferenceAttention,
    InferenceEngine,
    InferenceQuery,
    LogicalStatus,
    RelationGoal,
    StopReason,
)
from ah.model import Domain, Property, Ref


class M2GoalDirectedAcceptanceV041Tests(unittest.TestCase):
    """M2 proof + real inference attention.

    Cold Workspace is only a purity control: the first proof path starts with x=0
    so the answer cannot already be active. Runtime proof must also work with a warm
    unrelated Workspace. Every proposition actually expanded by inference is focused
    through QUERY_RECALL and a normal synchronous Ignition tick.
    """

    def setUp(self) -> None:
        self.core = AHCore(uid_generator=SequentialUidGenerator())
        self.inference = InferenceEngine(
            self.core,
            InferenceSettings(max_depth=6, max_expanded_states=500),
        )
        self.ignition = IgnitionEngine(
            self.core,
            IgnitionSettings(),
            WorkspaceSettings(threshold=0.35),
            LifecycleSettings(gc_enabled=False, orphan_cleanup=False),
        )
        self.attention = IgnitionInferenceAttention(self.ignition)

    def entity(self, domain: Domain, name: str) -> Ref:
        obj = self.core.add_entity(
            domain,
            properties={"name": Property("name", name, "str")},
        )
        return self.core.ref(obj.uid)

    def fact(self, domain: Domain, label: str) -> Ref:
        symbol = self.core.ensure_abstract_symbol(label)
        template = self.core.add_template(domain, self.core.ref(symbol.uid), ())
        node, _ = self.core.add_hypernode(
            domain,
            self.core.ref(template.uid),
            {},
            0.4,
            deduplicate=False,
            count_occurrence=False,
        )
        return self.core.ref(node.uid)

    def add_chain(self, relation_id: str, nodes: list[Ref]):
        return [
            self.core.add_link(relation_id, nodes[index], nodes[index + 1], 0.4)
            for index in range(len(nodes) - 1)
        ]

    def solve_chain(self, relation: str, nodes: list[Ref], depth: int):
        if relation == "CAUSE":
            query = InferenceQuery(
                GoalSpec(CauseEntailmentGoal(nodes[depth])),
                premise_refs=(nodes[0],),
                max_depth=6,
            )
        else:
            query = InferenceQuery(
                GoalSpec(RelationGoal(relation, nodes[0], nodes[depth])),
                max_depth=6,
            )
        return self.inference.solve(
            query,
            self.ignition.workspace_refs(),
            attention=self.attention,
        )

    def assert_exact_attention_proof(self, outcome, nodes, links, depth: int) -> None:
        self.assertIs(outcome.status, LogicalStatus.PROVED)
        self.assertIs(outcome.stop_reason, StopReason.GOAL_SATISFIED)
        self.assertEqual(outcome.logical_depth, depth)

        expected_trace: list[str] = []
        for index in range(depth):
            expected_trace.extend((nodes[index].uid, links[index].uid))
        expected_trace.append(nodes[depth].uid)
        self.assertEqual([ref.uid for ref in outcome.uid_trace], expected_trace)

        self.assertEqual(
            [event.ref.uid for event in self.attention.events],
            [ref.uid for ref in nodes[: depth + 1]],
        )
        for ref in nodes[: depth + 1]:
            self.assertGreater(self.core.store.runtime_state(ref.uid).excitation, 0.0)
        for ref in nodes[depth + 1 :]:
            self.assertEqual(self.core.store.runtime_state(ref.uid).excitation, 0.0)

    def test_depth_1_to_6_from_cold_paths_for_cause_follow_and_isa(self) -> None:
        specs = (
            ("CAUSE", Domain.C, True),
            ("FOLLOW", Domain.H, True),
            ("IS-A", Domain.C, False),
        )
        first = True
        for relation, domain, facts in specs:
            for depth in range(1, 7):
                with self.subTest(relation=relation, depth=depth):
                    nodes = [
                        self.fact(domain, f"{relation}_{depth}_{i}")
                        if facts
                        else self.entity(domain, f"{relation}_{depth}_{i}")
                        for i in range(9)
                    ]
                    links = self.add_chain(relation, nodes)
                    if first:
                        self.assertEqual(self.ignition.workspace_refs(), ())
                        first = False
                    for ref in nodes:
                        self.assertEqual(self.core.store.runtime_state(ref.uid).excitation, 0.0)

                    outcome = self.solve_chain(relation, nodes, depth)
                    self.assert_exact_attention_proof(outcome, nodes, links, depth)

    def test_warm_unrelated_workspace_does_not_change_proof(self) -> None:
        warm = tuple(self.entity(Domain.P, f"warm_{i}") for i in range(12))
        for ref in warm:
            self.attention.focus(ref, logical_depth=0)
        self.assertGreater(len(self.ignition.workspace_refs()), 0)

        nodes = [self.fact(Domain.C, f"warm_cause_{i}") for i in range(9)]
        links = self.add_chain("CAUSE", nodes)
        outcome = self.solve_chain("CAUSE", nodes, 6)
        self.assert_exact_attention_proof(outcome, nodes, links, 6)

    def test_many_dead_branches_are_pruned_by_goal_relevance_not_scanned_as_proof(self) -> None:
        nodes = [self.fact(Domain.C, f"branch_main_{i}") for i in range(9)]
        links = self.add_chain("CAUSE", nodes)
        distractors: list[Ref] = []
        for depth, source in enumerate(nodes[:-1]):
            for branch in range(64):
                ref = self.fact(Domain.C, f"dead_{depth}_{branch}")
                self.core.add_link("CAUSE", source, ref, 0.4)
                distractors.append(ref)

        # A budget far below the total branch count still suffices because graph
        # reachability is used only to prune impossible candidates; MP remains the
        # rule that proves each forward step.
        query = InferenceQuery(
            GoalSpec(CauseEntailmentGoal(nodes[6])),
            premise_refs=(nodes[0],),
            max_depth=6,
            max_expanded_states=12,
        )
        outcome = self.inference.solve(
            query,
            self.ignition.workspace_refs(),
            attention=self.attention,
        )
        self.assert_exact_attention_proof(outcome, nodes, links, 6)
        focused = {event.ref.uid for event in self.attention.events}
        self.assertTrue({ref.uid for ref in distractors}.isdisjoint(focused))
        self.assertLessEqual(outcome.expanded_states, 6)


if __name__ == "__main__":
    unittest.main()
