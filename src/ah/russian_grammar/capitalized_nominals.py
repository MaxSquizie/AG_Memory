from dataclasses import replace
from itertools import product

from .probe import Probe
from .rules import known_forms, name_type


def _first_attribute(tokens, tree, head):
    i = head
    while i:
        link = tree[i - 1]
        if link.role == 'punctuation' and tokens[i - 1].surface == ',':
            i -= 1
            continue
        if link.role != 'attribute' or link.head != head or not tokens[i - 1].surface.istitle():
            break
        i -= 1
    return i


def readings(tokens, tree, budget):
    from .parser import AnalysisBudgetExceeded

    positions = []
    for i, link in enumerate(tree):
        if not i or link.scope or link.rule.startswith('OPAQUE.') or not tokens[i].surface.istitle():
            continue
        form = link.morphology
        if not form or form.pos != 'NOUN' or link.role not in ('subject', 'governed'):
            continue
        if tokens[i - 1].surface in {'.', '!', '?', ':', '«', '"'}:
            continue
        names = any(name_type(tag) or 'Geox' in tag or 'Orgn' in tag or 'Trad' in tag
                    for lemma, tag in known_forms(tokens[i].surface) if lemma == link.lemma)
        first = _first_attribute(tokens, tree, i)
        if link.role == 'subject' and form.animacy == 'inan' and not names and first == i:
            positions.append((i, 'NAME.MENTION'))
        elif link.role == 'governed' and names and 0 < first < i and tree[first].role == 'attribute':
            positions.append((i, 'NAME.GROUP'))
    if 2 ** len(positions) > budget:
        raise AnalysisBudgetExceeded('NAME_READING_BUDGET')
    for choices in product((False, True), repeat=len(positions)):
        if not any(choices):
            yield tree
            continue
        result = list(tree)
        for (i, rule), selected in zip(positions, choices):
            if selected:
                result[i] = replace(tree[i], rule=rule, scope='proper_name',
                                    morphology=replace(tree[i].morphology, animacy=None))
        yield tuple(result)


def partitions(trees, tokens, text):
    from .parser import _span_label

    for i in range(len(tokens)):
        links = [tree[i] for tree in trees]
        roles = {link.role for link in links}
        if roles == {'attribute', 'adverb'}:
            heads = [t[i].head for t in trees]
            if None not in heads and len(set(heads)) > 1:
                options = {}
                for head in sorted(set(heads)):
                    relevant = [t for t in trees if t[i].head == head]
                    members = {head}
                    for j in range(len(tokens)):
                        if all(t[j].head == head and t[j].role in {'apposition', 'name_part', 'auxiliary', 'copula'}
                               for t in relevant):
                            members.add(j)
                    left, right = head, head + 1
                    while left - 1 in members:
                        left -= 1
                    while right in members:
                        right += 1
                    options[head] = _span_label(tokens, left, right)
                label = _span_label(tokens, i)
                question = f'К каким словам относится «{label}» в этом предложении?'
                noun_heads = {l.head for l in links if l.role == 'attribute'}
                action_heads = {l.head for l in links if l.role == 'adverb'}
                if len(noun_heads) == len(action_heads) == 1 and noun_heads != action_heads:
                    noun = options[next(iter(noun_heads))]
                    action = options[next(iter(action_heads))]
                    question += (f' Если это признак предмета, выберите «{noun}». '
                                 f'Если уточняется действие, выберите «{action}».')
                yield Probe(question, tuple(options.values()), text), [options[j] for j in heads]
        if len(roles) != 1:
            continue
        rules = {t[i].rule for t in trees}
        special = rules.intersection({'NAME.MENTION', 'NAME.GROUP'})
        if len(special) != 1 or len(rules) == 1:
            continue
        rule = next(iter(special))
        reference = next(t for t in trees if t[i].rule == rule)
        last = _span_label(tokens, i)
        if rule == 'NAME.GROUP':
            first = _first_attribute(tokens, reference, i)
            label = _span_label(tokens, first, i + 1).replace(' ,', ',')
            other = last
            question = 'Какие слова здесь образуют единое собственное имя или название?'
        else:
            label = last
            other = 'нарицательное существительное'
            question = (f'Как употреблено «{last}»? Если это собственное имя или название, '
                        f'выберите «{last}».')
        yield Probe(question, (label, other), text), [label if t[i].rule == rule else other for t in trees]
