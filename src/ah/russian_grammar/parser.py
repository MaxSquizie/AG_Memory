"""Incremental Russian grammar analysis and selection among complete structures."""
from collections import Counter
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, replace
from itertools import product

from .detached_prepositions import extent as group_extent
from .morphology import Morphology, feature_choices
from .nominal_chart import NominalChart, NominalStep
from .prepositions import CASE_NAMES, FORMS, GOVERNMENT, PREFIXES, TOKEN, group_heads
from .probe import MAX_WORD_CHOICES, FocusChoice, Probe
from . import modifier_focus
from .recovery import CaseRecovery, SpellingRecovery
from .rules import Reading, known_forms, name_continuations, plain_person_reference, preposition_reading, attribute_agrees, readings, subject_agrees



RULE_FOR_ROLE = {
    'name_part': 'NAME', 'predicate': 'V1', 'subject': 'S1', 'object': 'O1',
    'attribute': 'A1', 'coordinator': 'C1', 'duration': 'T1',
    'prep_part': 'P1', 'preposition': 'P2', 'governed': 'P1', 'group_attribute': 'A1', 'post_attribute': 'A1',
}


@dataclass(frozen=True)
class Occurrence:
    surface: str
    start: int
    end: int


@dataclass(frozen=True)
class Link:
    role: str
    lemma: str
    head: int | None  # token index
    rule: str
    case: str | None = None
    controller: int | None = None
    scope: str | None = None
    antecedent: int | None = None
    event_view: str | None = None
    recovery: CaseRecovery | SpellingRecovery | None = None
    morphology: Morphology | None = None
    implicit_subject: str | None = None
    quantity: str | None = None
    quantity_kind: str | None = None
    quantity_modifier: str | None = None
    coord_head: int | None = None
    shared_agent: int | None = None
    shared_object: int | None = None
    ellipsis_source: int | None = None


class AnalysisBudgetExceeded(Exception):
    pass


class NominalBudgetExceeded(AnalysisBudgetExceeded):
    pass


@dataclass(frozen=True)
class ProbeStep:
    before: int
    after: int
    outcome: str
    domain: str = 'trees'


@dataclass(frozen=True)
class Result:
    source: str
    status: str
    reason: str
    tokens: tuple[Occurrence, ...]
    analyses: tuple[tuple[Link, ...], ...] = ()
    probes: tuple[Probe, ...] = ()
    steps: tuple[ProbeStep, ...] = ()
    confirmed_focus: tuple[FocusChoice, ...] = ()


@dataclass(frozen=True)
class Prefix:
    words: tuple[Reading, ...] = ()
    subject: int | None = None
    predicate: int | None = None
    objects: tuple[int, ...] = ()
    coordinator: int | None = None
    # Pairs enter this set only upon reading the later endpoint.
    pairs: tuple[tuple[int, int], ...] = ()

    open_preposition: int | None = None
    groups: tuple[tuple[int, int], ...] = ()

    def next_readings(self, surface: str) -> Iterator[Reading]:
        if self.open_preposition is not None:
            start = self.open_preposition
            if self.words[start].role == 'prep_prefix':
                phrase = ' '.join([*(word.lemma for word in self.words[start:]), surface.lower()])
                if phrase in PREFIXES:
                    yield preposition_reading(surface.lower(), 'prep_part')
                if phrase in FORMS:
                    yield preposition_reading(FORMS[phrase], 'prep_end')
            else:
                yield from readings(surface, self.words[start].lemma)
            return
        yield from readings(surface)
        start = len(self.words) - 1
        while start >= 0 and self.words[start].role == 'name_part':
            start -= 1
        if start >= 0:
            head = self.words[start]
            if head.name_type and head.role in {'subject', 'object', 'governed'} and head.number == 'sing':
                yield from name_continuations(surface, self.words[start:])
        if self.words and self.words[-1].role in {'governed', 'post_attribute'}:
            start, noun = self.groups[-1]
            for variant in readings(surface, self.words[start].lemma):
                if variant.role == 'group_attribute' and attribute_agrees(variant, self.words[noun]):
                    yield replace(variant, role='post_attribute')

    def extend(self, reading: Reading) -> 'Prefix | None':
        i = len(self.words)
        role = reading.role
        if self.open_preposition is not None:
            start = self.open_preposition
            if role == 'prep_end':
                words = (self.words[:start] + (preposition_reading(reading.lemma, 'preposition'),)
                         + self.words[start+1:] + (preposition_reading(reading.lemma.split()[-1], 'prep_part'),))
                return replace(self, words=words)
            if role in {'prep_part', 'group_attribute'}:
                return replace(self, words=(*self.words, reading))
            if role != 'governed' or not all(attribute_agrees(adj, reading) for adj in self.words[start + 1:]
                                            if adj.role == 'group_attribute'):
                return None
            return replace(self, words=(*self.words, reading), open_preposition=None,
                           groups=(*self.groups, (start, i)))
        if role == 'name_part':
            head = i - 1
            while self.words[head].role == 'name_part':
                head -= 1
            words = self.words
            pairs = self.pairs
            if reading.gender and words[head].gender is None:
                nominal = replace(words[head], gender=reading.gender)
                if head == self.subject and self.predicate is not None and not subject_agrees(nominal, words[self.predicate]):
                    return None
                words = (*words[:head], nominal, *words[head + 1:])
                pairs = tuple(pair for pair in pairs if pair[1] != head)
                pairs += tuple((j, head) for j, word in enumerate(words)
                               if word.role == 'attribute' and attribute_agrees(word, nominal))
            return replace(self, words=(*words, reading), pairs=pairs)
        if role == 'post_attribute':
            return replace(self, words=(*self.words, reading))
        if role in {'preposition', 'prep_prefix'}:
            return replace(self, words=(*self.words, reading), open_preposition=i)
        subject, predicate = self.subject, self.predicate
        objects, coordinator = self.objects, self.coordinator
        pairs = self.pairs
        if role == 'subject':
            if subject is not None or (predicate is not None and not subject_agrees(reading, self.words[predicate])):
                return None
            subject = i
        elif role == 'predicate':
            if predicate is not None or (subject is not None and not subject_agrees(self.words[subject], reading)):
                return None
            if objects and not reading.transitive:
                return None
            predicate = i
        elif role == 'object':
            if len(objects) == 2 or (predicate is not None and not self.words[predicate].transitive):
                return None
            if objects and coordinator is None:
                return None
            objects = (*objects, i)
        elif role == 'duration':
            if any(w.role == 'duration' for w in self.words):
                return None
        elif role == 'coordinator':
            if coordinator is not None or len(objects) != 1:
                return None
            coordinator = i
        if role == 'attribute':
            pairs += tuple((i, j) for j, word in enumerate(self.words)
                           if word.role in {'object', 'subject', 'duration'} and attribute_agrees(reading, word))
        elif role in {'object', 'subject', 'duration'}:
            pairs += tuple((j, i) for j, word in enumerate(self.words)
                           if word.role == 'attribute' and attribute_agrees(word, reading))
        return replace(self, words=(*self.words, reading), subject=subject, predicate=predicate,
                       objects=objects, coordinator=coordinator, pairs=pairs)

    def structures(self) -> Iterator[tuple[Link, ...]]:
        if self.subject is None or self.predicate is None or self.open_preposition is not None:
            return
        if self.coordinator is not None:
            if len(self.objects) != 2:
                return
            first, second = self.objects
            if any(w.role not in {'attribute', 'coordinator', 'name_part'} for w in self.words[first + 1:second]):
                return
        attrs = [i for i, w in enumerate(self.words) if w.role == 'attribute']
        domains = [[host for adj, host in self.pairs if adj == i] for i in attrs]
        for chosen in product(*domains):
            heads = dict(zip(attrs, chosen))
            for i, word in enumerate(self.words):
                if word.role == 'name_part':
                    heads[i] = heads[i - 1] if self.words[i - 1].role == 'name_part' else i - 1
            if self.coordinator is not None:
                heads[self.coordinator] = self.objects[1]
            for attached in group_heads(self.groups, self.words, self.predicate, heads):
                yield tuple(Link('attribute' if w.role in {'group_attribute', 'post_attribute'} else w.role,
                                 w.lemma, None if i == self.predicate else attached.get(i, self.predicate),
                                 RULE_FOR_ROLE[w.role], w.case if w.role == 'governed' else None)
                            for i, w in enumerate(self.words))


