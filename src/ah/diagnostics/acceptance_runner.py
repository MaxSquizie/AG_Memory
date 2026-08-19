from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from copy import deepcopy
from datetime import datetime
from enum import Enum
import json
from pathlib import Path
import shutil
import traceback
from typing import Any, Mapping, TYPE_CHECKING

from ah.model import AbstractSymbol, Domain, FunctionSymbol, Group, Hypernode, Link, SemanticEntity, Template
from ah.perception.linguistic_candidates import LinguisticCandidateBuilder
from ah.perception.morphology import build_morphology
from ah.diagnostics.inference_proof import ProofChainSnapshot, ProofSnapshotBuilder
from ah.diagnostics.semantic_oracle import (
    DEFAULT_ORACLE_FILENAME,
    evaluate_semantic_case,
    load_semantic_oracle,
    validate_oracle_alignment,
)

if TYPE_CHECKING:
    from ah.bootstrap import RuntimeServices


DEFAULT_CASES_FILENAME = "acceptance_cases.txt"
RUNS_DIRNAME = "acceptance_runs"


@dataclass(frozen=True, slots=True)
class AcceptanceCase:
    index: int
    text: str


@dataclass(frozen=True, slots=True)
class AcceptanceRunResult:
    output_dir: Path
    cases_file: Path
    total: int
    succeeded: int
    failed: int
    semantic_passed: int = 0
    semantic_failed: int = 0
    semantic_gaps: int = 0
    oracle_file: Path | None = None
    proofs: tuple[ProofChainSnapshot, ...] = ()


@dataclass(slots=True)
class _AcceptanceRuntimeState:
    store: Any
    context: Any
    ignition: Any


def _capture_runtime_state(services: "RuntimeServices") -> _AcceptanceRuntimeState:
    """Capture the mutable cognitive state without touching the loaded LLM backend."""
    return _AcceptanceRuntimeState(
        store=services.core.store.clone(),
        context=deepcopy(services.context),
        ignition=services.ignition.export_snapshot(include_pending=True),
    )


def _restore_context(target: Any, source: Any) -> None:
    """Restore InteractionContext in place so existing closures keep the same object."""
    if is_dataclass(source) and not isinstance(source, type):
        for field in fields(source):
            setattr(target, field.name, deepcopy(getattr(source, field.name)))
        return
    if hasattr(target, "__dict__") and hasattr(source, "__dict__"):
        target.__dict__.clear()
        target.__dict__.update(deepcopy(source.__dict__))
        return
    raise TypeError(f"Unsupported acceptance context type: {type(target).__name__}")


def _restore_runtime_state(services: "RuntimeServices", state: _AcceptanceRuntimeState) -> None:
    services.core.store.replace_from(state.store)
    _restore_context(services.context, state.context)
    restore = getattr(services.ignition, "restore_snapshot", None)
    if restore is None:
        raise TypeError("Acceptance isolation requires ignition.restore_snapshot()")
    restore(state.ignition)


def load_acceptance_cases(path: str | Path) -> tuple[AcceptanceCase, ...]:
    """Load one user turn per non-empty, non-comment line.

    The text file remains a human-editable input list. Semantic expected outcomes
    live in the separate acceptance_oracle.json so the runner can distinguish
    "no exception" from actual semantic correctness. Lines starting with `#` are
    comments only and are never sent to the agent.
    """
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"Acceptance cases file not found: {source}")
    cases: list[AcceptanceCase] = []
    for raw in source.read_text(encoding="utf-8-sig").splitlines():
        text = raw.strip()
        if not text or text.startswith("#"):
            continue
        cases.append(AcceptanceCase(len(cases) + 1, text))
    if not cases:
        raise ValueError(f"Acceptance cases file contains no requests: {source}")
    return tuple(cases)


