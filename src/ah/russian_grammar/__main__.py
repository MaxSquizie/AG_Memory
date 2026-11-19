"""Inspect occurrences, syntax edges and the exact bounded question."""
import argparse
from dataclasses import asdict
import json

from . import analyze


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('text')
    args = parser.parse_args()
    result = analyze(args.text)
    print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
    for probe in result.probes:
        print(probe.prompt())


if __name__ == '__main__':
    main()
