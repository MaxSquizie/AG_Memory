from dataclasses import replace
from functools import cache
from importlib.resources import files

from .morphology import from_tag
from .rules import known_forms


def anchor_forms(surface):
    return tuple((lemma, tag) for lemma, tag in known_forms(surface)
                 if tag.gender == 'neut' and tag.case == 'accs' and (tag.POS == 'NPRO' or 'Apro' in tag))


@cache
def content_governors():
    source = files(__package__).joinpath('lexicon/content-governors.txt')
    return frozenset(source.read_text(encoding='utf-8').splitlines())


def nominal_boundary(part, end):
    if end < 2:
        return False
    return (any(tag.POS == 'NOUN' for _, tag in known_forms(part[end - 1].surface))
            and any(tag.POS in ('ADJF', 'PRTF') for _, tag in known_forms(part[end - 2].surface)))


def nominal_anchor(left):
    end = len(left) - 1
    return (left[end].role in ('subject', 'object') and left[end].head is not None
            and left[left[end].head].role == 'predicate'
            and any(link.head == end and link.role in ('attribute', 'participle') for link in left))


def attachments(part, left, right, boundary, start):
    from .parser import Link
    from .utterances import _linked

    links, host, child = _linked(left, right, range(boundary), range(start, len(part)),
                                 'clause_conjunct', 'UTT.PARATAXIS', None)
    if start > boundary:
        links[boundary] = Link('punctuation', part[boundary].surface, child, 'UTT.SEP')
    yield tuple(links[j] for j in range(len(part)))
    local_scope = right[child - start].scope
    embedded = 'embedded_' + local_scope if local_scope else 'embedded'
    if nominal_anchor(left):
        noun_reading = replace(links[child], head=boundary - 1, role='clause_complement',
                               rule='CONTENT.NOMINAL', scope=embedded)
        yield tuple(noun_reading if j == child else links[j] for j in range(len(part)))
    if left[host].lemma not in content_governors():
        return
    objects = [j for j, link in enumerate(left) if link.head == host and link.role in ('object', 'clause_complement')]
    if objects:
        if len(objects) != 1:
            return
        anchor, = objects
        if left[anchor].role != 'object' or any(item.head == anchor and item.role != 'particle' for item in left):
            return
        forms = [tag for lemma, tag in anchor_forms(part[anchor].surface) if lemma == left[anchor].lemma]
        if not forms:
            return
        links[anchor] = replace(links[anchor], rule='CONTENT.ANCHOR', quantity=None, quantity_kind=None,
                                quantity_modifier=None, morphology=from_tag(forms[0]), case='accs')
    else:
        anchor = host
    links[child] = replace(links[child], head=anchor, role='clause_complement', rule='CONTENT.EXPL',
                           scope=embedded)
    yield tuple(links[j] for j in range(len(part)))


def partitions(trees, tokens, text):
    from .parser import _span_label
    from .probe import Probe

    for i in range(len(tokens)):
        links = [tree[i] for tree in trees]
        content = {'CONTENT.EXPL', 'CONTENT.NOMINAL'}
        rules = {link.rule for link in links}
        if not rules & content or not rules <= content | {'UTT.PARATAXIS'}:
            continue
        labels = [_span_label(tokens, link.head) if link.rule in content else 'нет такого слова'
                  for link in links]
        options = tuple(dict.fromkeys(labels))
        if len(options) < 2:
            continue
        question = (f'Какое слово в первой части поясняет сообщение со сказуемым «{_span_label(tokens, i)}»? '
                    'Если это самостоятельное сообщение, выберите «нет такого слова».')
        members = tuple(j for j in range(i + 1, len(tokens)) if all(
            tree[j].role == 'clause_conjunct' and tree[j].head == i for tree in trees))
        if members and 'CONTENT.NOMINAL' in rules:
            actions = ', '.join(f'«{_span_label(tokens, j)}»' for j in (i, *members))
            question = (f'Какое слово первой части поясняют вместе сообщения со сказуемыми {actions}? '
                        'Если они самостоятельны, выберите «нет такого слова».')
        yield Probe(question, options, text), labels
