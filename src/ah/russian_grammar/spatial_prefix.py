from dataclasses import dataclass
from functools import lru_cache

from .adjuncts import _lexicon
from .rules import known_forms


_ROLES = {'где': 'place', 'куда': 'goal', 'откуда': 'source'}


def relative_role(surface):
    return _ROLES.get(surface.casefold())


@lru_cache(maxsize=1024)
def deictic_role(surface):
    _, adverbs = _lexicon()
    for lemma, tag in known_forms(surface):
        if tag.POS == 'ADVB' and 'Dmns' in tag:
            return _ROLES.get(adverbs.get(lemma))
    return None


@dataclass(frozen=True)
class SpatialStep:
    start: int
    surface: str
    kind: str
    local_role: str
    earlier_candidates: tuple[int, ...]


class SpatialPrefix:
    def __init__(self):
        self._anchors = {}
        self._relatives = {}

    def feed(self, token, report=None):
        role = relative_role(token.surface)
        if role:
            kind, own, other = 'relative', self._relatives, self._anchors
        else:
            role = deictic_role(token.surface)
            if not role:
                return
            kind, own, other = 'anchor', self._anchors, self._relatives
        own[token.start] = len(own), len(other)
        if report is not None:
            report(SpatialStep(token.start, token.surface, kind, role, tuple(other)))

    @classmethod
    def from_tokens(cls, tokens):
        chart = cls()
        for token in tokens:
            chart.feed(token)
        return chart

    def permits(self, relative, anchor):
        if relative not in self._relatives or anchor not in self._anchors:
            return False
        ref_number, anchors_before = self._relatives[relative]
        anchor_number, refs_before = self._anchors[anchor]
        return anchor_number < anchors_before if anchor < relative else ref_number < refs_before


def partitions(trees, tokens, text):
    from .parser import _span_label
    from .probe import Probe

    for i, token in enumerate(tokens):
        if not relative_role(token.surface):
            continue
        links = [tree[i] for tree in trees]
        rules = {link.rule for link in links}
        clausal = {'CL.SPATIAL.REF', 'CL.SPATIAL.WH', 'CL.SPATIAL.FREE'}
        if not rules & clausal or not rules <= clausal | {'B1'}:
            continue
        focus = _span_label(tokens, i)
        labels = []
        for tree, link in zip(trees, links):
            if link.rule == 'B1':
                if link.head is None or tree[link.head].head is not None:
                    break
                labels.append(focus)
            elif link.antecedent is not None:
                labels.append(_span_label(tokens, link.antecedent))
            else:
                governor = tree[link.head].head
                if governor is None:
                    break
                labels.append(_span_label(tokens, governor))
        else:
            options = tuple(dict.fromkeys(labels))
            if len(options) == 1 and rules == {'CL.SPATIAL.WH', 'CL.SPATIAL.FREE'}:
                verb, = options
                question = (f'Что выражает часть со словом «{focus}»? Если она передаёт содержание '
                            f'косвенного вопроса, выберите «{focus}». Если она описывает место '
                            f'действия «{verb}», выберите «{verb}».')
                if focus != verb:
                    yield Probe(question, (focus, verb), text), [
                        focus if link.rule == 'CL.SPATIAL.WH' else verb for link in links]
            if len(options) < 2:
                continue
            if 'B1' in rules:
                question = (f'Какую связь выражает «{focus}»? Если это прямой вопрос ко всему предложению, '
                            f'выберите «{focus}».')
                if 'CL.SPATIAL.REF' in rules:
                    question += ' Если уточняется место или предмет, выберите обозначающее его слово.'
            else:
                question = f'Какое слово уточняет придаточная часть со словом «{focus}»?'
            if 'CL.SPATIAL.WH' in rules:
                question += ' Если это косвенный вопрос, выберите слово, от которого он задаётся.'
            if 'CL.SPATIAL.FREE' in rules:
                question += ' Если придаточная часть указывает место самого действия, выберите слово действия.'
            yield Probe(question, options, text), labels
