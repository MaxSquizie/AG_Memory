from dataclasses import replace
from itertools import product

from .morphology import PREDICATE_ROLES
from .probe import FocusChoice, Probe
from .rules import known_forms


def site(tokens, tree, i):
    modifier = tree[i]
    if modifier.role != 'adverb' or modifier.scope or i + 1 >= len(tree):
        return None
    prep = i + 1
    if tree[prep].role != 'preposition' or tree[prep].head is None:
        return None
    action = tree[prep].head
    if tree[action].role == 'infinitive' and tree[action].scope in ('phase', 'modal'):
        action = tree[action].head
    if action is None or action <= prep or tree[action].role not in PREDICATE_ROLES:
        return None
    nouns = [j for j in range(prep + 1, action) if tree[j].head == prep and tree[j].role == 'governed']
    if len(nouns) != 1 or modifier.head not in (nouns[0], action):
        return None
    if not any(lemma == modifier.lemma and tag.POS == 'PRCL' for lemma, tag in known_forms(tokens[i].surface)):
        return None
    return nouns[0], action


def readings(tokens, tree, budget):
    from .parser import AnalysisBudgetExceeded

    slots = [(i, targets) for i in range(len(tree)) if (targets := site(tokens, tree, i))]
    if not slots:
        yield tree
        return
    if 2 ** len(slots) > budget:
        raise AnalysisBudgetExceeded('MODIFIER_FOCUS_BUDGET')
    for selected in product(*(targets for _, targets in slots)):
        links = list(tree)
        for (i, (noun, _)), head in zip(slots, selected):
            links[i] = replace(links[i], head=head, rule='ADV.MOD' if head == noun else 'B1')
        yield tuple(links)


def _phrase(tree, head, prep):
    if tree[head].role == 'governed':
        parts = [i for i in range(prep + 1, head) if tree[i].role == 'prep_part' and tree[i].head == prep]
        return (prep, *parts, head)
    end = head + 1
    while end < len(tree) and tree[end].role == 'infinitive' and tree[end].head == end - 1 and tree[end].scope in ('phase', 'modal'):
        end += 1
    return tuple(range(head, end))


def partitions(trees, tokens, text):
    from .parser import _span_label

    for i in range(len(tokens) - 1):
        heads = {tree[i].head for tree in trees}
        if len(heads) < 2 or not all(site(tokens, tree, i) for tree in trees):
            continue
        anchors = {}
        for tree in trees:
            head = tree[i].head
            members = set(_phrase(tree, head, i + 1))
            if head in anchors:
                anchors[head].intersection_update(members)
            else:
                anchors[head] = members
        ordered = sorted((tuple(sorted(members)), head) for head, members in anchors.items())
        labels = {}
        choices = []
        for members, head in ordered:
            if len(members) != members[-1] - members[0] + 1:
                members = (head,)
            labels[head] = _span_label(tokens, members[0], members[-1] + 1)
            choices.append(FocusChoice(i, members))
        if len(set(labels.values())) != len(labels):
            continue
        question = (f'Что уточняет слово «{_span_label(tokens, i)}» в этом контексте? '
                    'Выберите опорные слова обстоятельства или действия.')
        yield Probe(question, tuple(labels.values()), text, tuple(choices)), [labels[t[i].head] for t in trees]
