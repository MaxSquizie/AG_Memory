from dataclasses import replace
from itertools import product

from .morphology import from_tag
from .nominal_groups import _groups
from .rules import known_forms


ADDITIVE = {'и', 'а', 'но'}
ALTERNATIVE = {'или', 'либо'}
REFERENCES = ('head', 'controller', 'antecedent', 'coord_head', 'shared_agent', 'shared_object')


def _restore(tree, kept, size):
    restored = [None] * size
    for i, link in zip(kept, tree):
        refs = {key: kept[value] for key in REFERENCES if (value := getattr(link, key)) is not None}
        restored[i] = replace(link, **refs)
    return restored


def modals(tokens, base):
    yield from base(tokens)
    for i, token in enumerate(tokens):
        for lemma, short in known_forms(token.surface):
            if lemma not in {'должный', 'обязанный'} or short.POS != 'ADJS':
                continue
            copulas = []
            for j, other in enumerate(tokens):
                if j == i:
                    continue
                if any(form == 'быть' and tag.POS == 'VERB' and tag.mood == 'indc'
                       and tag.tense == 'past' and tag.number == short.number
                       and (short.number != 'sing' or not short.gender or tag.gender == short.gender)
                       for form, tag in known_forms(other.surface)):
                    copulas.append(j)
            if not copulas:
                copulas.append(None)
            for copula in copulas:
                kept = tuple(j for j in range(len(tokens)) if j != copula)
                modal = kept.index(i)
                for surface in (('могут', 'можем', 'можете') if short.number == 'plur' else ('может', 'могу', 'можешь')):
                    words = tuple(replace(tokens[j], surface=surface) if j == i else tokens[j] for j in kept)
                    for tree in base(words):
                        if tree[modal].role != 'predicate' or tree[modal].lemma != 'мочь':
                            continue
                        subjects = [j for j, part in enumerate(tree) if part.role == 'subject' and part.head == modal]
                        if not subjects or not any(part.role == 'infinitive' and part.head == modal for part in tree):
                            continue
                        j = subjects[0]
                        source_subject = kept[j]
                        if not any(noun == tree[j].lemma and tag.case == 'nomn' and tag.number == short.number
                                   and (not short.gender or not tag.gender or short.gender == tag.gender or
                                        'Ms-f' in tag)
                                   for noun, tag in known_forms(tokens[source_subject].surface)):
                            continue
                        restored = _restore(tree, kept, len(tokens))
                        restored[i] = replace(restored[i], lemma=lemma, rule='V2', morphology=from_tag(short))
                        if copula is not None:
                            form = next(tag for word, tag in known_forms(tokens[copula].surface)
                                        if word == 'быть' and tag.POS == 'VERB' and tag.tense == 'past'
                                        and tag.number == short.number)
                            from .parser import Link
                            restored[copula] = Link('copula', 'быть', i, 'V2.COP', morphology=from_tag(form))
                        yield tuple(restored)

def _subjects(tokens, local, budget):
    from .parser import Link

    for i in range(len(tokens)):
        for group in _groups(tokens, i, budget, bare_cases=('nomn',)):
            if not any(link.role == 'nominal_conjunct' for _, link in group.extra):
                continue
            if any(link.role == 'coordinator' and link.lemma != 'и' for _, link in group.extra):
                continue
            kept = (*range(i), group.noun, *range(group.end, len(tokens)))
            proxy = replace(tokens[group.noun], surface='они')
            for tree in local(tuple(proxy if j == group.noun else tokens[j] for j in kept)):
                if tree[i].role != 'subject':
                    continue
                restored = _restore(tree, kept, len(tokens))
                restored[group.noun] = Link('subject', group.lemma, restored[group.noun].head, 'S1', case='nomn')
                for j, link in group.extra:
                    restored[j] = link
                yield tuple(restored)


def _members(tokens, start, pos):
    i = start
    while i < len(tokens):
        if i != start:
            if tokens[i].surface.casefold() not in ADDITIVE | ALTERNATIVE or i + 1 >= len(tokens):
                return
            i += 1
        if not any(tag.POS == pos for _, tag in known_forms(tokens[i].surface)):
            return
        if i > start:
            yield tuple(range(start, i + 1, 2))
        i += 1


