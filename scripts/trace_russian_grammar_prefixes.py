import argparse
import json

from ah.russian_grammar import analyze
from ah.russian_grammar.prepositions import TOKEN


def trace(source):
    for match in TOKEN.finditer(source):
        prefix = source[:match.end()]
        result = analyze(prefix)
        trees = result.analyses
        edges = [{(i, link.role, link.head) for i, link in enumerate(tree) if link.head is not None}
                 for tree in trees]
        common = sorted(set.intersection(*edges)) if edges else []
        yield dict(prefix=prefix, status=result.status, trees=len(trees), common=common,
                   question=result.probes[-1].prompt() if result.probes else None)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('text')
    for record in trace(parser.parse_args().text):
        print(json.dumps(record, ensure_ascii=False))
