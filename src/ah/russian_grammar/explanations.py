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


def attachments(part, left, right, boundary, start):
    from .parser import Link
    from .utterances import _linked

    links, host, child = _linked(left, right, range(boundary), range(start, len(part)),
                                 'clause_conjunct', 'UTT.PARATAXIS', None)
    if start > boundary:
        links[boundary] = Link('punctuation', part[boundary].surface, child, 'UTT.SEP')
    yield tuple(links[j] for j in range(len(part)))
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
    local_scope = right[child - start].scope
    links[child] = replace(links[child], head=anchor, role='clause_complement', rule='CONTENT.EXPL',
                           scope='embedded' if not local_scope else 'embedded_' + local_scope)
    yield tuple(links[j] for j in range(len(part)))


def partitions(trees, tokens, text):
    from .parser import _span_label
    from .probe import Probe

    for i in range(len(tokens)):
        links = [tree[i] for tree in trees]
        if {link.rule for link in links} != {'CONTENT.EXPL', 'UTT.PARATAXIS'}:
            continue
        labels = [_span_label(tokens, link.head) if link.rule == 'CONTENT.EXPL' else 'нет такого слова'
                  for link in links]
        options = tuple(dict.fromkeys(labels))
        question = (f'Какое слово в первой части поясняет сообщение со сказуемым «{_span_label(tokens, i)}»? '
                    'Если это самостоятельное сообщение, выберите «нет такого слова».')
        yield Probe(question, options, text), labels
