from dataclasses import dataclass, replace
from collections import defaultdict
from itertools import chain, product
from math import prod

from .morphology import Morphology, from_tag
from .nominal_chart import agrees
from .nominal_groups import _groups
from .parser import Link
from .prepositions import DASHES
from .rules import dictionary, known_forms


def _nominals(word, case):
    return [(lemma, tag) for lemma, tag in known_forms(word)
            if tag.POS in ('NOUN', 'NPRO') and tag.case == case]


def _span(tokens, start, stop, case, budget):
    if start < stop:
        for group in _groups(tokens[:stop], start, budget, bare_cases=(case,)):
            if group.end == stop:
                yield group


def _place(tree, group, role, head, rule):
    tree[group.noun] = Link(role, group.lemma, head, rule, group.case)
    for index, link in group.extra:
        tree[index] = link


def _negative(tokens, words, budget):
    if words.count('нет') != 1 or words.count('у') != 1:
        return
    verb, prep = words.index('нет'), words.index('у')
    if prep + 1 >= len(tokens):
        return
    for owner in _groups(tokens, prep + 1, budget, bare_cases=('gent',)):
        occupied = {verb, *range(prep, owner.end)}
        remaining = sorted(set(range(len(tokens))) - occupied)
        if not remaining or remaining[-1] - remaining[0] + 1 != len(remaining):
            continue
        for entity in _span(tokens, remaining[0], remaining[-1] + 1, 'gent', budget):
            tree = [None] * len(tokens)
            tree[verb] = Link('predicate', 'нет', None, 'NEG.EXIST', scope='negated')
            tree[prep] = Link('preposition', 'у', verb, 'NEG.EXIST.PREP')
            _place(tree, owner, 'governed', prep, 'NEG.EXIST.OWNER')
            _place(tree, entity, 'object', verb, 'NEG.EXIST.ENTITY')
            yield tuple(tree)


def one_member(tokens, standalone, budget):
    words = tuple(token.surface.casefold() for token in tokens)
    yield from _negative(tokens, words, budget)
    if standalone and len(words) == 1:
        for lemma, tag in _nominals(words[0], 'nomn'):
            if tag.POS == 'NOUN' and 'Name' not in tag and 'Surn' not in tag:
                yield (Link('predicate', lemma, None, 'NOM.EXIST', 'nomn', morphology=from_tag(tag)),)


def _agreement(form, subject):
    return replace(form, number=subject.number,
                   gender=subject.gender if form.tense == 'past' and subject.number == 'sing' else None,
                   person=None if form.tense == 'past' else subject.person or '3per')


def _noun_paradigm(source, lemma):
    for parse in dictionary().parse(source):
        if parse.is_known and parse.normal_form == lemma and parse.tag.POS == 'NOUN':
            yield from parse.lexeme


@dataclass(frozen=True, kw_only=True)
class NounGap(Link):
    noun_form: Morphology


def _attribute_gaps(tokens, start, stop, sources, root, role, case, budget):
    from .parser import AnalysisBudgetExceeded

    modifiers = []
    for token in tokens[start:stop]:
        forms = [(lemma, tag) for lemma, tag in known_forms(token.surface)
                 if tag.POS == 'ADJF' and tag.case == case and 'Apro' not in tag and 'Anum' not in tag]
        if not forms:
            return
        modifiers.append(forms)
    for source, noun in sources:
        for variant in _noun_paradigm(tokens[source].surface, noun):
            if variant.tag.case != case:
                continue
            options = [tuple(dict.fromkeys((lemma, from_tag(tag)) for lemma, tag in forms if agrees(tag, variant.tag)))
                       for forms in modifiers]
            if prod(map(len, options)) > budget:
                raise AnalysisBudgetExceeded('NOMINAL_ELLIPSIS_BUDGET')
            for first, *rest in product(*options):
                gap = NounGap(role, first[0], root, 'GAP.ATTR', case, morphology=first[1],
                              noun_form=from_tag(variant.tag), ellipsis_source=source)
                yield ((start, gap), *((i, Link('attribute', lemma, start, 'A1', morphology=form))
                                       for i, (lemma, form) in enumerate(rest, start + 1)))


