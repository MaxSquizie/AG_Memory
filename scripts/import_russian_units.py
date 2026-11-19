from argparse import ArgumentParser
import json
from pathlib import Path
import re

from pymorphy3 import MorphAnalyzer


def build(units_path, currencies_path):
    data = json.loads(units_path.read_text(encoding='utf8'))['main']['ru']['units']['long']
    candidates = set()
    for entry in data.values():
        pattern = entry.get('unitPattern-count-one', '')
        if match := re.fullmatch(r'\{0\} ([а-яё-]+)', pattern):
            candidates.add(match[1])
    currencies = json.loads(currencies_path.read_text(encoding='utf8'))['main']['ru']['numbers']['currencies']
    dictionary = MorphAnalyzer(lang='ru')
    for entry in currencies.values():
        for word in entry.get('displayName-count-one', '').split():
            if re.fullmatch(r'[а-яё-]+', word) and any(
                p.is_known and p.tag.POS == 'NOUN' and p.tag.case == 'nomn' and p.tag.animacy == 'inan'
                for p in dictionary.parse(word)
            ):
                candidates.add(word)
                break
    return ''.join(f'{word}\n' for word in sorted(candidates))


if __name__ == '__main__':
    parser = ArgumentParser(description='Import single-word Russian unit names from Unicode CLDR.')
    parser.add_argument('units', type=Path)
    parser.add_argument('currencies', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    args.output.write_text(build(args.units, args.currencies), encoding='utf8')
