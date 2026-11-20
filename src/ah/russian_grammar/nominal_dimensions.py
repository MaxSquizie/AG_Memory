from .morphology import NOMINAL_ROLES, from_tag
from .nominal_groups import _groups as nominal_groups
from .numerals import expressions
from .quantity_groups import _groups as quantity_groups
from .rules import known_forms
from .utterances import _map


def _tails(tokens, noun, budget):
    from .parser import AnalysisBudgetExceeded, Link

    pending = [(noun + 1, (noun,), {})]
    produced = 0
    while pending:
        start, hosts, links = pending.pop()
        produced += 1
        if produced > budget:
            raise AnalysisBudgetExceeded('NOMINAL_MEASURE_BUDGET')
        yield start, links
        for group in nominal_groups(tokens, start, budget, bare_cases=('gent', 'gen2')):
            for j, host in enumerate(hosts):
                child = Link('genitive_modifier', group.lemma, host, 'N.GEN', case=group.case)
                extended = {**links, group.noun: child, **dict(group.extra)}
                pending.append((group.end, (*hosts[:j + 1], group.noun), extended))


def trees(tokens, parse, budget):
    from .parser import AnalysisBudgetExceeded, Link

    count = 0
    emitted = set()
    for i in range(1, len(tokens) - 3):
        if tokens[i + 1].surface.casefold() != 'в':
            continue
        measures = [(lemma, tag) for lemma, tag in known_forms(tokens[i].surface)
                    if tag.POS == 'NOUN' and tag.case == 'ablt' and tag.animacy == 'inan']
        if not measures:
            continue
        for number in expressions(tokens, i + 2):
            if number.kind not in ('fraction', 'cardinal'):
                continue
            for group in quantity_groups(tokens, i + 2, number, budget):
                if group.case != 'accs':
                    continue
                numeric = dict(group.links)
                numeric[group.noun] = Link('governed', group.lemma, i + 1, 'P1', 'accs', morphology=group.morphology)
                numeric[i + 1] = Link('preposition', 'в', i, 'P2')
                for end, tail in _tails(tokens, group.noun, budget):
                    kept = (*range(i), *range(end, len(tokens)))
                    for tree in parse(tuple(tokens[j] for j in kept)):
                        restored = _map(tree, kept)
                        host = i - 1
                        while host is not None and host < i and restored[host].role in NOMINAL_ROLES | {'genitive_modifier'}:
                            for lemma, tag in measures:
                                count += 1
                                if count > budget:
                                    raise AnalysisBudgetExceeded('NOMINAL_MEASURE_BUDGET')
                                dimension = Link('measure', lemma, host, 'N.MEASURE.QUANTIFIED', 'ablt', morphology=from_tag(tag))
                                links = {**restored, i: dimension, **numeric, **tail}
                                option = tuple(links[j] for j in range(len(tokens)))
                                if option not in emitted:
                                    emitted.add(option)
                                    yield option
                            host = restored[host].head
    if emitted:
        yield from parse(tokens)


def partitions(trees, tokens, text):
    from .parser import _span_label
    from .probe import Probe

    for i in range(len(tokens)):
        links = [tree[i] for tree in trees]
        if not any(link.rule == 'N.MEASURE.QUANTIFIED' for link in links):
            continue
        hosts = {link.head for link in links}
        if None in hosts or len(hosts) < 2:
            continue
        labels = {host: _span_label(tokens, host) for host in sorted(hosts)}
        focus = _span_label(tokens, i)
        question = f'К какому слову в этом предложении относится «{focus}»?'
        yield Probe(question, tuple(labels.values()), text), [labels[link.head] for link in links]


def confirmation(tokens, tree, i, text):
    if tree[i].rule != 'N.MEASURE.QUANTIFIED':
        return None
    from .parser import _span_label
    from .probe import Probe

    subject = _span_label(tokens, tree[i].head)
    measure = _span_label(tokens, i)
    return Probe(f'Какое слово называет измеряемый признак предмета «{subject}»?', (measure,), text)
