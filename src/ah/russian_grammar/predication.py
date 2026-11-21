from dataclasses import replace
from importlib.resources import files
from itertools import product
from functools import lru_cache

from .morphology import _common, from_tag
from .prepositions import DASHES, group_heads
from .rules import known_forms, readings


def _agree(first, second):
    number = first.number
    return (number == second.number and number is not None
            and (number != 'sing' or not first.gender or not second.gender or first.gender == second.gender))


def _copula_agrees(tag, subject):
    if subject is None:
        return tag.number == 'sing' and tag.gender in (None, 'neut') and tag.person in (None, '3per')
    person = subject.person or '3per'
    return _agree(tag, subject) and (tag.person is None or tag.person == person)


def _nominal(tag, case):
    return tag.POS in ('NOUN', 'NPRO') and tag.case == case


def _adjective(tag):
    return tag.POS in ('ADJF', 'ADJS', 'PRTS') and 'Apro' not in tag


def _modifies(forms, index, noun, head_tag):
    if index >= noun or head_tag.POS != 'NOUN':
        return False
    return all(any(tag.POS == 'ADJF' and tag.case == head_tag.case and _agree(tag, head_tag)
                   for _, tag in variants) for variants in forms[index+1:noun])


INSTRUMENTAL_COPULAS = frozenset(('оказаться', 'оказываться'))


def _decorated(tokens, forms, bindings, nominal_heads, root, subject, personal):
    from .parser import Link

    instrumental = any(i == root and tag.case == 'ablt' for i, tag in nominal_heads)
    choices = []
    for i, variants in enumerate(forms):
        if i in bindings:
            choices.append((bindings[i],))
            continue
        options = []
        for lemma, tag in variants:
            if (lemma == 'быть' or (lemma in INSTRUMENTAL_COPULAS and personal and instrumental)) and tag.POS == 'VERB' and tag.mood == 'indc' and _copula_agrees(tag, subject):
                options.append(Link('copula', lemma, root, 'V2.COP'))
            if tag.POS == 'ADVB':
                options.append(Link('adverb', lemma, root, 'V2.MOD'))
            if tag.POS == 'ADJF':
                for noun, head_tag in nominal_heads:
                    if tag.case == head_tag.case and _agree(tag, head_tag) and _modifies(forms, i, noun, head_tag):
                        options.append(Link('attribute', lemma, noun, 'A1'))
        if personal and tokens[i].surface in DASHES:
            subject_index = next(j for j, link in bindings.items() if link.role == 'subject')
            if min(root, subject_index) < i < max(root, subject_index):
                options.append(Link('punctuation', tokens[i].surface, root, 'V2.DASH'))
        if not options:
            return
        choices.append(tuple(dict.fromkeys(options)))
    for tree in product(*choices):
        if sum(link.role == 'copula' for link in tree) <= 1 and sum(link.role == 'punctuation' for link in tree) <= 1:
            yield tree


def _personal(tokens, forms, root, lemma, pred, substantive=None):
    from .parser import Link

    for subj, variants in enumerate(forms):
        if subj == root:
            continue
        for noun, tag in variants:
            if not (_nominal(tag, 'nomn') or (subj, noun, tag) == substantive):
                continue
            if _adjective(pred) and not _agree(pred, tag):
                continue
            rule = 'V2.PASS' if pred.POS == 'PRTS' and pred.voice == 'pssv' else 'V2'
            bindings = {root: Link('predicate', lemma, None, rule), subj: Link('subject', noun, root, 'S1')}
            for tree in _decorated(tokens, forms, bindings, [(subj, tag), (root, pred)], root, tag, True):
                explicit = any(link.role == 'copula' for link in tree)
                predicative_marker = explicit or any(link.role == 'punctuation' for link in tree)
                if pred.case == 'ablt' and not explicit:
                    continue
                if not predicative_marker and root < subj and pred.POS in ('ADJF', 'NOUN'):
                    continue
                if not predicative_marker and 'Name' in tag and 'Surn' in pred:
                    continue
                yield tree


IMPERSONAL_INFINITIVES = frozenset(files(__package__).joinpath(
    'lexicon/impersonal-infinitives.tsv').read_text(encoding='utf8').splitlines())


