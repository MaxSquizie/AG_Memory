"""Print the pending readable probe, with explicit export modes."""
import argparse
from dataclasses import asdict
import json

from . import analyze
from .probe import DEFAULT_JEV_MODEL


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('text')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--report', action='store_true', help='emit the full JSON analysis report')
    mode.add_argument('--jev', action='store_true', help='emit only the pending request, if any')
    parser.add_argument('--model', default=DEFAULT_JEV_MODEL, help='Jev model name or alias')
    args = parser.parse_args()
    result = analyze(args.text)
    if args.report:
        report = asdict(result)
        report['probes'] = [probe.prompt() for probe in result.probes]
        print(json.dumps(report, ensure_ascii=False, indent=2))
    elif result.probes:
        probe = result.probes[-1]
        if args.jev:
            print(json.dumps(probe.jev_request(args.model), ensure_ascii=False))
        else:
            print(probe.prompt())
    elif not args.jev:
        print(f'{result.status} ({result.reason})')


if __name__ == '__main__':
    main()
