from argparse import ArgumentParser
from csv import DictReader, QUOTE_NONE
from pathlib import Path


def rows(path):
    with path.open(encoding='utf-8') as source:
        yield from DictReader(source, delimiter='\t', quoting=QUOTE_NONE)


def governors(constructions, arguments):
    patterns = {row['ConstrIndex']: row['ConstrPattern'] for row in rows(constructions)}
    lemmas = set()
    for row in rows(arguments):
        slot = row['Form']
        if 'что + CL' not in slot or 'содержание' not in row['Role']:
            continue
        if patterns.get(row['ConstrIndex']) == f'Snom V {slot}':
            lemmas.update(lemma.strip().rstrip('0123456789') for lemma in row['KeyLexemes'].split(','))
    return sorted(lemma for lemma in lemmas if lemma)


if __name__ == '__main__':
    parser = ArgumentParser()
    parser.add_argument('constructions', type=Path)
    parser.add_argument('arguments', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    args.output.write_text('\n'.join(governors(args.constructions, args.arguments)) + '\n', encoding='utf-8')
