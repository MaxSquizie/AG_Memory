from __future__ import annotations

"""Public semantic-oracle facade with source-formula-aware canonical grading.

The large baseline grader lives in :mod:`semantic_oracle_core`.  This facade keeps
its public API stable while fixing one architectural seam: Integration deliberately
maps a source-level formula leaf to the positive scoped ``N`` and materializes local
polarity in the proposition formula.  A suite that does not explicitly grade
``proposition_roots`` must therefore inspect the *actual* source formula before it
can decide whether the leaf ref itself should be ``G:NOT``.

This is diagnostics only.  It does not repair perception, Integration or an oracle;
it prevents the acceptance grader from demanding a second NOT wrapper that would
change the represented formula.
"""

from copy import deepcopy
import json
from pathlib import Path
from typing import Any, Mapping, MutableMapping

from . import semantic_oracle_core as _core
from .semantic_oracle_core import *  # noqa: F401,F403 - preserve the historical API


# Rebind explicitly for static readers and callers that import these names directly.
DEFAULT_ORACLE_FILENAME = _core.DEFAULT_ORACLE_FILENAME
SemanticCaseVerdict = _core.SemanticCaseVerdict
SemanticOracleCase = _core.SemanticOracleCase
SemanticOracleError = _core.SemanticOracleError
SemanticOracleReport = _core.SemanticOracleReport
load_semantic_oracle = _core.load_semantic_oracle
validate_oracle_alignment = _core.validate_oracle_alignment
summarize_semantic_verdicts = _core.summarize_semantic_verdicts
apply_ah_diff = _core.apply_ah_diff


def _actual_formula_scope(
    perception: Mapping[str, Any] | None,
) -> tuple[frozenset[str], frozenset[str]]:
    """Return actual formula leaves and leaves whose local polarity is in NOT.

    ``negated`` contains only direct ``NOT(REF(local_id))`` / ``FALSE(REF(...))``
    occurrences.  A surrounding whole-formula NOT is traversed but is not confused
    with leaf polarity unless its direct operand really is that leaf.  This mirrors
    the Integration contract: formula-member refs remain positive scoped N nodes and
    the proposition AST owns the source-local wrapper exactly once.
    """

    if not isinstance(perception, Mapping):
        return frozenset(), frozenset()

    leaves: set[str] = set()
    negated: set[str] = set()

    def walk(expr: Any) -> None:
        if not isinstance(expr, Mapping):
            return
        operator = str(expr.get("operator", "")).upper()
        if operator == "REF":
            ref = str(expr.get("ref", "")).strip()
            if ref:
                leaves.add(ref)
            return

        members = tuple(
            item for item in (expr.get("members", []) or []) if isinstance(item, Mapping)
        )
        if operator in {"NOT", "FALSE"} and len(members) == 1:
            child = members[0]
            if str(child.get("operator", "")).upper() == "REF":
                ref = str(child.get("ref", "")).strip()
                if ref:
                    negated.add(ref)
        for member in members:
            walk(member)

    for root in perception.get("proposition_roots", []) or []:
        if isinstance(root, Mapping):
            walk(root.get("expression"))
    return frozenset(leaves), frozenset(negated)


def _replace_check(
    checks: list[dict[str, Any]],
    name: str,
    replacement: dict[str, Any],
) -> None:
    for index, check in enumerate(checks):
        if check.get("name") == name:
            checks[index] = replacement
            return
    checks.append(replacement)


def _formula_leaf_ref(
    record: Mapping[str, Any],
    key_to_local: Mapping[str, str],
    key: str,
) -> Mapping[str, Any] | None:
    refs = _core._canonical_assertion_ref_map(record, key_to_local)
    ref = refs.get(key)
    return ref if isinstance(ref, Mapping) else None


def _repair_formula_leaf_canonical_checks(
    verdict: SemanticCaseVerdict,
    record: Mapping[str, Any],
    oracle_case: SemanticOracleCase,
    after_snapshot: Mapping[str, Mapping[str, Any]],
) -> SemanticCaseVerdict:
    expected = oracle_case.expectation
    perception_expectation = expected.get("perception", {}) or {}
    if bool(perception_expectation.get("unchecked", False)):
        return verdict
    if str(record.get("status", "ERROR")) != "OK":
        return verdict

    perception = _core._decoded_perception(record)
    if not isinstance(perception, Mapping):
        return verdict

    actual_assertions = [
        item
        for item in perception.get("assertions", []) or []
        if isinstance(item, Mapping)
    ]
    expected_assertions = [
        item
        for item in perception_expectation.get("assertions", []) or []
        if isinstance(item, Mapping)
    ]
    key_to_local: dict[str, str] = {}
    for position, wanted in enumerate(expected_assertions):
        if position >= len(actual_assertions):
            break
        key = str(wanted.get("key") or f"a{position + 1}")
        key_to_local[key] = str(actual_assertions[position].get("local_id", ""))

    formula_leaves, formula_negated_leaves = _actual_formula_scope(perception)
    if not formula_leaves:
        return verdict

    checks = [dict(item) for item in verdict.checks]
    for position, wanted in enumerate(expected_assertions):
        key = str(wanted.get("key") or f"a{position + 1}")
        local_id = key_to_local.get(key)
        if not local_id or local_id not in formula_leaves:
            continue
        if str(wanted.get("status", "ASSERTED")).upper() == "CONDITIONAL":
            continue

        ref = _formula_leaf_ref(record, key_to_local, key)
        if ref is not None:
            scoped = _core._scoped_member_node(after_snapshot, ref)
            actual_scope = (
                (scoped.get("meta") or {}).get("semantic_scope")
                if isinstance(scoped, Mapping)
                else None
            )
            _replace_check(
                checks,
                f"canonical.assertions.{key}.scoped",
                {
                    "name": f"canonical.assertions.{key}.scoped",
                    "ok": actual_scope == "LOGICAL",
                    "expected": "semantic_scope=LOGICAL",
                    "actual": actual_scope,
                    "detail": "Actual proposition-root membership defines formula scope even when the oracle does not grade the root explicitly.",
                },
            )

        # Only a direct source formula NOT(REF(local)) authorizes a positive local
        # canonical member for an assertion the oracle says is negated.  Merely
        # belonging to a formula is insufficient and therefore cannot hide a real
        # lost-polarity defect.
        if bool(wanted.get("negated", False)) and local_id in formula_negated_leaves:
            item = (
                after_snapshot.get(str(ref.get("uid", "")))
                if isinstance(ref, Mapping)
                else None
            )
            local_has_not = bool(
                isinstance(item, Mapping)
                and item.get("kind") == "G"
                and str(item.get("function_id", "")).upper() == "NOT"
            )
            _replace_check(
                checks,
                f"canonical.assertions.{key}.negated",
                {
                    "name": f"canonical.assertions.{key}.negated",
                    "ok": not local_has_not,
                    "expected": False,
                    "actual": local_has_not,
                    "detail": "Source-local negation is already carried by actual proposition-root NOT(REF); the mapped scoped leaf must stay positive to avoid double NOT.",
                },
            )

    has_failures = any(not item.get("ok", False) for item in checks)
    if has_failures:
        status = "FAIL"
    elif oracle_case.grade == "ARCHITECTURE_GAP":
        status = "GAP"
    else:
        status = "PASS"
    return SemanticCaseVerdict(
        verdict.index,
        verdict.text,
        status,
        tuple(checks),
        verdict.note,
        verdict.family,
        verdict.tags,
    )