def _label_extent(tokens, index, end):
    """Identify a word or phrase in a one-line question, including repeated spans."""
    words = [t.surface.casefold() for t in tokens]
    width = end - index
    others = [j for j in range(len(words) - width + 1)
              if j != index and words[j:j+width] == words[index:end]]
    if not others:
        return index, end
    for radius in range(1, len(tokens)):
        for left, right in ((0, radius), (radius, 0),
                            (min(index, radius), min(len(tokens) - end, radius))):
            start, stop = index - left, end + right
            if start < 0 or stop > len(tokens):
                continue
            if any(j >= left and words[j-left:j+width+right] == words[start:stop] for j in others):
                continue
            return start, stop
    raise ValueError('could not distinguish occurrences in the complete sentence')


def _span_label(tokens, index, end=None):
    end = index + 1 if end is None else end
    start, stop = _label_extent(tokens, index, end)
    focus = ' '.join(t.surface for t in tokens[index:end])
    if (start, stop) == (index, end):
        return focus
    return ' '.join([*(t.surface for t in tokens[start:index]), f'[{focus}]',
                     *(t.surface for t in tokens[end:stop])])


def _agent_extent(tree, head):
    members = {head}
    pending = [head]
    while pending:
        parent = pending.pop()
        for j, link in enumerate(tree):
            if link.head == parent and link.role in {'name_part', 'nominal_conjunct', 'coordinator',
                                                       'coordinator_part', 'attribute', 'possessive', 'punctuation'}:
                members.add(j)
                pending.append(j)
    start, end = min(members), max(members) + 1
    return (start, end) if end - start == len(members) else (head, head + 1)


def _attachment_context(text, tokens, analyses, hosts, start, end):
    # Include the phrase and each candidate, plus the context needed to identify repeats.
    spans = [_label_extent(tokens, start, end)]
    spans.extend(_label_extent(tokens, j, j + 1) for j in set(hosts))
    needed = {j for lo, hi in spans for j in range(lo, hi)}
    children = {}
    for tree in analyses:
        for j, link in enumerate(tree):
            children.setdefault(link.head, set()).add(j)
    pending = list(needed)
    while pending:
        for child in children.get(pending.pop(), ()):
            if child in needed:
                continue
            if (child not in children and all(tree[child].role == 'subject' for tree in analyses)
                    and plain_person_reference(tokens[child].surface)):
                continue
            needed.add(child)
            pending.append(child)
    return text[tokens[min(needed)].start:tokens[max(needed)].end]


def _clause_context(text, tokens, trees, focus, anchors):
    spans = [_label_extent(tokens, i, i + 1) for i in {focus, *anchors} if i is not None]
    clause_roles = {'predicate', 'clause_complement', 'clause_adverbial', 'clause_conjunct', 'clause_relative'}
    for tree in trees:
        root = focus
        while tree[root].role not in clause_roles:
            root = tree[root].head
        included = {root}
        children = {}
        for j, link in enumerate(tree):
            if link.role not in clause_roles and link.role != 'clause_marker' and link.rule != 'CL.PUNCT':
                children.setdefault(link.head, []).append(j)
        pending = [root]
        while pending:
            child = pending.pop()
            included.add(child)
            pending.extend(children.get(child, ()))
        spans.append((min(included), max(included) + 1))
    start, end = min(lo for lo, _ in spans), max(hi for _, hi in spans)
    return text if (start, end) == (0, len(tokens)) else text[tokens[start].start:tokens[end - 1].end]


def _qualification_probe(tokens, start, end, host, context):
    phrase = _span_label(tokens, start, end)
    question = f'Какое сочетание передаёт оговорку к самому сообщению о действии «{_span_label(tokens, host)}»?'
    return Probe(question, (phrase, 'нет такого сочетания'), context)


