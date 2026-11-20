from datetime import date
from functools import cache
from importlib.resources import files

from .parser import Link
from .rules import known_forms
from .utterances import _map


@cache
def _months():
    rows = files(__package__).joinpath('lexicon/month-genitives.tsv').read_text(encoding='utf8')
    return {form: int(number) for number, form in (row.split('\t') for row in rows.splitlines())}


def calendar_day(tokens, i):
    if i + 3 > len(tokens):
        return None
    day, month, year = (t.surface.casefold() for t in tokens[i:i + 3])
    number = _months().get(month)
    if not number or not day.isdecimal() or len(day) > 2 or not year.isdecimal() or len(year) != 4:
        return None
    try:
        return date(int(year), number, int(day))
    except ValueError:
        return None


def year_unit(surface):
    return any(lemma == 'год' and tag.POS == 'NOUN' and tag.case == 'gent' for lemma, tag in known_forms(surface))


def full_date(tokens):
    if len(tokens) >= 5 and year_unit(tokens[3].surface):
        return calendar_day(tokens, 0)
    return None


def attach(tokens, value, parse):
    positions = range(4, len(tokens))
    month = next(lemma for lemma, tag in known_forms(tokens[1].surface) if tag.POS == 'NOUN' and tag.case == 'gent')
    for tree in parse(tokens[4:]):
        root = next(i for i, link in enumerate(tree) if link.head is None)
        if not any(link.role == 'subject' and link.head == root for link in tree):
            continue
        links = _map(tree, positions)
        links[0] = Link('temporal', tokens[0].surface, positions[root], 'DATE.DAY', case='gent')
        links[1] = Link('date_month', month, 0, 'DATE.MONTH', case='gent')
        links[2] = Link('date_year', str(value.year), 3, 'DATE.YEAR', case='gent')
        links[3] = Link('genitive_modifier', 'год', 1, 'DATE.YEAR.UNIT', case='gent')
        yield tuple(links[i] for i in range(len(tokens)))
