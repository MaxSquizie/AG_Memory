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
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cfg = load_config(Path(args.config))
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
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
