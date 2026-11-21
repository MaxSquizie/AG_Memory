from dataclasses import replace
from functools import lru_cache
from itertools import chain

from . import clauses, degree_clauses, personal_correlatives
from .morphology import ROLE_CASE, from_tag
from .nominal_groups import _groups
from .prepositions import FORMS, PREFIXES
from .rules import attested_name_parts, dictionary, known_forms


INDIRECT = frozenset('знать узнать помнить вспомнить понимать понять спросить спрашивать выяснить выяснять видеть увидеть сообщить сказать рассказать объяснить интересоваться'.split())
INDICES = ('head', 'controller', 'antecedent', 'coord_head', 'shared_agent', 'shared_object')


def _move(link, indices):
    return replace(link, **{key: indices[value] for key in INDICES if (value := getattr(link, key)) is not None})


def _anchors(tree, end):
    current = end - 1
    while current is not None:
        yield current
        current = tree[current].head


def _projections(token, host, relative):
    form = host.morphology
    case = host.case or ROLE_CASE.get(host.role) or (form.case if form else None)
    for noun in dictionary().parse(token.surface):
        if noun.normal_form != host.lemma or noun.tag.POS not in ('NOUN', 'NPRO') or case and noun.tag.case != case:
            continue
        if form and form.number and form.number != noun.tag.number:
            continue
        for lemma, tag in known_forms(relative.surface):
            if lemma != 'который' or tag.number != noun.tag.number:
                continue
            if tag.gender and tag.gender != noun.tag.gender or tag.animacy and tag.animacy != noun.tag.animacy:
                continue
            projected = noun.inflect({tag.case, tag.number})
            if projected:
                yield projected.word, tag


def _nominal_caption(part, budget):
    from .parser import Link

    for title in _groups(part, 0, budget, bare_cases=('nomn',)):
        if title.end >= len(part):
            continue
        for dependent in _groups(part, title.end, budget, bare_cases=('gent',)):
            if dependent.end != len(part):
                continue
            tree = dict((*title.extra, *dependent.extra))
            tree[title.noun] = Link('predicate', title.lemma, None, 'NOM.EXIST', 'nomn')
            tree[dependent.noun] = Link('genitive_modifier', dependent.lemma, title.noun, 'N.GEN', 'gent')
            yield tuple(tree[i] for i in range(len(part)))


def _relative_child(part, subordinate):
    from .parser import Link

    yield from subordinate(part)
    extras = {}
    for i in range(1, len(part)):
        token, previous = part[i], part[i - 1]
        if (token.surface.isalpha() and token.surface[0].isupper() and attested_name_parts(token.surface)
              and previous.surface[0].isupper() and any('Name' in tag for _, tag in known_forms(previous.surface))):
            extras[i] = 'name_part'
    if not extras:
        return
    kept = tuple(i for i in range(len(part)) if i not in extras)
    for tree in subordinate(tuple(part[i] for i in kept)):
        result = {i: _move(link, kept) for i, link in zip(kept, tree)}
        for i, kind in extras.items():
            host = result.get(i - 1)
            if not host:
                break
            if kind == 'name_part' and host.role in ('subject', 'predicate', 'object', 'recipient', 'governed'):
                form = host.morphology
                case = host.case or (form.case if form else None) or ROLE_CASE.get(host.role)
                if case is None and host.rule == 'V2' and not any(link.role == 'copula' for link in tree):
                    case = 'nomn'
                matches = {(lemma, tag) for lemma, tag in attested_name_parts(part[i].surface)
                           if tag.case == case and tag.number == (form.number if form else 'sing')
                           and (not form or not form.gender or tag.gender == form.gender)}
                if len(matches) != 1:
                    break
                lemma, tag = matches.pop()
                result[i] = Link('name_part', lemma, i - 1, 'NAME', case=case, morphology=from_tag(tag))
            else:
                break
        else:
            yield tuple(result[i] for i in range(len(part)))


