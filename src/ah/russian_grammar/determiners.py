from dataclasses import replace

from .morphology import NOMINAL_ROLES, ROLE_CASE
from .nominal_groups import _agree
from .rules import known_forms


SCOPES = {
    'этот': 'demonstrative', 'тот': 'demonstrative',
    'каждый': 'universal', 'весь': 'universal', 'всякий': 'universal',
    'любой': 'universal', 'некоторый': 'existential',
    'никакой': 'negative',
}


def trees(tokens, base):
    from .parser import Link

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
