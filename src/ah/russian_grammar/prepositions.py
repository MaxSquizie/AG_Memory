"""Simple prepositions and the attachment of completed nominal groups."""
from collections.abc import Iterator


GOVERNMENT = {
    'в': {'accs', 'loct', 'loc2'}, 'на': {'accs', 'loct', 'loc2'},
    'к': {'datv'}, 'из': {'gent', 'gen2'}, 'без': {'gent', 'gen2'},
    'с': {'gent', 'gen2', 'accs', 'ablt'}, 'под': {'accs', 'ablt'}, 'о': {'accs', 'loct'},
}
CASE_NAMES = {
    'gent': 'genitive', 'gen2': 'partitive genitive', 'datv': 'dative',
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
        local = {noun: start, **dict.fromkeys(range(start + 1, noun), noun)}
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
