from dataclasses import replace

from .nominal_groups import _groups
from .predication import _decorated
from .rules import known_forms


def _comparisons(tokens, forms, budget):
    for index, variants in enumerate(forms):
        comparatives = [lemma for lemma, tag in variants if tag.POS == 'COMP']
        if not comparatives:
            continue
        next_word = index + 1
        if next_word < len(tokens) and tokens[next_word].surface == ',':
            next_word += 1
        marked = next_word < len(tokens) and tokens[next_word].surface.lower() == 'чем'
        target = next_word + 1 if marked else index + 1
        if not marked:
            for lemma in comparatives:
                yield index, lemma, None
        if target < len(tokens):
            for group in _groups(tokens, target, budget, bare_cases={'nomn' if marked else 'gent'}):
                for lemma in comparatives:
                    yield index, lemma, group


def trees(tokens, local, *, budget):
    from .parser import Link

    forms = [known_forms(token.surface) for token in tokens]
    comparison_indices = {i for i, variants in enumerate(forms) if any(tag.POS == 'COMP' for _, tag in variants)}
    for tree in local(tokens):
        if any(tree[i].role == 'adverb' and tree[i].head is not None and tree[tree[i].head].rule == 'V2'
               and tree[i].head > i and any(link.role == 'subject' for link in tree[:i])
               for i in comparison_indices):
            continue
        yield tree
    for index, lemma, group in _comparisons(tokens, forms, budget):
        bindings = {}
        if group is not None:
            bindings.update(group.extra)
            bindings[group.noun] = Link('comparison_standard', group.lemma, index, 'CMP.STD', group.case)
            for i in range(index + 1, group.start):
                if tokens[i].surface == ',':
                    bindings[i] = Link('punctuation', ',', index, 'CMP.COMMA')
                else:
                    bindings[i] = Link('comparison_marker', 'чем', group.noun, 'CMP.MARK')
        bindings[index] = Link('predicate', lemma, None, 'V.CMP')
        for subj, variants in enumerate(forms):
            if subj in bindings:
                continue
            for subject, tag in variants:
                if tag.POS in ('NOUN', 'NPRO') and tag.case == 'nomn':
                    personal = bindings.copy()
                    personal[subj] = Link('subject', subject, index, 'S1')
                    yield from _decorated(tokens, forms, personal, [(subj, tag)], index, tag, True)
        if group is None:
            continue
        kept = [i for i in range(len(tokens)) if i not in bindings]
        if not any(tag.POS == 'VERB' for i in kept for _, tag in forms[i]):
            continue
        for base in local(tuple(tokens[i] for i in kept)):
            for host, link in zip(kept, base):
                if link.role != 'predicate' or not any(
                        word == link.lemma and tag.POS == 'VERB' for word, tag in forms[host]):
                    continue
                expanded = dict(bindings)
                expanded[index] = Link('comparative_adverb', lemma, host, 'CMP.ADV')
                for i, item in zip(kept, base):
                    changes = {field: kept[value] for field in ('head', 'controller', 'antecedent', 'coord_head', 'shared_agent', 'shared_object')
                               if (value := getattr(item, field)) is not None}
                    expanded[i] = replace(item, **changes)
                yield tuple(expanded[i] for i in range(len(tokens)))
