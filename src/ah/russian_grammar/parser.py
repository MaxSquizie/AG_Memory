"""Left-to-right analysis within a single simple verbal clause."""
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, replace
from itertools import product

from .prepositions import CASE_NAMES, FORMS, GOVERNMENT, PREFIXES, TOKEN, group_heads
from .probe import MAX_WORD_CHOICES, Probe
from .rules import Reading, plain_person_reference, preposition_reading, attribute_agrees, readings, subject_agrees


RULE_FOR_ROLE = {
    'predicate': 'V1', 'subject': 'S1', 'object': 'O1',
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


@dataclass(frozen=True)
class Result:
    source: str
    status: str
    reason: str
    tokens: tuple[Occurrence, ...]
    analyses: tuple[tuple[Link, ...], ...] = ()
    probes: tuple[Probe, ...] = ()


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
            if any(w.role not in {'attribute', 'coordinator'} for w in self.words[first + 1:second]):
                return
        attrs = [i for i, w in enumerate(self.words) if w.role == 'attribute']
        domains = [[host for adj, host in self.pairs if adj == i] for i in attrs]
        for chosen in product(*domains):
            heads = dict(zip(attrs, chosen))
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


def _partition(analyses, tokens, text):
    # Each tree has exactly one answer. Equal answers keep all matching trees.
    def word_choice(question, indices, context=text):
        candidates = sorted({i for i in indices if i is not None})
        labels = {i: _span_label(tokens, i) for i in candidates}
        if None in indices:
            labels[None] = 'no such word'
        return Probe(question, tuple(labels.values()), context), [labels[i] for i in indices]

    predicates = [next(i for i, link in enumerate(a) if link.role == 'predicate') for a in analyses]
    if len(set(predicates)) > 1:
        return word_choice('Which word is the verb?', predicates)
    verb = _span_label(tokens, predicates[0])
    subjects = [next(i for i, link in enumerate(a) if link.role == 'subject') for a in analyses]
    if len(set(subjects)) > 1:
        return word_choice(f'Which word is the subject of «{verb}»?', subjects)
    for i in range(len(tokens)):
        if all(a[i].role == 'attribute' for a in analyses):
            hosts = [a[i].head for a in analyses]
            if len(set(hosts)) > 1:
                return word_choice(f'Which word does «{_span_label(tokens, i)}» describe?', hosts)

    for i in range(len(tokens)):
        if all(a[i].role == 'preposition' for a in analyses):
            boundaries = [max((j for j, link in enumerate(tree) if link.role == 'prep_part' and link.head == i),
                              default=i) + 1 for tree in analyses]
            if len(set(boundaries)) > 1:
                labels = {end: _span_label(tokens, i, end) for end in sorted(set(boundaries))}
                return (Probe('Which expression functions as the preposition here?', tuple(labels.values()), text),
                        [labels[end] for end in boundaries])
            hosts = [a[i].head for a in analyses]
            ends = {j for a in analyses for j, link in enumerate(a) if link.role == 'governed' and link.head == i}
            if len(set(hosts)) > 1 and len(ends) == 1:
                noun = ends.pop()
                end = noun + 1
                while end < len(tokens) and all(a[end].role == 'attribute' and a[end].head == noun for a in analyses):
                    end += 1
                phrase = _span_label(tokens, i, end)
                context = _attachment_context(text, tokens, analyses, hosts, i, end)
                return word_choice(f'Which word does the phrase «{phrase}» depend on?', hosts, context)

    durations = [next((i for i, link in enumerate(a) if link.role == 'duration'), None) for a in analyses]
    if len(set(durations)) > 1:
        return word_choice(f'Which word tells how long the action «{verb}» lasts?', durations)

    for i in range(len(tokens)):
        links = [a[i] for a in analyses]
        if len(set(links)) == 1:
            continue
        focus = _span_label(tokens, i)
        roles = {link.role for link in links}
        if len(roles) > 1:
            role = sorted(roles)[0]
            return word_choice(f'Copy «{focus}» if it is the {role} here. Otherwise choose “no such word”.',
                               [i if link.role == role else None for link in links])
        heads = [link.head for link in links]
        if len(set(heads)) > 1:
            return word_choice(f'Which word does «{focus}» depend on?', heads)
        if len({link.lemma for link in links}) == 1:
            case = sorted({link.case for link in links})[0]
            return word_choice(f'Copy «{focus}» if it is in the {CASE_NAMES[case]} case. Otherwise choose “no such word”.',
                               [i if link.case == case else None for link in links])
        lemma = sorted({link.lemma for link in links})[0]
        return word_choice(f'Copy «{focus}» if its dictionary form is «{lemma}». Otherwise choose “no such word”.',
                           [i if link.lemma == lemma else None for link in links])
    raise ValueError('identical structures were not merged')


def analyze(text: str, choose: Callable[[Probe], str | Mapping] | None = None, *, budget: int = 256) -> Result:
    if budget < 1:
        raise ValueError('budget must be positive')
    tokens = tuple(Occurrence(m[0], m.start(), m.end()) for m in TOKEN.finditer(text))
    words = tokens[:-1] if tokens and tokens[-1].surface in {'.', '!', '?'} else tokens
    prefixes = {Prefix(): None}
    if not words:
        return Result(text, 'UNRESOLVED', 'EMPTY', tokens)
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
                        return Result(text, 'UNRESOLVED', 'PREFIX_BUDGET', tokens)
        if not following:
            if all(prefix.open_preposition is not None for prefix in prefixes):
                reason = 'GROUP_AGREEMENT' if has_reading else 'NO_GOVERNED_READING'
            else:
                reason = 'NO_PREFIX' if has_reading else 'NO_RULE'
            return Result(text, 'UNRESOLVED', f'{reason} @{token.start}', tokens)
        prefixes = following
    if all(prefix.open_preposition is not None for prefix in prefixes):
        return Result(text, 'UNRESOLVED', 'INCOMPLETE_PREPOSITIONAL_GROUP', tokens)
    structures = {}
    for prefix in prefixes:
        for structure in prefix.structures():
            structures[structure] = None
            if len(structures) > budget:
                return Result(text, 'UNRESOLVED', 'ANALYSIS_BUDGET', tokens)
    analyses = tuple(structures)
    if not analyses:
        return Result(text, 'UNRESOLVED', 'NO_COMPLETE_CLAUSE', tokens)
    probes = []
    checked_government = set()
    while True:
        if len(analyses) > 1:
            probe, keys = _partition(analyses, words, text)
        else:
            tree, = analyses
            unverified = next((j for j, link in enumerate(tree) if link.role == 'governed'
                               and not GOVERNMENT.get(tree[link.head].lemma) and j not in checked_government), None)
            if unverified is None:
                break
            # The morphology dictionary knows this preposition but supplies no government.
            # An inflected form alone cannot certify the missing lexical constraint.
            link = tree[unverified]
            label = _span_label(words, unverified)
            question = f'Which word is governed by «{tree[link.head].lemma}» in the {CASE_NAMES[link.case]} case?'
            probe = Probe(question, (label,), text)
            keys = [label]
            checked_government.add(unverified)
        if len(probe.options) > MAX_WORD_CHOICES:
            return Result(text, 'AMBIGUOUS', 'JEV_CHOICE_LIMIT', tokens, analyses, tuple(probes))
        probes.append(probe)
        try:
            answer = choose(probe) if choose is not None else '?'
        except OSError:
            return Result(text, 'AMBIGUOUS', 'SELECTOR_UNAVAILABLE', tokens, analyses, tuple(probes))
        if isinstance(answer, Mapping):
            answer = probe.response_choice(answer)
        answer = ' '.join(answer.split()).casefold() if isinstance(answer, str) else None
        choices = {label.casefold(): label for label in probe.options}
        if answer == '0':
            return Result(text, 'UNRESOLVED', 'OPTIONS_REJECTED', tokens, (), tuple(probes))
        if answer not in choices:
            reason = 'OPEN_CHOICE' if answer == '?' else 'INVALID_ANSWER'
            return Result(text, 'AMBIGUOUS', reason, tokens, analyses, tuple(probes))
        analyses = tuple(a for a, key in zip(analyses, keys) if key == choices[answer])
    return Result(text, 'PARSED_FRAGMENT', 'SIMPLE_CLAUSE', tokens, analyses, tuple(probes))
