from functools import cache
from importlib.resources import files

from .rules import known_forms


QUESTIONS = {'где', 'куда', 'откуда', 'когда', 'как', 'почему', 'зачем', 'сколько', 'насколько'}
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
    if row['rule'] == 'CL.ADV' and any(marker.get('scope') == 'temporal' for marker in markers):
        return 'когда'
    if row['rule'] == 'CL.ADV':
        for i in children[index]:
            marker = rows[i]
            if marker.get('rule') == 'CL.SPATIAL.FREE':
                entries, _ = _lexicon()
                wh = marker['lemma']
                governor = rows[row['head']]['lemma']
                if any(('governor', wh, prep, governor) in entries for prep, _ in SPATIAL):
                    return wh
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
        for i in children[index]:
            child = rows[i]
            if child['role'] == 'clause_relative':
                for j in children[i]:
                    if rows[j].get('rule') == 'CL.CORRELATE' and rows[j].get('antecedent') == index:
                        if rows[j]['lemma'] == 'что':
                            return 'насколько'
                        if rows[j]['lemma'] in ('когда', 'сколько'):
                            return rows[j]['lemma']
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


def place_partitions(trees, tokens, text):
    from .parser import _attachment_context, _span_label
    from .probe import Probe

    for i, token in enumerate(tokens):
        links = [tree[i] for tree in trees]
        if any(link.role != 'governed' or link.head is None for link in links):
            continue
        if len({(link.lemma, link.head) for link in links}) != 1:
            continue
        nominal = links[0]
        cases = {link.case for link in links}
        if 'accs' not in cases or not cases.intersection({'loct', 'loc2'}) or not cases <= {'loct', 'loc2', 'accs'}:
            continue
        if not any(lemma == nominal.lemma and {'Geox', 'Fixd'} <= tag.grammemes
                   for lemma, tag in known_forms(token.surface)):
            continue
        prep = nominal.head
        prepositions = {(tree[prep].lemma, tree[prep].head) for tree in trees if tree[prep].role == 'preposition'}
        if len(prepositions) != 1 or any(tree[prep].role != 'preposition' for tree in trees):
            continue
        form, host = prepositions.pop()
        meanings = {case: SPATIAL.get((form, case)) for case in cases}
        if host is None or set(meanings.values()) != {'где', 'куда'}:
            continue
        entries, _ = _lexicon()
        if not all(any(('governor', wh, form, tree[host].lemma) in entries for wh in meanings.values())
                   for tree in trees):
            continue
        phrase = _span_label(tokens, prep, i + 1)
        verb = _span_label(tokens, host)
        context = _attachment_context(text, tokens, trees, [host], prep, i + 1)
        question = (f'На какой вопрос отвечает сочетание «{phrase}» при слове «{verb}»? '
                    '«Где» указывает место действия, «куда» — его направление.')
        labels = {wh: f'{wh} — {phrase}' for wh in ('где', 'куда')}
        yield Probe(question, tuple(labels.values()), context), [labels[meanings[link.case]] for link in links]
