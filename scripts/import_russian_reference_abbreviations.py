import argparse
import csv
import re
from pathlib import Path


def entries(source):
    pairs = set()
    for row in csv.DictReader(source, delimiter='\t'):
        lemma = row['Constr'].split()[0]
        for short in re.findall(r'(?<![\w.])([а-яё]+)\.(?!\w)', row['ConstrPattern'], re.I):
            if (lemma.startswith(short) and row['Example'].lower().startswith(short + '.')
                    and lemma in row['KeyLexemes'].split(',')):
                pairs.add((short, lemma))
    return sorted(pairs)


if __name__ == '__main__':
    cli = argparse.ArgumentParser()
    cli.add_argument('source', type=Path)
    cli.add_argument('output', type=Path)
    args = cli.parse_args()
    with args.source.open(encoding='utf8') as source:
        args.output.write_text(''.join(f'{short}\t{lemma}\n' for short, lemma in entries(source)), encoding='utf8')