def _objects(tokens, start, stop, sources, root, budget, explicit):
    from .numerals import expressions
    from .quantity_groups import _groups as counted_groups

    for obj in _span(tokens, start, stop, 'accs', budget) if explicit else ():
        yield ((obj.noun, Link('object', obj.lemma, root, 'GAP.OBJ', obj.case)), *obj.extra)
    for expr in expressions(tokens[:stop], start):
        for group in counted_groups(tokens[:stop], start, expr, budget) if explicit else ():
            if group.case == 'accs' and group.noun + 1 == stop:
                yield ((group.noun, Link('object', group.lemma, root, 'GAP.OBJ', 'accs',
                                         morphology=group.morphology)), *group.links)
        if expr.end != stop or expr.kind not in ('cardinal', 'collective', 'both'):
            continue
        for source, lemma in sources:
            for variant in _noun_paradigm(tokens[source].surface, lemma):
                if not expr.compatible('accs', variant.tag, lemma):
                    continue
                parts = expr.parts_for('accs', variant.tag)
                first = NounGap('object', parts[0][0], root, 'GAP.COUNT', 'accs', ellipsis_source=source,
                                   quantity=expr.value, quantity_kind=expr.kind, quantity_modifier=expr.modifier,
                                   morphology=parts[0][1], noun_form=from_tag(variant.tag))
                yield ((start, first), *((i, Link('numeral_part', word, start, 'NUM.PART', morphology=morph))
                                         for i, (word, morph) in enumerate(parts[1:], start + 1)))
                break


def _parallel_nouns(prefix, arguments):
    result = defaultdict(list)
    for index, role in arguments:
        argument = prefix[index]
        if role != 'object' and argument.rule not in ('V.GOV', 'GAP.ATTR'):
            continue
        case = argument.case or ('accs' if role == 'object' else None)
        if case is None:
            continue
        members = [index]
        for member in members:
            members.extend(i for i, link in enumerate(prefix)
                           if link and link.head == member and link.role == 'nominal_conjunct')
            source = prefix[member].ellipsis_source if prefix[member].rule in ('GAP.ATTR', 'GAP.COUNT') else member
            result[role, case].append((source, prefix[source].lemma))
    return result


def _explicit_role(verb, role, case):
    from .case_arguments import _lexicon

    if role == 'object':
        return role if verb.morphology.transitivity == 'tran' and case == 'accs' else None
    cases, roles = _lexicon()
    if case in cases.get(verb.lemma, ()):
        return roles.get((verb.lemma, case), 'oblique')
    return None


