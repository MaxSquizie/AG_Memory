from dataclasses import replace
from functools import lru_cache
from importlib.resources import files

from .determiners import SCOPES
from .morphology import ROLE_CASE, from_tag
from .prepositions import FORMS
from .rules import dictionary, known_forms


@lru_cache(maxsize=256)
def readings(surface):
    return tuple((lemma, tag) for lemma, tag in known_forms(surface)
                 if lemma in SCOPES and {'ADJF', 'Apro', 'Subx'} <= tag.grammemes
                 and tag.gender != 'neut' and tag.animacy != 'inan')


def has_opening(tokens):
    seen_anchor = False
    for token in tokens:
        if seen_anchor and any(lemma == 'кто' for lemma, _ in known_forms(token.surface)):
            return True
        seen_anchor = seen_anchor or bool(readings(token.surface))
    return False


@lru_cache(maxsize=32)
def _pronoun_forms(number, gender, case, prepositional):
    lemma = 'они' if number == 'plur' else 'она' if gender == 'femn' else 'он'
    forms = dictionary().parse(lemma)[0].lexeme
    return tuple(dict.fromkeys((form.word, lemma) for form in forms if form.tag.case == case
                               and not {'Arch', 'Infr', 'V-ey'} & form.tag.grammemes
                               and ('Af-p' in form.tag) == prepositional))


@lru_cache(maxsize=1)
def _clausal_addressees():
    source = files(__package__).joinpath('lexicon/clausal-addressees.tsv')
    return frozenset(tuple(row.split('\t')) for row in source.read_text(encoding='utf8').splitlines())


def saturated_content(tree, tokens, start, governor):
    return any(link.head == governor and readings(tokens[i].surface)
               and link.role in ('object', 'recipient', 'oblique')
               for i, link in enumerate(tree[:start]))


def matrices(tokens, start, component):
    for i, token in enumerate(tokens[:start]):
        for lemma, tag in readings(token.surface):
            prep = i > 0 and tokens[i - 1].surface.casefold() in FORMS
            for word, pronoun in _pronoun_forms(tag.number, tag.gender, tag.case, prep):
                projected = (*tokens[:i], replace(token, surface=word), *tokens[i + 1:])
                for matrix in component(projected):
                    host = matrix[i]
                    case = host.case or ROLE_CASE.get(host.role) or getattr(host.morphology, 'case', None)
                    if host.lemma != pronoun or case != tag.case or host.role in ('attribute', 'possessive'):
                        continue
                    anchor = replace(host, lemma=lemma, case=case, morphology=from_tag(tag),
                                     scope=SCOPES[lemma], rule='NP.CORRELATE')
                    if not accessible(matrix, start, i):
                        continue
                    yield (*matrix[:i], anchor, *matrix[i + 1:]), i, None
                    if host.head is not None and (matrix[host.head].lemma, case) in _clausal_addressees():
                        participant = replace(anchor, rule='NP.DEMONSTRATIVE', role='recipient')
                        yield (*matrix[:i], participant, *matrix[i + 1:]), None, host.head


def accessible(tree, start, i):
    from .relative_clauses import _anchors

    edge = set(_anchors(tree, start))
    if i in edge:
        return True
    host = tree[i].head
    if host is not None and tree[host].role == 'preposition':
        host = tree[host].head
    return host in edge


def relative_forms(surface, tree, index):
    host = tree[index]
    predicate = tree[host.head] if host.head is not None else None
    plural = (host.role == 'subject' and host.morphology.number == 'plur'
              and predicate and predicate.morphology and predicate.morphology.number == 'plur')
    for lemma, tag in known_forms(surface):
        if lemma != 'кто' or tag.POS != 'NPRO':
            continue
        yield surface, tag
        if plural and tag.case == 'nomn':
            yield from ((word, tag) for word, _ in _pronoun_forms('plur', None, 'nomn', False))


def partitions(trees, tokens, text):
    from .parser import _span_label
    from .probe import Probe

    for i in range(len(tokens)):
        if not any(t[i].rule == 'CL.NOMREF' and t[i].antecedent is not None
                   and t[t[i].antecedent].rule == 'NP.CORRELATE' for t in trees):
            continue
        labels = []
        for tree in trees:
            link = tree[i]
            if link.rule == 'CL.NOMREF' and link.antecedent is not None:
                label = _span_label(tokens, link.antecedent)
            elif link.rule == 'CL.WH':
                host = link.head
                while host is not None and tree[host].role != 'clause_complement':
                    host = tree[host].head
                if host is None or tree[host].head is None:
                    break
                label = _span_label(tokens, tree[host].head)
            else:
                label = 'самостоятельная часть'
            labels.append(label)
        else:
            options = tuple(dict.fromkeys(labels))
            if len(options) > 1:
                focus = _span_label(tokens, i)
                question = (f'К чему относится часть со словом «{focus}»? Если она описывает участника, '
                            'выберите слово, которым он обозначен. Если она передаёт содержание вопроса '
                            'или сообщения, выберите соответствующее действие.')
                yield Probe(question, options, text), labels
