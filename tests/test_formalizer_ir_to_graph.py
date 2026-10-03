# -*- coding: utf-8 -*-
"""P2 — CandidateIR -> live AHStore graph (proves the locked type/domain mapping end-to-end).

Asserts, on a REAL store + durable journal:
* an asserted EventFrame materializes as Template(predicate=S) + Hypernode in Domain.C;
* an EMBEDDED / non-ASSERTED PropositionNode's head frame is quarantined to Domain.H (not C);
* graph edges become Links;
* re-committing identical ops under a NEW batch hash does NOT duplicate symbols/hypernodes
  (self-contained find-or-create handlers are idempotent).
"""

import tempfile
import unittest
from pathlib import Path

from ah.core.journal import JournalChannel
from ah.core.operations import AHCore
from ah.core.store import AHStore
from ah.formalizer.ah_adapter import AHStoreAdapter
from ah.formalizer.candidate_ir import ArgumentSpec, EventFrame, PropositionNode, SemanticGraphCandidate
from ah.formalizer.graph_ops import register_graph_handlers
from ah.formalizer.candidate_ir import ArgumentSpec, EventFrame, ScopeOperatorNode, ScopeTreeCandidate
from ah.formalizer.ir_to_graph import (
    CorefCluster,
    ScopeOperator,
    build_coref_ops,
    build_graph_ops,
    build_scope_ops,
    build_scope_tree_ops,
)
from ah.formalizer.store_interface import CommitDecision, MaterializationMarker, TerminalOutcome
from ah.model import ActantRole, BoundVar, Domain


def _frame(fid: str, pred: str, subj: str, obj: str) -> EventFrame:
    return EventFrame(
        frame_id=fid,
        predicate=pred,
        participants=(ArgumentSpec("SUBJECT", "ENTITY", subj), ArgumentSpec("OBJECT", "ENTITY", obj)),
    )