def _jsonable(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: _jsonable(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Mapping):
        return {str(key.value if isinstance(key, Enum) else key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, set, frozenset)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _properties(properties: Mapping[str, Any]) -> dict[str, Any]:
    return {name: _jsonable(prop) for name, prop in sorted(properties.items())}


def canonical_ah_snapshot(services: "RuntimeServices") -> dict[str, dict[str, Any]]:
    """Return a stable UID-keyed canonical snapshot using only public AH reads."""
    store = services.core.store
    records: dict[str, dict[str, Any]] = {}

    for uid in sorted(store.all_uids()):
        kind = store.kind_of(uid)
        domain = store.domain_of(uid)
        if isinstance(kind, Enum) and kind.value == "S":
            symbol: AbstractSymbol = store.get_symbol(uid)
            records[uid] = {
                "uid": uid,
                "kind": "S",
                "domain": None,
                "forms": sorted(symbol.forms),
            }
            continue
        if isinstance(kind, Enum) and kind.value == "L":
            link: Link = store.get_link(uid)
            records[uid] = {
                "uid": uid,
                "kind": "L",
                "domain": None,
                "relation_id": link.relation_id,
                "weight": link.weight,
                "source": _jsonable(link.source),
                "target": _jsonable(link.target),
            }
            continue

        if domain is None:
            raise RuntimeError(f"Canonical non-S/L UID has no domain: {uid}")
        element = store.get_element(domain, uid)
        base: dict[str, Any] = {"uid": uid, "kind": kind.value, "domain": domain.value}
        if isinstance(element, SemanticEntity):
            base.update(properties=_properties(element.properties), meta=_jsonable(element.meta))
        elif isinstance(element, Template):
            base.update(predicate=_jsonable(element.predicate), roles=[role.value for role in element.roles])
        elif isinstance(element, Hypernode):
            base.update(
                weight=element.weight,
                template=_jsonable(element.template),
                actants={role.value: _jsonable(ref) for role, ref in element.actants.items()},
                properties=_properties(element.properties),
                meta=_jsonable(element.meta),
            )
        elif isinstance(element, FunctionSymbol):
            base.update(function_id=element.function_id, operands=_jsonable(element.operands))
        elif isinstance(element, Group):
            base.update(
                members=_jsonable(element.members),
                properties=_properties(element.properties),
                meta=_jsonable(element.meta),
            )
        else:
            raise TypeError(f"Unsupported canonical element in acceptance snapshot: {type(element).__name__}")
        records[uid] = base
    return records


def diff_canonical_ah(
    before: Mapping[str, dict[str, Any]],
    after: Mapping[str, dict[str, Any]],
) -> dict[str, Any]:
    before_uids = set(before)
    after_uids = set(after)
    added = {uid: after[uid] for uid in sorted(after_uids - before_uids)}
    removed = {uid: before[uid] for uid in sorted(before_uids - after_uids)}
    changed = {
        uid: {"before": before[uid], "after": after[uid]}
        for uid in sorted(before_uids & after_uids)
        if before[uid] != after[uid]
    }
    return {"added": added, "removed": removed, "changed": changed}


def _runtime_summary(services: "RuntimeServices") -> dict[str, Any]:
    """Return only runtime state needed by acceptance diagnostics.

    Do not call GraphInspector.snapshot() here. That operation semantically projects
    every canonical node and is intended for the live graph/final graph dump. An
    acceptance run only needs the current Workspace and pending ignition state, so
    building a full graph once per turn is both redundant and memory-expensive.
    """
    ignition = services.ignition
    workspace_refs = tuple(ignition.workspace_refs())
    ignition_snapshot = ignition.export_snapshot(include_pending=True)
    active: dict[str, dict[str, Any]] = {}
    for ref in workspace_refs:
        runtime = services.core.store.runtime_state(ref.uid)
        active[ref.uid] = {
            "semantic": services.graph_inspector.semantic.dependency_text(ref),
            "excitation": runtime.excitation,
        }
    return {
        "tick": ignition_snapshot.tick_index,
        "workspace_uids": [ref.uid for ref in workspace_refs],
        "workspace": active,
        "pending_incoming": dict(ignition_snapshot.incoming),
        "pending_refutations": list(ignition_snapshot.pending_refutations),
    }


def _parser_diagnostics_since(services: "RuntimeServices", floor: int) -> list[dict[str, Any]]:
    parser = services.perception
    if parser is None or not hasattr(parser, "diagnostics"):
        return []
    return [_jsonable(item) for item in parser.diagnostics() if item.sequence > floor]


def _request_diagnostics_since(services: "RuntimeServices", floor: int) -> list[dict[str, Any]]:
    backend = services.llm
    if backend is None or not hasattr(backend, "request_diagnostics"):
        return []
    return [_jsonable(item) for item in backend.request_diagnostics() if item.sequence > floor]


def _diagnostic_floors(services: "RuntimeServices") -> tuple[int, int]:
    parser_floor = 0
    if services.perception is not None and hasattr(services.perception, "diagnostics"):
        history = services.perception.diagnostics()
        parser_floor = max((item.sequence for item in history), default=0)
    request_floor = 0
    if services.llm is not None and hasattr(services.llm, "request_diagnostics"):
        history = services.llm.request_diagnostics()
        request_floor = max((item.sequence for item in history), default=0)
    return parser_floor, request_floor


def _dump_json(path: Path, payload: Any) -> None:
    """Stream an already JSON-compatible payload directly to disk."""
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=False)
        handle.write("\n")


def _write_json(path: Path, payload: Any) -> None:
    """Normalize once and stream instead of building an additional giant string."""
    normalized = _jsonable(payload)
    _dump_json(path, normalized)


def run_acceptance_suite(
    services: "RuntimeServices",
    *,
    cases_file: str | Path | None = None,
    oracle_file: str | Path | None = None,
) -> AcceptanceRunResult:
    """Run file-defined requests sequentially through the normal orchestrator.

    This is diagnostics only: it does not repair, retry or reinterpret failed turns.
    Every request uses the normal sensory/perception/integration/inference/projection
    path. Oracle scenario IDs define the only intentional memory continuity: AH,
    InteractionContext and Ignition state are restored to the run baseline between
    scenarios, and the user's pre-run live state is restored when diagnostics end.
    The diagnostic suite intentionally stops at AgentContext: generated agent prose is irrelevant to parser/T/N acceptance
    and would add large, growing generation caches plus unrelated H utterances.
    Failures are recorded and the suite proceeds to the next independent user turn.
    """
    data_dir = Path(services.config.paths.data_dir)
    source = Path(cases_file) if cases_file is not None else data_dir / DEFAULT_CASES_FILENAME
    cases = load_acceptance_cases(source)
    oracle_source = Path(oracle_file) if oracle_file is not None else data_dir / DEFAULT_ORACLE_FILENAME
    oracle_cases = load_semantic_oracle(oracle_source)
    validate_oracle_alignment(cases, oracle_cases)

    timestamp = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S_%z")
    runs_root = data_dir / RUNS_DIRNAME
    output_dir = runs_root / timestamp
    suffix = 1
    while output_dir.exists():
        output_dir = runs_root / f"{timestamp}_{suffix:02d}"
        suffix += 1
    output_dir.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(source, output_dir / "cases_used.txt")
    shutil.copyfile(oracle_source, output_dir / "oracle_used.json")

    morphology = build_morphology(services.config.llm.perception_morphology_backend)
    candidate_builder = LinguisticCandidateBuilder(morphology)

    clock = getattr(services, "clock", None)
    clock_was_running = bool(clock is not None and getattr(clock, "running", False))
    if clock_was_running:
        clock.stop()

    with services.operation_lock:
        live_state = _capture_runtime_state(services)
        baseline_state = _capture_runtime_state(services)

    try:
        with services.operation_lock:
            initial_ah = canonical_ah_snapshot(services)
            initial_runtime = _runtime_summary(services)
        _write_json(output_dir / "config.json", services.config)
        _write_json(output_dir / "initial_context.json", services.context)
        _dump_json(output_dir / "initial_ah.json", initial_ah)
        _dump_json(output_dir / "initial_runtime.json", initial_runtime)
        del initial_ah, initial_runtime

        manifest_cases: list[dict[str, Any]] = []
        succeeded = 0
        failed = 0
        semantic_passed = 0
        semantic_failed = 0
        semantic_gaps = 0
        proofs: list[ProofChainSnapshot] = []
        required_template_roles: dict[str, set[str]] = {}

        active_scenario: str | None = None
        for case in cases:
            oracle_case = oracle_cases[case.index - 1]
            if active_scenario != oracle_case.scenario_id:
                with services.operation_lock:
                    _restore_runtime_state(services, baseline_state)
                required_template_roles = {}
                active_scenario = oracle_case.scenario_id

            parser_floor, request_floor = _diagnostic_floors(services)
            with services.operation_lock:
                before = canonical_ah_snapshot(services)

            record: dict[str, Any] = {
                "index": case.index,
                "input": case.text,
                "status": "ERROR",
                "scenario_id": oracle_case.scenario_id,
            }
            error_text: str | None = None
            try:
                linguistic_graph = candidate_builder.build(case.text)
                record["linguistic_candidate_graph"] = _jsonable(linguistic_graph)
                orchestrator = services.create_orchestrator()
                turn = orchestrator.handle_user_text(case.text, generate_response=False)
                record["perception_result"] = _jsonable(turn.perception)
                record["integration_commit"] = _jsonable(turn.integration)
                record["queries"] = _jsonable(turn.queries)
                proof_builder = ProofSnapshotBuilder(services.core)
                case_proofs = []
                for query_index, query_execution in enumerate(turn.queries, 1):
                    if query_execution.outcome is None:
                        continue
                    proof = proof_builder.build(
                        query_execution.outcome,
                        chain_id=f"acceptance:{timestamp}:{case.index}:{query_index}",
                        source="ACCEPTANCE",
                        title=f"Acceptance {case.index} · Query {query_index}",
                    )
                    proofs.append(proof)
                    case_proofs.append(proof)
                record["proofs"] = _jsonable(case_proofs)
                record["agent_context"] = _jsonable(turn.agent_context)
                record["agent_context_diagnostic"] = _jsonable(getattr(turn, "agent_context_diagnostic", None))
                record["agent_response"] = None
                record["agent_generation_skipped"] = True
                record["response_perception"] = _jsonable(turn.response_perception)
                record["response_integration"] = _jsonable(turn.response_integration)
                record["status"] = "OK"
                succeeded += 1
            except Exception as exc:  # diagnostics boundary: preserve the real failure verbatim
                error_text = f"{type(exc).__name__}: {exc}"
                record["error"] = error_text
                record["traceback"] = traceback.format_exc()
                failed += 1

            with services.operation_lock:
                after = canonical_ah_snapshot(services)
                runtime_after = _runtime_summary(services)
            record["parser_diagnostics"] = _parser_diagnostics_since(services, parser_floor)
            record["llm_requests"] = _request_diagnostics_since(services, request_floor)
            record["ah_diff"] = diff_canonical_ah(before, after)
            record["runtime_after"] = runtime_after
            record["interaction_context_after"] = _jsonable(services.context)

            try:
                semantic_verdict = evaluate_semantic_case(
                    record,
                    oracle_case,
                    after,
                    required_template_roles,
                )
            except Exception as exc:  # diagnostics must never truncate the remaining corpus
                evaluator_error = f"{type(exc).__name__}: {exc}"
                record["semantic_evaluator_error"] = evaluator_error
                record["semantic_evaluator_traceback"] = traceback.format_exc()
                record["semantic_status"] = "FAIL"
                record["semantic_checks"] = [
                    {
                        "name": "oracle.evaluation_error",
                        "ok": False,
                        "expected": "semantic evaluator completes",
                        "actual": evaluator_error,
                    }
                ]
                record["semantic_note"] = oracle_case.note
                record["semantic_family"] = oracle_case.family
                record["semantic_tags"] = list(oracle_case.tags)
                semantic_failed += 1
            else:
                record["semantic_status"] = semantic_verdict.status
                record["semantic_checks"] = list(semantic_verdict.checks)
                record["semantic_note"] = semantic_verdict.note
                record["semantic_family"] = semantic_verdict.family
                record["semantic_tags"] = list(semantic_verdict.tags)
                if semantic_verdict.status == "PASS":
                    semantic_passed += 1
                elif semantic_verdict.status == "GAP":
                    semantic_gaps += 1
                else:
                    semantic_failed += 1

            filename = f"turn_{case.index:03d}.json"
            # record is already normalized field-by-field above. Writing it directly
            # avoids recursively cloning the complete diagnostic payload a second time.
            _dump_json(output_dir / filename, record)
            manifest_cases.append(
                {
                    "index": case.index,
                    "input": case.text,
                    "status": record["status"],
                    "semantic_status": record["semantic_status"],
                    "semantic_family": record["semantic_family"],
                    "semantic_tags": record["semantic_tags"],
                    "scenario_id": oracle_case.scenario_id,
                    "semantic_failures": [
                        str(item.get("name", "<unnamed-check>"))
                        for item in record["semantic_checks"]
                        if isinstance(item, Mapping) and not item.get("ok", False)
                    ],
                    "error": error_text,
                    "file": filename,
                }
            )
            # Explicitly drop the two complete canonical snapshots before the next LLM
            # turn. CPython can then release their large value graphs immediately.
            del before, after, runtime_after, record

        with services.operation_lock:
            final_ah = canonical_ah_snapshot(services)
            final_graph = services.graph_inspector.snapshot()
        _write_json(output_dir / "final_context.json", services.context)
        _dump_json(output_dir / "final_ah.json", final_ah)
        _write_json(output_dir / "final_graph.json", final_graph)
        del final_ah, final_graph

        family_counts: dict[str, dict[str, int]] = {}
        for item in manifest_cases:
            bucket = family_counts.setdefault(
                str(item["semantic_family"]),
                {"total": 0, "passed": 0, "failed": 0, "gaps": 0},
            )
            bucket["total"] += 1
            if item["semantic_status"] == "PASS":
                bucket["passed"] += 1
            elif item["semantic_status"] == "GAP":
                bucket["gaps"] += 1
            else:
                bucket["failed"] += 1

        manifest = {
            "cases_file": str(source.resolve()),
            "output_dir": str(output_dir.resolve()),
            "total": len(cases),
            "succeeded": succeeded,
            "failed": failed,
            "semantic_passed": semantic_passed,
            "semantic_failed": semantic_failed,
            "semantic_gaps": semantic_gaps,
            "semantic_families": family_counts,
            "oracle_file": str(oracle_source.resolve()),
            "scenario_isolation": True,
            "scenario_count": len({item["scenario_id"] for item in manifest_cases}),
            "cases": manifest_cases,
        }
        _write_json(output_dir / "manifest.json", manifest)

        summary_lines = [
            f"Acceptance run: {output_dir.name}",
            f"Cases: {len(cases)} | RUNTIME OK: {succeeded} | RUNTIME ERROR: {failed}",
            f"SEMANTIC PASS: {semantic_passed} | FAIL: {semantic_failed} | GAP: {semantic_gaps}",
            f"SCENARIOS: {len({item['scenario_id'] for item in manifest_cases})} | isolated between scenarios",
            "",
            "Families:",
        ]
        for family, counts in family_counts.items():
            summary_lines.append(
                f"  {family}: PASS {counts['passed']}/{counts['total']} | "
                f"FAIL {counts['failed']} | GAP {counts['gaps']}"
            )
        summary_lines.append("")
        for item in manifest_cases:
            line = (
                f"{item['index']:03d} {item['semantic_status']} "
                f"(runtime={item['status']}, scenario={item['scenario_id']}): {item['input']}"
            )
            if item["semantic_failures"]:
                line += " | " + ", ".join(item["semantic_failures"][:6])
                if len(item["semantic_failures"]) > 6:
                    line += f", ... (+{len(item['semantic_failures']) - 6})"
            if item["error"]:
                line += f" | runtime: {item['error']}"
            summary_lines.append(line)
        (output_dir / "summary.txt").write_text("\n".join(summary_lines) + "\n", encoding="utf-8", newline="\n")

        runs_root.mkdir(parents=True, exist_ok=True)
        (runs_root / "latest.txt").write_text(str(output_dir.resolve()) + "\n", encoding="utf-8", newline="\n")

        return AcceptanceRunResult(
            output_dir,
            source,
            len(cases),
            succeeded,
            failed,
            semantic_passed,
            semantic_failed,
            semantic_gaps,
            oracle_source,
            tuple(proofs),
        )
    finally:
        with services.operation_lock:
            _restore_runtime_state(services, live_state)
        if clock_was_running:
            clock.start()
