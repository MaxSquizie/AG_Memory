import re
from argparse import ArgumentParser
from pathlib import Path

from pymorphy3 import MorphAnalyzer


TAGS = {
    'Animacy': {'Anim': 'anim', 'Inan': 'inan'},
    'Gender': {'Masc': 'masc', 'Fem': 'femn', 'Neut': 'neut'},
    'Number': {'Sing': 'sing', 'Plur': 'plur'},
    'Case': {'Nom': 'nomn', 'Acc': 'accs', 'Gen': 'gent', 'Dat': 'datv', 'Ins': 'ablt', 'Loc': 'loct'},
}


def extract(corpora, *, name_parts=False):
    morph = MorphAnalyzer()
    entries = set()
    for path in corpora:
        for line in path.read_text(encoding='utf-8').splitlines():
            columns = line.split('\t')
            if len(columns) != 10:
                continue
            if name_parts and (columns[3] != 'PROPN' or columns[7] != 'flat:name'):
                continue
            if not name_parts and columns[3] != 'NOUN':
                continue
            surface, lemma = (word.casefold() for word in columns[1:3])
            if not all(re.fullmatch('[а-яё]+(?:-[а-яё]+)*', word) for word in (surface, lemma)):
                continue
            if morph.word_is_known(surface):
                continue
            features = dict(field.split('=', 1) for field in columns[5].split('|') if '=' in field)
            values = [data.get(features.get(key)) for key, data in TAGS.items()]
            if all(values):
                animacy, gender, number, case = values
                entries.add((surface, lemma, f'NOUN,{animacy},{gender} {number},{case}'))
    return entries


if __name__ == '__main__':
    parser = ArgumentParser()
    parser.add_argument('corpora', nargs='+', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--name-parts', action='store_true')
    args = parser.parse_args()
    args.output.write_text(''.join('\t'.join(row) + '\n' for row in sorted(extract(args.corpora, name_parts=args.name_parts))), encoding='utf-8')
