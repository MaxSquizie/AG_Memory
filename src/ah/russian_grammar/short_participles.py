from dataclasses import replace
from functools import cache
from importlib.resources import files
from itertools import product

from .case_arguments import _lexicon, _pp_attachments, _writing_instruments
from .morphology import from_tag
from .nominal_groups import _groups
from .rules import known_forms


@cache
def _predicative_instrumentals():
    table = files(__package__).joinpath('lexicon/predicative-instrumentals.tsv')
    return frozenset(table.read_text(encoding='utf-8').splitlines())


def instrumental_roles(tokens, group, predicate_lemma):
    _, roles = _lexicon()
    lexical = roles.get((predicate_lemma, 'ablt'))
    members = [(group.noun, group.lemma), *((i, link.lemma) for i, link in group.extra
                                           if link.role == 'nominal_conjunct')]
    options = []
    for i, noun in members:
        tags = [tag for lemma, tag in known_forms(tokens[i].surface)
                if lemma == noun and tag.case == 'ablt' and tag.POS in {'NOUN', 'NPRO'}]
        animate = noun == 'кто' or any(tag.person or tag.animacy == 'anim' for tag in tags)
        proper = any({'Name', 'Surn', 'Patr'} & tag.grammemes or tag.POS == 'NPRO' for tag in tags)
        choices = set()
        if animate:
            choices.add('agent')
            if predicate_lemma in _predicative_instrumentals() and not proper:
                choices.add('oblique')
        if lexical == 'instrument' and (noun in _writing_instruments() or noun == 'что'):
            choices.add('instrument')
        elif lexical and lexical != 'instrument':
            choices.add(lexical)
        if not choices:
            choices.add('oblique')
        options.append(choices)
    return tuple(sorted(set.intersection(*options)))


def _predicates(tokens, tree, root, tags):
    predicate = tree[root]
    copula = next((i for i, link in enumerate(tree) if link.role == 'copula' and link.head == root), None)
    auxiliaries = (None,) if copula is None else (
        tag for lemma, tag in known_forms(tokens[copula].surface)
        if lemma == 'быть' and tag.POS == 'VERB' and tag.mood == 'indc')
    for aux in auxiliaries:
        for lemma, tag in tags:
            if lemma != predicate.lemma or aux and (tag.number != aux.number or
                    (tag.gender and aux.gender and tag.gender != aux.gender)):
                continue
            aux_form = from_tag(aux) if aux else None
            form = replace(from_tag(tag), tense=aux_form.tense if aux_form else 'pres',
                           person=aux_form.person if aux_form else None, mood='indc')
            result = list(tree)
            result[root] = replace(predicate, morphology=form)
            if copula is not None:
                result[copula] = replace(tree[copula], morphology=from_tag(aux))
            yield tuple(result)


def allows_copula_reading(tokens, tree):
    root = next((i for i, link in enumerate(tree) if link.rule == 'V2.PASS'), None)
    if root is None or any(link.role == 'copula' and link.head == root for link in tree):
        return True
    form = tree[root].morphology
    if form is None:
        return True
    heads = {link.head for link in tree}
    for step in (-1, 1):
        pos = root + step
        while 0 <= pos < len(tree) and tree[pos].role in {'adverb', 'particle'}:
            pos += step
        if not 0 <= pos < len(tree) or pos in heads or tree[pos].role not in {'oblique', 'genitive_modifier'}:
            continue
        if any(lemma == 'быть' and tag.POS == 'VERB' and tag.number == form.number
               and (not tag.gender or tag.gender == form.gender) for lemma, tag in known_forms(tokens[pos].surface)):
            return False
    return True


