from dataclasses import dataclass, replace
from functools import cache
import re

from . import participle_forms
from .case_arguments import _lexicon
from .finite_forms import _agreement_subject
from .morphology import Morphology, _agree as compatible, _common, from_tag
from .nominal_groups import POSSESSIVES, _agree, _markers, _members, _prepositions
from .prepositions import DASHES, GOVERNMENT
from .rules import known_forms, name_type, readings
from .utterances import _map


@dataclass(frozen=True)
class Nominal:
    head: int
    end: int
    lemma: str
    case: str
    morphology: Morphology
    extra: tuple = ()

    @property
    def noun(self):
        return self.head


_ROMAN = re.compile(r'(?=[IVXLCDM]+$)M{0,3}(?:CM|CD|D?C{0,3})(?:XC|XL|L?X{0,3})(?:IX|IV|V?I{0,3})')


def _merge_nominals(items):
    by_syntax = {}
    for n in items:
        key = n.head, n.end, n.lemma, n.case, n.extra, n.morphology.number
        by_syntax.setdefault(key, []).append(n.morphology)
    return tuple(Nominal(head, end, lemma, case, _common(forms), extra)
                 for (head, end, lemma, case, extra, _), forms in by_syntax.items())


def _nominals(words, budget):
    from .parser import AnalysisBudgetExceeded, Link

    def title(i):
        return i < len(words) and words[i].surface[:1].isupper()

    @cache
    def base(start, case):
        if start >= len(words):
            return ()
        numeric = words[start].surface.isdecimal()
        result = []
        for head, lemma, _, attrs in _members(words, start + int(numeric), None, case):
            for l, t in known_forms(words[head].surface):
                if l != lemma or t.POS not in ('NOUN', 'NPRO') or t.case != case:
                    continue
                extra = attrs
                if numeric:
                    if t.number != 'sing' or lemma != 'год' or len(words[start].surface) != 4:
                        continue
                    extra = ((start, Link('numeral', words[start].surface, head, 'CAL.YEAR', quantity=words[start].surface,
                                          quantity_kind='ordinal')), *attrs)
                n = Nominal(head, head + 1, lemma, case, from_tag(t), extra)
                result.append(n)
                end = n.end
                while title(end) and title(head) and not _ROMAN.fullmatch(words[end].surface):
                    forms = known_forms(words[end].surface)
                    matching = [(l, f) for l, f in forms if f.case == case and name_type(f)]
                    unknown = not forms or all(f.POS in ('INTJ', 'PRCL') for _, f in forms)
                    if not matching and not unknown:
                        break
                    label = matching[0][0] if matching else words[end].surface
                    role = 'name_part' if name_type(t) or not forms else 'apposition'
                    rule = 'NAME' if matching else 'OPAQUE.NAME'
                    n = replace(n, end=end + 1, extra=(*n.extra, (end, Link(role, label, head, rule, case))))
                    result.append(n)
                    end = n.end
                if end < len(words) and _ROMAN.fullmatch(words[end].surface) and title(head) and name_type(t):
                    result.append(replace(n, end=end + 1, extra=(*n.extra, (end, Link('attribute', words[end].surface,
                                          head, 'NAME.ORDINAL', case)))))
                if end < len(words):
                    for l, adj in known_forms(words[end].surface):
                        if l in POSSESSIVES and adj.POS == 'ADJF' and _agree(adj, t):
                            result.append(replace(n, end=end + 1, extra=(*n.extra, (end, Link('possessive', l, head, 'P.POSS')))))
        return _merge_nominals(result)

    @cache
    def expand(start, case):
        result = set(base(start, case))
        pending = list(result)
        while pending:
            n = pending.pop()
            if n.end >= len(words):
                continue
            for subcase in dict.fromkeys(('gent', case, 'nomn')):
                for child in expand(n.end, subcase):
                    samecase = child.case == n.case
                    is_name = title(child.head)
                    titled = title(n.head) or any(link.role == 'name_part' for _, link in n.extra)
                    appos = ((is_name and (samecase or child.case == 'nomn' and child.morphology.animacy == 'inan'))
                             or titled and samecase and child.morphology.animacy == 'anim')
                    roles = []
                    if subcase == 'gent':
                        roles.append('genitive_modifier')
                    if appos:
                        roles.append('apposition')
                    for role in roles:
                        link = Link(role, child.lemma, n.head, 'APP' if role == 'apposition' else 'N.GEN',
                                    subcase, morphology=child.morphology)
                        ext = replace(n, end=child.end, extra=(*n.extra, (child.head, link), *child.extra))
                        if ext not in result:
                            result.add(ext)
                            pending.append(ext)
                            if len(result) > budget:
                                raise AnalysisBudgetExceeded('NOMINAL_GROUP_BUDGET')
        return tuple(sorted(result, key=lambda n: (n.end, n.head, n.lemma, repr(n.extra))))

    return expand


