from dataclasses import replace
from itertools import combinations

from .morphology import NOMINAL_ROLES, ROLE_CASE, from_tag
from .nominal_groups import _agree
from .rules import known_forms


SCOPES = {
    'этот': 'demonstrative', 'тот': 'demonstrative',
    'каждый': 'universal', 'весь': 'universal', 'всякий': 'universal',
    'любой': 'universal', 'некоторый': 'existential',
    'никакой': 'negative',
}


def _nominal_predicates(tokens, head, word, tag, marker):
    from .predication import _bare_trees
    from .utterances import _map

    det = head - 1
    indices = tuple(j for j in range(len(tokens)) if j != det)
    for tree in _bare_trees(tuple(tokens[j] for j in indices), substantive=(det, word, tag)):
        if tree[det].role == 'subject' and tree[det].lemma == word:
            links = _map(tree, indices)
            links[det] = marker
            links[head] = replace(links[head], rule='PART.SUBSTANTIVE', case='nomn', morphology=from_tag(tag))
            yield tuple(links[j] for j in range(len(tokens)))


def _subject_matrix(tokens, kept, base, tag, head, marker):
    from .predication import _copula_agrees
    from .utterances import _map

    for tree in base(tuple(tokens[j] for j in kept)):
        root = next((i for i, link in enumerate(tree) if link.head is None), None)
        if root is None:
            continue
        pred = tree[root]
        if (pred.rule != 'V1' or pred.implicit_subject != 'unresolved'
                or not _copula_agrees(pred.morphology, tag)
                or any(link.role.startswith('clause_') for link in tree)
                or marker and marker.scope == 'negative' and 'negated' not in (pred.scope or '').split('_')):
            continue
        links = _map(tree, kept)
        predicate = kept[root]
        for i, link in tuple(links.items()):
            if link.implicit_subject == 'unresolved':
                links[i] = replace(link, implicit_subject=None, controller=head if i != predicate else link.controller)
        if marker:
            links[head - 1] = marker
        yield links, predicate


def _substantive_subjects(tokens, base, budget):
    from .parser import AnalysisBudgetExceeded, Link
    from .participle_forms import ParticipleForm
    from .predication import _copula_agrees
    from .participles import _inner, _remap

    forms = [known_forms(token.surface) for token in tokens]
    finite = {i for i, variants in enumerate(forms) if variants and all(tag.POS == 'VERB' for _, tag in variants)}
    if len(finite) > 1:
        return
    barriers = finite | {i for i, token in enumerate(tokens) if token.surface in {',', ':', ';'}}
    attempts = 0
    for head, variants in enumerate(forms):
        for word, tag in variants:
            if tag.POS != 'PRTF' or tag.case != 'nomn':
                continue
            form = ParticipleForm(word, from_tag(tag))
            previous = forms[head - 1] if head else ()
            determiners = [(name, t) for name, t in previous if name in SCOPES and t.POS == 'ADJF']
            markers = [Link('attribute', name, head, 'NP.DET', scope=SCOPES[name], morphology=from_tag(t))
                       for name, t in determiners if _agree(t, tag)] if determiners else [None]
            for marker in markers:
                if marker and marker.scope != 'negative':
                    yield from _nominal_predicates(tokens, head, word, tag, marker)
                if not any(t.POS == 'VERB' and t.mood == 'indc' and _copula_agrees(t, tag)
                           for variants in forms for _, t in variants):
                    continue
                end_limit = min((i for i in barriers if i > head), default=len(tokens))
                for end in range(head + 1, end_limit + 1):
                    kept = (*range(head - int(marker is not None)), *range(end, len(tokens)))
                    if not kept:
                        continue
                    attempts += 1
                    if attempts > budget:
                        raise AnalysisBudgetExceeded('PARTICIPLE_BUDGET')
                    for links, predicate in _subject_matrix(tokens, kept, base, tag, head, marker):
                        links[head] = Link('subject', word, predicate, 'PART.SUBSTANTIVE', 'nomn',
                                           morphology=form.morphology)
                        if end == head + 1:
                            yield tuple(links[j] for j in range(len(tokens)))
                            continue
                        anchors = {-1: head, **dict(enumerate(range(head, end)))}
                        for branch in _inner(tokens[head:end], 0, form, base, budget):
                            links.update((head + j, _remap(child, anchors)) for j, child in enumerate(branch) if j)
                            yield tuple(links[j] for j in range(len(tokens)))