class TestIrToGraph(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.core = AHCore(AHStore())
        self.adapter = AHStoreAdapter(
            self.core.store, JournalChannel(Path(self._tmp.name) / "j.jsonl"), core=self.core
        )
        register_graph_handlers(self.adapter)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def _graph(self) -> SemanticGraphCandidate:
        return SemanticGraphCandidate(
            graph_id="g1",
            ir_ref="ir1",
            nodes=(
                _frame("f1", "имеет", "Ворона", "перья"),  # asserted -> C
                _frame("f2", "читает", "студент", "книга"),  # asserted -> C
                PropositionNode(
                    expr_id="p1",
                    head=_frame("f3", "видит", "он", "дождь"),
                    status="EMBEDDED",
                    epistemic_status="POSSIBLE",  # non-asserted -> H quarantine
                ),
            ),
            edges=(("f1", "f2", "dependency"),),
        )

    def _commit(self, ops, batch_hash: str):
        marker = MaterializationMarker(observation_id="obs1", interpretation_version=1)
        decision = CommitDecision(
            run_id="r1", batch_hash=batch_hash, marker=marker, ops_digest="d", outcome=TerminalOutcome.APPLIED
        )
        return self.adapter.commit_transaction(ops, marker, decision)

    def _template_for(self, pred_form: str):
        s = self.core.store.find_symbol_by_form(pred_form)
        if s is None:
            return None
        for t in self.core.store.find_templates_by_predicate(s.uid):
            if ActantRole.SUBJECT in t.roles and ActantRole.OBJECT in t.roles:
                return t
        return None

    def _hypernode_domains(self, pred_form: str) -> list[Domain]:
        t = self._template_for(pred_form)
        if t is None:
            return []
        return [self.core.store.domain_of(n.uid) for n in self.core.store.find_hypernodes_by_template(t.uid)]

    def test_asserted_frames_materialize_in_C(self):
        ops, _ = build_graph_ops(self._graph())
        self._commit(ops, "b1")
        store = self.core.store
        # predicate materialized as a live AbstractSymbol (S)
        for form in ("имеет", "читает"):
            self.assertIsNotNone(store.find_symbol_by_form(form), f"predicate {form!r} must be a symbol")
        # asserted frames -> hypernodes in C, never H
        for form in ("имеет", "читает"):
            domains = self._hypernode_domains(form)
            self.assertIn(Domain.C, domains, f"{form!r} frame must materialize an asserted (C) hypernode")
            self.assertNotIn(Domain.H, domains, f"{form!r} is asserted; it must not be quarantined to H")

    def test_embedded_non_asserted_frame_is_quarantined_to_H(self):
        ops, _ = build_graph_ops(self._graph())
        self._commit(ops, "b1")
        domains = self._hypernode_domains("видит")
        self.assertEqual(domains, [Domain.H], "EMBEDDED/POSSIBLE head frame must live in H, not C/P")

    def test_edges_become_links(self):
        ops, _ = build_graph_ops(self._graph())
        self._commit(ops, "b1")
        kinds = {link.relation_id for link in self.core.store.links()}
        self.assertIn("dependency", kinds)

    def test_recommit_same_hash_is_noop(self):
        ops, _ = build_graph_ops(self._graph())
        first = self._commit(ops, "b1")
        second = self._commit(ops, "b1")  # identical batch hash -> idempotent no-op
        self.assertTrue(second.idempotent_noop)

    def test_reapply_same_ops_new_hash_does_not_duplicate(self):
        ops, _ = build_graph_ops(self._graph())
        self._commit(ops, "b1")
        before_symbols = len(self.core.store.find_symbols_by_form("имеет"))
        before_nodes = len(self._hypernode_domains("имеет"))
        self._commit(ops, "b2")  # same ops, new hash -> handlers re-run but find-or-create
        after_symbols = len(self.core.store.find_symbols_by_form("имеет"))
        after_nodes = len(self._hypernode_domains("имеет"))
        self.assertEqual(before_symbols, after_symbols, "re-apply must not duplicate symbols")
        self.assertEqual(before_nodes, after_nodes, "re-apply must not duplicate hypernodes")

    # -- scope operators (slice #1) ------------------------------------------
    def _hypernodes(self, pred_form: str):
        t = self._template_for(pred_form)
        return list(self.core.store.find_hypernodes_by_template(t.uid)) if t else []

    def _plain_node(self, pred_form: str):
        for n in self._hypernodes(pred_form):
            if not any(isinstance(a, BoundVar) for a in n.actants.values()):
                return n
        raise AssertionError(f"no plain (non-quantified) instance of {pred_form!r}")

    def _quant_node(self, pred_form: str):
        for n in self._hypernodes(pred_form):
            if any(isinstance(a, BoundVar) for a in n.actants.values()):
                return n
        raise AssertionError(f"no quantified (BoundVar) instance of {pred_form!r}")

    def test_not_wraps_asserted_frame_in_C(self):
        ops = build_scope_ops(_frame("f1", "имеет", "Ворона", "перья"), (ScopeOperator("NOT"),))
        self._commit(ops, "b1")
        parents = self.core.store.function_parents(self._plain_node("имеет").uid)
        not_nodes = [g for g in parents if g.function_id == "NOT"]
        self.assertTrue(not_nodes, "an asserted frame must be wrapped by a NOT G-node")
        self.assertEqual(self.core.store.domain_of(not_nodes[0].uid), Domain.C)

    def test_some_binds_boundvar_and_exists_in_C(self):
        ops = build_scope_ops(
            _frame("f1", "видит", "он", "дождь"), (ScopeOperator("SOME", target_slot="SUBJECT", variable_id=0),)
        )
        self._commit(ops, "b1")
        qnode = self._quant_node("видит")  # the quantified instance carries a BoundVar
        parents = self.core.store.function_parents(qnode.uid)
        exists = next((g for g in parents if g.function_id == "EXISTS"), None)
        self.assertIsNotNone(exists, "SOME must materialize an EXISTS G-node over the scoped instance")
        self.assertIsInstance(exists.operands[0], BoundVar)  # var is a quantifier operand
        self.assertEqual(self.core.store.domain_of(exists.uid), Domain.C)

    def test_at_least_n_binds_value_link(self):
        ops = build_scope_ops(
            _frame("f1", "сдал", "студент", "экзамен"),
            (ScopeOperator("AT_LEAST_N", target_slot="SUBJECT", variable_id=0, bound_value=6),)
        )
        self._commit(ops, "b1")
        kinds = {link.relation_id for link in self.core.store.links()}
        self.assertIn("AT_LEAST", kinds, "the numeric bound must be a Link from the scope to its value token")

    def test_possible_quarantined_to_H(self):
        ops = build_scope_ops(_frame("f1", "может", "он", "летать"), (ScopeOperator("POSSIBLE"),))
        self._commit(ops, "b1")
        parents = self.core.store.function_parents(self._plain_node("может").uid)
        poss = next((g for g in parents if g.function_id == "POSSIBLE"), None)
        self.assertIsNotNone(poss, "a POSSIBLE attitude must materialize a modal G-node")
        self.assertEqual(
            self.core.store.domain_of(poss.uid), Domain.H, "non-asserted (possible) content is quarantined to H"
        )

    # -- coreference clusters (slice #2) -------------------------------------
    def _groups_for(self, form: str):
        s = self.core.store.find_symbol_by_form(form)
        return self.core.store.groups_containing(s.uid) if s else ()

    def test_resolved_coref_cluster_materializes_in_K(self):
        ops = build_coref_ops((CorefCluster("c1", "он", ("студент",)),))
        self.assertEqual(len(ops), 1)
        self._commit(ops, "b1")
        groups = self._groups_for("студент")
        self.assertEqual(len(groups), 1, "a resolved coref must form exactly one K-group")
        g = groups[0]
        self.assertEqual(self.core.store.domain_of(g.uid), Domain.C)  # asserted identity fact
        self.assertEqual(g.meta.get("kind"), "COREF_CLUSTER")
        member_uids = {m.uid for m in g.members}
        for form in ("он", "студент"):
            self.assertIn(self.core.store.find_symbol_by_form(form).uid, member_uids)

    def test_unresolved_coref_emits_nothing(self):
        ops = build_coref_ops((CorefCluster("c1", "он", ()),))  # no resolved antecedent (I24)
        self.assertEqual(ops, [], "an unresolved candidate set must not assert identity")

    # -- scope trees (slice #4) ----------------------------------------------
    @staticmethod
    def _named_frame() -> EventFrame:
        return EventFrame(
            frame_id="F1", predicate="видит",
            participants=(
                ArgumentSpec(slot_ref="SUBJECT", arg_type="ENTITY", value="он"),
                ArgumentSpec(slot_ref="OBJECT", arg_type="ENTITY", value="дождь"),
            ),
        )

    def test_scope_tree_not_over_event_emits_chain(self):
        tree = ScopeTreeCandidate(
            tree_id="T1", graph_id="G1",
            root=ScopeOperatorNode(operator_id="OP0", operator_type="NOT", operand="F1"),
        )
        ops = build_scope_tree_ops(tree, {"F1": self._named_frame()})
        self.assertEqual(len(ops), 2)  # predicate symbol + the scope
        chain = ops[1].payload["chain"]
        self.assertEqual([c["op_type"] for c in chain], ["NOT"])

    def test_nested_scope_tree_orders_inner_to_outer(self):
        not_node = ScopeOperatorNode(operator_id="OP1", operator_type="NOT", operand="F1")
        some_node = ScopeOperatorNode(
            operator_id="OP0", operator_type="SOME", target_slot_ref="SUBJECT",
            local_variable_id="x", operand=not_node,
        )
        tree = ScopeTreeCandidate(tree_id="T2", graph_id="G1", root=some_node)
        ops = build_scope_tree_ops(tree, {"F1": self._named_frame()})
        chain = ops[1].payload["chain"]
        self.assertEqual([c["op_type"] for c in chain], ["NOT", "SOME"])  # inner -> outer

    def test_scope_tree_unresolved_event_emits_nothing(self):
        tree = ScopeTreeCandidate(
            tree_id="T3", graph_id="G1",
            root=ScopeOperatorNode(operator_id="OP0", operator_type="NOT", operand="GHOST"),
        )
        self.assertEqual(build_scope_tree_ops(tree, {"F1": self._named_frame()}), [])  # SCOPE_NOT_COVERED

    def test_scope_tree_materializes_not_over_frame_in_store(self):
        tree = ScopeTreeCandidate(
            tree_id="T4", graph_id="G1",
            root=ScopeOperatorNode(operator_id="OP0", operator_type="NOT", operand="F1"),
        )
        ops = build_scope_tree_ops(tree, {"F1": self._named_frame()})
        self._commit(ops, "b1")
        node = self._plain_node("видит")
        not_nodes = [g for g in self.core.store.function_parents(node.uid) if g.function_id == "NOT"]
        self.assertTrue(not_nodes, "the scope tree must wrap the base frame with a NOT G-node")


if __name__ == "__main__":
    unittest.main()
