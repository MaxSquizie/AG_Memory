"""Left-to-right analysis within a single simple verbal clause."""
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from itertools import product
import re

from .probe import MAX_WORD_CHOICES, Probe
from .rules import Reading, attribute_agrees, readings, subject_agrees


RULE_FOR_ROLE = {
    'predicate': 'V1', 'subject': 'S1', 'object': 'O1',
    'attribute': 'A1', 'coordinator': 'C1', 'duration': 'T1',
}


TOKEN = re.compile(r'[^\W\d_]+(?:[-‐‑][^\W\d_]+)*|\d+|[^\s]', re.UNICODE)


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

    def extend(self, reading: Reading) -> 'Prefix | None':
        i = len(self.words)
        role = reading.role
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
        return Prefix((*self.words, reading), subject, predicate, objects, coordinator, pairs)

    def structures(self) -> Iterator[tuple[Link, ...]]:
        if self.subject is None or self.predicate is None:
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
            yield tuple(Link(w.role, w.lemma, None if i == self.predicate else heads.get(i, self.predicate),
                             RULE_FOR_ROLE[w.role])
                        for i, w in enumerate(self.words))


def _word_label(tokens, index):
    """Copy the surface form; disambiguate repetitions by neighboring words."""
    words = [t.surface.casefold() for t in tokens]
    others = [j for j, word in enumerate(words) if word == words[index] and j != index]
    if not others:
        return tokens[index].surface
    # Expand only as far as needed. Brackets preserve the target within the quote,
    # including when all the surrounding words themselves repeat.
    for radius in range(1, len(tokens)):
        for left, right in ((0, radius), (radius, 0),
                            (min(index, radius), min(len(tokens) - index - 1, radius))):
            start, stop = index - left, index + right + 1
            if start < 0 or stop > len(tokens):
                continue
            window = words[start:stop]
            if any(j >= left and words[j-left:j+right+1] == window for j in others):
                continue
            return ' '.join(f'[{tokens[j].surface}]' if j == index else tokens[j].surface
                            for j in range(start, stop))
    raise ValueError('could not distinguish occurrences in the complete sentence')


def _partition(analyses, tokens, text):
    # Each tree has exactly one answer. Equal answers keep all matching trees.
    def word_choice(question, indices):
        candidates = sorted({i for i in indices if i is not None})
        labels = {i: _word_label(tokens, i) for i in candidates}
        if None in indices:
            labels[None] = 'no such word'
        return Probe(question, tuple(labels.values()), text), [labels[i] for i in indices]

    predicates = [next(i for i, link in enumerate(a) if link.role == 'predicate') for a in analyses]
    if len(set(predicates)) > 1:
        return word_choice('Which word is the verb?', predicates)
    verb = _word_label(tokens, predicates[0])
    subjects = [next(i for i, link in enumerate(a) if link.role == 'subject') for a in analyses]
    if len(set(subjects)) > 1:
        return word_choice(f'Which word is the subject of «{verb}»?', subjects)
    for i in range(len(tokens)):
        if all(a[i].role == 'attribute' for a in analyses):
            hosts = [a[i].head for a in analyses]
            if len(set(hosts)) > 1:
                return word_choice(f'Which word does «{_word_label(tokens, i)}» describe?', hosts)

    durations = [next((i for i, link in enumerate(a) if link.role == 'duration'), None) for a in analyses]
    if len(set(durations)) > 1:
        return word_choice(f'Which word tells how long the action «{verb}» lasts?', durations)

    for i in range(len(tokens)):
        links = [a[i] for a in analyses]
        if len(set(links)) == 1:
            continue
        focus = _word_label(tokens, i)
        roles = {link.role for link in links}
        if len(roles) > 1:
            role = sorted(roles)[0]
            return word_choice(f'Copy «{focus}» if it is the {role} here. Otherwise choose “no such word”.',
                               [i if link.role == role else None for link in links])
        heads = [link.head for link in links]
        if len(set(heads)) > 1:
            return word_choice(f'Which word does «{focus}» depend on?', heads)
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
        variants = readings(token.surface)
        if not variants:
            return Result(text, 'UNRESOLVED', f'NO_RULE @{token.start}', tokens)
        following = {}
        for prefix in prefixes:
            for variant in variants:
                extended = prefix.extend(variant)
                if extended is not None:
                    following[extended] = None
                    if len(following) > budget:
                        return Result(text, 'UNRESOLVED', 'PREFIX_BUDGET', tokens)
        prefixes = following
        if not prefixes:
            return Result(text, 'UNRESOLVED', f'NO_PREFIX @{token.start}', tokens)
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
    while len(analyses) > 1:
        probe, keys = _partition(analyses, words, text)
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
