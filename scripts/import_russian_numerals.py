from argparse import ArgumentParser
from pathlib import Path

from num2words.lang_RU import Num2Word_RU, THOUSANDS


def build():
    numbers = Num2Word_RU()
    rows = []
    atoms = [*range(20), *range(20, 100, 10), *range(100, 1000, 100), *(1000**order for order in THOUSANDS)]
    for value in sorted(set(atoms)):
        cardinal = numbers.to_cardinal(value).split()[-1]
        ordinal = numbers.to_ordinal(value)
        prefix = numbers.to_ordinal(1000 * value).removesuffix('тысячный') if 1 < value < 1000 else '-'
        rows.extend(((cardinal, 'scale' if value >= 1000 else 'cardinal', value, prefix), (ordinal, 'ordinal', value, '-')))
    rows.extend((numbers.to_cardinal(n, plural=True), 'collective', n, '-') for n in (2, 3, 4))
    return ''.join(f'{lemma}\t{kind}\t{value}\t{prefix}\n' for lemma, kind, value, prefix in rows)


if __name__ == '__main__':
    parser = ArgumentParser(description='Generate Russian numeral atoms with num2words 0.5.14.')
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    args.output.write_text(build(), encoding='utf-8')