def _attributes(tokens, local, members):
    from .parser import Link

    noun = members[-1] + 1
    if noun >= len(tokens):
        return
    kept = (*range(members[0]), *range(noun, len(tokens)))
    for tree in local(tuple(tokens[j] for j in kept)):
        link = tree[members[0]]
        if link.role not in ('subject', 'object', 'governed'):
            continue
        case = link.case or {'subject': 'nomn', 'object': 'accs'}.get(link.role)
        for lemma, tag in known_forms(tokens[noun].surface):
            if lemma != link.lemma or tag.POS != 'NOUN' or tag.case != case:
                continue
            options = [[(adj, form) for adj, form in known_forms(tokens[j].surface)
                        if form.POS == 'ADJF' and form.case == case and
                        (not form.animacy or not tag.animacy or form.animacy == tag.animacy) and
                        (form.number == 'plur' and tag.number == 'plur' or
                         form.number == 'sing' and form.gender == tag.gender)] for j in members]
            for selection in product(*options):
                if len({form.number for _, form in selection}) != 1:
                    continue
                restored = _restore(tree, kept, len(tokens))
                for j, (adj, form) in zip(members, selection):
                    restored[j] = Link('attribute', adj, noun, 'A1', morphology=from_tag(form))
                    if j != members[0]:
                        marker = tokens[j - 1].surface.casefold()
                        restored[j - 1] = Link('coordinator', marker, j, 'A.COORD',
                                               scope='alternative' if marker in ALTERNATIVE else None)
                yield tuple(restored)


def _infinitives(tokens, local, members):
    from .parser import Link

    first, last = members[0], members[-1]
    kept = (*range(first + 1), *range(last + 1, len(tokens)))
    for tree in local(tuple(tokens[j] for j in kept)):
        anchor = tree[first]
        future = anchor.rule == 'V.FUT'
        if not future and anchor.role != 'infinitive':
            continue
        objects = [kept[i] for i, link in enumerate(tree) if link.role == 'object' and link.head == first]
        options = [[(lemma, from_tag(tag)) for lemma, tag in known_forms(tokens[j].surface)
                    if tag.POS == 'INFN' and (not future and anchor.scope != 'phase' or tag.aspect == 'impf')
                    and (j != last or not objects or tag.transitivity == 'tran')] for j in members[1:]]
        for selection in product(*options):
            restored = _restore(tree, kept, len(tokens))
            for j, (lemma, form) in zip(members[1:], selection):
                marker = tokens[j - 1].surface.casefold()
                if future:
                    form = replace(form, **{k: getattr(anchor.morphology, k) for k in ('tense', 'person', 'number', 'mood')})
                restored[j] = Link('clause_conjunct' if future else 'infinitive', lemma,
                                   first if future else restored[first].head, 'V.FUT' if future else 'I.COORD',
                                   controller=restored[first].controller, scope=anchor.scope, morphology=form)
                restored[j - 1] = Link('clause_marker' if future else 'coordinator', marker, j, 'I.MARK',
                                       scope='alternative' if marker in ALTERNATIVE else None)
                if marker in ALTERNATIVE and future:
                    restored[first] = replace(restored[first], scope='alternative')
            for j in objects:
                restored[j] = replace(restored[j], head=last)
            yield tuple(restored)


def trees(tokens, local, *, budget):
    from .parser import AnalysisBudgetExceeded

    remaining = budget

    def bounded(candidates):
        nonlocal remaining
        for tree in candidates:
            remaining -= 1
            if remaining < 0:
                raise AnalysisBudgetExceeded('COORDINATION_BUDGET')
            yield tree

    def attributes(part):
        yield from local(part)
        for start in range(len(part)):
            for members in _members(part, start, 'ADJF'):
                yield from bounded(_attributes(part, local, members))

    def subjects(part):
        yield from attributes(part)
        yield from bounded(_subjects(part, attributes, budget))

    if not any(t.surface.casefold() in ADDITIVE | ALTERNATIVE for t in tokens):
        yield from local(tokens)
        return
    yield from subjects(tokens)
    for start in range(len(tokens)):
        for members in _members(tokens, start, 'INFN'):
            yield from bounded(_infinitives(tokens, subjects, members))


