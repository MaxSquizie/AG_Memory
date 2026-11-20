from dataclasses import replace
from functools import cache

from .determiners import SCOPES
from .morphology import NOMINAL_ROLES, ROLE_CASE, from_tag
from .nominal_groups import _groups, _members
from .prepositions import DASHES
from .rules import dictionary, known_forms
from .standalone_numerals import _SINGULAR
from .utterances import _map


def _partitives(tokens, start, budget):
    from .parser import Link

    if start + 2 >= len(tokens) or tokens[start + 1].surface.casefold() != 'из':
        return
    for head, lemma, case, attributes in _members(tokens, start + 2, 'из', 'gent'):
        for word, tag in known_forms(tokens[head].surface):
            if (word == lemma and tag.case == case and tag.number == 'plur'
                    and not (tag.POS == 'NPRO' and tag.person == '3per' and 'Af-p' not in tag)):
                yield head + 1, head, {**dict(attributes),
                                      head: Link('governed', lemma, start + 1, 'P1', case, morphology=from_tag(tag))}
    for group in _groups(tokens, start + 1, budget):
        if group.case == 'gent' and any(link.role == 'nominal_conjunct' for _, link in group.extra):
            yield group.end, group.noun, {**dict(group.extra),
                                          group.noun: Link('governed', group.lemma, start + 1, 'P1', group.case)}


def _topics(tokens, start, budget):
    yield 0, None
    if not start:
        return
    boundary = tokens[start - 1].surface in DASHES | {',', ':'}
    end = start - int(boundary)
    for group in _groups(tokens[:end], 0, budget, bare_cases=('nomn',)):
        if group.end == end and any(link.role == 'nominal_conjunct' for _, link in group.extra):
            yield start, group


def _member_tags(tokens, members):
    return [tag for i, lemma, case in members for word, tag in known_forms(tokens[i].surface)
            if word == lemma and tag.case == case and tag.POS in ('NPRO', 'NOUN')]


def _agrees(form, tags):
    genders = {tag.gender for tag in tags if tag.gender}
    animacy = {tag.animacy for tag in tags if tag.animacy}
    if form.animacy and len(animacy) == 1 and form.animacy not in animacy:
        return False
    return not genders or not form.gender or form.gender == (next(iter(genders)) if len(genders) == 1 else 'masc')


@cache
def _proxy(case, number, gender):
    citation = 'они' if number == 'plur' else _SINGULAR.get(gender, 'он')
    pronoun = next(p for p in dictionary().parse(citation) if p.tag.POS == 'NPRO' and p.tag.case == 'nomn')
    features = set(filter(None, (case, number)))
    inflected = pronoun.inflect(features)
    return inflected.word if inflected else None


def _substantive(tokens, start, lemma, forms, parse, budget):
    from .parser import Link

    for stop, head, members in _partitives(tokens, start, budget):
        for begin, topic in _topics(tokens, start, budget):
            domain_form = members[head].morphology
            if topic and not (domain_form and domain_form.pos == 'NPRO' and domain_form.person == '3per'):
                continue
            if topic:
                domain = [(topic.noun, topic.lemma, topic.case),
                          *((j, link.lemma, link.case) for j, link in topic.extra if link.role == 'nominal_conjunct')]
            else:
                domain = [(head, members[head].lemma, 'gent'),
                          *((j, link.lemma, link.case) for j, link in members.items() if link.role == 'nominal_conjunct')]
            tags = _member_tags(tokens, domain)
            indices = (*range(begin, start + 1), *range(stop, len(tokens)))
            for form in forms:
                proxy = _proxy(form.case, form.number, form.gender)
                if proxy is None or not _agrees(form, tags):
                    continue
                words = tuple(replace(tokens[i], surface=proxy) if i == start else tokens[i] for i in indices)
                for tree in parse(words):
                    links = _map(tree, indices)
                    host = links[start]
                    if host.role not in NOMINAL_ROLES or (host.case or ROLE_CASE.get(host.role)) != form.case:
                        continue
                    links[start] = replace(host, lemma=lemma, rule='NP.PARTITIVE', morphology=from_tag(form),
                                           scope=SCOPES[lemma])
                    links[start + 1] = Link('preposition', 'из', start, 'NP.PARTITIVE.DOMAIN')
                    links.update(members)
                    if topic:
                        links.update(topic.extra)
                        links[topic.noun] = Link('topic', topic.lemma, start, 'NP.TOPIC', 'nomn')
                        links[head] = replace(links[head], antecedent=topic.noun)
                        if topic.end < start:
                            links[topic.end] = Link('punctuation', tokens[topic.end].surface, start, 'NP.TOPIC.BOUND')
                    yield tuple(links[i] for i in range(len(tokens)))


