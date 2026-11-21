from dataclasses import replace

from .homogeneous import ADDITIVE, ALTERNATIVE, _restore
from .morphology import PREDICATE_ROLES
from .prepositions import FORMS, PREFIXES
from .rules import question_word


WH_MARKS = ('CL.WH', 'CL.SPATIAL.WH')


def _opening(tokens, start, end):
    prep = []
    for i in range(start, end):
        if question_word(tokens[i].surface) and (not prep or ' '.join(prep) in FORMS):
            return i
        prep.append(tokens[i].surface.casefold())
        if ' '.join(prep) not in PREFIXES:
            break
    return None


def _predicate(tree, i):
    while i is not None and tree[i].role not in PREDICATE_ROLES | {'infinitive', 'participle', 'converb'}:
        i = tree[i].head
    return i


def bind_overt_conjuncts(tokens, tree):
    events = {_predicate(tree, i) for i, link in enumerate(tree) if link.rule in WH_MARKS}
    if not events:
        return tree
    result = list(tree)
    for i, link in enumerate(tree):
        if link.role != 'clause_marker' or link.lemma not in ADDITIVE | ALTERNATIVE:
            continue
        event = link.head
        if (event is None or tree[event].role != 'clause_conjunct' or tree[event].head not in events
                or (focus := _opening(tokens, i + 1, len(tokens))) is None):
            continue
        marker = tree[focus]
        if (marker.role not in ('subject', 'object', 'recipient', 'oblique', 'governed', 'adverb')
                or marker.role == 'adverb' and marker.lemma in ('кто', 'что') or _predicate(tree, focus) != event
                or not question_word(tokens[focus].surface, marker.lemma)):
            continue
        result[focus] = replace(marker, rule='CL.WH')
        events.add(event)
    return tuple(result)


def coordinated_remnants(tokens, parse):
    from .parser import Link

    separators = [i for i, token in enumerate(tokens) if token.surface.casefold() in ADDITIVE | ALTERNATIVE]
    spans = []
    end = len(tokens)
    for sep in reversed(separators):
        start = sep + 1
        opening = _opening(tokens, start, end)
        if opening is None:
            break
        spans.append((sep, start, end, opening))
        end = sep
    if not spans or not any(question_word(token.surface) for token in tokens[:end]):
        return
    marks = {sep for sep, _, _, _ in spans}
    kept = tuple(i for i in range(len(tokens)) if i not in marks)
    for tree in parse(tuple(tokens[i] for i in kept)):
        result = _restore(tree, kept, len(tokens))
        first_marks = [i for i in range(spans[-1][0]) if result[i].rule in WH_MARKS]
        for sep, start, end, focus in reversed(spans):
            phrase = range(start, end)
            roots = [i for i in phrase if result[i].head not in phrase]
            wh = [i for i in phrase if question_word(tokens[i].surface, result[i].lemma)]
            if len(roots) != 1 or wh != [focus]:
                break
            root, = roots
            event = result[root].head
            if event is None or event >= sep or result[event].role != 'clause_complement':
                break
            if any(result[i].role.startswith('clause_') or result[i].role in ('predicate', 'infinitive', 'converb')
                   for i in phrase):
                break
            if focus == root and result[focus].role == 'adverb' and result[focus].lemma in ('что', 'кто'):
                break
            first = [i for i in first_marks if _predicate(result, i) == event]
            if len(first) != 1:
                break
            word = tokens[sep].surface.casefold()
            result[sep] = Link('coordinator', word, root, 'CL.WH.COORD',
                               scope='alternative' if word in ALTERNATIVE else None)
            result[focus] = replace(result[focus], rule='CL.WH', coord_head=first[0], ellipsis_source=event)
        else:
            yield tuple(result)
