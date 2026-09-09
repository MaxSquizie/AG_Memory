from __future__ import annotations

import argparse
import json
from dataclasses import asdict, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from ah.bootstrap import RuntimeServices
from ah.config import load_config


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {k: _jsonable(v) for k, v in asdict(value).items()}
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_jsonable(v) for v in value]
    return repr(value)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="AH Agent MVP diagnostic CLI")
    parser.add_argument("--config", default="config/default.toml")
    sub = parser.add_subparsers(dest="command", required=True)

    dsl = sub.add_parser("dsl", help="execute one AH DSL command/pipeline")
    dsl.add_argument("expression")

    sub.add_parser("summary", help="print runtime summary")
    sub.add_parser("preflight", help="print deterministic hackathon structural preflight (not M1-M5)")
    sub.add_parser("dump-json", help="dump canonical/runtime graph as JSON")
    sub.add_parser("dump-dot", help="dump graph as Graphviz DOT")

    tick = sub.add_parser("tick", help="advance ignition manually")
    tick.add_argument("count", nargs="?", type=int, default=1)

    refute = sub.add_parser("refute", help="create/reuse FALSE(N) and schedule h_N refutation")
    refute.add_argument("uid")
    refute.add_argument("--tick", action="store_true", help="apply one ignition tick immediately")

    corpus = sub.add_parser("import-corpus", help="cold-load structured JSON/.ahm/.prj into canonical AH")
    corpus.add_argument("path")
    corpus.add_argument("--domain", default="C")
    corpus.add_argument("--no-save", action="store_true")
    corpus.add_argument("--hot-save", action="store_true", help="persist current runtime x/queue too")

    raw = sub.add_parser("import-text", help="load raw text paragraphs as USER experience; strict semantic parse by default")
    raw.add_argument("path")
    raw.add_argument("--no-semantics", action="store_true")
    raw.add_argument("--best-effort", action="store_true", help="explicitly allow failed semantic chunks to fall back to H-only")
    raw.add_argument("--no-save", action="store_true")
    raw.add_argument("--hot-save", action="store_true")

    dialogue = sub.add_parser("import-dialogue", help="load ah_dialogue_v1 JSON")
    dialogue.add_argument("path")
    dialogue.add_argument("--no-semantics", action="store_true")
    dialogue.add_argument("--best-effort", action="store_true")
    dialogue.add_argument("--no-save", action="store_true")
    dialogue.add_argument("--hot-save", action="store_true")

    memory = sub.add_parser("import-memory", help="replace live AH from persistence snapshot")
    memory.add_argument("path")
    memory.add_argument("--hot-restore", action="store_true", help="restore saved runtime excitation/pending impulses")
    memory.add_argument("--no-save", action="store_true")

    sub.add_parser("reset-memory", help="clear AH/runtime/context and recreate SELF/USER")


    semantic = sub.add_parser(
        "semantic-acceptance",
        help="run a semantic acceptance cases/oracle pair through the normal local-LLM pipeline",
    )
    semantic.add_argument(
        "--cases",
        default="data/acceptance_cases_m1_adversarial.txt",
        help="one-turn-per-line acceptance cases file",
    )
    semantic.add_argument(
        "--oracle",
        default="data/acceptance_oracle_m1_adversarial.json",
        help="semantic oracle JSON aligned with --cases",
    )
    sub.add_parser(
        "m2-acceptance",
        help=(
            "run attention-driven M2 on a dirty/live-AH snapshot with >=150k UIDs "
            "(no LLM, no live AH mutation)"
        ),
    )
    m1 = sub.add_parser(
        "m1-score",
        help="score weighted actant-role F1 from an existing acceptance_runs bundle",
    )
    m1.add_argument("run_dir")
    sub.add_parser(
        "m3-acceptance",
        help="run committee-shape GC check: 200 injected orphans, <=50 ticks, 100%% live preservation",
    )
    sub.add_parser(
        "m4-acceptance",
        help="run AH vs Vanilla RAG benchmark (M4) on the document corpus",
    )
    sub.add_parser(
        "tick-benchmark",
        help="benchmark Ignition ticks on a fixture with >=1000 N+L graph units",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cfg = load_config(Path(args.config))
    if args.command == "m2-acceptance":
        from ah.diagnostics import run_m2_attention_acceptance

        services = RuntimeServices.build(cfg)
        result = run_m2_attention_acceptance(
            data_dir=cfg.paths.data_dir,
            inference_settings=cfg.inference,
            ignition_settings=cfg.ignition,
            workspace_settings=cfg.workspace,
            lifecycle_settings=cfg.lifecycle,
            base_core=services.core,
            base_ignition=services.ignition,
            runtime_lock=services.operation_lock,
        )
        print(json.dumps(_jsonable(result), ensure_ascii=False, indent=2))
        return 0 if result.failed == 0 else 1
    if args.command == "m1-score":
        from ah.diagnostics import score_m1_acceptance_bundle

        report = score_m1_acceptance_bundle(args.run_dir)
        print(json.dumps(_jsonable(report), ensure_ascii=False, indent=2))
        return 0 if report.weighted_mean >= 0.6 else 1
    if args.command == "m3-acceptance":
        from ah.diagnostics import run_m3_gc_acceptance

        report = run_m3_gc_acceptance(cfg, data_dir=cfg.paths.data_dir)
        print(json.dumps(_jsonable(report), ensure_ascii=False, indent=2))
        if report.output_dir:
            print(f"bundle: {report.output_dir}")
        return 0 if report.passed else 1
    if args.command == "m4-acceptance":
        from ah.diagnostics import run_m4_acceptance

        report = run_m4_acceptance(cfg)
        print(json.dumps(_jsonable(report), ensure_ascii=False, indent=2))
        if report.output_dir:
            print(f"bundle: {report.output_dir}")
        return 0 if report.passed else 1
    if args.command == "tick-benchmark":
        from ah.diagnostics import run_tick_benchmark

        report = run_tick_benchmark(cfg)
        print(json.dumps(_jsonable(report), ensure_ascii=False, indent=2))
        return 0 if report.passes_500ms else 1

    services = RuntimeServices.build(cfg)

    if args.command == "semantic-acceptance":
        from ah.diagnostics import run_acceptance_suite

        result = run_acceptance_suite(
            services,
            cases_file=Path(args.cases),
            oracle_file=Path(args.oracle),
            runs_dirname="acceptance_runs_m1_adversarial",
        )
        print(json.dumps(_jsonable(result), ensure_ascii=False, indent=2))
        return 0 if result.semantic_failed == 0 and result.failed == 0 else 1

    if args.command == "import-corpus":
        from ah.model import Domain
        try:
            domain = Domain(str(args.domain).strip().upper())
        except ValueError as exc:
            raise SystemExit(f"Invalid domain: {args.domain}") from exc
        result = services.import_corpus(args.path, domain=domain, save=not args.no_save, cold_save=not args.hot_save)
        print(json.dumps(_jsonable(result), ensure_ascii=False, indent=2))
        return 0
    if args.command == "import-text":
        text = Path(args.path).read_text(encoding="utf-8-sig")
        result = services.import_raw_text(text, save=not args.no_save, parse_user_semantics=not args.no_semantics, cold_save=not args.hot_save, strict=not args.best_effort)
        print(json.dumps(_jsonable(result), ensure_ascii=False, indent=2))
        return 0 if not getattr(result, "errors", ()) else (0 if args.best_effort else 1)
    if args.command == "import-dialogue":
        result = services.import_dialogue(args.path, save=not args.no_save, parse_user_semantics=not args.no_semantics, cold_save=not args.hot_save, strict=not args.best_effort)
        print(json.dumps(_jsonable(result), ensure_ascii=False, indent=2))
        return 0 if not getattr(result, "errors", ()) else (0 if args.best_effort else 1)
    if args.command == "import-memory":
        result = services.import_memory(args.path, save=not args.no_save, cold_restore=not args.hot_restore)
        print(json.dumps(_jsonable(result), ensure_ascii=False, indent=2))
        return 0
    if args.command == "reset-memory":
        services.reset_memory(persist=True)
        print(json.dumps(_jsonable(services.diagnostics.summary()), ensure_ascii=False, indent=2))
        return 0

    if args.command == "dsl":
        result = services.dsl.execute(args.expression)
        print(json.dumps(_jsonable(result), ensure_ascii=False, indent=2))
        return 0
    if args.command == "summary":
        print(json.dumps(_jsonable(services.diagnostics.summary()), ensure_ascii=False, indent=2))
        return 0
    if args.command == "preflight":
        from ah.diagnostics import HackathonPreflightInspector

        report = HackathonPreflightInspector(services.core, cfg).inspect()
        print(json.dumps(_jsonable(report), ensure_ascii=False, indent=2))
        return 0 if report.structural_ok else 1
    if args.command == "dump-json":
        print(services.graph_inspector.to_json())
        return 0
    if args.command == "dump-dot":
        print(services.graph_inspector.to_dot())
        return 0
    if args.command == "tick":
        if args.count < 1:
            raise SystemExit("count must be >= 1")
        for _ in range(args.count):
            services.ignition.tick()
        print(json.dumps(_jsonable(services.diagnostics.summary()), ensure_ascii=False, indent=2))
        return 0
    if args.command == "refute":
        uid = args.uid.lstrip("@")
        commit = services.refute(services.core.ref(uid))
        if args.tick:
            services.ignition.tick()
        print(json.dumps(_jsonable(commit), ensure_ascii=False, indent=2))
        return 0
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
