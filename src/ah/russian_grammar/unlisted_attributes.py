from .morphology import NOMINAL_ROLES, ROLE_CASE, _common, from_tag
from .nominal_groups import _agree
from .rules import dictionary, known_forms
from .utterances import _map


def predicted_attributes(surface):
    if not surface.isalpha() or known_forms(surface):
        return ()
    return tuple((p.normal_form, p.tag) for p in dictionary().parse(surface) if p.tag.POS == 'ADJF')


def trees(tokens, parse):
    from .parser import Link

    sites = {}
    for i, token in enumerate(tokens[:-1]):
        if not token.surface.isalpha() or known_forms(token.surface):
            continue
        nouns = [(lemma, tag) for lemma, tag in known_forms(tokens[i + 1].surface) if tag.POS == 'NOUN']
        variants = [(n, t, from_tag(tag)) for _, tag in predicted_attributes(token.surface)
                    for n, t in nouns if _agree(tag, t)]
        if variants:
            sites[i] = variants
    if not sites:
        return
    kept = tuple(i for i in range(len(tokens)) if i not in sites)
    for tree in parse(tuple(tokens[i] for i in kept)):
        links = _map(tree, kept)
        for i, variants in sites.items():
            head = links[i + 1]
            if head.role not in NOMINAL_ROLES | {'genitive_modifier'}:
                break
            case = head.case or ROLE_CASE.get(head.role) or (head.morphology and head.morphology.case)
            forms = [a for lemma, noun, a in variants if lemma == head.lemma and noun.case == case]
            if not forms:
                break
            links[i] = Link('attribute', tokens[i].surface, i + 1, 'OPAQUE.ATTRIBUTE', morphology=_common(forms))
        else:
            yield tuple(links[j] for j in range(len(tokens)))
