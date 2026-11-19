"""Left-to-right analysis within a single simple verbal clause."""
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from itertools import product
import re

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

    def label(self) -> str:
        return f'«{self.surface}» @{self.start}'


@dataclass(frozen=True)
class Link:
    role: str
    lemma: str
    head: int | None  # token index
    rule: str


@dataclass(frozen=True)
class Probe:
    question: str
    options: tuple[str, ...]
    context: str

    def prompt(self) -> str:
        choices = [f'{i}. {label}' for i, label in enumerate(self.options, 1)]
        return '\n'.join([self.context, self.question, *choices,
                         '0. None of these', '?. Cannot tell'])


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


def _partition(analyses, tokens, text):
    # Prefer one concrete relation over a whole-tree choice.
    predicates = {next(i for i, link in enumerate(a) if link.role == 'predicate') for a in analyses}
    if len(predicates) == 1:
        verb = tokens[next(iter(predicates))].label()
        subjects = [next(i for i, link in enumerate(a) if link.role == 'subject') for a in analyses]
        if len(set(subjects)) > 1:
            options = sorted(set(subjects))
            return Probe(f'Which occurrence is the subject of {verb}?',
                         tuple(tokens[j].label() for j in options), text), subjects, options
        for i, token in enumerate(tokens):
            if all(a[i].role == 'attribute' for a in analyses):
                hosts = [a[i].head for a in analyses]
                if len(set(hosts)) > 1:
                    options = sorted(set(hosts))
                    return Probe(f'Which occurrence does {token.label()} describe?',
                                 tuple(tokens[j].label() for j in options), text), hosts, options
    for i, token in enumerate(tokens):
        keys = [a[i] for a in analyses]
        if len(set(keys)) > 1:
            if {k.role for k in keys} == {'object', 'duration'} and len({(k.head, k.lemma) for k in keys}) == 1:
                options = ['object', 'duration']
                question = f'What does {token.label()} indicate here?'
                labels = ('What the action is directed at', 'How long the action lasts')
                return Probe(question, labels, text), [k.role for k in keys], options
            options = list(dict.fromkeys(keys))
            labels = tuple(f'{k.role} «{k.lemma}»' + (f' → {tokens[k.head].label()}' if k.head is not None else '')
                           for k in options)
            return Probe(f'Which reading fits {token.label()}?', labels, text), keys, options
    raise ValueError('identical structures were not merged')


def analyze(text: str, choose: Callable[[Probe], str] | None = None, *, budget: int = 256) -> Result:
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
        probe, keys, options = _partition(analyses, words, text)
        probes.append(probe)
        try:
            answer = choose(probe) if choose is not None else '?'
        except OSError:
            return Result(text, 'AMBIGUOUS', 'SELECTOR_UNAVAILABLE', tokens, analyses, tuple(probes))
        choices = {str(i): option for i, option in enumerate(options, 1)}
        if answer == '0':
            return Result(text, 'UNRESOLVED', 'OPTIONS_REJECTED', tokens, (), tuple(probes))
        if not isinstance(answer, str) or answer not in choices:
            reason = 'OPEN_CHOICE' if answer == '?' else 'INVALID_ANSWER'
            return Result(text, 'AMBIGUOUS', reason, tokens, analyses, tuple(probes))
        analyses = tuple(a for a, key in zip(analyses, keys) if key == choices[answer])
    return Result(text, 'PARSED_FRAGMENT', 'SIMPLE_CLAUSE', tokens, analyses, tuple(probes))
