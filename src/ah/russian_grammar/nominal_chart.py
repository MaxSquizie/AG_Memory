from dataclasses import dataclass

from .prepositions import FORMS, GOVERNMENT, PREFIXES
from .rules import known_forms, name_type


def agrees(adj, noun):
    case = {'loc2': 'loct', 'gen2': 'gent'}.get(noun.case, noun.case)
    return (adj.case == case and adj.number == noun.number
            and (noun.number == 'plur' or not noun.gender or noun.gender == adj.gender)
            and (not adj.animacy or not noun.animacy or noun.animacy == adj.animacy))


@dataclass(frozen=True)
class NominalStep:
    index: int
    surface: str
    genitive_hosts: tuple[int, ...]
    attribute_hosts: tuple[int, ...]
    attribute_dependents: tuple[int, ...]
    preposition_hosts: tuple[int, ...]
    awaits_noun: bool
    right_edge: tuple[int, ...]
    overflow: bool


class NominalChart:
    def __init__(self, budget=256):
        self.budget = budget
        self.steps = []
        self._noun_forms = []
        self._pending = []
        self._before_attributes = ()
        self._local_edge = ()
        self._prep_prefixes = []
        self._prep_ends = []
        self.overflow = False

    def feed(self, surface):
        index = len(self.steps)
        forms = known_forms(surface)
        nouns = tuple(tag for _, tag in forms if tag.POS in ('NOUN', 'NPRO'))
        adjectives = tuple(tag for _, tag in forms if tag.POS == 'ADJF')
        self._noun_forms.append(nouns)
        previous = self._local_edge
        full_previous = self.steps[-1].right_edge if self.steps else ()
        hosts = tuple(j for j in previous if any(agrees(a, n) for a in adjectives for n in self._noun_forms[j]))
        dependents = []
        genitives = []
        if any(n.case in ('gent', 'gen2') for n in nouns):
            genitives.extend(previous)
        for j, attrs in reversed(self._pending):
            nouns = tuple(n for n in nouns if any(agrees(a, n) for a in attrs))
            if not nouns:
                break
            dependents.append(j)
            if j == self._pending[0][0] and any(n.case in ('gent', 'gen2') for n in nouns):
                genitives.extend(self._before_attributes)
        genitives = tuple(dict.fromkeys(genitives))
        word = surface.casefold()
        phrases = [(word, full_previous), *((f'{prefix} {word}', outer) for prefix, outer in self._prep_prefixes)]
        self._prep_prefixes = [(phrase, outer) for phrase, outer in phrases if phrase in PREFIXES]
        finished = [(FORMS[phrase], outer) for phrase, outer in phrases if phrase in FORMS]
        if not finished:
            finished = [(lemma, full_previous) for lemma, tag in forms if tag.POS == 'PREP']
        self._prep_ends.append(finished)
        prep = word in FORMS or word in PREFIXES or any(tag.POS == 'PREP' for _, tag in forms)
        edge = []
        if self._noun_forms[-1]:
            if all(tag.POS == 'NOUN' and not name_type(tag) for _, tag in forms):
                edge.append(index)
            edge.extend(genitives)
        if hosts:
            for host in hosts:
                edge.extend((host, *self.steps[host].genitive_hosts))
        self._local_edge = tuple(dict.fromkeys(edge))[:self.budget]
        inherited = set()
        for j in (*genitives, *hosts):
            if j not in inherited:
                inherited.update(self.steps[j].right_edge)
                edge.extend(self.steps[j].right_edge)
        for start in (index, *dependents):
            if start == 0:
                continue
            for lemma, outer in self._prep_ends[start - 1]:
                if any(tag.case in GOVERNMENT.get(lemma, ()) for tag in self._noun_forms[-1]):
                    edge.extend(outer)
        edge = tuple(dict.fromkeys(edge))
        if len(edge) > self.budget:
            self.overflow = True
            edge = edge[:self.budget]
        if adjectives:
            if not self._pending:
                self._before_attributes = previous
            if len(self._pending) < self.budget:
                self._pending.append((index, adjectives))
            else:
                self.overflow = True
        else:
            self._pending.clear()
        step = NominalStep(index, surface, genitives, hosts, tuple(reversed(dependents)),
                           full_previous if prep else (), bool(adjectives), edge, self.overflow)
        self.steps.append(step)
        return step