def _floated(tokens, start, lemma, form, parse):
    from .parser import Link

    if start == 0 or form.case != 'nomn' or form.number != 'sing':
        return
    indices = tuple(i for i in range(len(tokens)) if i != start)
    for tree in parse(tuple(tokens[i] for i in indices)):
        links = _map(tree, indices)
        for i, subject in links.items():
            if subject.role != 'subject' or i >= start:
                continue
            siblings = [j for j, link in links.items() if link.role == 'nominal_conjunct' and link.head == i]
            if not siblings and not (subject.morphology and subject.morphology.number == 'plur'):
                continue
            if any(links[j].role == 'coordinator' and links[j].lemma != 'и' for j in links
                   if links[j].head in {i, *siblings}):
                continue
            tags = _member_tags(tokens, [(j, links[j].lemma, 'nomn') for j in (i, *siblings)])
            if not _agrees(form, tags):
                continue
            candidate = dict(links)
            candidate[start] = Link('attribute', lemma, i, 'NP.DISTR', scope='universal', morphology=from_tag(form))
            yield tuple(candidate[j] for j in range(len(tokens)))


def _counted_argument(tokens, start, parse, quantities):
    from .parser import Link

    if not any(expr.kind in ('cardinal', 'digit', 'collective') and 'accs' in expr.cases
               for expr in quantities):
        return
    indices = tuple(i for i in range(len(tokens)) if i != start)
    for tree in parse(tuple(tokens[i] for i in indices)):
        links = _map(tree, indices)
        numeral = links[start + 1]
        if numeral.role != 'numeral':
            continue
        argument = links[numeral.head]
        if argument.role == 'subject':
            links[start] = Link('quantity_modifier', 'по', numeral.head, 'NUM.DISTR', scope='distribution')
        elif argument.role == 'object' and argument.case == 'accs':
            prep = next(tag for _, tag in known_forms(tokens[start].surface) if tag.POS == 'PREP')
            links[start] = Link('preposition', 'по', argument.head, 'P2', morphology=from_tag(prep))
            links[numeral.head] = replace(argument, role='governed', rule='P1', head=start)
        else:
            continue
        yield tuple(links[j] for j in range(len(tokens)))


def _subgroups(tokens, start, parse, budget, quantities):
    from .parser import Link
    from .quantity_groups import _groups as counted_groups

    for expression in quantities:
        if expression.kind != 'collective' or next(counted_groups(tokens, start + 1, expression, budget), None):
            continue
        parts = expression.parts_for('accs')
        if len(parts) != 1:
            continue
        indices = tuple(i for i in range(len(tokens)) if i < start or i >= expression.end)
        for tree in parse(tuple(tokens[i] for i in indices)):
            links = _map(tree, indices)
            predicates = [i for i, link in links.items() if link.role == 'predicate' and link.head is None
                          and link.morphology and link.morphology.pos == 'VERB' and link.morphology.number == 'plur'
                          and link.morphology.transitivity == 'intr']
            if len(predicates) != 1 or any(link.role.startswith('clause_') for link in tree):
                continue
            links[start] = Link('preposition', 'по', start + 1, 'NUM.SUBGROUP')
            lemma, morphology = parts[0]
            links[start + 1] = Link('quantity_modifier', lemma, predicates[0], 'NUM.SUBGROUP', 'accs',
                                    quantity_kind=expression.kind, quantity=expression.value, morphology=morphology)
            yield tuple(links[i] for i in range(len(tokens)))


def trees(tokens, parse, budget, prefix=None):
    from .distribution_prefix import DistributionPrefix

    if prefix is None:
        prefix = DistributionPrefix.from_tokens(tokens)
    for i, forms, quantities in prefix.sites(tokens):
        if tokens[i].surface.casefold() == 'по' and quantities:
            yield from _counted_argument(tokens, i, parse, quantities)
            yield from _subgroups(tokens, i, parse, budget, quantities)
        for lemma in dict.fromkeys(word for word, _ in forms):
            tags = [tag for word, tag in forms if word == lemma]
            yield from _substantive(tokens, i, lemma, tags, parse, budget)
            if lemma == 'каждый' and not (i + 1 < len(tokens) and tokens[i + 1].surface.casefold() == 'из'):
                for form in tags:
                    yield from _floated(tokens, i, lemma, form, parse)


def partitions(analyses, tokens, text):
    from .probe import Probe
    from .parser import _span_label

    for i, token in enumerate(tokens[:-1]):
        uses = [tree[i] for tree in analyses]
        if not any(link.role == 'preposition' or link.rule == 'NUM.DISTR' for link in uses):
            continue
        if not any(link.morphology and link.morphology.pos == 'NOUN' for link in uses):
            continue
        amounts = [tree[i + 1] for tree in analyses]
        if not all(link.role == 'numeral' and link.head == amounts[0].head for link in amounts):
            continue
        end = amounts[0].head + 1
        if end <= i + 1:
            continue
        phrase, word = _span_label(tokens, i, end), _span_label(tokens, i)
        choices = [phrase if link.role == 'preposition' or link.rule == 'NUM.DISTR' else word for link in uses]
        yield Probe(f'Образует ли «{word}» сочетание с количеством? Выберите всё сочетание, '
                    'если да, или само слово, если оно называет отдельного участника.', (phrase, word), text), choices