def _arguments(words, budget):
    nouns = _nominals(words, budget)

    @cache
    def at(start):
        slots = []
        for first, prep in _prepositions(words, start):
            for case in sorted(GOVERNMENT.get(prep, ())):
                for noun in nouns(first, case):
                    if any(r.role == 'governed' and r.lemma == noun.lemma and r.case == case
                           for r in readings(words[noun.head].surface, prep)):
                        slots.append((start, prep, noun))
            if first < len(words):
                for part in participle_forms.readings(words[first].surface):
                    if first + 1 < len(words) and any(t.POS == 'NOUN' and participle_forms.agrees(part, t)
                                                       for _, t in known_forms(words[first + 1].surface)):
                        continue
                    if part.morphology.case in GOVERNMENT.get(prep, ()):
                        slots.append((start, prep, Nominal(first, first + 1, part.lemma, part.morphology.case, part.morphology)))
        if not slots:
            for case in ('nomn', 'accs', 'ablt', 'datv', 'gent'):
                slots.extend((start, None, noun) for noun in nouns(start, case))
        return tuple(slots)

    return at


def _project(tokens, quoted):
    boundaries = {i for pair in quoted for i in pair}
    ignored = []
    kept = []
    for i, token in enumerate(tokens):
        if token.surface == ',' or token.surface in DASHES or i in boundaries:
            ignored.append(i)
        else:
            kept.append(i)
    return kept, ignored


