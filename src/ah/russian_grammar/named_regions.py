from dataclasses import replace
from functools import cache
from importlib.resources import files

from . import adjuncts, quantity_groups
from .morphology import from_tag
from .nominal_groups import POSSESSIVES, _groups, _markers, _members, _open_heads, _prepositions
from .parser import AnalysisBudgetExceeded, Link, _span_label
from .prepositions import GOVERNMENT
from .probe import Probe
from .quote_titles import spans
from .rules import dictionary, known_forms, unaccented
from .utterances import _map, _root


@cache
def _infinitive_connectives():
    resource = files(__package__).joinpath('lexicon/infinitive-connectives.tsv')
    return frozenset(tuple(line.split('\t')) for line in resource.read_text(encoding='utf8').splitlines())


def _title_layouts(tokens, quoted):
    if quoted:
        start, end = quoted[-1]
        if end == len(tokens) - 1 and end > start + 1:
            yield start, start + 1, end
        return
    for i in range(1, len(tokens)):
        if tokens[i].surface.istitle() and all(t.surface.isalpha() for t in tokens[i:]):
            yield i, i, len(tokens)


def _brackets(tokens, left, start, end, head):
    if left == start:
        return {}
    return {i: Link('punctuation', tokens[i].surface, head, 'TITLE.QUOTE') for i in (left, end)}


def _apposition(tokens, parse, quoted):
    candidates = {start + 1: (start, end) for start, end in quoted}
    if not quoted:
        candidates = {i: (i, None) for i in range(1, len(tokens)) if tokens[i].surface.istitle()}
    for start, (left, fence) in candidates.items():
        if left == 0 or not any(tag.POS == 'NOUN' for _, tag in known_forms(tokens[left - 1].surface)):
            continue
        members = _members(tokens, start, None, 'nomn')
        surface = tokens[start].surface
        if (fence == start + 1 and unaccented(surface).isalpha() and surface[:1].isupper()
                and not known_forms(surface)):
            members = ((start, surface, None, ()),)
        for noun, lemma, case, attrs in members:
            if fence is None and not attrs or fence is not None and noun + 1 != fence:
                continue
            stop = noun + 1 if fence is None else fence + 1
            kept = (*range(left), *range(stop, len(tokens)))
            for base in parse(tuple(tokens[i] for i in kept)):
                governor = base[left - 1]
                if governor.role not in {'subject', 'object', 'governed', 'genitive_modifier'}:
                    continue
                if fence is None and governor.case in ('nomn', None):
                    continue
                links = _map(base, kept)
                links.update(attrs)
                links.update(_brackets(tokens, left, start, noun + 1, noun))
                links[noun] = Link('apposition', lemma, left - 1, 'TITLE.APPOSITION', case, scope='title')
                yield tuple(links[i] for i in range(len(tokens)))


def _destination(tokens, verb, left, start, end):
    if start == left and (end - start < 2 or not all(t.surface.istitle() for t in tokens[start:end])):
        return
    if not all(t.surface.isalpha() for t in tokens[start:end]):
        return
    entries, _ = adjuncts._lexicon()
    for lemma, tag in known_forms(tokens[verb].surface):
        if tag.POS != 'INFN':
            continue
        prep = verb + 1
        for first, form in _prepositions(tokens, prep):
            if first != left:
                continue
            for case in sorted(GOVERNMENT.get(form, ())):
                wh = adjuncts.SPATIAL.get((form, case))
                if ('governor', wh, form, lemma) not in entries:
                    continue
                result = _brackets(tokens, left, start, end, start)
                result[prep] = Link('preposition', form, verb, 'P2')
                for i in range(prep + 1, first):
                    result[i] = Link('prep_part', tokens[i].surface.casefold(), prep, 'P1')
                result[start] = Link('governed', tokens[start].surface.casefold(), prep, 'TITLE.GOVERNED', case, scope='title')
                for i in range(start + 1, end):
                    result[i] = Link('name_part', tokens[i].surface.casefold(), start, 'TITLE.PART')
                yield lemma, tag, result