def trees(tokens, local, *, budget, spatial_prefix=None, nominal_fragment=False):
    from .parser import AnalysisBudgetExceeded, Link

    remaining = budget

    def spend():
        nonlocal remaining
        remaining -= 1
        if remaining < 0:
            raise AnalysisBudgetExceeded('RELATIVE_BUDGET')

    @lru_cache(maxsize=budget)
    def subordinate(part, allow_inference):
        spend()
        result = []
        for tree in parse(part, allow_inference):
            if len(result) >= budget:
                raise AnalysisBudgetExceeded('RELATIVE_BUDGET')
            result.append(tree)
        return tuple(result)

    def parse(part, allow_inference):
        found = False
        for tree in clauses.trees(part, local, budget=budget, spatial_prefix=spatial_prefix):
            found = True
            yield tree
        explicit = any(token.surface == ',' for token in part)
        if explicit:
            for tree in attachments(part, inferred=False):
                found = True
                yield tree
        if allow_inference and (not explicit or not found):
            yield from attachments(part, inferred=True)

    def attachments(part, inferred, *, fragment=False):
        def component(tokens):
            return subordinate(tokens, inferred)

        words = [t.surface.casefold() for t in part]
        commas = [i for i, w in enumerate(words) if w == ',']
        candidates = {i for i, word in enumerate(words) if i and any(lemma in {
            'который', 'кто', 'что', 'где', 'куда', 'когда', 'откуда', 'почему', 'как'
        } for lemma, _ in known_forms(word))}
        amounts = set()
        has_counter = False
        for i, word in enumerate(words):
            lemmas = {lemma for lemma, tag in known_forms(word) if tag.POS == 'NUMR'}
            if has_counter and 'сколько' in lemmas:
                amounts.add(i)
            has_counter |= 'столько' in lemmas
        candidates.update(amounts)
        if not candidates:
            return
        for begin in range(1, len(words)):
            if words[begin] == ',':
                continue
            start = begin - (words[begin - 1] == ',')
            if not inferred and start == begin:
                continue
            marker = begin
            for stop in range(begin + 1, len(words)):
                phrase = " ".join(words[begin:stop])
                if phrase in FORMS:
                    marker = stop
                if phrase not in PREFIXES:
                    break
            if start == 0 or marker == len(words):
                continue
            possessor = False
            if marker not in candidates and marker == begin:
                for next_word in range(begin + 1, len(part)):
                    if any(lemma == 'который' and tag.case == 'gent' for lemma, tag in known_forms(words[next_word])):
                        possessor = any(group.end == next_word for group in _groups(
                            part[:next_word], begin, budget, bare_cases=('nomn', 'gent', 'datv', 'accs', 'ablt', 'loct')))
                        if possessor:
                            marker = next_word
                        break
                    if words[next_word] == ',':
                        break
            if marker not in candidates:
                continue
            lemmas = {lemma for lemma, _ in known_forms(words[marker])}
            spatial = clauses.relative_role(words[marker])
            temporal = words[marker] == 'когда' and 'тогда' in words[:start]
            if (spatial or temporal) and marker != begin:
                continue
            relative = 'который' in lemmas
            amount = marker == begin and marker in amounts
            if not relative and not amount and not lemmas.intersection({'кто', 'что', 'где', 'куда', 'когда', 'откуда', 'почему', 'как'}):
                continue
            personal = 'кто' in lemmas and any(personal_correlatives.readings(w) for w in words[:start])
            indirect = not relative and any(lemma in INDIRECT for w in words[:start] for lemma, _ in known_forms(w))
            if not (relative or personal or indirect or spatial or temporal or amount):
                continue
            stops = [i for i in commas if i > marker]
            if inferred and not stops:
                resumed_verbs = [i for i in range(marker + 1, len(part))
                                 if any(tag.POS == 'VERB' for _, tag in known_forms(words[i]))]
                if resumed_verbs:
                    stops = range(marker + 1, resumed_verbs[-1] + 1)
            for end in (*stops, len(part)):
                if (spatial or amount) and end == len(part):
                    continue
                resume = end + (end < len(part) and words[end] == ',')
                outside = tuple(range(start)) + tuple(range(resume, len(part)))
                inside = tuple(range(begin, end))
                inner = tuple(part[i] for i in inside)
                matrix = tuple(part[i] for i in outside)
                if fragment:
                    if not personal or len(matrix) != 1 or end != len(part):
                        continue
                    matrices = (((head,), 0, None) for head in personal_correlatives.nominal_heads(matrix[0]))
                else:
                    captions = _nominal_caption(matrix, budget) if relative and end == len(part) else ()
                    ordinary = ((tree, None, None) for tree in chain(component(matrix), captions)) if relative or indirect or spatial or temporal or amount else ()
                    personal_matrices = personal_correlatives.matrices(matrix, start, component) if personal else ()
                    matrices = chain(ordinary, personal_matrices)
                for outer, person, addressee_governor in matrices:
                    fixed_host = person if person is not None else addressee_governor
                    for host in ((fixed_host,) if fixed_host is not None else _anchors(outer, start)):
                        if host >= start:
                            continue
                        if amount:
                            for joined in degree_clauses.centered_quantity(part, outside, outer, host, inside, component):
                                spend()
                                yield joined
                            continue
                        if spatial or temporal and end < len(part):
                            from .spatial_clauses import centered

                            for joined in centered(part, outside, outer, host, inside, component, spatial_prefix,
                                                   budget, temporal=temporal):
                                spend()
                                yield joined
                            if spatial or not indirect:
                                continue
                        if person is not None:
                            variants = personal_correlatives.relative_forms(words[marker], outer, person)
                        elif relative:
                            variants = _projections(part[outside[host]], outer[host], part[marker])
                        elif addressee_governor is not None or (outer[host].lemma in INDIRECT
                                and outer[host].role in ('predicate', 'infinitive')):
                            if personal and fixed_host is None and personal_correlatives.saturated_content(
                                    outer, matrix, start, host):
                                continue
                            variants = [(words[marker], None)]
                        else:
                            continue
                        for surface, tag in variants:
                            offset = marker - begin
                            projected = (*inner[:offset], replace(inner[offset], surface=surface), *inner[offset + 1:])
                            children = _relative_child(projected, component) if possessor else component(projected)
                            for child in children:
                                reference = child[offset]
                                if possessor and (tag.case != 'gent' or reference.role != 'genitive_modifier'):
                                    continue
                                expected = 'кто' if person is not None else outer[host].lemma
                                if person is not None and surface != words[marker]:
                                    if reference.role != 'subject':
                                        continue
                                    expected = surface
                                if tag and (reference.lemma != expected or
                                            (reference.case or ROLE_CASE.get(reference.role)) != tag.case):
                                    continue
                                if not tag and (reference.lemma not in lemmas or reference.role not in
                                                ('subject', 'object', 'adverb', 'recipient', 'oblique', 'governed')):
                                    continue
                                if not tag and reference.role == 'adverb' and reference.lemma in ('что', 'кто'):
                                    continue
                                root = next((i for i, link in enumerate(child) if link.head is None and link.role == 'predicate'), None)
                                if root is None:
                                    continue
                                spend()
                                merged = [None] * len(part)
                                for i, link in zip(outside, outer):
                                    merged[i] = _move(link, outside)
                                for i, link in zip(inside, child):
                                    merged[i] = _move(link, inside)
                                index = inside[root]
                                scope = merged[index].scope
                                if person is not None:
                                    scope = 'restrictive' if not scope else 'restrictive_' + scope
                                elif not tag:
                                    scope = scope or 'embedded'
                                merged[index] = replace(merged[index], head=outside[host],
                                    role='clause_relative' if tag else 'clause_complement',
                                    rule='CL.REL' if tag else 'CL.COMP',
                                    scope=scope)
                                if tag:
                                    merged[marker] = replace(merged[marker], lemma='кто' if person is not None else 'который',
                                        antecedent=outside[host],
                                        morphology=from_tag(tag), case=tag.case, rule='CL.NOMREF')
                                else:
                                    merged[marker] = replace(merged[marker], rule='CL.WH')
                                for i in (start, end):
                                    if i < len(part) and words[i] == ',':
                                        merged[i] = Link('punctuation', ',', index, 'CL.PUNCT')
                                yield tuple(merged)

    if nominal_fragment:
        yield from attachments(tokens, inferred=True, fragment=True)
    else:
        yield from parse(tokens, True)