def trees(tokens, *, budget=256, extended=False):
    from .parser import AnalysisBudgetExceeded, Link
    from .quote_titles import spans
    from .short_participles import instrumental_roles

    quoted = spans(tokens)
    kept, ignored = _project(tokens, quoted)
    words = tuple(tokens[i] for i in kept)
    forms = tuple(known_forms(t.surface) for t in words)
    finite = {i for i, values in enumerate(forms) if values and all(t.POS == 'VERB' and t.mood == 'indc' for _, t in values)}
    parts = {i for i, values in enumerate(forms) if values and all(t.POS == 'PRTF' for _, t in values)}
    if not finite or not parts:
        return
    signals = any((_ROMAN.fullmatch(w.surface) and i > 0 and words[i - 1].surface.istitle()) or
                  (i > 0 and w.surface[:1].isupper() and words[i - 1].surface[:1].isupper() and
                   (not forms[i] or all(tag.POS == 'INTJ' for _, tag in forms[i])))
                  for i, w in enumerate(words))
    if not extended and not signals:
        return
    if not extended and not any(any(name_type(f) or 'Geox' in f for _, f in values) for values in forms):
        return
    arguments = _arguments(words, budget)
    root = min(finite)
    cases, roles = _lexicon()
    seen = set()
    work = 0

    def parse(pos, action, actor, last, links):
        nonlocal work
        work += 1
        if work > budget * max(1, len(words)):
            raise AnalysisBudgetExceeded('PARTICIPIAL_REGION_BUDGET')
        if pos == len(words):
            if not all(i in links for i in finite | parts):
                return
            if any(i != root and links[i].role != 'clause_conjunct' for i in finite):
                return
            if not any(links[i].role == 'participle' for i in parts):
                return
            if actor is None and links[root].morphology.transitivity == 'tran':
                return
            restored = _map(tuple(links[i] for i in range(pos)), kept)
            if actor is None:
                f = links[root].morphology
                restored[kept[root]] = replace(restored[kept[root]], implicit_subject=_agreement_subject(f.person, f.number, f.gender)[1])
            for j in ignored:
                right = next((i for i in kept if i > j), None)
                left = next((i for i in reversed(kept) if i < j), None)
                target = right if right is not None else left
                if tokens[j].surface in DASHES and (right is None or restored[right].role != 'apposition'):
                    return
                restored[j] = Link('punctuation', tokens[j].surface, target, 'PUNCT')
            for left, right in quoted:
                inside = {n for n in kept if left < n < right}
                tops = [n for n in inside if restored[n].head not in inside]
                if len(tops) != 1 or any(restored[n].head in inside for n in kept if n not in inside):
                    return
                top, = tops
                if restored[top].morphology is None or restored[top].morphology.pos != 'NOUN':
                    return
                restored[top] = replace(restored[top], scope='title')
                for mark in (left, right):
                    restored[mark] = replace(restored[mark], head=top)
            tree = tuple(restored[i] for i in range(len(tokens)))
            readings = [tree]
            if not quoted:
                for i in kept:
                    link = restored[i]
                    if (link.role != 'genitive_modifier' or not tokens[i].surface.istitle()
                            or not link.morphology or link.morphology.animacy != 'inan'
                            or not any(other.head == i and other.role == 'genitive_modifier' for other in tree)):
                        continue
                    readings += [(*reading[:i], replace(reading[i], scope='title'), *reading[i+1:])
                                 for reading in readings]
                    if len(readings) > budget:
                        raise AnalysisBudgetExceeded('PARTICIPIAL_REGION_BUDGET')
            for option in readings:
                if option not in seen:
                    seen.add(option)
                    if len(seen) > budget:
                        raise AnalysisBudgetExceeded('PARTICIPIAL_REGION_BUDGET')
                    yield option
            return
        if pos == root:
            yield from parse(pos + 1, root, actor, None, links)
            return
        marker = next(iter(_markers(words, pos)), ())
        start = marker[-1] + 1 if marker else pos
        if start >= len(words):
            return
        if marker:
            if len(marker) != 1:
                return
            links = links | {pos: Link('coordinator', words[pos].surface.casefold(), start, 'C1')}
        if start in finite:
            if not marker or actor is None:
                return
            for lemma, tag in forms[start]:
                if compatible('subject', links[actor].morphology, from_tag(tag)):
                    link = Link('clause_conjunct', lemma, root, 'CL.CONJ', morphology=from_tag(tag), controller=actor)
                    yield from parse(start + 1, start, actor, None, links | {start: link})
            return
        if start in parts:
            if last is None:
                return
            anchors = []
            if marker and action in parts and links[action].role == 'participle':
                anchors.append((links[action].head, action))
            elif not marker:
                anchor = last
                while anchor is not None and links[anchor].role in {'subject', 'object', 'governed', 'name_part', 'apposition', 'genitive_modifier', 'attribute'}:
                    if links[anchor].role not in {'name_part', 'attribute'}:
                        anchors.append((anchor, None))
                    anchor = links[anchor].head
            for host, coord in anchors:
                noun = links[host]
                for part in participle_forms.matching(words[start].surface, noun):
                    link = Link('participle', part.lemma, host, 'PART.ATTR', part.morphology.case, coord_head=coord,
                                controller=host if part.morphology.voice == 'actv' else None, morphology=part.morphology)
                    yield from parse(start + 1, start, actor, None, links | {start: link})
            return

        for first, prep, n in arguments(start):
            candidates = []
            if prep:
                if marker:
                    continue
                candidates.append((action, 'governed', actor))
                if last is not None and pos > action:
                    candidates.append((last, 'governed', actor))
            elif marker:
                if last is not None and links[last].case == n.case:
                    candidates.append((last, 'nominal_conjunct', actor))
            else:
                pred = links[action]
                if n.case == 'nomn' and actor is None and compatible('subject', n.morphology, links[root].morphology):
                    candidates.append((root, 'subject', n.head))
                if n.case == 'accs' and pred.morphology.transitivity == 'tran' and pred.morphology.voice != 'pssv' and not any(
                        l.head == action and l.role == 'object' for l in links.values()):
                    candidates.append((action, 'object', actor))
                if n.case == 'ablt' and pred.morphology.voice == 'pssv':
                    candidates.extend((action, role, actor) for role in instrumental_roles(words, n, pred.lemma))
                elif n.case in {'ablt', 'datv'} and n.case in cases.get(pred.lemma, ()):
                    candidates.append((action, roles.get((pred.lemma, n.case), 'oblique'), actor))
            for host, role, next_actor in candidates:
                inner = dict(n.extra)
                head = host
                if prep:
                    inner[first] = Link('preposition', prep, host, 'P2')
                    after = next((stop for stop, p in _prepositions(words, start) if p == prep), first + 1)
                    for j in range(first + 1, after):
                        inner[j] = Link('prep_part', words[j].surface.casefold(), first, 'P1')
                    head = first
                rule = {'object': 'O1', 'governed': 'P1', 'subject': 'S1',
                        'nominal_conjunct': 'N.COORD'}.get(role, 'PART.ARG')
                if role == 'governed' and n.morphology.pos == 'PRTF':
                    rule = 'PART.SUBSTANTIVE'
                lemma = n.lemma
                if (any(l.role == 'name_part' and l.rule == 'OPAQUE.NAME' and l.head == n.head for _, l in n.extra)
                        and not any(name_type(t) for _, t in forms[n.head])):
                    rule = 'OPAQUE.NAME'
                    lemma = words[n.head].surface
                ant = next_actor if n.lemma == 'себя' else None
                inner[n.head] = Link(role, lemma, head, rule, n.case, antecedent=ant, morphology=n.morphology)
                if marker:
                    inner[pos] = replace(links[pos], head=n.head)
                if set(inner) | set(links) != set(range(n.end)) | {root}:
                    continue
                target = n.head if n.morphology.pos == 'PRTF' and prep else action
                yield from parse(n.end, target, next_actor, n.head, links | inner)
                if prep and host == root and root < start and any(l.role == 'genitive_modifier' for _, l in n.extra):
                    if any(_prepositions(words, n.end)):
                        qualified = replace(inner[first], scope='qualification')
                        yield from parse(n.end, target, next_actor, n.head, links | inner | {first: qualified})

    for lemma, tag in forms[root]:
        if tag.POS == 'VERB' and tag.mood == 'indc':
            base = {root: Link('predicate', lemma, None, 'V1', morphology=from_tag(tag))}
            yield from parse(0, root, None, None, base)