def _actor(links, predicate):
    subjects = [i for i, link in links.items() if link.head == predicate and link.role == 'subject']
    if len(subjects) == 1:
        return subjects[0]
    return links[predicate].controller


def _agrees(mention, omitted):
    return (mention and omitted
            and not (mention.number and omitted.number and mention.number != omitted.number)
            and not (mention.gender and omitted.gender and mention.gender != omitted.gender)
            and not (mention.person and omitted.person and mention.person != omitted.person))


def _relative_matrix(tokens, parse, budget):
    from .numerals import expressions

    def bases(part):
        yield from parse(part)
        for i in range(len(part)):
            for expression in expressions(part, i):
                for group in quantity_groups._groups(part, i, expression, budget):
                    if group.case != 'gent':
                        continue
                    extra = dict(group.links)
                    kept = tuple(j for j in range(len(part)) if j not in extra)
                    for tree in parse(tuple(part[j] for j in kept)):
                        links = _map(tree, kept)
                        noun = links[group.noun]
                        if noun.role == 'genitive_modifier' and noun.lemma == group.lemma and noun.case == group.case:
                            links[group.noun] = replace(noun, morphology=group.morphology)
                            links.update(extra)
                            yield tuple(links[j] for j in range(len(part)))

    for i in range(1, len(tokens)):
        markers = [(lemma, tag) for lemma, tag in known_forms(tokens[i].surface)
                   if tag.POS == 'ADVB' and lemma in adjuncts.SPATIAL.values()]
        if not markers:
            continue
        end = i - (tokens[i - 1].surface == ',')
        if end < 1:
            continue
        for base in bases(tokens[:end]):
            host = end - 1
            if base[host].role not in {'governed', 'object', 'subject', 'genitive_modifier'}:
                continue
            for child in parse(tokens[i:]):
                if child[0].role != 'adverb' or child[0].lemma not in {lemma for lemma, _ in markers}:
                    continue
                links = {**dict(enumerate(base)), **_map(child, range(i, len(tokens)))}
                root = i + _root(child)
                if not any(tag.POS == 'VERB' for _, tag in known_forms(tokens[root].surface)):
                    continue
                links[root] = replace(links[root], role='clause_relative', head=host, rule='CL.REL')
                links[i] = replace(links[i], rule='CL.NOMREF', antecedent=host)
                if end != i:
                    links[end] = Link('punctuation', ',', root, 'CL.PUNCT')
                yield links, root
                if _actor(links, root) is not None or links[root].implicit_subject != 'unresolved':
                    continue
                actor = _actor(links, _root(base))
                if actor is None:
                    continue
                if _agrees(links[actor].morphology, links[root].morphology):
                    yield {**links, root: replace(links[root], controller=actor, implicit_subject=None)}, root


def _infinitive_complements(tokens, verb, layouts):
    for left, start, end in layouts:
        yield from _destination(tokens, verb, left, start, end)
    for lemma, tag in known_forms(tokens[verb].surface):
        if tag.POS != 'INFN':
            continue
        if verb + 1 == len(tokens):
            yield lemma, tag, {}
        for first, prep in _prepositions(tokens, verb + 1):
            for noun, word, case, attrs in _members(tokens, first, prep):
                if noun + 1 != len(tokens):
                    continue
                links = dict(attrs)
                links[verb + 1] = Link('preposition', prep, verb, 'P2')
                for j in range(verb + 2, first):
                    links[j] = Link('prep_part', tokens[j].surface.casefold(), verb + 1, 'P1')
                links[noun] = Link('governed', word, verb + 1, 'P1', case)
                yield lemma, tag, links


