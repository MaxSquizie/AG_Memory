from dataclasses import dataclass, replace
from fractions import Fraction
from functools import cache, lru_cache
from importlib.resources import files
import re

from .morphology import Morphology, _common, from_tag
from .rules import dictionary, known_forms


CASES = ('nomn', 'gent', 'datv', 'accs', 'ablt', 'loct')
DIRECT = {'nomn', 'accs'}
DIGITS = re.compile(r'(\d+)(?:([.,/])(\d+)|[-‐‑]([а-яё]+))?')
GROUPED = re.compile(r'\d{1,3}(?:[ \u00a0\u202f]\d{3})+(?:[.,/]\d+|[-‐‑][а-яё]+)?')


def _key(text):
    return text.casefold().replace('ё', 'е')


@cache
def _units():
    return frozenset(_key(word) for word in files(__package__).joinpath('lexicon/units.txt').read_text(encoding='utf8').splitlines())


def known_unit(lemma):
    return _key(lemma) in _units()


@cache
def _entries():
    data = files(__package__).joinpath('lexicon/numerals.tsv').read_text(encoding='utf8')
    return tuple((lemma, kind, int(value), prefix) for lemma, kind, value, prefix
                 in (row.split('\t') for row in data.splitlines()))


@cache
def _lexicon():
    result = {_key(lemma): (kind, value) for lemma, kind, value, _ in _entries()}
    for i, lemma in enumerate(('пятеро', 'шестеро', 'семеро', 'восьмеро', 'девятеро', 'десятеро'), 5):
        result[lemma] = 'collective', i
    for lemma in ('несколько', 'столько', 'много', 'мало', 'немало', 'немного', 'многовато', 'маловато'):
        result[lemma] = 'indefinite', None
    result.update({'нуль': ('cardinal', 0), 'оба': ('both', 2), 'сколько': ('query', None),
                   'полтора': ('sesqui', Fraction(3, 2)), 'полтораста': ('cardinal', 150),
                   'целый': ('whole', 1), 'половина': ('denominator', 2),
                   'треть': ('denominator', 3), 'четверть': ('denominator', 4)})
    return result


@cache
def _ordinals():
    return {v: lemma for lemma, (kind, v) in _lexicon().items() if kind == 'ordinal'}


@cache
def _multipliers():
    atoms = {n: _key(prefix) for _, _, n, prefix in _entries() if prefix != '-'}
    atoms[1] = 'одно'
    result = {}
    for value in range(2, 1000):
        rest = value % 100
        pieces = [value - rest, rest] if rest < 20 else [value - rest, rest - rest % 10, rest % 10]
        result[''.join(atoms[n] for n in pieces if n)] = value
    return result


@cache
def _scale_paradigms():
    forms = {}
    for lemma, (kind, value) in _lexicon().items():
        if kind not in {'scale', 'ordinal'} or value < 10**6 or known_forms(lemma):
            continue
        model = 'миллионный' if kind == 'ordinal' else 'миллион'
        stem = lemma[:-3] if kind == 'ordinal' else lemma
        for parse in dictionary().parse(model):
            if parse.normal_form != model or not parse.is_known:
                continue
            for word in parse.lexeme:
                surface = stem + word.word.removeprefix('миллион')
                key = (lemma, kind, value)
                forms.setdefault(surface, {}).setdefault(key, []).append(from_tag(word.tag))
    return forms


def _ordinal_unit(value):
    if value in _ordinals():
        return value
    low = value % 100
    if low:
        return low if low < 20 or low % 10 == 0 else low % 10
    if value % 1000:
        return value % 1000
    scale = 1000
    while value % (scale * 1000) == 0:
        scale *= 1000
    return scale


@lru_cache(maxsize=1024)
def _suffix_forms(value, suffix):
    lemma = _ordinals().get(_ordinal_unit(value))
    if not lemma:
        return ()
    model = lemma if known_forms(lemma) else 'миллионный'
    matches = []
    for parse in dictionary().parse(model):
        if parse.tag.POS != 'ADJF' or not parse.is_known:
            continue
        for variant in parse.lexeme:
            word = variant.word
            tail = word[-1:] if word[-2] in 'аеёиоуыэюя' else word[-2:]
            if tail == suffix:
                matches.append(from_tag(variant.tag))
    return tuple(dict.fromkeys(matches))


@dataclass(frozen=True)
class _Atom:
    lemma: str
    kind: str
    value: int | Fraction | None
    forms: tuple[Morphology, ...]


