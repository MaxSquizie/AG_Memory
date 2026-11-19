from dataclasses import dataclass, replace
from functools import lru_cache
from importlib.resources import files

from .rules import known_forms, readings, subject_agrees


@dataclass(frozen=True)
class Frame:
    scope: str
    control: str
    recipient_cases: frozenset[str]


def _lexicon():
    folder = files(__package__).joinpath('lexicon')
    open_frame = Frame('embedded', 'open', frozenset(('accs', 'datv')))
    frames = dict.fromkeys(folder.joinpath('infinitives.tsv').read_text(encoding='utf8').splitlines(), open_frame)
    for row in folder.joinpath('infinitive_control.tsv').read_text(encoding='utf8').splitlines():
        scope, control, case, lemmas = row.split('\t')
        frame = Frame(scope, control, frozenset() if case == '-' else frozenset((case,)))
        frames.update(dict.fromkeys(lemmas.split(), frame))
    return frames


FRAMES = _lexicon()


@lru_cache(maxsize=4096)
def _nominals_and_infinitives(surface):
    return tuple((lemma, tag) for lemma, tag in known_forms(surface)
                 if tag.POS == 'INFN' or (tag.POS in ('NOUN', 'NPRO') and tag.case in ('accs', 'datv')))



def _participants(frame, subject, recipient):
    if frame.control == 'subject':
        return (subject,)
    if frame.control == 'recipient':
        return (recipient,)
    return tuple(dict.fromkeys((subject, recipient)))


def _check(breadth, budget):
    from .parser import AnalysisBudgetExceeded

    if breadth > budget:
        raise AnalysisBudgetExceeded('INFINITIVE_BUDGET')


def _with_control(tree, verbs, subject, budget):
    recipients = {link.head: i for i, link in enumerate(tree) if link.role == 'recipient'}
    chains = [(subject,)]
    for governor in verbs[:-1]:
        frame = FRAMES[tree[governor].lemma]
        chains = [(*prefix, controller)
                  for prefix in chains
                  for controller in _participants(frame, prefix[-1], recipients.get(governor))]
        _check(len(chains), budget)
    for chain in chains:
        resolved = list(tree)
        for child, controller in zip(verbs[1:], chain[1:]):
            resolved[child] = replace(tree[child], controller=controller)
        yield tuple(resolved)


def _arguments(forms, links, verbs, last_transitive, budget):
    from .parser import Link

    last = verbs[-1]
    slots = []
    for i, variants in enumerate(forms):
        if i in links:
            slots.append((links[i],))
            continue
        options = []
        for lemma, tag in variants:
            if tag.POS not in ('NOUN', 'NPRO'):
                continue
            if last_transitive and tag.case == 'accs':
                options.append(Link('object', lemma, last, 'O1', case=tag.case))
            for governor in verbs[:-1]:
                frame = FRAMES[links[governor].lemma]
                animate = tag.animacy != 'inan' and lemma != 'что'
                if tag.case in frame.recipient_cases and (tag.case != 'accs' or animate):
                    options.append(Link('recipient', lemma, governor, 'I2', case=tag.case))
        if not options:
            return
        slots.append(tuple(dict.fromkeys(options)))
    partials = [((), frozenset())]
    for options in slots:
        following = []
        for prefix, occupied in partials:
            for link in options:
                key = (link.role, link.head)
                if key in occupied:
                    continue
                assigned = occupied | {key} if link.role in ('recipient', 'object') else occupied
                following.append(((*prefix, link), assigned))
                _check(len(following), budget)
        partials = following
    for tree, _ in partials:
        yield tree


def _complements(forms, root, finite, subject, nominal, budget):
    from .parser import Link

    base = {root: Link('predicate', finite.lemma, None, 'V1'),
            subject: Link('subject', nominal.lemma, root, 'S1', case=nominal.case)}
    states = [(base, (root,), False)]
    for i, variants in enumerate(forms):
        if i in base or not any(tag.POS == 'INFN' for _, tag in variants):
            continue
        following = []
        for links, verbs, transitive in states:
            if any(tag.POS != 'INFN' for _, tag in variants):
                following.append((links, verbs, transitive))
            frame = FRAMES.get(links[verbs[-1]].lemma)
            if frame is None:
                continue
            for lemma, tag in variants:
                if tag.POS != 'INFN' or (frame.scope == 'phase' and tag.aspect != 'impf'):
                    continue
                child = Link('infinitive', lemma, verbs[-1], 'I1', scope=frame.scope)
                following.append(({**links, i: child}, (*verbs, i), 'tran' in tag))
        _check(len(following), budget)
        states = following
    for links, verbs, transitive in states:
        if len(verbs) > 1:
            for tree in _arguments(forms, links, verbs, transitive, budget):
                yield from _with_control(tree, verbs, subject, budget)


def candidates(tokens, *, budget=256):
    forms = [_nominals_and_infinitives(token.surface) for token in tokens]
    if not any(tag.POS == 'INFN' for variants in forms for _, tag in variants):
        return
    words = [readings(token.surface) for token in tokens]
    subjects = [(i, word) for i, variants in enumerate(words) for word in variants if word.role == 'subject']
    for root, variants in enumerate(words):
        for finite in variants:
            if finite.role != 'predicate' or finite.lemma not in FRAMES:
                continue
            for subject, nominal in subjects:
                if root != subject and subject_agrees(nominal, finite):
                    yield from _complements(forms, root, finite, subject, nominal, budget)