def _correlatives(tokens, parse, budget, quoted):
    for adv in range(1, len(tokens) - 2):
        conj = adv + 1 + (tokens[adv + 1].surface == ',')
        verb = conj + 1
        pair = tokens[adv].surface.casefold(), tokens[conj].surface.casefold()
        if pair not in _infinitive_connectives() or verb >= len(tokens):
            continue
        tails = tuple(_infinitive_complements(tokens, verb, _title_layouts(tokens, quoted)))
        if not tails:
            continue
        matrix = tokens[:adv]
        embedded = tuple(_relative_matrix(matrix, parse, budget))
        if embedded:
            bases = embedded
        else:
            bases = ((dict(enumerate(tree)), _root(tree)) for tree in parse(matrix))
        for links, root in bases:
            if not any(tag.POS == 'VERB' for _, tag in known_forms(tokens[root].surface)):
                continue
            for lemma, tag, tail in tails:
                result = {**links, **tail}
                result[adv] = Link('adverb', pair[0], root, 'ADV.CORRELATE')
                result[conj] = Link('clause_marker', pair[1], verb, 'CL.MARK', scope='adverbial')
                result[verb] = Link('clause_adverbial', lemma, adv, 'CL.INF', morphology=from_tag(tag),
                                    controller=_actor(links, root) if 'Impe' not in tag else None)
                if conj != adv + 1:
                    result[adv + 1] = Link('punctuation', ',', verb, 'CL.PUNCT')
                yield tuple(result[i] for i in range(len(tokens)))


def _unlisted_groups(tokens, i, budget):
    surface = tokens[i].surface
    if (not unaccented(surface).isalpha() or known_forms(surface)
            or not any(tag.POS == 'NOUN' for _, tag in known_forms(tokens[i - 1].surface))):
        return
    guessed = dictionary().parse(surface)
    if (any(p.tag.POS == 'VERB' for p in guessed)
            or not any(p.tag.POS == 'NOUN' and p.tag.case == 'gent' for p in guessed)):
        return
    yield i + 1, {}
    for marker in _markers(tokens, i + 1):
        start = marker[-1] + 1
        groups = tuple(_groups(tokens, start, budget, bare_cases=('gent',)))
        possessive = any(any(j == start and link.role == 'possessive' for j, link in group.extra)
                         for group in groups)
        for group in groups:
            if possessive and group.noun == start and tokens[start].surface.casefold() in POSSESSIVES:
                continue
            extra = dict(group.extra)
            extra[group.noun] = Link('nominal_conjunct', group.lemma, i, 'P.COORD', 'gent')
            for j in marker:
                extra[j] = Link('coordinator' if j == marker[0] else 'coordinator_part',
                                tokens[j].surface.casefold(), group.noun if j == marker[0] else marker[0], 'P.COORD')
            yield group.end, extra


def unlisted_genitives(tokens, parse, budget):
    from .morphology import NOMINAL_ROLES
    from itertools import product

    sites = {i: groups for i in range(1, len(tokens))
             if (groups := tuple(_unlisted_groups(tokens, i, budget)))}
    if not sites:
        return
    examined = 0
    for selected in product(*((None, *groups) for groups in sites.values())):
        examined += 1
        if examined > budget:
            raise AnalysisBudgetExceeded('NOMINAL_GROUP_BUDGET')
        chosen = [(i, group) for i, group in zip(sites, selected) if group]
        if not chosen or any(i < previous[1][0] for previous, (i, _) in zip(chosen, chosen[1:])):
            continue
        hidden = {j for i, (end, _) in chosen for j in range(i, end)}
        kept = tuple(j for j in range(len(tokens)) if j not in hidden)
        for tree in parse(tuple(tokens[j] for j in kept)):
            if not any(link.head is None and any(lemma == link.lemma and tag.POS in ('VERB', 'PRTS')
                                                  for lemma, tag in known_forms(tokens[kept[j]].surface))
                       for j, link in enumerate(tree)):
                continue
            links = _map(tree, kept)
            allowed = {j for j, l in links.items() if l.role in NOMINAL_ROLES | {'genitive_modifier'}}
            hosts = [tuple(_open_heads(links, i, allowed)) for i, _ in chosen]
            for heads in product(*hosts):
                examined += 1
                if examined > budget:
                    raise AnalysisBudgetExceeded('NOMINAL_GROUP_BUDGET')
                output = links.copy()
                for (i, (_, extra)), head in zip(chosen, heads):
                    output[i] = Link('genitive_modifier', tokens[i].surface, head, 'N.UNLISTED.GEN', 'gent')
                    output.update(extra)
                yield tuple(output[i] for i in range(len(tokens)))


