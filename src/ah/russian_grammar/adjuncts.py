from functools import cache
from importlib.resources import files

from .rules import known_forms


QUESTIONS = {'где', 'куда', 'откуда', 'когда', 'как', 'почему', 'зачем'}
SPATIAL = {
    ('в', 'loct'): 'где', ('на', 'loct'): 'где', ('в', 'loc2'): 'где', ('на', 'loc2'): 'где',
    ('в', 'accs'): 'куда', ('на', 'accs'): 'куда', ('к', 'datv'): 'куда',
    ('из', 'gent'): 'откуда', ('с', 'gent'): 'откуда', ('от', 'gent'): 'откуда',
}
PP = {('с', 'ablt'): 'как', ('от', 'gent'): 'почему', ('из-за', 'gent'): 'почему', ('для', 'gent'): 'зачем'}


@cache
def _lexicon():
    directory = files(__package__).joinpath('lexicon')
    entries = set()
    adverbs = {}
    for name in ('adjunct_frames.tsv', 'adjunct_readings.tsv'):
        for line in directory.joinpath(name).read_text(encoding='utf-8').splitlines():
            kind, wh, prep, lemma = line.split('\t')
            if kind == 'adverb':
                adverbs[lemma] = wh
            else:
                entries.add((kind, wh, prep, lemma))
    return entries, adverbs


def question(row):
    return row['role'] == 'adverb' and row['lemma'] in QUESTIONS


def clause_category(rows, children, index):
    row = rows[index]
    if row['role'] != 'clause_adverbial':
        return None
    markers = [rows[i] for i in children[index] if rows[i]['role'] == 'clause_marker']
    if row['rule'] == 'UTT.PURPOSE' and any(marker.get('scope') == 'purpose' for marker in markers):
        return 'зачем'
    if row['rule'] == 'CL.ADV' and any(marker.get('scope') == 'cause' for marker in markers):
        return 'почему'
    return None


def matches(query, rows, children, index):
    row = rows[index]
    clause = clause_category(rows, children, index)
    if clause:
        parent = rows[row['head']]
        return query['lemma'] == clause and parent['assertion_status'] == query['assertion_status']
    return (row['assertion_status'] == query['assertion_status'] and not row.get('scope') and
            category(rows, children, index) == query['lemma'])


def category(rows, children, index):
    row = rows[index]
    entries, adverbs = _lexicon()
    if row['role'] == 'adverb':
        return adverbs.get(row['lemma'])
    if row['role'] != 'preposition' or row['head'] is None:
        return None
    nouns = [rows[i] for i in children[index] if rows[i]['role'] == 'governed']
    if len(nouns) != 1:
        return None
    noun, = nouns
    prep, case, lemma = row['lemma'], noun['case'], noun['lemma']
    host = rows[row['head']]['lemma']
    wh = PP.get((prep, case))
    if wh and ('nominal', wh, prep, lemma) in entries:
        return wh
    if (prep, case) in {('благодаря', 'datv'), ('вследствие', 'gent')}:
        return 'почему'
    if (('nominal', 'когда', '-', lemma) in entries and
            (prep, case) in {('в', 'accs'), ('в', 'loct'), ('через', 'accs'), ('на', 'loct')}):
        return 'когда'
    wh = SPATIAL.get((prep, case))
    if wh and ('governor', wh, prep, host) in entries:
        geographic = any(l == lemma and 'Geox' in tag for l, tag in known_forms(noun['surface']))
        if geographic or ('nominal', wh, prep, lemma) in entries:
            return wh
    return None