def _digit(surface, match):
    integer, separator, remainder, suffix = match.groups()
    if len(integer) > 1024 or (remainder and len(remainder) > 1024):
        return
    value = int(integer)
    if suffix:
        forms = _suffix_forms(value, suffix)
        if forms:
            yield _Atom(surface, 'digit_ordinal', value, forms)
        return
    if separator == '/':
        denominator = int(remainder)
        if not denominator:
            return
        value = Fraction(value, denominator)
    elif separator:
        value = Fraction(value * 10**len(remainder) + int(remainder), 10**len(remainder))
    forms = tuple(Morphology(pos='NUMR', case=case) for case in CASES)
    yield _Atom(surface, 'digit_fraction' if separator else 'digit', value, forms)


@lru_cache(maxsize=4096)
def _atoms(surface):
    surface = surface.casefold()
    digits = re.sub(r'[ \u00a0\u202f]', '', surface) if GROUPED.fullmatch(surface) else surface
    if match := DIGITS.fullmatch(digits):
        return tuple(_digit(surface, match))
    for ending in ('-то', '-либо', '-нибудь'):
        if surface.endswith(ending):
            return tuple(_Atom(atom.lemma + ending, 'indefinite', None, atom.forms)
                         for atom in _atoms(surface[:-len(ending)]) if atom.lemma in {'сколько', 'столько'})
    key = _key(surface)
    entries = dict(_scale_paradigms().get(key, {}))
    for value, lemma in _ordinals().items():
        if value < 1000:
            continue
        cut = key.rfind(lemma[:-2])
        if cut > 0 and (multiplier := _multipliers().get(key[:cut])):
            for tail in _atoms(key[cut:]):
                if tail.kind == 'ordinal' and tail.value == value:
                    entries[(surface[:cut] + lemma, 'ordinal', multiplier * value)] = list(tail.forms)
    for lemma, tag in known_forms(surface):
        term = _lexicon().get(_key(lemma))
        if term is None or tag.case not in CASES:
            continue
        kind, value = term
        if kind in {'ordinal', 'whole'} and tag.POS != 'ADJF':
            continue
        if kind in {'scale', 'denominator'} and (tag.POS != 'NOUN' or tag.animacy != 'inan'):
            continue
        if kind in {'query', 'indefinite', 'collective', 'both', 'sesqui'} and tag.POS != 'NUMR':
            continue
        if kind == 'cardinal' and tag.POS not in {'NUMR', 'ADJF', 'NOUN'}:
            continue
        entries.setdefault((lemma, kind, value), []).append(from_tag(tag))
    return tuple(_Atom(*key, tuple(dict.fromkeys(forms))) for key, forms in entries.items())


def _canonical(value):
    if value is None:
        return None
    if isinstance(value, int) or value.denominator == 1:
        return str(int(value))
    n, d = value.numerator, value.denominator
    twos = fives = 0
    while d % 2 == 0:
        d //= 2
        twos += 1
    while d % 5 == 0:
        d //= 5
        fives += 1
    if d != 1:
        return str(value)
    power = max(twos, fives)
    digits = str(n * 2**(power - twos) * 5**(power - fives)).zfill(power + 1)
    return digits[:-power] + '.' + digits[-power:]


def _count_class(value):
    if value is None or 11 <= value % 100 <= 14:
        return 'many'
    if value % 10 == 1:
        return 'one'
    return 'few' if 2 <= value % 10 <= 4 else 'many'


def _noun_fits(atom, case, noun, compound=False):
    kind = atom.kind
    nc, num = noun.case, noun.number
    if kind in {'ordinal', 'digit_ordinal'}:
        return nc == case
    if kind in {'digit_fraction', 'fraction', 'denominator'}:
        return nc == 'gent'
    if kind in {'query', 'indefinite'} and case in DIRECT:
        accusatives = tuple(form for form in atom.forms if form.case == 'accs')
        if case == 'accs' and noun.animacy == 'anim' and accusatives and all(f.animacy == 'anim' for f in accusatives):
            return nc == 'accs' and num == 'plur'
        return nc == 'gent' and (num == 'plur' or atom.lemma != 'несколько' or 'Sgtm' in getattr(noun, 'grammemes', ()))
    if kind == 'scale' or (atom.value == 0 and kind != 'query'):
        return nc == 'gent' and num == 'plur'
    count = _count_class(atom.value)
    if kind == 'sesqui':
        count = 'few'
    if kind == 'collective':
        number_only = 'Pltm' in getattr(noun, 'grammemes', ())
        if not number_only and not (noun.animacy == 'anim' and noun.gender in ('masc', None)):
            return False
    if count == 'one' and kind != 'collective':
        return nc == case and (num == 'sing' or 'Pltm' in getattr(noun, 'grammemes', ()))
    if case not in DIRECT:
        return nc == case and num == 'plur'
    if case == 'accs' and noun.animacy == 'anim' and (kind in {'both', 'collective', 'query', 'indefinite'} or count == 'few' and kind != 'sesqui'):
        if compound and count == 'few' and nc == 'gent' and num == 'sing':
            return True
        return nc == 'accs' and num == 'plur'
    if kind in {'collective', 'query'}:
        count = 'many'
    return nc == 'gent' and num == ('sing' if count == 'few' else 'plur')


