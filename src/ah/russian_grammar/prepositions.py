"""Simple prepositions and the attachment of completed nominal groups."""
from collections.abc import Iterator
from importlib.resources import files
import re


TOKEN = re.compile(r'[^\W\d_]+(?:[-‐‑][^\W\d_]+)*|\d+|[^\s]', re.UNICODE)


def _load_lexicon():
    forms, government, prefixes = {}, {}, set()
    rows = files(__package__).joinpath('lexicon/prepositions.tsv').read_text(encoding='utf8')
    for row in rows.splitlines():
        form, lemma, cases = row.split('\t')
        tokens = TOKEN.findall(form)
        forms[' '.join(tokens)] = lemma
        government[lemma] = frozenset() if cases == '-' else frozenset(cases.split())
        prefixes.update(' '.join(tokens[:i]) for i in range(1, len(tokens)))
    return forms, government, prefixes


FORMS, GOVERNMENT, PREFIXES = _load_lexicon()

CASE_NAMES = {
    'nomn': 'nominative', 'gent': 'genitive', 'gen2': 'partitive genitive', 'datv': 'dative',
    'accs': 'accusative', 'ablt': 'instrumental', 'loct': 'prepositional', 'loc2': 'locative',
}


def group_heads(groups, words, predicate, nominal_heads) -> Iterator[dict[int, int]]:
    """Attach groups to the verb or to a noun on the preceding phrase's right edge."""
    pending = [(0, nominal_heads)]
    while pending:
        position, heads = pending.pop()
        if position == len(groups):
            yield heads
            continue
        start, noun = groups[position]
        local = {j: start if words[j].role == 'prep_part' else noun for j in range(start + 1, noun)}
        local[noun] = start
        j = noun + 1
        while j < len(words) and words[j].role == 'post_attribute':
            local[j] = noun
            j += 1
        candidates = [predicate]
        j = start - 1
        while 0 <= j < start and j != predicate:
            role = words[j].role
            if role in {'subject', 'object', 'duration', 'governed'}:
                candidates.append(j)
            # A nominal at the edge can itself belong to an earlier PP.
            # Its chosen governor determines which larger phrase is still open.
            if j not in heads:
                break
            j = heads[j]
        for host in reversed(candidates):
            pending.append((position + 1, {**heads, **local, start: host}))