def trees(tokens, base, *, budget=256):
    from .parser import AnalysisBudgetExceeded, Link

    tags = {i: tuple((lemma, tag) for lemma, tag in known_forms(token.surface)
                     if tag.POS == 'PRTS' and tag.voice == 'pssv') for i, token in enumerate(tokens)}
    tags = {i: forms for i, forms in tags.items() if forms}
    if not tags:
        yield from base(tokens)
        return

    from .passive_arguments import trees as argument_trees
    yield from argument_trees(tokens, budget=budget)

    starts = [(i, tuple(_groups(tokens, i, budget, bare_cases=('ablt',)))) for i in range(len(tokens))]
    starts = [(i, groups) for i, groups in starts if groups]
    seen = set()
    work = [(0, ())]
    attempts = 0
    while work:
        position, selected = work.pop()
        for j in range(position, len(starts)):
            start, groups = starts[j]
            if selected and start < selected[-1].end:
                continue
            for group in groups:
                attempts += 1
                if attempts > budget:
                    raise AnalysisBudgetExceeded('PASSIVE_BUDGET')
                work.append((j + 1, (*selected, group)))
        hidden = {i for group in selected for i in range(group.start, group.end)}
        kept = tuple(i for i in range(len(tokens)) if i not in hidden)
        words = tuple(tokens[i] for i in kept)
        for tree in base(words):
            root = next((i for i, link in enumerate(tree) if link.rule == 'V2.PASS'), None)
            if root is None:
                if not selected:
                    yield tree
                continue
            if any(link.rule == 'V.GOV' and link.case == 'ablt' and link.head == root for link in tree):
                continue
            host = kept[root]
            roles = [instrumental_roles(tokens, g, tree[root].lemma) for g in selected]
            for bound in product(*roles):
                if len(set(bound)) != len(bound):
                    continue
                for read in _predicates(words, tree, root, tags[host]):
                    links = {i: replace(link, **{field: kept[j] for field in ('head', 'controller', 'antecedent')
                                                 if (j := getattr(link, field)) is not None})
                             for i, link in zip(kept, read)}
                    if any(link.role == 'governed' and any(link.head < g.start < i for g in selected)
                           for i, link in links.items()):
                        continue
                    for group, role in zip(selected, bound):
                        links[group.noun] = Link(role, group.lemma, host, 'PASS.ABL', case='ablt')
                        links.update(group.extra)
                    result = tuple(links[i] for i in range(len(tokens)))
                    for expanded in _pp_attachments(result, selected, budget):
                        if expanded not in seen:
                            seen.add(expanded)
                            if len(seen) > budget:
                                raise AnalysisBudgetExceeded('PASSIVE_BUDGET')
                            yield expanded


def voice_partitions(analyses, tokens, text):
    from .parser import _clause_context, _span_label
    from .probe import Probe
    from .rules import dictionary

    for i in range(len(tokens)):
        links = [tree[i] for tree in analyses]
        rules = {link.rule for link in links}
        if rules != {'V2', 'V2.PASS'}:
            continue
        if any(link.morphology is None or link.morphology.pos not in ('ADJS', 'PRTS') for link in links):
            continue
        passive = [link for link in links if link.rule == 'V2.PASS']
        lemmas = {link.lemma for link in passive}
        if len(lemmas) != 1:
            continue
        lemma, = lemmas
        tenses = {link.morphology.tense for link in passive}
        tense = tenses.pop() if len(tenses) == 1 else None
        paraphrase = f'речь идёт о действии «{lemma}»'
        if tense in ('past', 'pres', 'futr'):
            features = {tense, 'plur'} if tense == 'past' else {tense, 'plur', '3per'}
            active = {form.word for reading in dictionary().parse(lemma) if reading.tag.POS == 'INFN'
                      and (form := reading.inflect(features)) is not None and form.tag.POS == 'VERB'}
            if len(active) == 1:
                paraphrase = f'сообщается, что кого-то или что-то {active.pop()}'
        focus = _span_label(tokens, i)
        state = 'только свойство или состояние'
        question = (f'Как понимать «{focus}» в этом предложении? Если {paraphrase}, выберите «{focus}». '
                    f'Если описано только свойство или состояние, выберите «{state}».')
        probe = Probe(question, (focus, state), _clause_context(text, tokens, analyses, i, ()))
        yield probe, [focus if link.rule == 'V2.PASS' else state for link in links]