def _forms(atom, case, noun=None):
    forms = []
    for form in atom.forms:
        if form.case != case:
            continue
        if noun is not None:
            if form.gender and noun.gender and form.gender != noun.gender:
                continue
            if atom.kind not in {'query', 'indefinite'} and form.animacy and noun.animacy and form.animacy != noun.animacy:
                continue
            if (atom.kind in {'ordinal', 'digit_ordinal'} or atom.value == 1) and form.number and form.number != noun.number:
                continue
        forms.append(form)
    return tuple(forms)


def _unit(parts, case, noun):
    rows = tuple(_forms(part, case, noun if i == len(parts) - 1 else None) for i, part in enumerate(parts))
    return rows if all(rows) else ()


def _group(parts, case, noun):
    rows = []
    start = 0
    for i, part in enumerate(parts):
        if part.kind != 'scale':
            continue
        prefix = parts[start:i]
        choices = []
        for form in part.forms:
            if prefix:
                if not _noun_fits(prefix[-1], case, form):
                    continue
                unit = _unit(prefix, case, form)
                if unit:
                    choices.append((*unit, (form,)))
            elif form.case == case and form.number == 'sing':
                choices.append(((form,),))
        if not choices:
            return ()
        rows.extend(tuple(dict.fromkeys(form for group in groups for form in group)) for groups in zip(*choices))
        start = i + 1
    tail = parts[start:]
    if tail:
        unit = _unit(tail, case, noun)
        if not unit:
            return ()
        rows.extend(unit)
    return tuple(rows)


def _fraction_parts(numerator, denominators, case):
    denominator = denominators[-1]
    prefix = _group(denominators[:-1], 'nomn', None)
    if denominators[:-1] and not prefix:
        return ()
    rows = []
    last = numerator[-1]
    for form in denominator.forms:
        if denominator.kind == 'denominator':
            if not _noun_fits(last, case, form):
                continue
        else:
            one = _count_class(last.value) == 'one'
            expected_case = 'gent' if case in DIRECT and not one else case
            if form.case != expected_case or form.number != ('sing' if one else 'plur') or (one and form.gender != 'femn'):
                continue
        target = Morphology(pos='NOUN', gender='femn', number='sing' if _count_class(last.value) == 'one' else 'plur',
                            animacy='inan')
        unit = _group(numerator, case, target)
        if unit:
            rows.append((*unit, *prefix, (form,)))
    return tuple(tuple(dict.fromkeys(f for group in groups for f in group)) for groups in zip(*rows))


@dataclass(frozen=True)
class Numeric:
    end: int
    value: str | None
    kind: str
    atoms: tuple[_Atom, ...]
    fractional_groups: tuple[tuple[int, int], ...] = ()

    def _rows(self, case, noun):
        if case not in CASES:
            return ()
        last = self.atoms[-1]
        if self.fractional_groups:
            if noun is not None and noun.case != 'gent':
                return ()
            rows = []
            start = 0
            for num_len, den_len in self.fractional_groups:
                middle = start + num_len
                end = middle + den_len
                part = _fraction_parts(self.atoms[start:middle], self.atoms[middle:end], case)
                if not part:
                    return ()
                rows.extend(part)
                start = end
            return tuple(rows)
        compound = self.kind == 'cardinal' and (len(self.atoms) > 1 or last.value >= 20)
        if noun is not None and not _noun_fits(last, case, noun, compound):
            return ()
        if self.kind == 'ordinal':
            prefix = _group(self.atoms[:-1], 'nomn', None)
            if self.atoms[:-1] and not prefix:
                return ()
            final = _forms(last, case, noun)
            return (*prefix, final) if final else ()
        if last.kind == 'denominator':
            forms = tuple(f for f in _forms(last, case) if f.number == 'sing')
            return (forms,) if forms else ()
        target = None if last.kind in {'digit_fraction', 'scale'} or last.value == 0 else noun
        if compound and target is not None and case == 'accs' and target.animacy == 'anim' and target.case == 'gent':
            target = replace(from_tag(target) if not isinstance(target, Morphology) else target, animacy='inan')
        return _group(self.atoms, case, target)

    @property
    def cases(self):
        return frozenset(case for case in CASES if self._rows(case, None))

    def parts_for(self, external_case, noun_tag=None):
        rows = self._rows(external_case, noun_tag)
        return tuple((a.lemma, _common(forms)) for a, forms in zip(self.atoms, rows))

    def compatible(self, external_case, noun_tag, noun_lemma=None):
        if self.kind == 'fraction' and noun_lemma and noun_tag.number == 'plur' and noun_tag.animacy != 'anim':
            decimal = self.atoms[-1].kind == 'digit_fraction' and '/' not in self.atoms[-1].lemma
            if (decimal or len(self.fractional_groups) > 1) and known_unit(noun_lemma) and 'Pltm' not in getattr(noun_tag, 'grammemes', ()):
                return False
        return bool(self._rows(external_case, noun_tag))

    def agreement(self, external_case, noun_tag):
        if not self.compatible(external_case, noun_tag):
            return frozenset()
        last = self.atoms[-1]
        if self.kind == 'ordinal' or (self.kind == 'cardinal' and _count_class(last.value) == 'one'):
            return frozenset({(str(noun_tag.number), str(noun_tag.gender) if noun_tag.number == 'sing' and noun_tag.gender else None)})
        if self.kind == 'both':
            return frozenset({('plur', None)})
        if self.kind == 'fraction':
            nominal = last.kind == 'denominator' and len(self.atoms) == 1
            if len(self.fractional_groups) == 1:
                num_len, _ = self.fractional_groups[0]
                nominal = _count_class(self.atoms[num_len - 1].value) == 'one'
            if nominal:
                return frozenset({('sing', 'femn')})
        if self.kind == 'cardinal' and last.kind == 'scale' and self._rows(external_case, noun_tag)[-1][0].number == 'sing':
            form = self._rows(external_case, noun_tag)[-1][0]
            return frozenset({('sing', form.gender), ('plur', None)})
        return frozenset({('sing', 'neut'), ('plur', None)})