def bindings(tree):
    resolved = list(tree)
    for i, link in enumerate(tree):
        if link.role != 'clause_conjunct' or link.rule == 'GAP' or link.head is None:
            continue
        own = [j for j, part in enumerate(tree) if part.role == 'subject' and part.head == i]
        if own or link.implicit_subject not in (None, 'unresolved'):
            continue
        siblings = [j for j in range(link.head + 1, i)
                    if tree[j].role == 'clause_conjunct' and tree[j].head == link.head]
        previous = siblings[-1] if siblings else link.head
        actors = [j for j, part in enumerate(tree) if part.role == 'subject' and part.head == previous]
        actor = next(iter(actors), resolved[previous].controller)
        if actor is None:
            continue
        actor_form = tree[actor].morphology
        action = link.morphology
        plural = any(part.role == 'nominal_conjunct' and part.head == actor for part in tree)
        if actor_form and action:
            number = 'plur' if plural else actor_form.number
            if action.number and number and action.number != number:
                continue
            if number == 'sing' and action.gender and actor_form.gender and action.gender != actor_form.gender:
                continue
            if action.person and action.person != (actor_form.person or '3per'):
                continue
        resolved[i] = replace(link, controller=actor, implicit_subject=None)
    return tuple(resolved)


def object_variants(tree, *, budget):
    choices = []
    for i, link in enumerate(tree):
        if link.morphology is None or link.morphology.transitivity != 'tran':
            continue
        if any(part.role == 'object' and part.head == i for part in tree):
            continue
        j = i
        while j + 2 < len(tree):
            marker, following = tree[j + 1:j + 3]
            if marker.lemma not in ADDITIVE or marker.head != j + 2:
                break
            if not (following.role == 'clause_conjunct' and following.controller is not None
                    and following.head in (i, link.head) or
                    following.rule == 'I.COORD' and following.head == link.head
                    and following.controller == link.controller):
                break
            j += 2
            objects = [k for k, part in enumerate(tree) if part.role == 'object' and part.head == j]
            if objects:
                if len(objects) == 1 and objects[0] > j:
                    choices.append((i, objects[0]))
                break
    count = 1 << len(choices)
    if count > budget:
        from .parser import AnalysisBudgetExceeded
        raise AnalysisBudgetExceeded('SHARED_OBJECT_BUDGET')
    for mask in range(count):
        result = list(tree)
        for bit, (predicate, obj) in enumerate(choices):
            if mask & (1 << bit):
                result[predicate] = replace(tree[predicate], shared_object=obj)
        yield tuple(result)


def projection_members(rows, root):
    if rows[root]['assertion_status'] not in ('asserted', 'negated') or rows[root].get('scope') not in (None, 'negated'):
        return ()
    members = [root]
    for i, row in enumerate(rows):
        if row['role'] != 'clause_conjunct' or row['head'] != root:
            continue
        markers = [m for m in rows if m['role'] == 'clause_marker' and m['head'] == i]
        if (row['assertion_status'] not in ('asserted', 'negated') or row.get('scope') not in (None, 'negated') or
                row['rule'] == 'GAP' or
                not markers or any(m['lemma'] not in ADDITIVE for m in markers)):
            return ()
        members.append(i)
    return members if len(members) > 1 else ()


def project(rows, members, target):
    if rows[target]['assertion_status'] != 'asserted':
        return None
    children = [[] for _ in rows]
    for i, row in enumerate(rows):
        if row['head'] is not None:
            children[row['head']].append(i)
    row = rows[target]
    attachments = {i for i in children[target] if i not in members and
                   rows[i]['role'] not in ('punctuation', 'clause_marker')}
    if row.get('controller') is not None:
        attachments.add(row['controller'])
    if target != members[0] and row['rule'] == 'V.FUT':
        attachments.update(i for i in children[members[0]] if rows[i]['role'] == 'auxiliary')
    if row.get('shared_object') is not None:
        attachments.add(row['shared_object'])
    nodes = sorted(attachments)
    for i in nodes:
        nodes.extend(children[i])
    indices = sorted({target, *nodes})
    mapping = {original: i for i, original in enumerate(indices)}
    projected = []
    for i in indices:
        part = dict(rows[i])
        part.pop('shared_object', None)
        if i == target:
            part.update(head=None, role='predicate', controller=None)
        elif i in attachments:
            part['head'] = target
        for key in REFERENCES:
            value = part.get(key)
            if value is not None:
                if value not in mapping:
                    return None
                part[key] = mapping[value]
        projected.append(part)
    return projected, mapping[target]
