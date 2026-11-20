from dataclasses import replace

from .morphology import NOMINAL_ROLES, ROLE_CASE, from_tag
from .nominal_groups import _agree
from .rules import known_forms


SCOPES = {
    'этот': 'demonstrative', 'тот': 'demonstrative',
    'каждый': 'universal', 'весь': 'universal', 'всякий': 'universal',
    'любой': 'universal', 'некоторый': 'existential',
    'никакой': 'negative',
}


def _substantive_subjects(tokens, base):
    from .parser import Link
    from .predication import _bare_trees, _copula_agrees
    from .utterances import _map

    for i, token in enumerate(tokens[:-1]):
        quantifiers = [(word, tag) for word, tag in known_forms(token.surface)
                       if word in SCOPES and tag.POS == 'ADJF' and tag.case == 'nomn']
        if not quantifiers:
            continue
        head = i + 1
        candidates = [(word, tag, det, det_tag) for word, tag in known_forms(tokens[head].surface)
                      if tag.POS == 'PRTF' and tag.case == 'nomn'
                      for det, det_tag in quantifiers if _agree(det_tag, tag)]
        if not candidates:
            continue
        visible = tuple(j for j in range(len(tokens)) if j != i)
        nominal_clause = tuple(tokens[j] for j in visible)
        for word, tag, det, det_tag in candidates:
            if SCOPES[det] == 'negative':
                continue
            for tree in _bare_trees(nominal_clause, substantive=(i, word, tag)):
                if tree[i].role != 'subject' or tree[i].lemma != word:
                    continue
                bound = _map(tree, visible)
                bound[i] = Link('attribute', det, head, 'NP.DET', scope=SCOPES[det], morphology=from_tag(det_tag))
                bound[head] = replace(bound[head], rule='PART.SUBSTANTIVE', case='nomn', morphology=from_tag(tag))
                yield tuple(bound[j] for j in range(len(tokens)))
        kept = tuple(j for j in range(len(tokens)) if j not in (i, head))
        for tree in base(tuple(tokens[j] for j in kept)):
            roots = [j for j, link in enumerate(tree) if link.head is None and link.role == 'predicate'
                     and link.rule == 'V1' and link.implicit_subject == 'unresolved']
            if len(roots) != 1 or any(link.role.startswith('clause_') for link in tree):
                continue
            root = kept[roots[0]]
            links = _map(tree, kept)
            predicate = links[root]
            for word, tag, det, det_tag in candidates:
                if (not _copula_agrees(predicate.morphology, tag)
                        or SCOPES[det] == 'negative' and 'negated' not in (predicate.scope or '').split('_')):
                    continue
                bound = {j: replace(link, implicit_subject=None, controller=head if j != root else link.controller)
                         if link.implicit_subject == 'unresolved' else link for j, link in links.items()}
                bound[i] = Link('attribute', det, head, 'NP.DET', scope=SCOPES[det], morphology=from_tag(det_tag))
                bound[head] = Link('subject', word, root, 'PART.SUBSTANTIVE', 'nomn', morphology=from_tag(tag))
                yield tuple(bound[j] for j in range(len(tokens)))


def trees(tokens, base):
    from .parser import Link

    yield from _substantive_subjects(tokens, base)
    groups = {}
    for i, token in enumerate(tokens[:-1]):
        forms = [(lemma, tag) for lemma, tag in known_forms(token.surface)
                 if tag.POS == 'ADJF' and lemma in SCOPES]
        if not forms:
            continue
        for j in range(i + 1, len(tokens)):
            readings = known_forms(tokens[j].surface)
            if any(tag.POS == 'NOUN' for _, tag in readings):
                groups[i] = j, forms
                break
            if not any(tag.POS == 'ADJF' for _, tag in readings):
                break
    if not groups:
        yield from base(tokens)
        return
    kept = tuple(i for i in range(len(tokens)) if i not in groups)
    for tree in base(tuple(tokens[i] for i in kept)):
        links = {i: replace(link, **{key: kept[j] for key in ('head', 'controller', 'antecedent', 'coord_head', 'shared_agent', 'shared_object')
                                     if (j := getattr(link, key)) is not None})
                 for i, link in zip(kept, tree)}
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
            if SCOPES[lemma] == 'negative':
                governor = host
                while governor.head is not None and governor.role not in ('predicate', 'infinitive', 'converb'):
                    governor = links[governor.head]
                if 'negated' not in (governor.scope or '').split('_'):
                    break
            links[i] = Link('attribute', lemma, j, 'NP.DET', scope=SCOPES[lemma])
        else:
            yield tuple(links[i] for i in range(len(tokens)))