def _value(parts):
    total = block = 0
    scale_limit = unit_limit = None
    for part in parts:
        n = part.value
        if part.kind == 'scale':
            if scale_limit is not None and n >= scale_limit:
                return None
            total += (block or 1) * n
            block = 0
            scale_limit, unit_limit = n, None
        else:
            if unit_limit is not None and not 0 < n < unit_limit:
                return None
            block += n
            unit_limit = 100 if n >= 100 and n % 100 == 0 else 10 if 20 <= n < 100 and n % 10 == 0 else 0
    return total + block


def _surface(token):
    return token if isinstance(token, str) else token.surface


def _integers(tokens, start):
    pending = [(start, ())]
    while pending:
        i, parts = pending.pop()
        if i == len(tokens):
            continue
        for atom in _atoms(_surface(tokens[i])):
            if atom.kind not in {'cardinal', 'digit', 'scale', 'ordinal', 'digit_ordinal'}:
                continue
            if parts and (atom.kind in {'digit', 'digit_ordinal'} or parts[-1].kind == 'digit' and atom.kind != 'scale'):
                continue
            chain = (*parts, atom)
            value = _value(chain)
            if value is None:
                continue
            ordinal = atom.kind in {'ordinal', 'digit_ordinal'}
            expression = Numeric(i + 1, str(value), 'ordinal' if ordinal else 'cardinal', chain)
            yield expression
            if not ordinal and value > 0:
                pending.append((i + 1, chain))


def _fractions(tokens, numerator, *, whole=False):
    if numerator.end == len(tokens) or numerator.kind != 'cardinal':
        return
    options = [((a,), a.value) for a in _atoms(_surface(tokens[numerator.end]))
               if a.kind == ('whole' if whole else 'denominator')]
    if not whole:
        options.extend((e.atoms, int(e.value)) for e in _integers(tokens, numerator.end)
                       if e.kind == 'ordinal' and int(e.value) >= 2)
    for denominator, divisor in options:
        value = Fraction(int(numerator.value), divisor)
        atoms = numerator.atoms + denominator
        sizes = (len(numerator.atoms), len(denominator))
        fraction = Numeric(numerator.end + len(denominator), _canonical(value), 'fraction', atoms, (sizes,))
        if fraction.cases:
            yield value, fraction


def expressions(tokens, start=0):
    if not 0 <= start < len(tokens):
        return
    for atom in _atoms(_surface(tokens[start])):
        kind = atom.kind
        if kind in {'digit_fraction', 'sesqui', 'denominator', 'collective', 'both', 'query', 'indefinite'}:
            value = Fraction(1, atom.value) if kind == 'denominator' else atom.value
            if kind in {'digit_fraction', 'sesqui', 'denominator'}:
                kind = 'fraction'
            yield Numeric(start + 1, _canonical(value), kind, (atom,))
    for expr in _integers(tokens, start):
        if expr.cases:
            yield expr
        for _, fraction in _fractions(tokens, expr):
            yield fraction
        for integer, whole in _fractions(tokens, expr, whole=True):
            for numerator in _integers(tokens, whole.end):
                for fraction_value, fraction in _fractions(tokens, numerator):
                    joined = Numeric(fraction.end, _canonical(integer + fraction_value), 'fraction',
                                     whole.atoms + fraction.atoms, whole.fractional_groups + fraction.fractional_groups)
                    if joined.cases:
                        yield joined