def gapped_leaves(tokens, start, stop, prefix, host, budget, leaves):
    dashes = [i for i in range(start, stop) if tokens[i].surface in DASHES]
    anchor = prefix[host]
    source_verb = anchor.ellipsis_source if anchor.rule in ('GAP', 'GAP.REMNANT') else host
    verb = prefix[source_verb]
    form = verb.morphology
    if len(dashes) > 1 or not form or form.pos != 'VERB' or form.mood != 'indc' or verb.scope or anchor.scope:
        return
    arguments = [(i, link.role) for i, link in enumerate(prefix) if link and link.head == host
                 and link.role not in ('clause_conjunct', 'clause_marker', 'punctuation')]
    parallel = _parallel_nouns(prefix, arguments)
    if not parallel or anchor.rule != 'GAP.REMNANT' and not any(role == 'subject' for _, role in arguments):
        return
    simple = sorted(role for _, role in arguments) == ['object', 'subject']
    objects = [source for (role, _), sources in parallel.items() if role == 'object' for source in sources]
    argument_roles = {role for _, role in arguments if role != 'subject'}
    single_slot = len(parallel) == 1 and argument_roles == {role for role, _ in parallel}
    if not dashes and any(tag.POS == 'ADJF' for _, tag in known_forms(tokens[stop - 1].surface)):
        for end in range(start + 2, stop):
            if not any(tag.POS == 'VERB' for _, tag in known_forms(tokens[end - 1].surface)):
                continue
            for body, root in leaves(start, end):
                predicate = body[root - start]
                if (root != end - 1 or not predicate.morphology or predicate.morphology.pos != 'VERB'
                        or not any(link.role == 'subject' and link.head == root for link in body)):
                    continue
                for (role, case), sources in parallel.items():
                    target = _explicit_role(predicate, role, case)
                    if not target or any(link.role == target and link.head == root for link in body):
                        continue
                    for obj in _attribute_gaps(tokens, end, stop, sources, root, target, case, budget):
                        yield (*body, *(link for _, link in obj)), root
    for subject in _groups(tokens[:stop], start, budget, bare_cases=('nomn',)):
        split = subject.end
        if split >= stop or dashes and split != dashes[0]:
            continue
        comma = tokens[split].surface == ','
        right = split + bool(dashes or comma)
        if right >= stop:
            continue
        root = split if dashes else subject.noun
        attributes = (obj for (role, case), sources in parallel.items() if single_slot
                      for obj in _attribute_gaps(tokens, right, stop, sources, root, role, case, budget))
        gaps = _objects(tokens, right, stop, objects, root, budget, simple) if objects else ()
        governed = (((obj.noun, Link(role, obj.lemma, root, 'V.GOV', case)), *obj.extra)
                     for role, case in parallel if single_slot and role != 'object'
                     for obj in _span(tokens, right, stop, case, budget))
        for obj in chain(attributes, gaps, governed):
            for lemma, tag in _nominals(tokens[subject.noun].surface, 'nomn'):
                if lemma != subject.lemma or form.tense != 'past' and tag.POS == 'NPRO' and not tag.person:
                    continue
                tree = [None] * stop
                _place(tree, subject, 'subject', root, 'GAP.SUBJ')
                if dashes:
                    tree[root] = Link('predicate', verb.lemma, None, 'GAP', morphology=_agreement(form, tag),
                                      ellipsis_source=source_verb)
                else:
                    tree[root] = Link('predicate', subject.lemma, None, 'GAP.REMNANT', morphology=from_tag(tag),
                                      ellipsis_source=source_verb)
                if comma:
                    tree[split] = Link('punctuation', ',', root, 'CL.PUNCT')
                for index, link in obj:
                    tree[index] = link
                yield tuple(tree[start:]), root


def _personal_count(head, dependents):
    return (head.morphology and head.morphology.pos in ('NOUN', 'NPRO') and head.morphology.animacy == 'anim'
            and any(link.role == 'subject' and link.quantity_kind == 'cardinal' for link in dependents))


def unsupported_count(tree, i):
    link = tree[i]
    if link.role != 'clause_conjunct' or link.head is None or not _personal_count(link, (l for l in tree[i + 1:] if l.head == i)):
        return False
    predicates = {link.head}
    predicates.update(j for j, l in enumerate(tree) if l.head == link.head and l.role == 'infinitive')
    return any(l.role == 'object' and l.head in predicates for l in tree)


def competing_leaves(candidates, start, gaps):
    adjectival = any(any(link.rule == 'GAP.ATTR' for link in variant) for variant, _ in gaps)
    unmarked = any(variant[anchor - start].rule == 'GAP.REMNANT' for variant, anchor in gaps)
    for leaf, root in candidates:
        own = leaf[root - start]
        subjects = [link for link in leaf if link.head == root and link.role == 'subject']
        if _personal_count(own, (link for link in leaf[root - start + 1:] if link.head == root)):
            continue
        personal = own.morphology and own.morphology.animacy == 'anim'
        nominal_identity = personal and any(link.morphology and link.morphology.animacy == 'anim' for link in subjects)
        adjectival_predicate = adjectival and own.morphology and own.morphology.pos == 'ADJF' and subjects
        if (unmarked or adjectival_predicate or nominal_identity or own.morphology and own.morphology.pos == 'VERB'
                or any(link.quantity_kind for link in subjects)):
            yield leaf, root