def experiencer(surface, lemma, root):
    from .parser import Link

    forms = tuple((word, tag) for word, tag in known_forms(surface)
                  if tag.POS == 'NPRO' and tag.person == '3per' and tag.case == 'datv')
    lemmas = {word for word, _ in forms}
    if lemma in lemmas and len(lemmas) > 1:
        common = _common(tuple(from_tag(tag) for _, tag in forms))
        return Link('experiencer', surface.casefold(), root, 'V3.DAT.UNBOUND', 'datv', morphology=common)
    return Link('experiencer', lemma, root, 'V3.DAT', 'datv')


def _impersonal(tokens, forms, root, lemma, pred, *, requires_infinitive=False, unavailable=False):
    from .parser import Link

    infinitives = [(i, form, tag) for i, variants in enumerate(forms) if i != root
                   for form, tag in variants if tag.POS == 'INFN']
    datives = [(i, form, tag) for i, variants in enumerate(forms) if i != root
               for form, tag in variants if _nominal(tag, 'datv') and 'Af-p' not in tag]
    accusatives = [(i, form, tag) for i, variants in enumerate(forms) if i != root
                   for form, tag in variants if _nominal(tag, 'accs') and 'Af-p' not in tag]
    if unavailable:
        complements = [None]
    elif requires_infinitive:
        complements = infinitives
    else:
        complements = [None, *infinitives]
    for infinitive, dat in product(complements, [None, *datives]):
        if infinitive and dat and infinitive[0] == dat[0]:
            continue
        if unavailable:
            predicate = Link('predicate', lemma, None, 'V3.UNAVAILABLE', scope='unavailable',
                             morphology=from_tag(pred), controller=dat[0] if dat else None)
        elif requires_infinitive:
            predicate = Link('predicate', lemma, None, 'V3.FRAME', morphology=from_tag(pred))
        else:
            predicate = Link('predicate', lemma, None, 'V3')
        bindings = {root: predicate}
        heads = []
        if infinitive:
            bindings[infinitive[0]] = Link('infinitive', infinitive[1], root, 'V3.INF',
                                           controller=dat[0] if dat else None)
        if dat:
            bindings[dat[0]] = experiencer(tokens[dat[0]].surface, dat[1], root)
            heads.append((dat[0], dat[2]))
        transitive = 'tran' in (infinitive[2] if infinitive else pred)
        for obj in [None, *(accusatives if transitive else ())]:
            if obj and obj[0] in bindings:
                continue
            bound = bindings.copy()
            nominal_heads = list(heads)
            if obj:
                bound[obj[0]] = Link('object', obj[1], infinitive[0] if infinitive else root, 'O1')
                nominal_heads.append((obj[0], obj[2]))
            for tree in _decorated(tokens, forms, bound, nominal_heads, root, None, False):
                if pred.POS != 'VERB' or not any(link.role == 'copula' for link in tree):
                    yield tree


@lru_cache(maxsize=4096)
def _admits_bare_predication(surface):
    return surface in DASHES or any(
        tag.POS != 'VERB' or lemma == 'быть' or lemma in INSTRUMENTAL_COPULAS
        or lemma in IMPERSONAL_INFINITIVES or 'Impe' in tag or 'Prdx' in tag
        for lemma, tag in known_forms(surface))


def _bare_trees(tokens, substantive=None):
    if not all(_admits_bare_predication(token.surface) for token in tokens):
        return
    forms = [known_forms(token.surface) for token in tokens]
    seen = set()
    for root, variants in enumerate(forms):
        for lemma, pred in variants:
            if _adjective(pred) and pred.case in (None, 'nomn', 'ablt') or (
                    pred.POS == 'NOUN' and pred.case in ('nomn', 'ablt')):
                candidates = _personal(tokens, forms, root, lemma, pred, substantive)
            elif pred.POS == 'PRED' or 'Prdx' in pred or (pred.POS == 'VERB' and 'Impe' in pred):
                candidates = _impersonal(tokens, forms, root, lemma, pred)
            elif lemma in IMPERSONAL_INFINITIVES and pred.POS == 'VERB' and pred.mood == 'indc' and _copula_agrees(pred, None):
                candidates = _impersonal(tokens, forms, root, lemma, pred, requires_infinitive=True)
            else:
                continue
            for tree in candidates:
                if tree not in seen:
                    seen.add(tree)
                    yield tree


def _groups_at(tokens, start, budget):
    from .parser import AnalysisBudgetExceeded, Prefix

    states = (Prefix(),)
    for i in range(start, len(tokens)):
        following = {}
        for state in states:
            for word in state.next_readings(tokens[i].surface):
                if i == start:
                    if word.role not in {'preposition', 'prep_prefix'}:
                        continue
                elif state.open_preposition is None and word.role not in {'post_attribute', 'name_part'}:
                    continue
                extended = state.extend(word)
                if extended is not None:
                    following[extended] = None
                    if len(following) > budget:
                        raise AnalysisBudgetExceeded('ANALYSIS_BUDGET')
        if not following:
            return
        for state in following:
            if state.groups and state.open_preposition is None:
                yield state
        states = following