def _partitions(analyses, tokens, text):
    # Each tree has exactly one answer. Equal answers keep all matching trees.
    def word_choice(question, indices, context=text):
        candidates = sorted({i for i in indices if i is not None})
        labels = {i: _span_label(tokens, i) for i in candidates}
        if None in indices:
            labels[None] = 'no such word'
        return Probe(question, tuple(labels.values()), context), [labels[i] for i in indices]

    from . import clause_series, nominal_definitions, nominal_mentions, nominal_predicates, temporal_groups
    from .morphology import NOMINAL_ROLES
    yield from clause_series.partitions(analyses, tokens, text)
    yield from nominal_definitions.partitions(analyses, tokens, text)
    yield from nominal_mentions.partitions(analyses, tokens, text)
    yield from temporal_groups.partitions(analyses, tokens, text)
    yield from nominal_predicates.partitions(analyses, tokens, text)
    yield from modifier_focus.partitions(analyses, tokens, text)

    predicates = [next(i for i, link in enumerate(a) if link.head is None) for a in analyses]
    if len(set(predicates)) > 1:
        yield word_choice('Which word is the main predicate?', predicates)
        return
    for i in range(1, len(tokens)):
        links = [tree[i] for tree in analyses]
        roles = {link.role for link in links}
        if 'name_part' not in roles or not roles.intersection({'recipient', 'oblique', 'object'}):
            continue
        if not all(tree[i - 1].role == 'subject' and
                   (link.role != 'name_part' or link.head == i - 1) for tree, link in zip(analyses, links)):
            continue
        full, short = _span_label(tokens, i - 1, i + 1), _span_label(tokens, i - 1)
        verb = _span_label(tokens, predicates[0])
        yield Probe(f'Какими словами назван тот, кто совершил действие «{verb}»?', (full, short), text), [
            full if link.role == 'name_part' else short for link in links]
        return
    verb = _span_label(tokens, predicates[0])
    subjects = [next((i for i, link in enumerate(a) if link.role == 'subject' and link.head == predicates[0]), None) for a in analyses]
    if len(set(subjects)) > 1:
        lemmas = [tree[predicates[0]].lemma for tree in analyses]
        for lemma in sorted(set(lemmas))[:-1]:
            context = _clause_context(text, tokens, analyses, predicates[0], subjects)
            yield word_choice(f'Copy «{verb}» if its dictionary form is «{lemma}». Otherwise choose “no such word”.',
                              [predicates[0] if value == lemma else None for value in lemmas], context)
        yield word_choice(f'Which word is the subject of «{verb}»?', subjects)
    for i in range(len(tokens)):
        links = [tree[i] for tree in analyses]
        roles = {link.role for link in links}
        if 'genitive_modifier' in roles and roles <= NOMINAL_ROLES | {'genitive_modifier'}:
            heads = [link.head for link in links]
            if None not in heads and len(set(heads)) > 1:
                context = _attachment_context(text, tokens, analyses, heads, i, i + 1)
                yield word_choice(f'К какому слову относится «{_span_label(tokens, i)}»?', heads, context)
        if roles == {'oblique', 'recipient'} and all(a[i].case == 'datv' for a in analyses):
            hosts = {a[i].head for a in analyses}
            if len(hosts) == 1 and None not in hosts:
                host, = hosts
                yield word_choice(f'Кому адресовано действие «{_span_label(tokens, host)}»? '
                                  'Выберите участника, если он получатель.',
                                  [i if a[i].role == 'recipient' else None for a in analyses],
                                  _clause_context(text, tokens, analyses, i, (host,)))
        if roles == {'clause_conjunct'} or roles == {'clause_relative'}:
            subjects = [next((j for j, dep in enumerate(tree) if dep.head == i and dep.role == 'subject'),
                             tree[i].controller) for tree in analyses]
            if None not in subjects and len(set(subjects)) > 1:
                yield word_choice(f'Какое слово служит подлежащим при «{_span_label(tokens, i)}»?', subjects,
                                  _clause_context(text, tokens, analyses, i, subjects))
        if roles == {'governed', 'nominal_conjunct'} and all(
                link.role == 'governed' or link.rule == 'P.COORD.UNMARKED' for link in links):
            sample = next(tree for tree in analyses if tree[i].role == 'nominal_conjunct')
            start = next(j for j, link in enumerate(sample) if link.role == 'case' and link.head == i)
            phrase = _span_label(tokens, start, i + 1)
            options = (phrase, 'нет такого продолжения')
            previous = _span_label(tokens, start - 1)
            question = f'Какие слова продолжают перечисление после «{previous}»?'
            hosts = {tree[start].head for tree in analyses if tree[i].role == 'governed'}
            context = _attachment_context(text, tokens, analyses, hosts | {start - 1}, start, i + 1)
            yield Probe(question, options, context), [phrase if link.role == 'nominal_conjunct' else options[1]
                                                       for link in links]
            return
        if roles == {'oblique', 'experiencer'} and any(a[i].scope == 'age_holder' for a in analyses):
            focus = _span_label(tokens, i)
            options = (focus, 'нет такого слова')
            yield Probe(f'Какое слово обозначает того или то, чей возраст указан в этой части предложения? '
                        f'Выберите «{focus}», если речь идёт о его возрасте.', options, text), [
                            options[0] if a[i].scope == 'age_holder' else options[1] for a in analyses]
        if all(tree[i].rule == 'N.MEASURE' for tree in analyses):
            hosts = [tree[i].head for tree in analyses]
            if len(set(hosts)) > 1:
                yield word_choice(f'К какому слову относится указание меры со словом «{_span_label(tokens, i)}»?', hosts)
        if roles == {'apposition'} and all(tree[i].rule == 'PAREN.EXPL' for tree in analyses):
            hosts = [tree[i].head for tree in analyses]
            if len(set(hosts)) > 1:
                bounds = [j for j, node in enumerate(analyses[0]) if node.head == i and node.rule == 'PAREN.BOUND']
                if len(bounds) == 2:
                    phrase = text[tokens[bounds[0]].end:tokens[bounds[1]].start]
                    yield word_choice(f'К какому слову относится пояснение «{phrase}»?', hosts)
        if roles in ({'attribute'}, {'participle'}):
            hosts = [a[i].head for a in analyses]
            if len(set(hosts)) > 1:
                context = _attachment_context(text, tokens, analyses, hosts, i, i + 1) if roles == {'participle'} else text
                question = f'Какое слово характеризует определение «{_span_label(tokens, i)}»?'
                if roles == {'participle'}:
                    groups = {tuple(j for j, link in enumerate(tree) if j == i or link.coord_head == i)
                              for tree in analyses}
                    if len(groups) == 1:
                        group, = groups
                        if len(group) > 1:
                            labels = [f'«{_span_label(tokens, j)}»' for j in group]
                            names = ', '.join(labels[:-1]) + ' и ' + labels[-1]
                            question = f'Какое слово характеризуют определения {names}?'
                yield word_choice(question, hosts, context)

    agents = sorted({link.shared_agent for tree in analyses for link in tree if link.shared_agent is not None})
    for agent in agents:
        if not all(tree[agent].role == 'agent' for tree in analyses):
            continue
        readings = [tuple(sorted({tree[agent].head, *(i for i, link in enumerate(tree) if link.shared_agent == agent)}))
                    for tree in analyses]
        distinct = sorted(set(readings), key=lambda group: (len(group), group))
        if len(distinct) > 1:
            labels = {group: ' и '.join(_span_label(tokens, i) for i in group) for group in distinct}
            hosts = {i for group in distinct for i in group}
            nouns = {tree[i].head for tree, group in zip(analyses, readings) for i in group
                     if tree[i].role == 'participle' and tree[i].head is not None}
            extents = {_agent_extent(tree, agent) for tree in analyses}
            start, end = extents.pop() if len(extents) == 1 else (agent, agent + 1)
            context = _attachment_context(text, tokens, analyses, hosts | nouns, start, end).strip(' ,\t\r\n')
            question = (f'Which actions does the text identify «{_span_label(tokens, start, end)}» as performing? '
                        'Choose ? if it is unclear whether the performer is shared.')
            yield Probe(question, tuple(labels.values()), context), [labels[group] for group in readings]

    objects = sorted({link.shared_object for tree in analyses for link in tree if link.shared_object is not None})
    for obj in objects:
        if not all(tree[obj].role == 'object' for tree in analyses):
            continue
        readings = [tuple(sorted({tree[obj].head, *(i for i, link in enumerate(tree) if link.shared_object == obj)}))
                    for tree in analyses]
        distinct = sorted(set(readings), key=lambda group: (len(group), group))
        if len(distinct) > 1:
            labels = {group: ' и '.join(_span_label(tokens, i) for i in group) for group in distinct}
            context = _attachment_context(text, tokens, analyses,
                                          {i for group in distinct for i in group}, obj, obj + 1)
            question = (f'Which actions does the text identify «{_span_label(tokens, obj)}» as an object of? '
                        'Choose ? if it is unclear whether the object is shared.')
            yield Probe(question, tuple(labels.values()), context), [labels[group] for group in readings]

    earlier_attachments = []
    for i in range(len(tokens)):
        if all(a[i].role == 'preposition' for a in analyses):
            boundaries = [max((j for j, link in enumerate(tree) if link.role == 'prep_part' and link.head == i),
                              default=i) + 1 for tree in analyses]
            if len(set(boundaries)) > 1:
                labels = {end: _span_label(tokens, i, end) for end in sorted(set(boundaries))}
                yield (Probe('Which expression functions as the preposition here?', tuple(labels.values()), text),
                        [labels[end] for end in boundaries])
            hosts = [a[i].head for a in analyses]
            scope_readings = {a[i].scope for a in analyses}
            if len(set(hosts)) == 1 and scope_readings == {None, 'qualification'}:
                limits = {group_extent(a, i, external_modifier=True) for a in analyses}
                if len(limits) == 1 and None not in limits:
                    end = limits.pop()
                    probe = _qualification_probe(tokens, i, end, hosts[0], text)
                    yield probe, [probe.options[0] if a[i].scope else probe.options[1] for a in analyses]
            ends = {j for a in analyses for j, link in enumerate(a) if link.role == 'governed' and link.head == i}
            if len(set(hosts)) > 1 and len(ends) == 1:
                noun = ends.pop()
                depends_on_previous = any(
                    len({host for host, prior in zip(hosts, previous) if prior == value}) < len(set(hosts))
                    for previous in earlier_attachments for value in set(previous))
                earlier_attachments.append(hosts)
                undecided_modifier = any(
                    all(tree[j].role == 'attribute' for tree in analyses)
                    and len({tree[j].head for tree in analyses}) > 1
                    and any(tree[j].head == noun for tree in analyses)
                    for j in range(noun + 1, len(tokens)))
                if depends_on_previous or undecided_modifier:
                    continue
                extents = []
                for tree in analyses:
                    end = noun + 1
                    for j in range(noun + 1, len(tree)):
                        anchor = j
                        while tree[anchor].role in {'attribute', 'possessive', 'coordinator', 'nominal_conjunct',
                                                     'case', 'name_part', 'punctuation'}:
                            anchor = tree[anchor].head
                        if anchor != noun:
                            break
                        end = j + 1
                    extents.append(end)
                end = min(extents)
                if all(a[i].rule == 'PP.DETACHED' for a in analyses) or any(a[i].scope == 'qualification' for a in analyses):
                    limits = {group_extent(a, i, external_modifier=True) for a in analyses}
                    if len(limits) == 1 and None not in limits:
                        end = limits.pop()
                has_focus = i > 0 and all(modifier_focus.site(tokens, a, i - 1) for a in analyses)
                if has_focus:
                    limits = [group_extent(a, i, external_modifier=True) for a in analyses]
                    if None not in limits:
                        end = min(limits)
                phrase = _span_label(tokens, i, end).replace(' ,', ',')
                context = _attachment_context(text, tokens, analyses, hosts, i, end)
                question = (f'Какое действие уточняет обстоятельство «{phrase}»?' if has_focus else
                            f'От какого из предложенных слов в этом месте текста задаётся вопрос к сочетанию «{phrase}»? '
                            'Выберите слово, с которым оно связано непосредственно.')
                yield word_choice(question, hosts, context)

    duration_heads = sorted({link.head for tree in analyses for link in tree if link.role == 'duration'})
    for head in duration_heads:
        durations = [next((i for i, link in enumerate(tree) if link.role == 'duration' and link.head == head), None)
                     for tree in analyses]
        if len(set(durations)) > 1:
            yield word_choice(f'Which word tells how long the action «{_span_label(tokens, head)}» lasts?', durations)

    for i in range(len(tokens)):
        links = [tree[i] for tree in analyses]
        if len(set(links)) < 2:
            continue
        roles = {link.role for link in links}
        focus = _span_label(tokens, i)
        if roles == {'coordinator'} and all(link.lemma == 'да' and link.rule == 'PART.COORD' for link in links):
            readings = {'addition': 'да в значении «и»', 'contrast': 'да в значении «но»'}
            if {link.scope for link in links} == set(readings):
                context = _clause_context(text, tokens, analyses, i, [link.head for link in links])
                yield Probe(f'Which reading does «{focus}» have here?', tuple(readings.values()), context), [
                    readings[link.scope] for link in links]
        if roles == {'attribute', 'participle'}:
            heads = [link.head for link in links]
            context = _attachment_context(text, tokens, analyses, heads, i, i + 1)
            quality = 'только признак'
            question = (f'Указывает ли «{focus}» здесь на действие? Если да, выберите «{focus}». '
                        f'Если это только характеристика предмета, выберите «{quality}».')
            yield Probe(question, (focus, quality), context), [
                focus if link.role == 'participle' else quality for link in links]
        if roles == {'agent', 'oblique'} and len({link.head for link in links}) == 1:
            host = links[0].head
            context = _clause_context(text, tokens, analyses, i, (host,))
            question = f'Copy «{focus}» if it names who performed the action «{_span_label(tokens, host)}». Otherwise choose “no such word”.'
            yield word_choice(question, [i if link.role == 'agent' else None for link in links], context)
        if len(roles) == 1 and roles <= {'adverb', 'agent', 'recipient', 'object', 'instrument', 'oblique'}:
            heads = [link.head for link in links]
            if len(set(heads)) > 1 and all(head is not None for head in heads) and any(
                    tree[head].role == 'participle' for tree, head in zip(analyses, heads)):
                context = _attachment_context(text, tokens, analyses, heads, i, i + 1)
                yield word_choice(f'Which action does «{focus}» belong to?', heads, context)
        if len(roles) == 1 and all(link.morphology for link in links):
            moods = [link.morphology.mood for link in links]
            if 'impr' in moods and len(set(moods)) > 1:
                yield word_choice(f'Copy «{focus}» if the speaker is giving an instruction. Otherwise choose “no such word”.',
                                  [i if mood == 'impr' else None for mood in moods], _clause_context(text, tokens, analyses, i, ()))
            tenses = [link.morphology.tense for link in links]
            if set(tenses) == {'pres', 'futr'}:
                yield word_choice(f'Copy «{focus}» if it describes a future action. Otherwise choose “no such word”.',
                                  [i if tense == 'futr' else None for tense in tenses], _clause_context(text, tokens, analyses, i, ()))
        if 'quantity_modifier' in roles and 'preposition' in roles:
            heads = [link.head for link in links]
            context = _clause_context(text, tokens, analyses, i, heads)
            question = f'Copy «{focus}» if it marks an approximate quantity. Otherwise choose “no such word”.'
            yield word_choice(question, [i if link.role == 'quantity_modifier' else None for link in links], context)
        if roles == {'numeral'}:
            heads = [link.head for link in links]
            if len(set(heads)) > 1:
                context = _clause_context(text, tokens, analyses, i, heads)
                ordinal = all(link.quantity_kind == 'ordinal' for link in links)
                question = (f'Which word does «{focus}» put in order?' if ordinal
                            else f'Which word names what «{focus}» counts?')
                yield word_choice(question, heads, context)
            elif heads[0] is not None:
                noun = heads[0]
                relations = [tree[noun] for tree in analyses]
                governors = {link.head for link in relations}
                if len(governors) == 1 and None not in governors and len({link.role for link in relations}) > 1:
                    governor, = governors
                    if any(link.role == 'object' for link in relations):
                        action = _span_label(tokens, governor)
                        context = _clause_context(text, tokens, analyses, noun, (i, governor))
                        label = _span_label(tokens, noun)
                        question = f'Copy «{label}» if it names the direct object of «{action}». Otherwise choose “no such word”.'
                        yield word_choice(question, [noun if link.role == 'object' else None for link in relations], context)
                cases = {link.case for link in relations}
                if len({link.role for link in relations}) == 1 and len(cases) > 1 and None not in cases:
                    split = any(link.rule == 'NUM.SPLIT' for link in links)
                    group = _span_label(tokens, noun) if split else _span_label(tokens, i, noun + 1)
                    description = f'the group counted by «{focus}»' if split else 'the whole phrase'
                    context = _clause_context(text, tokens, analyses, noun, (i,))
                    for case in sorted(cases)[:-1]:
                        question = f'Copy «{group}» if {description} is in the {CASE_NAMES[case]} case. Otherwise choose “no such word”.'
                        yield Probe(question, (group, 'no such word'), context), [
                            group if link.case == case else 'no such word' for link in relations]
        corrected = [link.recovery.corrected if link.recovery else tokens[i].surface for link in links]
        if len(set(corrected)) > 1:
            choices = tuple(dict.fromkeys(corrected))
            yield Probe(f'Which form of «{focus}» fits the sentence here?', choices, text), corrected
        antecedents = [link.antecedent for link in links]
        if all(link.rule == 'CL.NOMREF' for link in links) and len(set(antecedents)) > 1:
            yield word_choice(f'Which word does «{focus}» refer to?', antecedents)
        if roles == {'possessive'} and len(set(antecedents)) > 1:
            context = _clause_context(text, tokens, analyses, i, antecedents)
            yield word_choice(f'Which word does the possessive «{focus}» refer to?', antecedents, context)
        if {link.rule for link in links} == {'CL.MARK', 'CL.REF'}:
            yield word_choice(f'Copy «{focus}» if it refers to a preceding event here. Otherwise choose “no such word”.',
                              [i if link.rule == 'CL.REF' else None for link in links])
        if all(link.rule == 'CL.REF' for link in links):
            if len(set(antecedents)) > 1:
                yield word_choice(f'Which preceding predicate does «{focus}» refer to?', antecedents)
            elif len({link.event_view for link in links}) > 1:
                host = antecedents[0]
                starts = [j for j, link in enumerate(analyses[0]) if link.rule == 'N2' and link.head == host]
                if starts:
                    labels = {'event': _span_label(tokens, host), 'situation': _span_label(tokens, min(starts), host + 1)}
                    question = f'Which expression does «{focus}» refer to here?'
                    context = _clause_context(text, tokens, analyses, i, (min(starts), host))
                    yield Probe(question, tuple(labels.values()), context), [labels[link.event_view] for link in links]
        controllers = [link.controller for link in links]
        if len(roles) == 1 and len(set(controllers)) > 1:
            if roles == {'clause_conjunct'}:
                controllers = [actor if actor is not None else next((j for j, dep in enumerate(tree)
                               if dep.role == 'subject' and dep.head == i), None)
                               for tree, actor in zip(analyses, controllers)]
            context = _clause_context(text, tokens, analyses, i, controllers)
            if len(set(controllers)) > 1:
                question = (f'Which word names the subject of «{focus}»?' if roles == {'clause_conjunct'}
                            else f'Who is to perform the action «{focus}»?')
                if roles == {'clause_relative'}:
                    question = f'Кто в этом предложении выполняет действие «{focus}»?'
                yield word_choice(question, controllers, context)
        heads = [link.head for link in links]
        if roles == {'name_part', 'attribute'} and len(set(heads)) == 1 and heads[0] < i:
            head = heads[0]
            if all(all(link.role == 'name_part' and link.head == head for link in tree[head + 1:i])
                   for tree in analyses):
                short = _span_label(tokens, head, i)
                full = _span_label(tokens, head, i + 1)
                question = f'Which words form the personal name here, including «{focus}» if it is a nickname?'
                context = _clause_context(text, tokens, analyses, i, (head,))
                yield Probe(question, (full, short), context), [full if link.role == 'name_part' else short for link in links]
        if roles == {'clause_conjunct'} and len(set(heads)) > 1:
            yield word_choice(f'Which predicate is «{focus}» coordinated with?', heads)


