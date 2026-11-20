from dataclasses import replace
from functools import cache, lru_cache
from importlib.resources import files

from .morphology import from_tag
from .rules import dictionary, known_forms


@cache
def head_lemmas():
    resource = files(__package__).joinpath('lexicon/collective-agreement.tsv')
    return frozenset(resource.read_text(encoding='utf8').splitlines())


@lru_cache(maxsize=2048)
def _singular_verbs(surface, gender):
    variants = []
    for form in dictionary().parse(surface):
        tag = form.tag
        if not form.is_known or tag.POS != 'VERB' or tag.number != 'plur' or tag.mood != 'indc':
            continue
        if tag.person not in (None, '3per'):
            continue
        agreement = {'sing', gender} if tag.tense == 'past' else {'sing', '3per'}
        singular = form.inflect(agreement)
        if singular is not None:
            variants.append((singular.word, form.normal_form, tag))
    return tuple(dict.fromkeys(variants))


def trees(tokens, local, *, budget, chart):
    from .nominal_groups import _extensions, _groups, _restore_indices
    from .parser import NominalBudgetExceeded

    heads = [(i, lemma, form) for i, token in enumerate(tokens)
             for lemma, form in known_forms(token.surface)
             if lemma in head_lemmas() and form.POS == 'NOUN' and form.case == 'nomn' and form.number == 'sing']
    calls = 0
    for head, noun, form in heads:
        for start in range(head + 1, len(tokens)):
            for group in _groups(tokens, start, budget, bare_cases=('gent',), chart=chart):
                if head not in chart.steps[group.noun].genitive_hosts:
                    continue
                members = tuple(dict.fromkeys(from_tag(tag) for lemma, tag in known_forms(tokens[group.noun].surface)
                               if lemma == group.lemma and tag.POS == 'NOUN' and tag.case == 'gent' and tag.number == 'plur'))
                if not members:
                    continue
                kept = (*range(start), *range(group.end, len(tokens)))
                reduced = tuple(tokens[i] for i in kept)
                for verb, token in enumerate(reduced):
                    for surface, lemma, tag in _singular_verbs(token.surface, form.gender):
                        calls += 1
                        if calls > budget:
                            raise NominalBudgetExceeded('COLLECTIVE_AGREEMENT_BUDGET')
                        projected = (*reduced[:verb], replace(token, surface=surface), *reduced[verb + 1:])
                        for tree in local(projected):
                            subject, predicate = tree[head], tree[verb]
                            if (subject.role != 'subject' or subject.head != verb or subject.lemma != noun
                                    or predicate.lemma != lemma or predicate.role != 'predicate'):
                                continue
                            links = {k: _restore_indices(link, kept) for k, link in zip(kept, tree)}
                            links[head] = replace(links[head], rule='S.COLLECTIVE', morphology=from_tag(form))
                            links[kept[verb]] = replace(links[kept[verb]], morphology=from_tag(tag))
                            for variant in _extensions(links, (group,), chart, budget):
                                member = variant[group.noun]
                                if member.head == head:
                                    for morph in members:
                                        yield (*variant[:group.noun], replace(member, morphology=morph),
                                               *variant[group.noun + 1:])


def partitions(trees, tokens, text):
    from .parser import _span_label
    from .probe import Probe

    for i in range(len(tokens)):
        links = [tree[i] for tree in trees]
        if not any(link.rule == 'S.COLLECTIVE' for link in links):
            continue
        heads = {link.head for link in links}
        if len(heads) != 1 or None in heads:
            continue
        head, = heads
        moods = [tree[head].morphology.mood if tree[head].morphology else None for tree in trees]
        if set(moods) != {'indc', 'impr'}:
            continue
        focus = _span_label(tokens, head)
        group = _span_label(tokens, i)
        question = (f'Как здесь употреблено «{focus}»? Если слово сообщает о действии группы, '
                    f'выберите «{group}». Если это просьба или приказ собеседнику, выберите «{focus}».')
        yield Probe(question, (group, focus), text), [group if mood == 'indc' else focus for mood in moods]


def query_features(rows, result):
    animacies = {}
    for member in rows:
        i = member.get('head')
        if i is None or member['role'] != 'genitive_modifier':
            continue
        head = rows[i]
        form = member.get('morphology') or {}
        if (head['role'] == 'subject' and head['lemma'] in head_lemmas()
                and (head.get('morphology') or {}).get('number') == 'sing'
                and form.get('number') == 'plur' and form.get('case') == 'gent'):
            animacies.setdefault(i, set()).add(form.get('animacy'))
    for i, values in animacies.items():
        predicate = rows[i]['head']
        result[predicate] = dict(result[predicate], collective_agreement=True)
        if len(values) == 1:
            result[i] = dict(result[i], member_animacy=next(iter(values)))


def comma_governor(tree, left, right):
    member = tree[left]
    if member.role == 'genitive_modifier' and member.head is not None:
        head = tree[member.head]
        if head.rule == 'S.COLLECTIVE' and head.head == right:
            return right
    return None
