"""Print a grammar report or the pending System One request."""
import argparse
from dataclasses import asdict
import json

from . import analyze
from .probe import DEFAULT_JEV_MODEL


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('text')
    parser.add_argument('--jev', action='store_true', help='emit only the pending request, if any')
    parser.add_argument('--model', default=DEFAULT_JEV_MODEL, help='Jev model name or alias')
    args = parser.parse_args()
    result = analyze(args.text)
    if args.jev:
        if result.probes:
            print(result.probes[-1].prompt(args.model))
        return
    report = asdict(result)
    report['probes'] = [probe.jev_request(args.model) for probe in result.probes]
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