def _appositive_hosts(tokens, budget):
    from .numerals import expressions
    from .quantity_groups import _groups as counted_groups

    hosts = set()
    for i in range(len(tokens)):
        for expression in expressions(tokens, i):
            if expression.kind not in ('both', 'collective', 'cardinal'):
                continue
            hosts.add(expression.end - 1)
            hosts.update(group.noun for group in counted_groups(tokens, i, expression, budget))
    return sorted(hosts)


def enumerations(tokens, parse, budget):
    from .parser import Link

    for host in _appositive_hosts(tokens, budget):
        opening = host + 1
        if opening >= len(tokens):
            continue
        mark = tokens[opening].surface
        bounded = mark in DASHES | {','}
        start = opening + int(bounded)
        subset = tuple(t.surface.casefold() for t in tokens[start:start + 3]) == ('в', 'том', 'числе')
        first = start + (3 if subset else 0)
        for group in _groups(tokens, first, budget, bare_cases=('nomn', 'gent', 'datv', 'accs', 'ablt', 'loct')):
            if group.end >= len(tokens):
                continue
            closing = tokens[group.end].surface in (DASHES if mark in DASHES else {','})
            if bounded != closing:
                continue
            if not bounded and not subset and not any(part.role == 'nominal_conjunct' for _, part in group.extra):
                continue
            if any(link.role == 'coordinator' and link.lemma != 'и' for _, link in group.extra):
                continue
            kept = (*range(opening), *range(group.end + int(closing), len(tokens)))
            for tree in parse(tuple(tokens[i] for i in kept)):
                links = _map(tree, kept)
                noun = links[host]
                case = noun.case or ROLE_CASE.get(noun.role)
                if case != group.case or not (noun.quantity or any(link.head == host and link.role == 'numeral'
                                                                  for link in links.values())):
                    continue
                links.update(group.extra)
                links[group.noun] = Link('apposition', group.lemma, host, 'NP.SUBSET' if subset else 'NP.ENUM', case)
                if bounded:
                    for i in (opening, group.end):
                        links[i] = Link('punctuation', tokens[i].surface, group.noun, 'NP.ENUM.BOUND')
                for i in range(start, first):
                    links[i] = Link('coordinator' if i == start else 'coordinator_part', tokens[i].surface.casefold(),
                                    group.noun if i == start else start, 'NP.SUBSET.MARK',
                                    scope='addition' if i == start else None)
                yield tuple(links[i] for i in range(len(tokens)))


def cardinality_violation(tree):
    for i, link in enumerate(tree):
        if link.rule not in ('NP.ENUM', 'NP.SUBSET'):
            continue
        amount = next((part for part in tree if part.role == 'numeral' and part.head == link.head), tree[link.head])
        if (amount.quantity_kind not in ('both', 'collective', 'cardinal') or
                amount.quantity_modifier not in (None, 'exact') or not (amount.quantity or '').isdigit()):
            continue
        count = 1 + sum(part.role == 'nominal_conjunct' and part.head == i for part in tree)
        if count > int(amount.quantity) or link.rule == 'NP.ENUM' and count != int(amount.quantity):
            return 'GROUP_CARDINALITY_MISMATCH'
    return None


def quantified_attachment(analyses, tokens, hosts, prep, phrase, context, source):
    from .parser import _span_label
    from .probe import Probe

    spans = {}
    for tree, head in zip(analyses, hosts):
        if head is None or tree[head].rule == 'N.MEASURE':
            return None
        children = [[] for _ in tree]
        for j, link in enumerate(tree[:prep]):
            if link.head is not None and link.role in ('numeral', 'numeral_part', 'quantity_modifier', 'attribute'):
                children[link.head].append(j)
        included = [head]
        for j in included:
            included.extend(children[j])
        left, right = min(included), max(included)
        if len(included) != right - left + 1 or not any(tree[j].role == 'numeral' for j in included):
            left = right = head
        if spans.setdefault(head, (left, right)) != (left, right):
            return None
    if all(left == right for left, right in spans.values()):
        return None
    labels = {head: _span_label(tokens, left, right + 1) for head, (left, right) in sorted(spans.items())}
    if len(set(labels.values())) != len(labels):
        return None
    if any(label not in context for label in labels.values()):
        context = source
    question = f'К какому слову или сочетанию по смыслу относится «{phrase}»?'
    return Probe(question, tuple(labels.values()), context), [labels[head] for head in hosts]