def parallel_ordinals(tokens, candidates, budget):
    from .morphology import CASE_EQUIVALENTS
    from .parser import AnalysisBudgetExceeded

    for tree in candidates:
        yield tree
        if not any(link.rule == 'NUM.ARG' and link.role == 'governed' for link in tree):
            continue
        sources = {}
        alternatives = {}
        for i, link in enumerate(tree):
            if link.quantity_kind == 'ordinal' and link.role == 'attribute' and link.head is not None:
                noun = tree[link.head]
                if noun.role != 'governed' or noun.head is None or not link.morphology:
                    continue
                prep = tree[noun.head]
                key = prep.head, prep.lemma, CASE_EQUIVALENTS.get(noun.case, noun.case)
                sources.setdefault(key, []).append((link.head, link.morphology))
            elif (link.rule == 'NUM.ARG' and link.role == 'governed' and link.quantity_kind == 'cardinal'
                  and tokens[i].surface.isdecimal() and link.head is not None):
                prep = tree[link.head]
                if prep.head is None or tree[prep.head].role != 'clause_conjunct':
                    continue
                key = tree[prep.head].head, prep.lemma, CASE_EQUIVALENTS.get(link.case, link.case)
                for source, form in sources.get(key, ()):
                    if source < i:
                        alternatives.setdefault(i, [link]).append(replace(link, rule='ELL.PARALLEL.ORDINAL',
                            quantity_kind='ordinal', morphology=form, ellipsis_source=source))
        if not alternatives:
            continue
        if prod(map(len, alternatives.values())) > budget:
            raise AnalysisBudgetExceeded('ORDINAL_ELLIPSIS_BUDGET')
        choices = product(*alternatives.values())
        next(choices)
        for choice in choices:
            restored = list(tree)
            for i, reading in zip(alternatives, choice):
                restored[i] = reading
            yield tuple(restored)


def expand(tokens, tree):
    from .parser import Occurrence

    if not any(l.rule in ('GAP.COUNT', 'GAP.ATTR', 'GAP.REMNANT') for l in tree):
        return tokens, tree
    links = list(tree)
    words = list(tokens[:len(tree)])
    for i, link in enumerate(tree):
        if link.rule == 'GAP.REMNANT':
            host = links[link.ellipsis_source]
            root = len(links)
            words.append(Occurrence('', tokens[i].end, tokens[i].end))
            links.append(Link('clause_conjunct', host.lemma, link.head, 'GAP', scope=link.scope,
                              morphology=_agreement(host.morphology, link.morphology), ellipsis_source=link.ellipsis_source))
            for j, child in enumerate(links):
                if child.head == i and child.role not in ('attribute', 'name_part', 'possessive'):
                    links[j] = replace(child, head=root)
            links[i] = Link('subject', link.lemma, root, 'GAP.SUBJ', 'nomn', morphology=link.morphology)
        elif link.rule in ('GAP.COUNT', 'GAP.ATTR'):
            src = link.ellipsis_source
            noun = tree[src].lemma
            end = i + 1
            while end < len(tree) and tree[end].head == i and tree[end].role in ('numeral_part', 'attribute'):
                end += 1
            noun_index = len(links)
            words.append(Occurrence('', tokens[end - 1].end, tokens[end - 1].end))
            links.append(Link(link.role, noun, links[i].head, 'GAP.NOUN', link.case, morphology=link.noun_form, ellipsis_source=src))
            if link.rule == 'GAP.ATTR':
                parent = links[i].head
                if links[parent].rule == 'CL.CONJ':
                    links[parent] = replace(links[parent], rule='CL.NOUN.GAP')
                links[i] = Link('attribute', link.lemma, noun_index, 'A1', morphology=link.morphology)
                for j in range(i + 1, end):
                    links[j] = replace(links[j], head=noun_index)
                continue
            links[i] = Link('numeral', link.lemma, noun_index, 'NUM.GROUP', morphology=link.morphology,
                            quantity=link.quantity, quantity_kind=link.quantity_kind, quantity_modifier=link.quantity_modifier)
    return (*words, *tokens[len(tree):]), tuple(links)


def noun_surface(row, rows):
    form = row['morphology']
    source = rows[row['ellipsis_source']]
    return next((p.word for p in _noun_paradigm(source['surface'], row['lemma'])
                 if p.tag.case == form['case'] and p.tag.number == form['number']), row['lemma'])
