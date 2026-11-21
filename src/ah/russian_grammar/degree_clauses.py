from dataclasses import replace

from .morphology import PREDICATE_ROLES, from_tag
from .rules import known_forms


PAIRS = {
    'когда': ('time', {'тогда'}),
    'сколько': ('amount', {'столько'}),
    'что': ('degree_result', {'так', 'настолько'}),
}


def anchors(tree, marker, governor):
    if marker not in PAIRS:
        return
    _, anchors = PAIRS[marker]
    for i, link in enumerate(tree):
        if not link or link.lemma not in anchors or link.role not in ('adverb', 'numeral'):
            continue
        owner = link.head
        while owner is not None and owner != governor and tree[owner].role not in PREDICATE_ROLES:
            owner = tree[owner].head
        if owner == governor:
            yield i


def bind(tree, marker, child, host, form):
    relation, _ = PAIRS[form]
    links = list(tree)
    if form == 'сколько':
        link = links[marker]
        links[marker] = replace(link, rule='CL.CORRELATE', antecedent=host,
                                quantity_kind='relative' if link.quantity_kind == 'query' else link.quantity_kind)
    else:
        links[marker] = replace(links[marker], role='clause_marker' if form == 'что' else 'adverb',
                                head=child, rule='CL.CORRELATE', scope=None, antecedent=host)
    links[child] = replace(links[child], role='clause_relative', head=host, rule='CL.REL',
                           scope=links[child].scope or relation)
    return tuple(links)


def centered_quantity(tokens, outside, outer, noun, inside, parse):
    from .parser import Link
    from .utterances import _map, _root

    counters = [outside[i] for i, item in enumerate(outer) if item.role == 'numeral' and
                item.lemma == 'столько' and item.head == noun and outside[i] < inside[0]]
    if not counters:
        return
    for child in parse(tuple(tokens[i] for i in inside)):
        if child[0].quantity_kind != 'query' or child[0].lemma != 'сколько':
            continue
        root = inside[_root(child)]
        merged = _map(outer, outside) | _map(child, inside)
        for i in (inside[0] - 1, inside[-1] + 1):
            if i not in merged:
                merged[i] = Link('punctuation', ',', root, 'CL.PUNCT')
        joined = tuple(merged[i] for i in range(len(tokens)))
        for anchor in counters:
            yield bind(joined, inside[0], root, anchor, 'сколько')


def concessive_adverbs(tokens, parse):
    from .adjuncts import QUESTIONS
    from .clauses import _preposed_splits
    from .modifiers import _apply_particles
    from .parser import Link
    from .utterances import _map, _root

    words = tuple(t.surface.casefold() for t in tokens)
    if 'ни' not in words:
        return
    for marker, word in enumerate(words):
        if word not in QUESTIONS:
            continue
        start = marker - int(marker > 0 and words[marker - 1] == ',')
        for ni in range(marker + 1, len(tokens)):
            if words[ni] == ',':
                break
            if words[ni] != 'ни':
                continue
            spans = ((len(words), 0),) if marker else _preposed_splits(words, ni + 1)
            for end, resume in spans:
                modal = [i for i in range(marker + 1, end) if words[i] in ('бы', 'б')]
                inner = tuple(j for j in range(marker, end) if j != ni and j not in modal)
                outer = tuple(range(start)) if marker else tuple(range(resume, len(tokens)))
                if not inner or not outer:
                    continue
                for child in parse(tuple(tokens[i] for i in inner)):
                    predicate = _root(child)
                    verb = child[predicate]
                    form = verb.morphology
                    if (child[0].role != 'adverb' or child[0].head != predicate or
                            form is None or form.pos != 'VERB' or inner[predicate] <= ni):
                        continue
                    root = inner[predicate]
                    dependent = _map(child, inner)
                    neighbor = dependent.get(ni + 1)
                    if not neighbor or (ni + 1 != root and not (
                            neighbor.role == 'adverb' and neighbor.head == root)):
                        continue
                    if modal and not _apply_particles(words, dependent, {}, modal):
                        continue
                    conditional = bool(modal) or form.mood == 'impr' or form.tense == 'futr'
                    relation = 'concessive_condition' if conditional else 'concession'
                    for matrix in parse(tuple(tokens[i] for i in outer)):
                        host = outer[_root(matrix)]
                        joined = dependent | _map(matrix, outer)
                        joined[marker] = replace(joined[marker], role='clause_marker', rule='CL.MARK', scope=relation)
                        joined[ni] = Link('particle', 'ни', marker, 'CL.FOCUS')
                        joined[root] = replace(joined[root], role='clause_adverbial', head=host,
                                               rule='CL.ADV', scope=dependent[root].scope or relation)
                        for i in (*range(start, marker), *range(end, resume)):
                            joined[i] = Link('punctuation', words[i], root, 'CL.PUNCT')
                        yield tuple(joined[i] for i in range(len(tokens)))