def _partition(analyses, tokens, text):
    def cost(item):
        probe, answers = item
        return (len(probe.options) > MAX_WORD_CHOICES, max(Counter(answers).values()))

    specific = list(_partitions(analyses, tokens, text))
    if specific:
        return min(specific, key=cost)

    def binary(question, focus, flags):
        labels = (focus, 'no such word')
        probe = Probe(question + ' Otherwise choose “no such word”.', labels, text)
        return probe, [focus if flag else 'no such word' for flag in flags]

    choices = []
    for i in range(len(tokens)):
        links = [tree[i] for tree in analyses]
        if len(set(links)) == 1:
            continue
        focus = _span_label(tokens, i)
        roles = sorted({link.role for link in links})
        if len(roles) > 1:
            for role in roles[:-1]:
                choices.append(binary(f'Copy «{focus}» if its role here is {role.replace("_", " ")}.', focus,
                                      [link.role == role for link in links]))
            continue
        if roles == ['punctuation']:
            continue
        heads = [link.head for link in links]
        if len(set(heads)) > 1:
            labels = {j: _span_label(tokens, j) if j is not None else 'no such word' for j in heads}
            choices.append((Probe(f'Which word does «{focus}» depend on?', tuple(dict.fromkeys(labels.values())), text),
                            [labels[j] for j in heads]))
        for attr, template in [('lemma', 'its dictionary form is «{}»'), ('case', 'it is in the {} case'),
                               ('scope', 'the action has the reading «{}»')]:
            values = [getattr(link, attr) for link in links]
            distinct = sorted(set(values) - {None})
            if len(set(values)) < 2:
                continue
            for value in (distinct if None in values else distinct[:-1]):
                condition = template.format(CASE_NAMES.get(value, value) if attr == 'case' else value)
                choices.append(binary(f'Copy «{focus}» if {condition}.', focus, [v == value for v in values]))
        subjects = [link.implicit_subject for link in links]
        descriptions = {'speaker': 'the speaker', 'speaker_group': 'a group including the speaker',
                        'addressee': 'the addressee', 'addressee_group': 'the addressees',
                        'unresolved': 'an unspecified participant'}
        if len(set(subjects)) > 1:
            for key in sorted(set(subjects) - {None}):
                choices.append(binary(f'Copy «{focus}» if its unstated subject is {descriptions.get(key, key)}.',
                                      focus, [value == key for value in subjects]))
        if all(link.morphology for link in links):
            for condition, flags in feature_choices([link.morphology for link in links]):
                choices.append(binary(f'Copy «{focus}» if {condition}.', focus, flags))
    return min(choices, key=cost, default=None)


