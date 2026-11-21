from argparse import ArgumentParser
from collections import defaultdict
from csv import DictReader
from pathlib import Path

from ah.russian_grammar.numerals import expressions
from ah.russian_grammar.parser import Occurrence
from ah.russian_grammar.prepositions import TOKEN
from ah.russian_grammar.quantity_groups import _groups


def units(source):
    evidence = defaultdict(set)
    for row in DictReader(source, delimiter='\t'):
        if (row['Type'], row['Role'], row['Form']) != ('Circum', 'частота', 'Sacc'):
            continue
        tokens = tuple(Occurrence(m[0], m.start(), m.end()) for m in TOKEN.finditer(row['Phrase']))
        for expression in expressions(tokens):
            if expression.kind != 'cardinal':
                continue
            for group in _groups(tokens, 0, expression, 256):
                if group.case == 'accs' and group.noun == len(tokens) - 1:
                    evidence[group.lemma].add(expression.value)
    return sorted(unit for unit, values in evidence.items() if len(values) > 1)


if __name__ == '__main__':
    parser = ArgumentParser()
    parser.add_argument('source', type=Path)
    parser.add_argument('target', type=Path)
    args = parser.parse_args()
    with args.source.open(encoding='utf-8') as source:
        args.target.write_text(''.join(unit + '\n' for unit in units(source)), encoding='utf-8')
