from dataclasses import dataclass
from functools import lru_cache
import re

from .prepositions import LETTERS
from .rules import dictionary, unaccented


_WORD = re.compile(LETTERS)
_HYPHENS = str.maketrans({'‐': '-', '‑': '-'})


@dataclass(frozen=True)
class Part:
    surface: str
    start: int
    end: int
    abbreviation_evidence: str | None


@lru_cache(maxsize=8192)
def attested(surface):
    return tuple(dict.fromkeys((p.normal_form, p.tag) for p in dictionary().parse(surface) if p.is_known))


@lru_cache(maxsize=4096)
def _abbreviation(surface):
    letters = unaccented(surface)
    if len(letters) < 2 or not letters.isalpha():
        return None
    forms = attested(surface)
    marked = any('Abbr' in tag and tag.POS == 'NOUN' for _, tag in forms)
    if marked and (sum(c.isupper() for c in letters) >= 2 or all('Abbr' in t for _, t in forms)):
        return 'dictionary'
    if not letters.isupper() or any(tag.POS != 'NOUN' or lemma == letters.casefold() for lemma, tag in forms):
        return None
    if not any('ROMN' in p.tag for p in dictionary().parse(surface)):
        return 'capitalization'
    return None


@lru_cache(maxsize=4096)
def parts(surface):
    return tuple(Part(m[0], m.start(), m.end(), _abbreviation(m[0])) for m in _WORD.finditer(surface))


def opaque_abbreviation(surface):
    return _abbreviation(surface) == 'capitalization'


@lru_cache(maxsize=1)
def _opaque_cases():
    return tuple(dictionary().TagClass(f'NOUN,Abbr {case}')
                 for case in ('nomn', 'gent', 'datv', 'accs', 'ablt', 'loct'))


def _compound_forms(surface, items):
    normalized = unaccented(surface.translate(_HYPHENS)).casefold()
    words = normalized.split('-')
    if len(words) < 2 or words != [unaccented(part.surface).casefold() for part in items]:
        return ()
    evidence = []
    for word, part in zip(words, items):
        if part.abbreviation_evidence:
            evidence.append({word: set()})
        else:
            forms = {}
            for lemma, tag in attested(part.surface):
                forms.setdefault(lemma, set()).add(tag)
            if not forms:
                return ()
            evidence.append(forms)
    result = []
    for candidate in dictionary().parse(normalized):
        lemmas = candidate.normal_form.split('-')
        if len(lemmas) != len(evidence):
            continue
        if not all(lemma in forms for lemma, forms in zip(lemmas, evidence)):
            continue
        if any(candidate.tag in forms[lemma] for lemma, forms in zip(lemmas, evidence)):
            result.append((candidate.normal_form, candidate.tag))
    return tuple(dict.fromkeys(result))


@lru_cache(maxsize=4096)
def forms(surface):
    whole = attested(surface)
    items = parts(surface)
    marked = len(items) == 1 and items[0].surface == surface and items[0].abbreviation_evidence == 'dictionary'
    regular = tuple((lemma, tag) for lemma, tag in whole if 'Abbr' not in tag or marked and tag.POS == 'NOUN')
    if len(items) > 1:
        return regular or _compound_forms(surface, items)
    if opaque_abbreviation(surface):
        return regular + tuple((surface, tag) for tag in _opaque_cases())
    return regular


def metadata(surface, start, lemma):
    items = parts(surface)
    if len(items) == 1:
        part = items[0]
        if part.abbreviation_evidence == 'capitalization' and lemma != surface:
            return ()
        if part.abbreviation_evidence == 'dictionary' and not any(
                'Abbr' in tag and base == lemma for base, tag in attested(surface)):
            return ()
    components = lemma.translate(_HYPHENS).casefold().split('-')
    evidence = [part.abbreviation_evidence for part in items]
    if len(items) > 1:
        for i, part in enumerate(items):
            if evidence[i] == 'capitalization' and (
                    len(components) != len(items) or components[i] != unaccented(part.surface).casefold()):
                evidence[i] = None
    if not any(evidence):
        return ()
    return tuple({'surface': part.surface, 'start': start + part.start, 'end': start + part.end,
                  'abbreviation_evidence': reason} for part, reason in zip(items, evidence))


def confirmation(tokens, tree, i, text):
    from .probe import Probe
    from .parser import _span_label

    word = tokens[i].surface
    if tree[i].lemma == word and opaque_abbreviation(word):
        option = _span_label(tokens, i)
        return Probe('Какое обозначение в этой фразе употреблено как существительное?', (option,), text)
    return None