def matrix_readings(tokens, parse, budget):
    from .dated_name_notes import _first_name
    from .named_arguments import missing_subjects, single_finite_region

    if not single_finite_region(tokens):
        return

    def subjects(part):
        attempts = 0
        for start in range(len(part) - 1):
            if not all(unaccented(t.surface).istitle() for t in part[start:start + 2]):
                continue
            for stop, name in _first_name(part[start:]):
                if stop < 2 or not any(not known_forms(t.surface) for t in part[start:start + stop]):
                    continue
                attempts += 1
                if attempts > budget:
                    raise AnalysisBudgetExceeded('NOMINAL_GROUP_BUDGET')
                pivot = next((i for i in range(stop) if known_forms(part[start + i].surface)), 0)
                kept = (*range(start), start + pivot, *range(start + stop, len(part)))
                reduced = tuple(part[j] for j in kept)
                alternatives = (parse(reduced) if known_forms(part[start + pivot].surface)
                                else missing_subjects(reduced, parse))
                for tree in alternatives:
                    anchor = tree[start]
                    if anchor.role != 'subject' or anchor.head is None or any(
                            l.role == 'name_part' and l.head == start for l in tree):
                        continue
                    positions = (*range(start + 1), *range(start + stop, len(part)))
                    links = _map(tree, positions)
                    host = links[start].head
                    links.update(_map(tuple(name[i] for i in range(stop)), range(start, start + stop)))
                    links[start] = replace(links[start], head=host, rule='NAME.COMPOUND.SUBJECT')
                    yield tuple(links[j] for j in range(len(part)))

    yield from subjects(tokens)
    quoted = spans(tokens)
    if quoted:
        yield from _apposition(tokens, subjects, quoted)


def trees(tokens, parse, budget):
    quoted = spans(tokens)
    seen = set()
    for variants in (_apposition(tokens, parse, quoted), _correlatives(tokens, parse, budget, quoted)):
        for tree in variants:
            if tree not in seen:
                seen.add(tree)
                if len(seen) > budget:
                    raise AnalysisBudgetExceeded('NAMED_REGION_BUDGET')
                yield tree


def confirmation(tokens, tree, index, text):
    link = tree[index]
    if link.rule == 'NAME.COMPOUND.SUBJECT':
        stop = index + 1
        while stop < len(tree) and tree[stop].role == 'name_part' and tree[stop].head == index:
            stop += 1
        return Probe(f'Каким именем назван исполнитель действия «{tokens[link.head].surface}»?',
                     (_span_label(tokens, index, stop),), text)
    if link.rule == 'N.UNLISTED.GEN':
        host = _span_label(tokens, link.head)
        target = _span_label(tokens, index)
        return Probe(f'Какое слово здесь отвечает на вопрос «кого или чего?» от слова «{host}»?', (target,), text)
    if link.rule not in {'TITLE.APPOSITION', 'TITLE.GOVERNED'}:
        return None
    members = [j for j, part in enumerate(tree) if j == index or part.head == index and
               part.role in {'attribute', 'name_part'}]
    label = _span_label(tokens, min(members), max(members) + 1)
    return Probe('Какие слова вместе образуют название?', (label,), text)