def _layouts(tokens, budget):
    from .parser import AnalysisBudgetExceeded

    starts = {i for i, token in enumerate(tokens)
              if any(word.role in {'preposition', 'prep_prefix'} for word in readings(token.surface))}
    if not starts:
        return
    groups = {i: tuple(_groups_at(tokens, i, budget)) for i in starts}
    required = {i for i in starts if all(tag.POS == 'PREP' for _, tag in known_forms(tokens[i].surface))}
    stack = [(0, ())]
    count = 0
    while stack:
        index, layout = stack.pop()
        while index < len(tokens) and index not in starts:
            index += 1
        if index == len(tokens):
            if layout:
                yield layout
            continue
        count += 1
        if count > budget:
            raise AnalysisBudgetExceeded('ANALYSIS_BUDGET')
        if index not in required:
            stack.append((index + 1, layout))
        for group in groups[index]:
            stack.append((index + len(group.words), (*layout, (index, group))))


def _attach(tokens, kept, tree, layout):
    from .parser import Link, RULE_FOR_ROLE

    mapped = [None] * len(tokens)
    heads = {}
    for i, link in zip(kept, tree):
        if link.head is None:
            root = i
        else:
            heads[i] = kept[link.head]
        mapped[i] = replace(link, head=heads.get(i),
                            controller=None if link.controller is None else kept[link.controller])
    groups = []
    for start, group in layout:
        noun = start + group.groups[0][1]
        groups.append((start, noun))
        for i, word in enumerate(group.words, start):
            role = 'attribute' if word.role in {'group_attribute', 'post_attribute'} else word.role
            mapped[i] = Link(role, word.lemma, None, RULE_FOR_ROLE[word.role],
                             word.case if role == 'governed' else None)
            if role in {'attribute', 'name_part'}:
                heads[i] = noun
    for attached in group_heads(groups, mapped, root, heads):
        yield tuple(replace(link, head=attached.get(i)) for i, link in enumerate(mapped))


def _unavailable_predicates(tokens):
    forms = [known_forms(token.surface) for token in tokens]
    for index, variants in enumerate(forms):
        for lemma, tag in variants:
            if tag.POS == 'INFN':
                yield from _impersonal(tokens, forms, index, lemma, tag, unavailable=True)


def _unavailable(tokens, budget):
    from .homogeneous import _restore
    from .parser import Link

    for marker, token in enumerate(tokens[:-2]):
        if token.surface.casefold() != 'не':
            continue
        prep = marker + 1
        for group in _groups_at(tokens, prep, budget):
            noun = prep + group.groups[0][1]
            word = group.words[noun - prep]
            if (word.role != 'governed' or word.lemma not in {'кто', 'что'} or noun != marker + len(group.words)
                    or any(w.role != 'prep_part' for w in group.words[1:-1])):
                continue
            kept = tuple(i for i in range(len(tokens)) if not marker <= i <= noun)
            reduced = tuple(tokens[i] for i in kept)
            for tree in _with_prepositions(reduced, _unavailable_predicates, budget):
                restored = _restore(tree, kept, len(tokens))
                root = next(i for i in kept if restored[i].head is None)
                restored[marker] = Link('particle', 'не', noun, 'NEG.PRON', scope='negative')
                restored[prep] = Link('preposition', group.words[0].lemma, root, 'P2')
                for i in range(prep + 1, noun):
                    restored[i] = Link('prep_part', group.words[i - prep].lemma, prep, 'P1')
                restored[noun] = Link('governed', word.lemma, prep, 'NEG.PRON.ARG', case=word.case)
                yield tuple(restored)


def _with_prepositions(tokens, bare, budget):
    yield from bare(tokens)
    for layout in _layouts(tokens, budget):
        covered = {i for start, group in layout for i in range(start, start + len(group.words))}
        kept = tuple(i for i in range(len(tokens)) if i not in covered)
        for tree in bare(tuple(tokens[i] for i in kept)):
            yield from _attach(tokens, kept, tree, layout)


def trees(tokens, *, budget=256):
    yield from _unavailable(tokens, budget)
    yield from _with_prepositions(tokens, _bare_trees, budget)
