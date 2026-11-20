import csv
from argparse import ArgumentParser
from collections import defaultdict
from pathlib import Path

from pymorphy3 import MorphAnalyzer


def governors(path):
    with path.open(encoding='utf-8') as stream:
        constructions = defaultdict(list)
        for row in csv.DictReader(stream, delimiter='\t', quoting=csv.QUOTE_NONE):
            constructions[row['ConstrIndex']].append(row)
    morph = MorphAnalyzer()
    result = set()
    for frame in constructions.values():
        if not any(row['Form'] == 'Sacc' for row in frame):
            continue
        for row in frame:
            if row['Form'] != 'Sdat' or row['Role'] not in {'адресат', 'конечный посессор'}:
                continue
            for lemma in row['KeyLexemes'].split(','):
                if any(p.is_known and p.tag.POS == 'INFN' for p in morph.parse(lemma)):
                    result.add(lemma)
    return sorted(result)


if __name__ == '__main__':
    parser = ArgumentParser()
    parser.add_argument('items', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    args.output.write_text(''.join(verb + '\n' for verb in governors(args.items)), encoding='utf-8')