def _scales(tokens, positions, local):
    from .parser import Link
    from .utterances import _map, _root

    local_tokens = tuple(tokens[i] for i in positions)
    for tree in local(local_tokens):
        mapped = _map(tree, positions)
        for i in positions:
            if mapped[i].rule in ('V.CMP', 'CMP.ADV'):
                yield mapped, positions[_root(tree)], i
    for i in positions:
        variants = [(lemma, tag) for lemma, tag in known_forms(tokens[i].surface) if tag.POS == 'COMP']
        if not variants:
            continue
        rest = tuple(j for j in positions if j != i)
        if not rest:
            continue
        for tree in local(tuple(tokens[j] for j in rest)):
            predicate = _root(tree)
            if not any(tag.POS == 'VERB' and lemma == tree[predicate].lemma
                       for lemma, tag in known_forms(tokens[rest[predicate]].surface)):
                continue
            mapped = _map(tree, rest)
            for lemma, tag in variants:
                yield mapped | {i: Link('comparative_adverb', lemma, rest[predicate], 'CMP.ADV',
                                        morphology=from_tag(tag))}, rest[predicate], i


def proportional(tokens, local, spend):
    from .parser import Link

    if tokens[0].surface.casefold() != 'чем':
        return
    for marker in range(2, len(tokens) - 1):
        if tokens[marker].surface.casefold() != 'тем':
            continue
        comma = tokens[marker - 1].surface == ','
        split = marker - int(comma)
        for left, child, first in _scales(tokens, tuple(range(1, split)), local):
            for right, host, second in _scales(tokens, tuple(range(marker + 1, len(tokens))), local):
                spend()
                mapped = left | right
                mapped[0] = Link('clause_marker', 'чем', first, 'CL.SCALE', antecedent=marker)
                mapped[marker] = Link('clause_marker', 'тем', second, 'CL.SCALE')
                mapped[child] = replace(mapped[child], role='clause_adverbial', head=host,
                                        rule='CL.PROPORTIONAL', scope=mapped[child].scope or 'proportional')
                mapped[host] = replace(mapped[host], scope=mapped[host].scope or 'proportional')
                if comma:
                    mapped[split] = Link('punctuation', ',', child, 'CL.PUNCT')
                yield tuple(mapped[i] for i in range(len(tokens)))


def partitions(trees, tokens, text):
    from .parser import _span_label
    from .probe import Probe

    if not any(link.rule == 'CL.CORRELATE' or link.scope == 'concession' for tree in trees for link in tree):
        return
    for i in range(len(tokens)):
        links = [tree[i] for tree in trees]
        rules = {link.rule for link in links}
        word = _span_label(tokens, i)
        if rules == {'V1', 'V2'}:
            verbs = {link.lemma for link in links if link.rule == 'V1'}
            adjectives = {link.lemma for link in links if link.rule == 'V2'}
            if len(verbs) == len(adjectives) == 1:
                verb, = verbs
                adjective, = adjectives
                if any(lemma == adjective and tag.POS == 'ADJS' for lemma, tag in known_forms(tokens[i].surface)):
                    options = (word, 'только признак')
                    question = (f'Каким словом названо действие «{verb}»? Выберите «{word}», если это глагол. '
                                f'Если «{word}» здесь означает признак «{adjective}», выберите «только признак».')
                    yield Probe(question, options, text), [options[link.rule == 'V2'] for link in links]
        if rules == {'CL.MARK'} and {link.scope for link in links} == {None, 'concession'}:
            head = {link.head for link in links}
            if len(head) == 1:
                child = _span_label(tokens, head.pop())
                options = (child, 'нет такого обстоятельства')
                question = (f'Какое действие после «{word}» обозначает обстоятельство, вопреки которому '
                            'произошло главное событие? Если говорящий поправляет свою мысль, '
                            'выберите «нет такого обстоятельства».')
                yield Probe(question, options, text), [child if link.scope == 'concession' else options[1]
                                                      for link in links]
        if rules == {'CL.MARK', 'CL.CORRELATE'} and any(link.lemma == 'когда' for link in links):
            anchors = {link.antecedent for link in links if link.rule == 'CL.CORRELATE'}
            if len(anchors) == 1 and None not in anchors:
                anchor, = anchors
                heads = [tree[anchor].head for tree in trees]
                if None not in heads and len(set(heads)) > 1:
                    labels = [_span_label(tokens, head) for head in heads]
                    question = f'К какому действию в предложении относится слово «{_span_label(tokens, anchor)}»?'
                    yield Probe(question, tuple(dict.fromkeys(labels)), text), labels
        if rules == {'CL.CORRELATE', 'CL.REF'}:
            if all(link.antecedent is not None for link in links):
                labels = [_span_label(tokens, link.antecedent) for link in links]
                if len(set(labels)) > 1:
                    question = (f'Что поясняет часть после «{word}»? Если указана степень, выберите слово, '
                                'которое её обозначает. Если речь о предшествующем событии, выберите действие.')
                    yield Probe(question, tuple(dict.fromkeys(labels)), text), labels