def _simple_trees(words, budget, fail):
    prefixes = {Prefix(): None}
    for token in words:
        following = {}
        has_reading = False
        for prefix in prefixes:
            for variant in prefix.next_readings(token.surface):
                has_reading = True
                extended = prefix.extend(variant)
                if extended is not None:
                    following[extended] = None
                    if len(following) > budget:
                        raise AnalysisBudgetExceeded('PREFIX_BUDGET')
        if not following:
            if all(prefix.open_preposition is not None for prefix in prefixes):
                reason = 'GROUP_AGREEMENT' if has_reading else 'NO_GOVERNED_READING'
            else:
                reason = 'NO_PREFIX' if has_reading else 'NO_RULE'
            fail(f'{reason} @{token.start}')
            return
        prefixes = following
    if all(prefix.open_preposition is not None for prefix in prefixes):
        fail('INCOMPLETE_PREPOSITIONAL_GROUP')
        return
    for prefix in prefixes:
        yield from prefix.structures()


def _nickname_readings(tokens, tree, budget):
    candidates = []
    dependents = {link.head for link in tree}
    for i, link in enumerate(tree):
        head = link.head
        if link.role != 'attribute' or head is None or head >= i or i in dependents:
            continue
        if any(part.role != 'name_part' or part.head != head for part in tree[head + 1:i]):
            continue
        if any(lemma == tree[head].lemma and 'Name' in tag for lemma, tag in known_forms(tokens[head].surface)):
            candidates.append(i)
    if 2 ** len(candidates) > budget:
        raise AnalysisBudgetExceeded('ANALYSIS_BUDGET')
    yield tree
    if candidates:
        for choices in product((False, True), repeat=len(candidates)):
            if any(choices):
                variant = list(tree)
                for i, is_name in zip(candidates, choices):
                    if is_name:
                        variant[i] = replace(tree[i], role='name_part', rule='NAME.EPITHET')
                yield tuple(variant)


