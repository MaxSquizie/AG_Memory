"""Effective open policy is shared by real native reads and observed exports."""
from __future__ import annotations

from dataclasses import replace
import json

import pytest

from ah.config import InferenceSettings
from ah.formalizer.inference_policy import node_inference_policy
from ah.formalizer.native_derivations import pattern_from_ref
from ah.formalizer.native_queries import Pattern
from ah.inference.contracts import LogicalStatus, NativeFormulaGoal
from ah.inference.engine import InferenceEngine
from ah.model import ActantRole
from tools.formalizer_v7_extended_binding import Session
from tools.formalizer_v7_native_binding import ChatBackend, execute_native


CONFIG = {"provider": "lmstudio", "base_url": "http://unused-test-endpoint", "model": "bounded-policy-test"}


def ingest_open(monkeypatch, tmp_path, scope=None):
    # These syntax fixtures are independent of oracle gold. T0–T6, canonical
    # store, support paths and provider WAL are the actual runtime machinery.
    text = {None: "Иван глоркнул книгу.", "NOT": "Иван не глоркнул книгу.",
            "OR": "Иван глоркнул книгу или Мария уснула."}[scope]
    def generate(self, prompt, **kwargs):
        tokens = json.loads(prompt)["tokens"]
        anchors = {token["text"]: token["id"] for token in tokens}
        nodes = [{"kind": kind, "anchor_spans": [anchors[word]]} for kind, word in (
            ("PREDICATE", "глоркнул"), ("ENTITY", "Иван"), ("ENTITY", "книгу"))]
        edges = [{"kind": "ARGUMENT", "from": 0, "to": 1, "role_id": "SUBJECT"},
                 {"kind": "ARGUMENT", "from": 0, "to": 2, "role_id": "OBJECT"}]
        if scope == "NOT":
            nodes.append({"kind": "NOT", "anchor_spans": [anchors["не"]]})
            edges.append({"kind": "OPERAND", "from": 3, "to": 0})
        elif scope == "OR":
            nodes.extend([{"kind": kind, "anchor_spans": [anchors[word]]} for kind, word in (
                ("OR", "или"), ("PREDICATE", "уснула"), ("ENTITY", "Мария"))])
            edges.extend([{"kind": "OPERAND", "from": 3, "to": 0},
                          {"kind": "OPERAND", "from": 3, "to": 4},
                          {"kind": "ARGUMENT", "from": 4, "to": 5, "role_id": "SUBJECT"}])
        return json.dumps({"hypotheses": [{"local_id": "policy-test", "nodes": nodes,
            "edges": edges, "alignment": [token["id"] for token in tokens]}]}, ensure_ascii=False)
    monkeypatch.setattr(ChatBackend, "generate", generate)
    payload = {"raw_input": {"text": text, "source_id": "policy:" + str(scope), "revision": 1,
        "range": [0, len(text)], "language": "ru", "request_kind": "ASSERTION", "batch_kind": "MESSAGE",
        "source_timestamp": "2026-10-09T12:00:00+00:00"}}
    session = Session([payload], tmp_path / "native-policy.log")
    return session, execute_native(session, payload, CONFIG)


@pytest.mark.parametrize("scope", [None, "NOT", "OR"])
def test_native_export_reports_effective_open_capability_without_optional_metadata(monkeypatch, tmp_path, scope):
    session, actual = ingest_open(monkeypatch, tmp_path, scope)
    assert actual["runtime"]["report"]["terminal"] == "APPLIED"
    assert actual["open"] == {"semantic_status": "UNLINKED", "capabilities": ["EXACT_ATTESTATION"]}
    assert actual["aliases"] == []
    assert actual["diagnostics"]["codes"] == []
    open_records = [node for node in session.store.ledger.data["nodes"].values()
                    if node.get("semantic_status") == "UNLINKED"]
    assert len(open_records) == 1
    node = open_records[0]
    # The old exporter looked only here, but the runtime does not store flags.
    assert "inference_capabilities" not in session.core.store.get_hypernode(node["uid"]).meta
    assert node_inference_policy(node).capabilities == ("EXACT_ATTESTATION",)
    with pytest.raises(ValueError, match="OPEN_LEXICAL_INFERENCE_FORBIDDEN"):
        pattern_from_ref(session.core, session.store.ledger, node["uid"], [100])


def test_exact_attestation_still_needs_excitation_exact_roles_and_scope(monkeypatch, tmp_path):
    session, actual = ingest_open(monkeypatch, tmp_path)
    ledger = session.store.ledger
    uid, node = next((uid, node) for uid, node in ledger.data["nodes"].items()
                     if node.get("semantic_status") == "UNLINKED")
    pattern = Pattern(lexical_anchor="глоркнул", actants=tuple(
        (ActantRole(role), session.core.ref(ref)) for role, ref in node["actants"].items()))
    engine = InferenceEngine(session.core, InferenceSettings(max_expanded_states=128))
    before = session.store._codec.export(session.core)
    workspace = (session.core.ref(uid),)
    assert engine.solve(NativeFormulaGoal(pattern), workspace_refs=workspace).status == LogicalStatus.PROVED
    assert engine.solve(NativeFormulaGoal(pattern)).status == LogicalStatus.UNKNOWN
    assert engine.solve(NativeFormulaGoal(replace(pattern, lexical_anchor="отправил")), workspace_refs=workspace).status == LogicalStatus.UNKNOWN
    swapped = replace(pattern, actants=tuple((role, pattern.actants[1-i][1]) for i, (role, _) in enumerate(pattern.actants)))
    assert engine.solve(NativeFormulaGoal(swapped), workspace_refs=workspace).status == LogicalStatus.UNKNOWN
    negated = Pattern(operator="NOT", members=(pattern,))
    # Exact open content does not license logical inversion to a negative answer.
    assert engine.solve(NativeFormulaGoal(negated), workspace_refs=workspace).status == LogicalStatus.UNKNOWN
    assert session.store._codec.export(session.core) == before


def test_unvalidated_metadata_cannot_grant_open_canonical_inference():
    policy = node_inference_policy({"semantic_status": "UNLINKED", "inference_capabilities": ["IS_A", "CAUSE"]})
    assert policy.capabilities == ("EXACT_ATTESTATION",)
    assert policy.exact_attestation_only
    assert not node_inference_policy({"semantic_status": "KNOWN"}).exact_attestation_only
