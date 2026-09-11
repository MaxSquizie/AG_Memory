from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
import json
from pathlib import Path
import re
import shutil
import traceback
from typing import Any, Mapping

from ah.documents import DocumentIngestionResult, DocumentProcessor

from .acceptance_runner import (
    AcceptanceRunResult,
    _capture_runtime_state,
    _restore_runtime_state,
    canonical_ah_snapshot,
    diff_canonical_ah,
)
from .document_acceptance import (
    DEFAULT_DOCUMENT_ORACLE,
    DOCUMENT_RUNS_DIRNAME,
    DocumentAcceptanceRunResult,
    DocumentSpec,
    DocumentVerdict,
    _graph_category_counts,
    evaluate_document_graph,
    load_document_specs,
)


RUNTIME_CONTRACT = "document_acceptance/runtime_contract.json"
_BATCH_LOCAL_RE = re.compile(r"^B(?P<unit>\d+):(?P<local>.+)$")


def _jsonable(value: Any) -> Any:
    if hasattr(value, "value") and value.__class__.__module__ == "enum":
        return value.value
    if hasattr(value, "__dataclass_fields__"):
        return {key: _jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, set, frozenset)):
        return [_jsonable(item) for item in value]
    if isinstance(value, Path):
        return str(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return repr(value)


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(_jsonable(payload), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _new_output_dir(data_dir: Path) -> Path:
    timestamp = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S_%z")
    root = data_dir / DOCUMENT_RUNS_DIRNAME
    candidate = root / timestamp
    suffix = 1
    while candidate.exists():
        candidate = root / f"{timestamp}_{suffix:02d}"
        suffix += 1
    candidate.mkdir(parents=True, exist_ok=False)
    return candidate


def _load_runtime_contract(data_dir: Path) -> Mapping[str, Mapping[str, Any]]:
    source = data_dir / RUNTIME_CONTRACT
    if not source.is_file():
        return {}
    payload = json.loads(source.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict) or payload.get("version") != 1:
        raise ValueError("document runtime contract must be an object with version=1")
    raw = payload.get("documents") or {}
    if not isinstance(raw, dict) or any(not isinstance(item, dict) for item in raw.values()):
        raise ValueError("document runtime contract documents must be an object of objects")
    return {str(key): item for key, item in raw.items()}


def _acceptance_chunk_limit(spec: DocumentSpec, contract: Mapping[str, Any]) -> int:
    configured = contract.get("max_chunk_chars")
    if configured is not None:
        value = int(configured)
        if value < 256:
            raise ValueError(f"{spec.document_id}: max_chunk_chars must be >= 256")
        return value
    # Existing oracle units are only authoring aids now, but their maximum length is
    # a deterministic source-derived ceiling that guarantees bounded multi-window
    # ingestion for the acceptance documents without cutting an oversized unit.
    longest_authored_unit = max((len(item.text) for item in spec.paragraphs), default=256)
    return max(256, min(1800, longest_authored_unit + 32))


def _experience_count(snapshot: Mapping[str, Mapping[str, Any]], source_ref: str) -> int:
    count = 0
    for item in snapshot.values():
        if not isinstance(item, Mapping):
            continue
        if item.get("kind") != "N" or str(item.get("domain") or "").upper() != "H":
            continue
        meta = item.get("meta") or {}
        if isinstance(meta, Mapping) and str(meta.get("source_ref") or "") == source_ref:
            count += 1
    return count


def _evidence_span(assertion: Any) -> tuple[int, int] | None:
    evidence = getattr(assertion, "evidence", None)
    if evidence is None:
        predicate = getattr(assertion, "predicate", None)
        evidence = getattr(predicate, "evidence", None)
    candidates = []
    if evidence is not None:
        candidates.append(evidence)
    predicate = getattr(assertion, "predicate", None)
    if predicate is not None and getattr(predicate, "evidence", None) is not None:
        candidates.append(predicate.evidence)
    for actant in getattr(assertion, "actants", ()):
        if getattr(actant, "evidence", None) is not None:
            candidates.append(actant.evidence)
    spans = [
        (int(item.start), int(item.end))
        for item in candidates
        if getattr(item, "start", None) is not None
        and getattr(item, "end", None) is not None
        and int(item.end) >= int(item.start)
    ]
    if not spans:
        return None
    return min(start for start, _ in spans), max(end for _, end in spans)


def _assertion_global_spans(result: DocumentIngestionResult) -> Mapping[str, tuple[int, int]]:
    spans: dict[str, tuple[int, int]] = {}
    for integrated in getattr(result.integration, "assertions", ()):
        match = _BATCH_LOCAL_RE.match(str(getattr(integrated, "local_id", "")))
        if match is None:
            continue
        unit_index = int(match.group("unit"))
        local_id = match.group("local")
        if unit_index >= len(result.perception_units) or unit_index >= len(result.chunks):
            continue
        assertion = next(
            (
                item
                for item in result.perception_units[unit_index].assertions
                if str(item.local_id) == local_id
            ),
            None,
        )
        if assertion is None:
            continue
        local_span = _evidence_span(assertion)
        if local_span is None:
            continue
        chunk = result.chunks[unit_index]
        start = chunk.start + local_span[0]
        end = chunk.start + local_span[1]
        if 0 <= start <= end <= len(result.source_text):
            spans[str(integrated.ref.uid)] = (start, end)
    return spans


def _runtime_checks(
    spec: DocumentSpec,
    contract: Mapping[str, Any],
    result: DocumentIngestionResult,
    snapshot: Mapping[str, Mapping[str, Any]],
    matched: Mapping[str, str],
) -> tuple[dict[str, Any], ...]:
    checks: list[dict[str, Any]] = []
    source_ref = result.source_ref
    experience_count = _experience_count(snapshot, source_ref)
    checks.append(
        {
            "name": "runtime.atomic_document_commit",
            "ok": experience_count == 1,
            "expected": 1,
            "actual": experience_count,
        }
    )
    checks.append(
        {
            "name": "runtime.source_coverage",
            "ok": result.coverage_ratio == 1.0
            and "".join(item.text for item in result.chunks) == result.source_text,
            "expected": 1.0,
            "actual": result.coverage_ratio,
        }
    )
    if bool(contract.get("require_multiple_chunks", True)):
        checks.append(
            {
                "name": "runtime.multiple_operational_chunks",
                "ok": len(result.chunks) > 1,
                "expected": ">1",
                "actual": len(result.chunks),
            }
        )

    spans = _assertion_global_spans(result)
    for fact_id, expectation in (contract.get("source_spans") or {}).items():
        if not isinstance(expectation, Mapping):
            continue
        uid = matched.get(str(fact_id))
        span = spans.get(uid or "")
        contains = str(expectation.get("contains") or "")
        actual_text = None if span is None else result.source_text[span[0]:span[1]]
        ok = span is not None
        if ok and contains:
            ok = contains.casefold().replace("ё", "е") in str(actual_text).casefold().replace("ё", "е")
        checks.append(
            {
                "name": f"source_span.{fact_id}",
                "ok": ok,
                "expected": {"contains": contains} if contains else "canonical assertion has source span",
                "actual": {"span": span, "text": actual_text},
            }
        )
    return tuple(checks)


def run_document_acceptance(services, *, oracle_file: str | Path | None = None) -> DocumentAcceptanceRunResult:
    """Run true whole-document acceptance through ``DocumentProcessor``.

    Each specification is restored to the same baseline, ingested by one
    ``FormalizationBatch(DOCUMENT)`` transaction and evaluated only after that
    transaction against the resulting canonical graph. The old authored units are
    retained solely as corpus metadata and a deterministic chunk-size hint; they
    are never replayed as independent dialogue turns.
    """
    data_dir = Path(services.config.paths.data_dir)
    oracle_source = (
        Path(oracle_file)
        if oracle_file is not None
        else data_dir / DEFAULT_DOCUMENT_ORACLE
    )
    specs = load_document_specs(data_dir, oracle_source)
    runtime_contract = _load_runtime_contract(data_dir)
    output_dir = _new_output_dir(data_dir)
    shutil.copyfile(oracle_source, output_dir / "oracle_used.json")
    runtime_contract_path = data_dir / RUNTIME_CONTRACT
    if runtime_contract_path.is_file():
        shutil.copyfile(runtime_contract_path, output_dir / "runtime_contract_used.json")

    clock = getattr(services, "clock", None)
    clock_was_running = bool(clock is not None and getattr(clock, "running", False))
    if clock_was_running:
        clock.stop()

    with services.operation_lock:
        live_state = _capture_runtime_state(services)
        baseline_state = _capture_runtime_state(services)
        initial_ah = canonical_ah_snapshot(services)
    _write_json(output_dir / "initial_ah.json", initial_ah)
    _write_json(output_dir / "config.json", services.config)

    verdicts: list[DocumentVerdict] = []
    records: list[dict[str, Any]] = []
    runtime_errors = 0
    runtime_successes = 0

    try:
        for index, spec in enumerate(specs, 1):
            with services.operation_lock:
                _restore_runtime_state(services, baseline_state)
                before = canonical_ah_snapshot(services)

            contract = runtime_contract.get(spec.document_id, {})
            source_ref = f"document-acceptance:{spec.document_id}"
            chunk_limit = _acceptance_chunk_limit(spec, contract)
            processor = DocumentProcessor(services, max_chunk_chars=chunk_limit)
            ingestion: DocumentIngestionResult | None = None
            error_text: str | None = None
            error_traceback: str | None = None

            try:
                ingestion = processor.ingest_text(
                    spec.source_text,
                    title=spec.title,
                    source_ref=source_ref,
                )
                runtime_successes += 1
            except Exception as exc:  # diagnostics boundary: preserve real failure
                runtime_errors += 1
                error_text = f"{type(exc).__name__}: {exc}"
                error_traceback = traceback.format_exc()

            with services.operation_lock:
                after = canonical_ah_snapshot(services)

            graph_checks: tuple[Mapping[str, Any], ...]
            matched: Mapping[str, str] = {}
            if ingestion is None:
                rollback_ok = before == after
                graph_checks = (
                    {
                        "name": "runtime.atomic_rollback",
                        "ok": rollback_ok,
                        "expected": "canonical graph unchanged after failed DOCUMENT",
                        "actual": "unchanged" if rollback_ok else diff_canonical_ah(before, after),
                    },
                )
                status = "FAIL"
            else:
                oracle_checks, matched = evaluate_document_graph(after, spec.final_expectation)
                graph_checks = tuple(oracle_checks) + _runtime_checks(
                    spec,
                    contract,
                    ingestion,
                    after,
                    matched,
                )
                status = "PASS" if all(bool(item.get("ok")) for item in graph_checks) else "FAIL"

            # Compatibility fields now describe authored oracle units, not separately
            # replayed turns. A passing document means those unit hints were covered
            # by one successful whole-document transaction.
            authored_units = len(spec.paragraphs)
            verdict = DocumentVerdict(
                document_id=spec.document_id,
                title=spec.title,
                status=status,
                paragraph_passed=authored_units if status == "PASS" else 0,
                paragraph_total=authored_units,
                runtime_errors=0 if ingestion is not None else 1,
                graph_checks=tuple(graph_checks),
                m2_question_count=len(spec.m2_questions),
            )
            verdicts.append(verdict)

            record = {
                "index": index,
                "document_id": spec.document_id,
                "title": spec.title,
                "source_ref": source_ref,
                "status": status,
                "runtime_status": "OK" if ingestion is not None else "ERROR",
                "error": error_text,
                "traceback": error_traceback,
                "chunk_limit": chunk_limit,
                "authored_oracle_units": authored_units,
                "chunks": (
                    []
                    if ingestion is None
                    else [
                        {"index": item.index, "start": item.start, "end": item.end}
                        for item in ingestion.chunks
                    ]
                ),
                "coverage_ratio": None if ingestion is None else ingestion.coverage_ratio,
                "integration": None if ingestion is None else ingestion.integration,
                "matched_facts": dict(matched),
                "graph_checks": list(graph_checks),
                "ah_diff": diff_canonical_ah(before, after),
            }
            filename = f"document_{index:03d}_{spec.document_id}.json"
            _write_json(output_dir / filename, record)
            records.append(
                {
                    "document_id": spec.document_id,
                    "title": spec.title,
                    "status": status,
                    "runtime_status": record["runtime_status"],
                    "file": filename,
                    "failures": [
                        str(item.get("name") or "<unnamed>")
                        for item in graph_checks
                        if not bool(item.get("ok"))
                    ],
                }
            )

        passed = sum(item.status == "PASS" for item in verdicts)
        failed = len(verdicts) - passed
        manifest = {
            "mode": "WHOLE_DOCUMENT_ATOMIC",
            "oracle_file": str(oracle_source.resolve()),
            "output_dir": str(output_dir.resolve()),
            "documents_total": len(verdicts),
            "documents_passed": passed,
            "documents_failed": failed,
            "runtime_successes": runtime_successes,
            "runtime_errors": runtime_errors,
            "scenario_isolation": True,
            "one_document_one_commit": True,
            "documents": records,
        }
        _write_json(output_dir / "manifest.json", manifest)

        report = {
            "summary": manifest,
            "documents": [
                {
                    "id": item.document_id,
                    "title": item.title,
                    "status": item.status,
                    "authored_oracle_units": item.paragraph_total,
                    "runtime_errors": item.runtime_errors,
                    "m2_question_count": item.m2_question_count,
                    "graph_categories": _graph_category_counts(item.graph_checks),
                    "graph_checks": list(item.graph_checks),
                }
                for item in verdicts
            ],
        }
        _write_json(output_dir / "document_report.json", report)

        lines = [
            f"Whole-document acceptance: PASS {passed}/{len(verdicts)}",
            f"Runtime: OK {runtime_successes} | ERROR {runtime_errors}",
            "Mode: one DocumentProcessor.ingest_text() / one atomic DOCUMENT commit per document",
            "",
        ]
        for item in verdicts:
            lines.append(
                f"{item.document_id} {item.status}: {item.title} | "
                f"checks {sum(bool(check.get('ok')) for check in item.graph_checks)}/{len(item.graph_checks)}"
            )
            for failure in item.failures[:10]:
                lines.append(
                    f"  FAIL {failure.get('name')}: expected={failure.get('expected')} actual={failure.get('actual')}"
                )
        (output_dir / "document_summary.txt").write_text(
            "\n".join(lines) + "\n", encoding="utf-8", newline="\n"
        )

        root = data_dir / DOCUMENT_RUNS_DIRNAME
        root.mkdir(parents=True, exist_ok=True)
        (root / "latest.txt").write_text(
            str(output_dir.resolve()) + "\n", encoding="utf-8", newline="\n"
        )

        underlying = AcceptanceRunResult(
            output_dir=output_dir,
            cases_file=oracle_source,
            total=len(verdicts),
            succeeded=runtime_successes,
            failed=runtime_errors,
            semantic_passed=passed,
            semantic_failed=failed,
            semantic_gaps=0,
            oracle_file=oracle_source,
        )
        total_authored_units = sum(len(spec.paragraphs) for spec in specs)
        return DocumentAcceptanceRunResult(
            output_dir=output_dir,
            total_documents=len(verdicts),
            passed_documents=passed,
            failed_documents=failed,
            total_paragraphs=total_authored_units,
            paragraph_semantic_passed=sum(
                item.paragraph_total for item in verdicts if item.status == "PASS"
            ),
            paragraph_semantic_failed=sum(
                item.paragraph_total for item in verdicts if item.status != "PASS"
            ),
            runtime_errors=runtime_errors,
            verdicts=tuple(verdicts),
            underlying=underlying,
        )
    finally:
        with services.operation_lock:
            _restore_runtime_state(services, live_state)
        if clock_was_running:
            clock.start()