def _possessor_readings(tokens, tree, budget):
    if any(link.lemma == 'себя' for link in tree):
        bound = list(tree)
        for i, link in enumerate(tree):
            if link.lemma != 'себя' or link.head is None:
                continue
            host = link.head
            while tree[host].role == 'preposition' and tree[host].head is not None:
                host = tree[host].head
            actors = [j for j, item in enumerate(tree) if item.role == 'subject' and item.head == host]
            if (len(actors) == 1 and tree[host].morphology and tree[host].morphology.pos == 'VERB'
                    and not any(item.role == 'nominal_conjunct' and item.head == actors[0] for item in tree)):
                bound[i] = replace(link, antecedent=actors[0])
        tree = tuple(bound)
    counts = {link.head: link.quantity for link in tree if link.role == 'numeral'
              and link.quantity_kind in ('cardinal', 'both', 'collective')}
    slots = {}
    size = 1
    for i, link in enumerate(tree):
        form = tokens[i].surface.casefold().replace('ё', 'е')
        if link.role != 'possessive' or form not in ('его', 'ее', 'их'):
            continue
        candidates = []
        for j in range(i):
            noun = tree[j]
            if noun.role not in ('subject', 'object', 'recipient', 'experiencer', 'beneficiary', 'stimulus', 'instrument', 'oblique', 'governed', 'nominal_conjunct'):
                continue
            count = counts.get(j) if noun.quantity_kind not in ('cardinal', 'both', 'collective') else noun.quantity
            if count is not None and count.isdecimal() and count != '1':
                if count != '0' and form == 'их':
                    candidates.append(j)
                continue
            surface = noun.recovery.corrected if noun.recovery else tokens[j].surface
            for lemma, tag in known_forms(surface):
                if lemma != noun.lemma or tag.POS not in ('NOUN', 'NPRO') or tag.person in ('1per', '2per'):
                    continue
                case = (noun.morphology.case if noun.morphology and noun.morphology.case else
                        noun.case or {'subject': 'nomn', 'object': 'accs'}.get(noun.role))
                if case is not None and tag.case != case:
                    continue
                number = 'plur' if form == 'их' else 'sing'
                genders = {'masc', 'neut'} if form == 'его' else {'femn'}
                if tag.number == number and (number == 'plur' or tag.gender is None or tag.gender in genders):
                    candidates.append(j)
                    break
        if candidates:
            slots[i] = (*candidates, None)
            size *= len(slots[i])
            if size > budget:
                raise AnalysisBudgetExceeded('ANALYSIS_BUDGET')
    if not slots:
        yield tree
        return
    for selected in product(*slots.values()):
        result = list(tree)
        for i, antecedent in zip(slots, selected):
            result[i] = replace(tree[i], antecedent=antecedent)
        yield tuple(result)


def _connected(tree):
    roots = [i for i, link in enumerate(tree) if link.head is None]
    if len(roots) != 1 or tree[roots[0]].role != 'predicate':
        return False
    children = [[] for _ in tree]
    for i, link in enumerate(tree):
        if any(ref is not None and not 0 <= ref < len(tree)
               for ref in (link.controller, link.antecedent, link.shared_object, link.ellipsis_source)):
            return False
        if link.coord_head is not None:
            if link.role != 'participle' or not 0 <= link.coord_head < i:
                return False
            first = tree[link.coord_head]
            if first.role != 'participle' or first.head != link.head or first.coord_head is not None:
                return False
        if link.shared_agent is not None:
            if link.role != 'participle' or not 0 <= link.shared_agent < len(tree):
                return False
            agent = tree[link.shared_agent]
            if agent.role != 'agent' or agent.head is None or agent.head == i or not 0 <= agent.head < len(tree):
                return False
            sibling = tree[agent.head]
            first = i if link.coord_head is None else link.coord_head
            sibling_first = agent.head if sibling.coord_head is None else sibling.coord_head
            if sibling.role != 'participle' or sibling.head != link.head or sibling_first != first:
                return False
        if link.shared_object is not None:
            if link.role not in {'predicate', 'clause_conjunct', 'infinitive'}:
                return False
            obj = tree[link.shared_object]
            if obj.role != 'object' or obj.head is None or obj.head == i:
                return False
        if link.head is not None:
            if not 0 <= link.head < len(tree):
                return False
            children[link.head].append(i)
    pending = roots.copy()
    count = 0
    while pending:
        count += 1
        current = pending.pop()
        pending.extend(children[current])
    return count == len(tree)


