from argparse import ArgumentParser
from collections import defaultdict
from csv import DictReader
from pathlib import Path


def entries(source):
    groups = defaultdict(list)
    for row in DictReader(source, delimiter='\t'):
        groups[row['ConstrIndex']].append(row)
    pairs = set()
    for rows in groups.values():
        if not any('Rel + CL' in row['Form'] and row['Role'] != 'адресат' for row in rows):
            continue
        for row in rows:
            if row['Role'] != 'адресат':
                continue
            choices = set(row['Form'].strip('{}').split(' / '))
            cases = {case for form, case in [('Sacc', 'accs'), ('Sdat', 'datv')] if form in choices}
            lemmas = (lemma.strip().rstrip('0123456789') for lemma in row['KeyLexemes'].split(','))
            pairs.update((lemma, case) for lemma in lemmas if lemma for case in cases)
    return sorted(pairs)


if __name__ == '__main__':
    parser = ArgumentParser()
    parser.add_argument('source', type=Path)
    parser.add_argument('target', type=Path)
    args = parser.parse_args()
    with args.source.open(encoding='utf8') as source:
        rows = entries(source)
    args.target.write_text(''.join(f'{lemma}\t{case}\n' for lemma, case in rows), encoding='utf8')