def with_agreeing_determiners(tokens, base, *, include_bare=False):
    from .parser import Link
    from .utterances import _map

    groups = {}
    for i, token in enumerate(tokens[:-1]):
        forms = [(lemma, tag) for lemma, tag in known_forms(token.surface)
                 if tag.POS == 'ADJF' and (lemma in SCOPES or
                    {'Apro', 'Subx'} <= tag.grammemes and not {'Anph', 'Anum'} & tag.grammemes)]
        if not forms:
            continue
        for j in range(i + 1, len(tokens)):
            readings = known_forms(tokens[j].surface)
            if any(tag.POS == 'NOUN' for _, tag in readings):
                groups[i] = j, forms
                break
            if not any(tag.POS == 'ADJF' for _, tag in readings):
                break
    if include_bare or not groups:
        yield from base(tokens)
    if not groups:
        return
    kept = tuple(i for i in range(len(tokens)) if i not in groups)
    for tree in base(tuple(tokens[i] for i in kept)):
        links = _map(tree, kept)
        for i, (j, forms) in groups.items():
            host = links.get(j)
            if host is None or host.role not in NOMINAL_ROLES | {'genitive_modifier'}:
                break
            case = host.case or ROLE_CASE.get(host.role)
            lemma = next((adj for adj, tag in forms for noun, reading in known_forms(tokens[j].surface)
                          if noun == host.lemma and reading.POS == 'NOUN' and reading.case == case
                          and _agree(tag, reading)), None)
            if lemma is None:
                break
            scope = SCOPES.get(lemma)
            if scope == 'negative':
                governor = host
                while governor.head is not None and governor.role not in ('predicate', 'infinitive', 'converb'):
                    governor = links[governor.head]
                if 'negated' not in (governor.scope or '').split('_'):
                    break
            links[i] = Link('attribute', lemma, j, 'NP.DET', scope=scope)
        else:
            yield tuple(links[i] for i in range(len(tokens)))


def _determined(tokens, base, budget):
    yield from _substantive_subjects(tokens, base, budget)
    yield from with_agreeing_determiners(tokens, base)


def trees(tokens, base, *, budget=256):
    from .modal_regions import adverbial_modifiers
    from .parser import AnalysisBudgetExceeded, Link
    from .utterances import _map

    yield from _determined(tokens, base, budget)
    _, particles = adverbial_modifiers()
    sites = [i for i in range(1, len(tokens) - 1)
             if tokens[i].surface.casefold() in particles
             and any(tag.POS == 'ADJF' for _, tag in known_forms(tokens[i - 1].surface))
             and any(tag.POS in {'ADJF', 'NOUN', 'NPRO'} for _, tag in known_forms(tokens[i + 1].surface))]
    if (1 << len(sites)) > budget:
        raise AnalysisBudgetExceeded('MODIFIER_BUDGET')
    for count in range(1, len(sites) + 1):
        for marked in combinations(sites, count):
            kept = tuple(i for i in range(len(tokens)) if i not in marked)
            for tree in _determined(tuple(tokens[i] for i in kept), base, budget):
                links = _map(tree, kept)
                for i in marked:
                    host = links[i - 1]
                    if host.role not in ('attribute', 'possessive') or host.head is None or host.head <= i:
                        break
                    links[i] = Link('particle', tokens[i].surface.casefold(), i - 1, 'F.NP')
                else:
                    yield tuple(links[i] for i in range(len(tokens)))
