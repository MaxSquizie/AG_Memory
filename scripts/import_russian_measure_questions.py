from argparse import ArgumentParser
from collections import defaultdict
from csv import DictReader
import json
from pathlib import Path
import re

from pymorphy3 import MorphAnalyzer


DIMENSIONS = {
    'вес': 'mass', 'цена': 'currency', 'срок': 'duration', 'длительность': 'duration',
    'расстояние': 'length', 'возраст': 'duration', 'скорость': 'speed',
}


def predicate_dimensions(items):
    frames = defaultdict(list)
    with items.open(encoding='utf8') as stream:
        for row in DictReader(stream, delimiter='\t'):
            frames[row['ConstrIndex']].append(row)
    roles = defaultdict(lambda: defaultdict(set))
    for rows in frames.values():
        if len(rows) != 3 or not any(row['Form'] == 'Snom' for row in rows):
            continue
        predicates = [row['Form'] for row in rows if row['Rank'] == 'Предикат']
        if len(predicates) != 1:
            continue
        for row in rows:
            forms = set(row['Form'].strip('{}').split(' / '))
            for form in forms & {'Sacc', 'ADV'}:
                roles[predicates[0]][form].add(row['Role'])
    for predicate, slots in roles.items():
        if slots['ADV'] == slots['Sacc'] and len(slots['ADV']) == 1:
            dimension = DIMENSIONS.get(next(iter(slots['ADV'])))
            if dimension:
                yield predicate, dimension


def unit_dimensions(units, currencies):
    data = json.loads(units.read_text(encoding='utf8'))['main']['ru']['units']['long']
    for unit, entry in data.items():
        label = re.fullmatch(r'\{0\} ([а-яё-]+)', entry.get('unitPattern-count-one', ''))
        if label:
            yield label[1], unit.partition('-')[0]
    dictionary = MorphAnalyzer(lang='ru')
    entries = json.loads(currencies.read_text(encoding='utf8'))['main']['ru']['numbers']['currencies']
    for entry in entries.values():
        for word in entry.get('displayName-count-one', '').split():
            if re.fullmatch(r'[а-яё-]+', word) and any(
                p.is_known and p.tag.POS == 'NOUN' and p.tag.case == 'nomn' and p.tag.animacy == 'inan'
                for p in dictionary.parse(word)
            ):
                yield word, 'currency'
                break


if __name__ == '__main__':
    parser = ArgumentParser()
    for name in ('frame_items', 'units', 'currencies', 'output'):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    predicates = set(predicate_dimensions(args.frame_items))
    dimensions = {dim for _, dim in predicates}
    records = {('predicate', lemma, dim) for lemma, dim in predicates}
    records.update(('unit', lemma, dim) for lemma, dim in unit_dimensions(args.units, args.currencies)
                   if dim in dimensions)
    args.output.write_text(''.join('\t'.join(row) + '\n' for row in sorted(records)), encoding='utf8')
