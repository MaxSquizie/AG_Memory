from __future__ import annotations

import argparse
from dataclasses import asdict, is_dataclass
from enum import Enum
import json
from pathlib import Path
from typing import Any

from ah.bootstrap import RuntimeServices
from ah.config import load_config
from ah.diagnostics import run_document_acceptance

from . import DEFAULT_DOCUMENT_SUMMARY_BUDGET_TOKENS


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {key: _jsonable(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, set, frozenset)):
        return [_jsonable(item) for item in value]
    return repr(value)


def _print(value: Any) -> None:
    print(json.dumps(_jsonable(value), ensure_ascii=False, indent=2))


def _add_summary_controls(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--request",
        default="Сделай краткое содержание документа в 5–7 предложениях.",
    )
    parser.add_argument(
        "--budget-tokens",
        type=int,
        default=DEFAULT_DOCUMENT_SUMMARY_BUDGET_TOKENS,
    )
    parser.add_argument("--roots-per-slice", type=int, default=24)
    parser.add_argument("--max-slices", type=int, default=128)
    parser.add_argument("--settle-ticks", type=int, default=1)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Whole-document AH ingestion and deterministic continuation diagnostics"
    )
    parser.add_argument("--config", default="config/default.toml")
    sub = parser.add_subparsers(dest="command", required=True)

    ingest = sub.add_parser("ingest", help="ingest one TXT/MD/DOCX as one atomic DOCUMENT batch")
    ingest.add_argument("path")
    ingest.add_argument("--title")
    ingest.add_argument("--source-ref")
    ingest.add_argument("--chunk-chars", type=int, default=6000)
    ingest.add_argument("--save", action="store_true", help="persist AH after successful commit")

    summary = sub.add_parser(
        "summarize",
        help="summarize an already-ingested source through bounded AH-only slices",
    )
    summary.add_argument("source_ref")
    _add_summary_controls(summary)

    run = sub.add_parser(
        "run",
        help="ingest one document and immediately execute bounded AH-only summary continuation",
    )
    run.add_argument("path")
    run.add_argument("--title")
    run.add_argument("--source-ref")
    run.add_argument("--chunk-chars", type=int, default=6000)
    run.add_argument("--save", action="store_true")
    _add_summary_controls(run)

    acceptance = sub.add_parser(
        "acceptance",
        help="run true whole-document atomic acceptance against the configured document oracle",
    )
    acceptance.add_argument("--oracle")
    return parser


def _summary_payload(result) -> dict[str, Any]:
    return {
        "source_ref": result.source_ref,
        "request": result.request,
        "text": result.text,
        "stop_reason": result.stop_reason,
        "final_estimated_tokens": result.estimated_tokens,
        "workspace_ref_count": len(result.workspace_refs),
        "slice_count": len(result.slice_diagnostics),
        "primary_covered": sum(len(item.primary_refs) for item in result.slice_diagnostics),
        "source_primary_total": (
            result.slice_diagnostics[-1].cursor_end if result.slice_diagnostics else 0
        ),
        "slices": [
            {
                "slice": item.slice_index,
                "cursor_start": item.cursor_start,
                "cursor_end": item.cursor_end,
                "primary_refs": item.primary_refs,
                "overlap_refs": item.overlap_refs,
                "workspace_refs": item.workspace_refs,
                "estimated_tokens": item.estimated_tokens,
                "done": item.done,
            }
            for item in result.slice_diagnostics
        ],
    }


def _ingestion_payload(result) -> dict[str, Any]:
    return {
        "source_ref": result.source_ref,
        "title": result.title,
        "source_chars": len(result.source_text),
        "chunk_count": len(result.chunks),
        "coverage_chars": result.coverage_chars,
        "coverage_ratio": result.coverage_ratio,
        "chunks": [
            {"index": item.index, "start": item.start, "end": item.end}
            for item in result.chunks
        ],
        "assertion_count": len(getattr(result.integration, "assertions", ())),
        "relation_count": len(getattr(result.integration, "relations", ())),
        "experience_ref": getattr(result.integration, "experience_ref", None),
    }


def _run_summary(services: RuntimeServices, args) -> Any:
    return services.document_processor().summarize(
        args.source_ref,
        request=args.request,
        settle_ticks=args.settle_ticks,
        budget_tokens=args.budget_tokens,
        max_primary_roots=args.roots_per_slice,
        max_slices=args.max_slices,
    )


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config = load_config(Path(args.config))
    services = RuntimeServices.build(config)

    if args.command == "acceptance":
        result = run_document_acceptance(
            services,
            oracle_file=None if args.oracle is None else Path(args.oracle),
        )
        _print(
            {
                "output_dir": result.output_dir,
                "documents_total": result.total_documents,
                "documents_passed": result.passed_documents,
                "documents_failed": result.failed_documents,
                "runtime_errors": result.runtime_errors,
                "verdicts": result.verdicts,
            }
        )
        return 0 if result.failed_documents == 0 and result.runtime_errors == 0 else 1

    if args.command == "ingest":
        result = services.document_processor(max_chunk_chars=args.chunk_chars).ingest_file(
            args.path,
            title=args.title,
            source_ref=args.source_ref,
        )
        if args.save:
            services.save()
        _print(_ingestion_payload(result))
        return 0

    if args.command == "summarize":
        result = _run_summary(services, args)
        _print(_summary_payload(result))
        return 0

    if args.command == "run":
        ingestion = services.document_processor(max_chunk_chars=args.chunk_chars).ingest_file(
            args.path,
            title=args.title,
            source_ref=args.source_ref,
        )
        if args.save:
            services.save()
        args.source_ref = ingestion.source_ref
        summary = _run_summary(services, args)
        _print({"ingestion": _ingestion_payload(ingestion), "summary": _summary_payload(summary)})
        return 0

    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
