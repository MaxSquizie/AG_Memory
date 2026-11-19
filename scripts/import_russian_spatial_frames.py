import csv
import re
from argparse import ArgumentParser
from collections import defaultdict
from functools import cache
from pathlib import Path

import pymorphy3


MORPH = pymorphy3.MorphAnalyzer()
SPATIAL = {'где': 'место', 'куда': 'конечная точка', 'откуда': 'начальная точка'}
CASES = {'где': {'в': 'loct', 'на': 'loct'}, 'куда': {'в': 'accs', 'на': 'accs', 'к': 'datv'},
         'откуда': {'из': 'gent', 'с': 'gent', 'от': 'gent'}}
ROLES = {'образ действия': 'как', 'способ': 'как', 'момент времени': 'когда', 'цель': 'зачем', 'причина': 'почему'}
CASETAGS = {'loct': 'Sloc', 'accs': 'Sacc', 'datv': 'Sdat', 'gent': 'Sgen'}
WORD = re.compile('[а-яё]+(?:-[а-яё]+)*', re.I)


def rows(path):
    with path.open(encoding='utf-8') as stream:
        yield from csv.DictReader(stream, delimiter='\t', quoting=csv.QUOTE_NONE)


@cache
def parses(word):
    return [form for form in MORPH.parse(word) if form.is_known]


def pp(words, prep, case):
    if sum(any(p.tag.POS == 'PREP' for p in parses(w)) for w in words) != 1 or prep not in words:
        return set()
    for word in words[words.index(prep) + 1:]:
        forms = parses(word)
        nouns = {p.normal_form for p in forms if p.tag.POS == 'NOUN' and p.tag.case in
                 ({case, 'loc2'} if case == 'loct' else {case}) and p.tag.animacy == 'inan'}
        if nouns:
            return nouns if len(nouns) == 1 else set()
        if not any(p.tag.POS == 'ADJF' and p.tag.case == case for p in forms):
            break
    return set()


def extract(items, constructions):
    titles = {r['ConstrIndex']: r['ConstrName'].partition('_')[2] for r in rows(constructions)}
    result = set()
    adverbs = defaultdict(lambda: defaultdict(set))
    for row in rows(items):
        role, form = row['Role'], row['Form']
        wh = next((w for w, role_name in SPATIAL.items() if role == role_name), ROLES.get(role))
        if not wh:
            continue
        words = WORD.findall(titles.get(row['ConstrIndex'], '').casefold())
        if not words:
            continue
        if 'ADV' in form and not any(any(p.tag.POS == 'PREP' for p in parses(w)) for w in words):
            candidates = {p.normal_form for w in words for p in parses(w) if p.tag.POS == 'ADVB'}
            if len(candidates) == 1:
                word = candidates.pop()
                if not any(p.tag.POS in {'PRCL', 'CONJ'} or 'Ques' in p.tag for p in parses(word)):
                    adverbs[word][wh].add(row['ConstrIndex'])
        if wh not in SPATIAL:
            continue
        for prep, case in CASES[wh].items():
            if 'PR' + wh not in form and f'{prep} + {CASETAGS[case]}' not in form:
                continue
            for verb in row['KeyLexemes'].split(','):
                if any(p.tag.POS == 'INFN' for p in parses(verb)):
                    result.add(('governor', wh, prep, verb))
            if row['SemClass'] in {'-', 'место', 'предметный', 'вместилище', 'помещение', 'поверхность'}:
                for noun in pp(words, prep, case):
                    result.add(('nominal', wh, prep, noun))
    for word, kinds in adverbs.items():
        if len(kinds) == 1:
            wh, examples = next(iter(kinds.items()))
            if len(examples) >= 2:
                result.add(('adverb', wh, '-', word))
    return result


if __name__ == '__main__':
    parser = ArgumentParser()
    parser.add_argument('items', type=Path)
    parser.add_argument('constructions', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    with args.output.open('w', encoding='utf-8') as stream:
        for entry in sorted(extract(args.items, args.constructions)):
            stream.write('\t'.join(entry) + '\n')