def analyze(text: str, choose: Callable[[Probe], str | Mapping] | None = None, *,
            budget: int = 256, accept_tree: Callable[[tuple[Link, ...]], bool] | None = None,
            on_nominal_step: Callable[[NominalStep], None] | None = None) -> Result:
    if budget < 1:
        raise ValueError('budget must be positive')
    from . import internal_comma, qualification, sentence_regions

    scanner = qualification.GroupOpenings()
    prefix_openings = []
    nominal_chart = NominalChart(budget=budget)
    occurrences = []
    text_end = len(text.rstrip())
    for match in TOKEN.finditer(text):
        surface = match[0]
        occurrences.append(Occurrence(surface, match.start(), match.end()))
        if match.end() == text_end and surface in {'.', '!', '?'}:
            continue
        prefix_openings.extend(scanner.feed(surface))
        step = nominal_chart.feed(surface)
        if on_nominal_step is not None:
            on_nominal_step(step)

    tokens = tuple(occurrences)
    words = tokens[:len(nominal_chart.steps)]
    if not words:
        return Result(text, 'UNRESOLVED', 'EMPTY', tokens)
    from . import homogeneous, case_arguments, clauses, determiners, finite_forms, infinitives, modifiers, morphology, nominal_groups, participles, predication, quantity_groups, quantity_modifiers, recovery, shared_agents, short_participles, standalone_numerals

    failures = []
    working_words = words
    starts_after_comma = {right.start for left, right in zip(words, words[1:]) if left.surface == ','}
    ends_before_comma = {left.end for left, right in zip(words, words[1:]) if right.surface == ','}
    spelling_sites = recovery.spelling_sites(words, budget, min(MAX_WORD_CHOICES - 1, budget))
    spellings = {}

    from . import ellipsis

    def reuse_completed(parse):
        cached = {}
        def run(part):
            if part in cached:
                yield from cached[part]
                return
            collected = []
            for tree in parse(part):
                if len(collected) <= budget:
                    collected.append(tree)
                yield tree
            if len(collected) <= budget:
                if len(cached) >= budget:
                    cached.pop(next(iter(cached)))
                cached[part] = tuple(collected)
        return run

    @reuse_completed
    def base(part):
        yield from ellipsis.one_member(part, part == working_words, budget)
        yield from _simple_trees(part, budget, failures.append if part == working_words else lambda _: None)
        yield from predication.trees(part, budget=budget)
        yield from infinitives.candidates(part, budget=budget)
        from . import infinitive_phrases
        yield from infinitive_phrases.trees(part, budget=budget)

    @reuse_completed
    def modal(part):
        yield from homogeneous.modals(part, base)
        from . import modal_regions
        yield from modal_regions.trees(part, lambda core: homogeneous.modals(core, base), budget)

    def governed(part):
        yield from case_arguments.trees(part, modal, budget=budget)

    def passive(part):
        yield from short_participles.trees(part, governed, budget=budget)

    @reuse_completed
    def finite(part):
        yield from finite_forms.trees(part, passive, budget=budget)

    def modified(part):
        for tree in modifiers.structures(part, finite, budget=budget):
            yield from _nickname_readings(part, tree, budget)

    def nominal(part):
        yield from nominal_groups.trees(part, modified, budget=budget)

    def counted(part):
        yield from quantity_groups.trees(part, nominal, budget=budget)

    def numbers(part):
        yield from standalone_numerals.trees(part, counted, budget=budget)

    def qualified_numbers(part):
        yield from quantity_modifiers.trees(part, numbers, budget=budget)

    def quantified(part):
        chart = nominal_chart if part == words else None
        yield from nominal_groups.with_genitives(part, qualified_numbers, budget=budget, chart=chart)

    def comparative(part):
        from . import comparatives

        yield from comparatives.trees(part, quantified, budget=budget)

    @reuse_completed
    def local(part):
        for tree in determiners.trees(part, lambda words: participles.trees(words, comparative, budget=budget)):
            if short_participles.allows_copula_reading(part, tree):
                yield from morphology.variants(part, tree, budget=budget)

    @reuse_completed
    def attributed(part):
        from . import unlisted_attributes
        yield from local(part)
        yield from unlisted_attributes.trees(part, local)

    def coordinated(part):
        from itertools import chain
        from . import dated_clauses, detached_measures, detached_prepositions, named_arguments

        date = dated_clauses.full_date(part)
        ordinary = chain(dated_clauses.attach(part, date, coordinated) if date else (),
                         named_arguments.trees(part, budget=budget),
                         homogeneous.trees(part, attributed, budget=budget),
                         detached_measures.trees(part, attributed, budget))
        parsed = False
        for tree in ordinary:
            parsed = True
            yield tree
        yield from detached_prepositions.trees(part, attributed, recover=not parsed,
                                               starts_after_comma=starts_after_comma, ends_before_comma=ends_before_comma)

    from . import marked_regions, nominal_entries
    group_heads_by_start = {}
    relative_hosts = {}

    def candidates(part):
        from . import relative_clauses, utterances
        if part is working_words:
            completed = marked_regions.complete(part, text, coordinated, relative_hosts, budget)
            if completed:
                yield from completed
                return
            yield from nominal_entries.trees(part, text, group_heads_by_start, budget)
        yield from utterances.trees(part, lambda segment: relative_clauses.trees(
            segment, coordinated, budget=budget), budget=budget)

    def supplemented(part):
        from . import nominal_supplements
        from itertools import chain
        variants = nominal_supplements.trees(part, candidates)
        first = next(variants, None)
        if first is None:
            yield from candidates(part)
        else:
            yield from chain((first,), variants)

    comma_choices = {}

    @reuse_completed
    def regional(part):
        yield from sentence_regions.trees(part, candidates, budget)

    @reuse_completed
    def remaining(part):
        yield from sentence_regions.remaining(part, candidates, budget)

    def checked_comma_readings(part, parse, sites=None):
        if part in comma_choices and comma_choices[part] is None:
            return
        possible = internal_comma.repairs(part, parse, budget, sites=sites)
        if possible and part not in comma_choices:
            raise internal_comma.BoundaryChoice(possible, part, text)
        for index, variants in possible.items():
            if part[index].start == comma_choices[part]:
                yield from variants

    def readings_for_region(part, grammar=regional, fallback=supplemented):
        from itertools import chain

        generated = grammar(part)
        first = next(generated, None)
        if first is None:
            repaired = checked_comma_readings(part, grammar)
            option = next(repaired, None)
            if option is not None:
                yield from chain((option,), repaired)
            elif fallback is not None:
                yield from fallback(part)
            return

        commas = {i for i, token in enumerate(part) if token.surface == ','}
        if commas:
            ordinary = []
            suspect = set()
            for tree in chain((first,), generated):
                ignored = {i for i in commas if internal_comma.ignored_inside_group(tree, i)}
                suspect.update(ignored)
                if not ignored:
                    ordinary.append(tree)
                if len(ordinary) > budget:
                    raise AnalysisBudgetExceeded('REGION_BUDGET')
                suspect.update(i for i in commas if tree[i].rule == 'PP.DETACHED.COMMA')
            if suspect:
                repaired = checked_comma_readings(part, grammar, suspect)
                option = next(repaired, None)
                if option is not None:
                    yield from chain((option,), repaired)
                    return
            if ordinary:
                yield from ordinary
            elif fallback is not None:
                yield from fallback(part)
        else:
            yield from chain((first,), generated)

    def exact(part, candidates_for=readings_for_region):
        opened = prefix_openings
        if accept_tree is not None and part is not words:
            opened = tuple(qualification.openings(part))
        for tree in candidates_for(part):
            if len(tree) != len(part):
                continue
            annotated = morphology.annotate(part, tree)
            for agent_variant in shared_agents.variants(part, annotated, budget=budget):
                bound = homogeneous.bindings(agent_variant)
                for variant in homogeneous.object_variants(bound, budget=budget):
                    if _connected(variant):
                        for scoped in quantity_groups.age_variants(variant, budget):
                            for reading in modifier_focus.readings(part, scoped, budget):
                                if accept_tree is None:
                                    yield reading
                                else:
                                    yield from qualification.filtered(reading, opened, accept_tree, budget)

    structures = {}

    def collect(candidates):
        for tree in candidates:
            if any(link.role == 'governed' and not GOVERNMENT.get(tree[link.head].lemma) for link in tree):
                if not failures or failures[0] != 'UNKNOWN_GOVERNMENT':
                    failures.insert(0, 'UNKNOWN_GOVERNMENT')
                continue
            if spellings:
                if any(tree[i].recovery for i in spellings):
                    continue
                tree = tuple(replace(link, recovery=spellings[i]) if i in spellings else link
                             for i, link in enumerate(tree))
            for reading in _possessor_readings(working_words, tree, budget):
                key = tuple((l.role, l.lemma, l.head, l.case, l.controller, l.scope,
                             l.antecedent, l.ellipsis_source, l.event_view, l.recovery, l.morphology, l.implicit_subject, l.quantity, l.quantity_kind, l.quantity_modifier, l.coord_head, l.shared_agent, l.shared_object) for l in reading)
                structures.setdefault(key, reading)
                if len(structures) > budget:
                    raise AnalysisBudgetExceeded('ANALYSIS_BUDGET')

    probes = []
    steps = []

    def select(probe, count, pending=(), domain='trees'):
        probes.append(probe)
        if len(probe.options) > MAX_WORD_CHOICES:
            return None, Result(text, 'AMBIGUOUS', 'JEV_CHOICE_LIMIT', tokens, pending, tuple(probes), tuple(steps))
        try:
            answer = choose(probe) if choose is not None else '?'
        except OSError:
            steps.append(ProbeStep(count, count, 'unavailable', domain))
            return None, Result(text, 'AMBIGUOUS', 'SELECTOR_UNAVAILABLE', tokens, pending, tuple(probes), tuple(steps))
        if isinstance(answer, Mapping):
            answer = probe.response_choice(answer)
        answer = ' '.join(answer.split()).casefold() if isinstance(answer, str) else None
        choices = {label.casefold(): label for label in probe.options}
        if answer == '0':
            steps.append(ProbeStep(count, 0, 'rejected', domain))
            return None, Result(text, 'UNRESOLVED', 'OPTIONS_REJECTED', tokens, (), tuple(probes), tuple(steps))
        if answer not in choices:
            reason = 'OPEN_CHOICE' if answer == '?' else 'INVALID_ANSWER'
            steps.append(ProbeStep(count, count, 'open' if answer == '?' else 'invalid', domain))
            return None, Result(text, 'AMBIGUOUS', reason, tokens, pending, tuple(probes), tuple(steps))
        return choices[answer], None

    while True:
        try:
            budget_error = None
            try:
                collect(exact(working_words))
            except AnalysisBudgetExceeded as error:
                if structures or isinstance(error, NominalBudgetExceeded):
                    raise
                budget_error = error
            try:
                if not structures:
                    collect(exact(working_words, lambda part: readings_for_region(part, remaining, None)))
                if not structures and budget_error is None and any(t.surface == ',' for t in working_words):
                    collect(exact(working_words, lambda part: checked_comma_readings(part, supplemented)))
                if not structures and budget_error is None:
                    collect(recovery.trees(working_words, exact, budget=budget))
            except AnalysisBudgetExceeded as error:
                if structures or isinstance(error, NominalBudgetExceeded):
                    raise
                budget_error = error
            if structures:
                if working_words is words and nominal_chart.overflow:
                    raise NominalBudgetExceeded('NOMINAL_FRONTIER_BUDGET')
                break
            for i, forms in spelling_sites:
                focus = _span_label(words, i)
                original = words[i].surface
                question = f'Какое написание передаёт слово «{focus}» в этом предложении?'
                probe = Probe(question, (original, *forms), text)
                label, stopped = select(probe, len(probe.options), domain='spelling')
                if stopped is not None:
                    return stopped
                steps.append(ProbeStep(len(probe.options), 1, 'selected', 'spelling'))
                if label == original:
                    continue
                spellings[i] = SpellingRecovery(original, label)
                working_words = (*working_words[:i], replace(words[i], surface=label), *working_words[i + 1:])
                relative_hosts.clear()
                group_heads_by_start.clear()
                failures.clear()
                break
            else:
                if budget_error is not None:
                    raise budget_error
                break
        except internal_comma.BoundaryChoice as group:
            count = len(group.options)
            label, stopped = select(group.probe, count, domain='internal_comma')
            if stopped is not None:
                return stopped
            comma_choices[group.part] = group.options[label]
            steps.append(ProbeStep(count, 1, 'selected', 'internal_comma'))
            structures.clear()
        except marked_regions.RelativeChoice as group:
            label, stopped = select(group.probe, len(group.heads), domain=group.domain)
            if stopped is not None:
                return stopped
            relative_hosts[group.start] = group.heads[label]
            steps.append(ProbeStep(len(group.heads), 1, 'selected', group.domain))
            structures.clear()
        except nominal_entries.GroupChoice as group:
            count = len(group.heads)
            label, stopped = select(group.probe, count, domain='group_heads')
            if stopped is not None:
                return stopped
            group_heads_by_start[group.start] = group.heads[label]
            steps.append(ProbeStep(count, 1, 'selected', 'group_heads'))
            structures.clear()
        except AnalysisBudgetExceeded as error:
            return Result(text, 'UNRESOLVED', str(error) or 'ANALYSIS_BUDGET', tokens, (), tuple(probes), tuple(steps))
    analyses = tuple(structures.values())
    from .converb_control import needs_confirmation
    confirmed_names = set()
    confirmed_focus = []
    if not analyses:
        return Result(text, 'UNRESOLVED', next(iter(failures), 'NO_COMPLETE_CLAUSE'), tokens, (), tuple(probes), tuple(steps))
    while True:
        if len(analyses) > 1:
            partition = _partition(analyses, words, text)
            if partition is None:
                return Result(text, 'AMBIGUOUS', 'NO_DISTINGUISHING_PROBE', tokens, analyses, tuple(probes), tuple(steps))
            probe, keys = partition
        else:
            unconfirmed = next((i for i, link in enumerate(analyses[0])
                                if (link.rule.startswith('OPAQUE.') or link.rule in {'ELL.NOMINAL', 'NAME.TITLE'}
                                    or needs_confirmation(analyses[0], i)
                                    or sentence_regions.confirmation(words, analyses[0], i, text))
                                and i not in confirmed_names), None)
            if unconfirmed is None:
                break
            surface = _span_label(words, unconfirmed)
            candidate = analyses[0][unconfirmed]
            regional_probe = sentence_regions.confirmation(words, analyses[0], unconfirmed, text)
            if regional_probe is not None:
                probe = regional_probe
                keys = [probe.options[0]]
            elif candidate.rule == 'ELL.NOMINAL':
                noun = _span_label(words, candidate.ellipsis_source)
                probe = Probe(f'Какое существительное подразумевается после «{surface}»?', (noun,), text)
                keys = [noun]
            elif candidate.rule == 'NAME.TITLE':
                name = _span_label(words, unconfirmed, unconfirmed + 3)
                probe = Probe('Какие слова вместе образуют название?', (name,), text)
                keys = [name]
            elif candidate.role == 'converb':
                head = candidate.controller
                actor = _span_label(words, head)
                for j, member in enumerate(analyses[0]):
                    if member.role != 'nominal_conjunct' or member.head != head:
                        continue
                    marks = [k for k, item in enumerate(analyses[0]) if item.role == 'coordinator' and item.head == j]
                    parts = [k for k, item in enumerate(analyses[0]) if item.role == 'coordinator_part' and item.head in marks]
                    connector = ' '.join(words[k].surface for k in sorted(marks + parts))
                    actor += (f' {connector} ' if connector else ', ') + _span_label(words, j)
                probe = Probe(f'К какому участнику в тексте относится действие «{surface}»?', (actor,), text)
                keys = [actor]
            elif candidate.rule == 'OPAQUE.ATTRIBUTE':
                anchor = _span_label(words, candidate.head)
                probe = Probe(f'Какое слово характеризует согласованное определение «{surface}»?', (anchor,), text)
                keys = [anchor]
            else:
                probe = Probe(f'Слово «{surface}» здесь служит именем или названием? Выберите его, если да.',
                              (surface,), text)
                keys = [surface]
            confirmed_names.add(unconfirmed)
        before = len(analyses)
        selected, stopped = select(probe, before, analyses)
        if stopped is not None:
            return stopped
        if probe.focus_choices:
            confirmed_focus.append(probe.focus_choices[probe.options.index(selected)])
        analyses = tuple(a for a, key in zip(analyses, keys) if key == selected)
        steps.append(ProbeStep(before, len(analyses), 'selected'))
    if accept_tree is None:
        tree = analyses[0]
        opened = prefix_openings
        if any(link.recovery for link in tree):
            corrected = (replace(t, surface=link.recovery.corrected) if link.recovery else t
                         for t, link in zip(words, tree))
            opened = qualification.openings(corrected)
        for start, end in qualification.sites(tree, opened):
            host = tree[start].head
            context = _clause_context(text, words, (tree,), host, (start, end - 1))
            probe = _qualification_probe(words, start, end, host, context)
            selected, stopped = select(probe, 2, (tree,), 'qualification')
            if stopped is not None:
                return stopped
            if selected == probe.options[0]:
                tree = (*tree[:start], replace(tree[start], scope='qualification'), *tree[start + 1:])
            steps.append(ProbeStep(2, 1, 'selected', 'qualification'))
        analyses = (tree,)
    reason = 'COMPLEX_CLAUSE' if any(link.role.startswith('clause_') for link in analyses[0]) else 'SIMPLE_CLAUSE'
    return Result(text, 'PARSED_FRAGMENT', reason, tokens, analyses, tuple(probes), tuple(steps), tuple(confirmed_focus))