def evaluate_semantic_case(
    record: Mapping[str, Any],
    oracle_case: SemanticOracleCase,
    after_snapshot: Mapping[str, Mapping[str, Any]],
    required_template_roles: MutableMapping[str, set[str]],
) -> SemanticCaseVerdict:
    baseline = _core.evaluate_semantic_case(
        record,
        oracle_case,
        after_snapshot,
        required_template_roles,
    )
    return _repair_formula_leaf_canonical_checks(
        baseline,
        record,
        oracle_case,
        after_snapshot,
    )


def evaluate_acceptance_bundle(
    run_dir: str | Path,
    oracle_file: str | Path,
    *,
    write_report: bool = True,
) -> SemanticOracleReport:
    """Re-grade a saved bundle with the same semantics used by live acceptance."""

    root = Path(run_dir)
    oracle = load_semantic_oracle(oracle_file)
    initial_path = root / "initial_ah.json"
    if not initial_path.is_file():
        raise FileNotFoundError(f"Acceptance bundle has no initial_ah.json: {root}")
    initial_snapshot: dict[str, dict[str, Any]] = json.loads(
        initial_path.read_text(encoding="utf-8")
    )
    snapshot: dict[str, dict[str, Any]] = deepcopy(initial_snapshot)
    required_template_roles: dict[str, set[str]] = {}
    verdicts: list[SemanticCaseVerdict] = []
    active_scenario: str | None = None

    for case in oracle:
        if active_scenario != case.scenario_id:
            snapshot = deepcopy(initial_snapshot)
            required_template_roles = {}
            active_scenario = case.scenario_id
        turn_path = root / f"turn_{case.index:03d}.json"
        if not turn_path.is_file():
            raise FileNotFoundError(f"Acceptance bundle missing {turn_path.name}")
        record = json.loads(turn_path.read_text(encoding="utf-8"))
        if str(record.get("input", "")).strip() != case.text:
            raise SemanticOracleError(
                f"Bundle/oracle text mismatch at #{case.index}: "
                f"bundle={record.get('input')!r}; oracle={case.text!r}"
            )
        apply_ah_diff(snapshot, record.get("ah_diff", {}) or {})
        verdicts.append(
            evaluate_semantic_case(record, case, snapshot, required_template_roles)
        )

    report = summarize_semantic_verdicts(verdicts)
    if write_report:
        payload = {
            "total": report.total,
            "passed": report.passed,
            "failed": report.failed,
            "gaps": report.gaps,
            "families": report.family_counts,
            "cases": [
                {
                    "index": item.index,
                    "text": item.text,
                    "status": item.status,
                    "note": item.note,
                    "family": item.family,
                    "tags": list(item.tags),
                    "checks": list(item.checks),
                }
                for item in report.cases
            ],
        }
        (root / "semantic_report.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        lines = [
            f"Semantic oracle: PASS {report.passed}/{report.total} | FAIL {report.failed} | GAP {report.gaps}",
            "",
            "Families:",
        ]
        for family, counts in report.family_counts.items():
            lines.append(
                f"  {family}: PASS {counts['passed']}/{counts['total']} | "
                f"FAIL {counts['failed']} | GAP {counts['gaps']}"
            )
        lines.append("")
        for item in report.cases:
            line = f"{item.index:03d} {item.status}: {item.text}"
            if item.failures:
                failed_names = ", ".join(
                    check["name"] for check in item.failures[:6]
                )
                if len(item.failures) > 6:
                    failed_names += f", ... (+{len(item.failures) - 6})"
                line += f" | {failed_names}"
            if item.note and item.status == "GAP":
                line += f" | {item.note}"
            lines.append(line)
        (root / "semantic_summary.txt").write_text(
            "\n".join(lines) + "\n",
            encoding="utf-8",
        )
    return report


def __getattr__(name: str) -> Any:
    """Keep private diagnostic helpers reachable for existing white-box tests."""
    return getattr(_core, name)
