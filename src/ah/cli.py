from __future__ import annotations

import argparse
import json
from dataclasses import asdict, is_dataclass
from enum import Enum
from pathlib import Path
from typing import Any

from ah.bootstrap import RuntimeServices
from ah.config import load_config
from ah.diagnostics.session_log import start_session


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
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
    sub.add_parser("dump-json", help="dump canonical/runtime graph as JSON")
    sub.add_parser("dump-dot", help="dump graph as Graphviz DOT")

    tick = sub.add_parser("tick", help="advance ignition manually")
    tick.add_argument("count", nargs="?", type=int, default=1)

    refute = sub.add_parser("refute", help="create/reuse FALSE(N) and schedule h_N refutation")
    refute.add_argument("uid")
    refute.add_argument("--tick", action="store_true", help="apply one ignition tick immediately")

    corpus = sub.add_parser(
        "import-corpus",
        help="cold-load facts from JSON/.ahm/.prj without lighting Ignition",
    )
    corpus.add_argument("path", help="corpus file: .json, .ahm, or .prj")
    corpus.add_argument(
        "--domain",
        default="C",
        help="default domain for unnamed modules (C, P, or H)",
    )
    corpus.add_argument(
        "--no-save",
        action="store_true",
        help="write into the loaded memory but do not persist",
    )
    corpus.add_argument(
        "--cold-save",
        action="store_true",
        help="save canonical graph only, dropping leftover excitation",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cfg = load_config(Path(args.config))
    start_session(
        cfg.paths.logs_dir,
        extra={"entry": "cli", "command": args.command, "backend": cfg.llm.backend},
    )
    services = RuntimeServices.build(cfg)

    if args.command == "dsl":
        result = services.dsl.execute(args.expression)
        print(json.dumps(_jsonable(result), ensure_ascii=False, indent=2))
        return 0
    if args.command == "summary":
        print(json.dumps(_jsonable(services.diagnostics.summary()), ensure_ascii=False, indent=2))
        return 0
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
    if args.command == "import-corpus":
        from ah.config import PersistenceSettings
        from ah.core.persistence import JsonPersistence
        from ah.corpus import import_corpus_file, max_excitation
        from ah.model import Domain

        try:
            domain = Domain(str(args.domain).strip().upper())
        except ValueError as exc:
            raise SystemExit(f"Invalid domain: {args.domain}") from exc
        result = import_corpus_file(services.core, Path(args.path), default_domain=domain)
        saved = False
        if not args.no_save:
            if args.cold_save:
                JsonPersistence(
                    services.persistence.path,
                    PersistenceSettings(
                        enabled=True,
                        load_on_start=True,
                        autosave_every_ticks=services.config.persistence.autosave_every_ticks,
                        save_runtime_state=False,
                        save_pending_impulses=False,
                    ),
                ).save(services.core, context=services.context)
            else:
                services.save()
            saved = True
        print(
            json.dumps(
                {
                    **result.as_dict(),
                    "saved": saved,
                    "cold_save": bool(args.cold_save) and saved,
                    "max_excitation": max_excitation(services.core),
                    "persistence_file": str(services.persistence.path),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
