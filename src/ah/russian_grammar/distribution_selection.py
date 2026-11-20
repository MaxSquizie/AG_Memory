from collections.abc import Mapping
from dataclasses import replace
from itertools import combinations

from .distribution import frames, modes
from .parser import ProbeStep
from .probe import MAX_WORD_CHOICES, Probe


def _phrase(rows, domain):
    words = ' и '.join(rows[i]['surface'] for i in (domain.members or (domain.head,)))
    return f'«{words}»'


def _choose(result, choose, question, choices):
    probe = Probe(question, tuple(choices), result.source)
    try:
        answer = choose(probe) if choose else '?'
    except OSError:
        answer = '?'
    if isinstance(answer, Mapping):
        answer = probe.response_choice(answer)
    match = next((label for label in choices if isinstance(answer, str)
                  and label.casefold() == ' '.join(answer.split()).casefold()), None)
    step = ProbeStep(len(choices), 1 if match else len(choices), 'selected' if match else 'open', 'distribution')
    result = replace(result, probes=(*result.probes, probe), steps=(*result.steps, step))
    if match is None:
        result = replace(result, status='UNRESOLVED' if answer == '0' else 'AMBIGUOUS',
                         reason='DISTRIBUTION_DOMAIN_UNKNOWN')
    return match, result


def select(rows, result, choose, budget):
    selected = []
    for mode in modes(rows):
        kind = mode.kind
        if kind == 'successive_candidate':
            phrase = ' '.join(rows[j]['surface'] for j in (mode.marker, mode.argument))
            choices = ('порядок выполнения действия', 'сама очередь')
            label, result = _choose(result, choose, f'Что обозначает сочетание «{phrase}» в этом предложении?', choices)
            if label is None:
                return (), result
            if label == choices[1]:
                continue
            kind = 'successive'
        row = rows[mode.marker]
        row['distribution_mode'] = kind
        row['distribution_predicate'] = mode.predicate
        if mode.argument is not None:
            row['distribution_argument'] = mode.argument
    for frame in frames(rows):
        if frame.resolved:
            selected.append(frame)
            continue
        choices = {}
        alternatives = frame.alternatives
        if (1 << len(alternatives)) > min(budget, MAX_WORD_CHOICES):
            return (), replace(result, status='UNRESOLVED', reason='DISTRIBUTION_BUDGET')
        for size in range(len(alternatives) + 1):
            for extra in combinations(alternatives, size):
                domains = frame.domains + extra
                if not domains:
                    continue
                label = ', '.join(_phrase(rows, d) for d in domains)
                if len(domains) > 1:
                    label += ' (для каждого сочетания)'
                if label in choices:
                    return (), replace(result, status='AMBIGUOUS', reason='DISTRIBUTION_LABEL_COLLISION')
                choices[label] = replace(frame, domains=domains, optional=False, alternatives=())
        if frame.optional:
            choices['сочетание без распределения'] = None
        if not choices or len(choices) > MAX_WORD_CHOICES:
            return (), replace(result, status='UNRESOLVED', reason='DISTRIBUTION_DOMAIN_UNKNOWN')
        if len(choices) == 1 and frame.optional:
            continue
        question = f'Для каждого из каких участников или периодов отдельно указана доля со словом «{rows[frame.share]["surface"]}»?'
        match, result = _choose(result, choose, question, choices)
        if match is None:
            return (), result
        if choices[match] is not None:
            selected.append(choices[match])
    return tuple(selected), result
