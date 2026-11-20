from functools import partial

from audit_russian_grammar_fifth_ten import answer as previous_answer
from audit_russian_grammar_fourth_ten import project
from audit_russian_grammar_third_ten import batch, bounds, compare, main, run


def semantic_errors(identity, words):
    errors = []
    forms = {row['surface'].rstrip('.'): row for row in words}

    def field(surface, key, allowed):
        row = forms.get(surface)
        if not row or row.get(key) not in allowed:
            errors.append(f'{surface}: expected {key} in {sorted(allowed)}')

    def linked(surface, targets, fields):
        row = forms.get(surface, {})
        if not any(row.get(key) is not None and words[row[key]]['surface'] in targets for key in fields):
            errors.append(f'{surface}: missing {"/".join(fields)} to {"/".join(targets)}')

    for row in words:
        if row.get('participant_ref'):
            errors.append(f"Unlicensed dialogue participant on {row['surface']}")
        if row.get('recovery') and row['recovery'].get('corrected', row['surface']) != row['surface']:
            errors.append(f"Changed source spelling of {row['surface']}")

    for number in {
        'test-s52': ('2008',),
        'test-s53': ('17', '1924'),
        'test-s54': ('50', '30', '25', '20'),
        'test-s61': ('18', '1868', '25', '1940'),
    }.get(identity, ()):
        field(number, 'quantity', {number})

    if identity == 'test-s52':
        field('Динамо', 'role', {'subject'})
        field('Динамо', 'scope', {'proper_name'})
        field('прекратило', 'assertion_status', {'asserted'})
    elif identity == 'test-s53':
        field('Ханукашвили', 'role', {'name_part'})
        field('Тбилиси', 'case', {'loct'})
        field('родился', 'assertion_status', {'asserted'})
    elif identity == 'test-s54':
        if sum(w['surface'] == '%' for w in words) != 4:
            errors.append('Missing percentage unit')
        field('производится', 'assertion_status', {'asserted'})
        field('50', 'quantity_modifier', {'upper_bound'})
        if any(forms.get(n, {}).get('quantity_modifier') not in (None, 'exact') for n in ('30', '25', '20')):
            errors.append('Upper bound leaked to another measurement')
    elif identity == 'test-s55':
        field('просит', 'role', {'clause_conjunct'})
        linked('просит', ('человек',), ('controller', 'shared_agent'))
        field('опаздывает', 'scope', {'cause'})
        if forms.get('пропустить', {}).get('assertion_status') == 'asserted':
            errors.append('Requested action stored as accomplished')
    elif identity == 'test-s56':
        if forms.get('штрафоваться', {}).get('assertion_status') == 'asserted':
            errors.append('Obligation recorded as an accomplished penalty')
        field('должны', 'role', {'predicate'})
        if any(w['scope'] != 'focus' for w in words if w['surface'] == 'даже'):
            errors.append('Lost focus on the coordinated attempts')
    elif identity == 'test-s57':
        if (forms.get('приняты', {}).get('morphology') or {}).get('voice') != 'pssv':
            errors.append('Lost passive voice')
        linked('действовать', ('партиям',), ('controller',))
        for verb in ('действовать', 'наступать', 'бить'):
            if forms.get(verb, {}).get('assertion_status') == 'asserted':
                errors.append(f'{verb}: elaboration of decision recorded as accomplished')
    elif identity == 'test-s58':
        field('выпускающее', 'assertion_status', {'attributive'})
        linked('выпускающее', ('предприятие',), ('controller',))
    elif identity == 'test-s59':
        field('сиреневые', 'role', {'predicate'})
        field('сиреневые', 'assertion_status', {'asserted'})
    elif identity == 'test-s60':
        field('относится', 'assertion_status', {'qualified'})
        field('относится', 'implicit_subject', {'unresolved'})
        field('России', 'role', {'genitive_modifier'})
        field('Аркуль', 'role', {'apposition'})
        if len([w for w in words if w['surface'] == 'Вятка' and w['role'] == 'clause_conjunct']) != 2:
            errors.append('Missing one of the two nominal clauses')
    elif identity == 'test-s61':
        for title in ('психиатр', 'композитор', 'изобретатель'):
            if forms.get(title, {}).get('role') == 'subject':
                errors.append(f'{title}: profession interpreted as an actor')
        for part in ('Ште́кель', 'Stekel'):
            field(part, 'role', {'name_part'})
    return errors


def _labels_for(tokens, positions, options):
    labels = set()
    for label in options:
        before, delimiter, rest = label.partition('[')
        word, _, after = rest.partition(']') if delimiter else (label, '', '')
        left, right = before.split(), after.split()
        matches = {i for i, form in enumerate(tokens) if form == word
                   and i >= len(left) and tokens[i - len(left):i] == left
                   and tokens[i + 1:i + 1 + len(right)] == right}
        if matches and matches <= positions:
            labels.add(label)
    return labels


def answer(identity, text, probe, gold):
    if probe.question.startswith('Какое слово служит здесь сказуемым при подлежащем'):
        indices = {int(r[6]) - 1 for r in gold if r[7] == 'nsubj' and f'«{r[1]}»' in probe.question}
        matching = _labels_for([r[1] for r in gold], indices, probe.options)
        if len(matching) == 1:
            return matching.pop(), 'UD'

    if identity == 'test-s60' and 'передаёт оговорку' in probe.question:
        choices = [label for label in probe.options if label.casefold().startswith('по данным')]
        if len(choices) == 1:
            return choices[0], 'control reading'
    if 'if its role here is attribute' in probe.question:
        choices = {r[1] if r[7] == 'amod' else 'no such word'
                   for r in gold if f'«{r[1]}»' in probe.question}
        matching = choices.intersection(probe.options)
        if len(matching) == 1:
            return matching.pop(), 'UD'
    if probe.question.startswith('Какие слова перечисляют однородные определения'):
        spans = bounds(text, gold)
        for i, row in enumerate(gold):
            if row[7] != 'amod' or f'«{gold[int(row[6]) - 1][1]}»' not in probe.question:
                continue
            conjuncts = [j for j, r in enumerate(gold) if r[7] == 'conj' and r[6] == row[0]]
            if conjuncts:
                label = text[spans[i][0]:spans[max(conjuncts)][1]]
                if label in probe.options:
                    return label, 'UD'
    if probe.question.startswith('Каким словом дано само обозначение'):
        choices = {r[1] for r in gold if r[7] == 'appos' and f'«{gold[int(r[6]) - 1][1]}»' in probe.question}
        matching = choices.intersection(probe.options)
        if len(matching) == 1:
            return matching.pop(), 'UD'
    if probe.question.startswith('Кого именно характеризует слово'):
        choices = {gold[int(r[6]) - 1][1] for r in gold if r[7] == 'appos' and f'«{r[1]}»' in probe.question}
        matching = choices.intersection(probe.options)
        if len(matching) == 1:
            return matching.pop(), 'UD'
    if probe.question.startswith('Какое слово в неопределённой форме раскрывает содержание слова'):
        labels = {r[1] for r in gold if r[7] == 'appos' and 'VerbForm=Inf' in r[5]
                  and f'«{gold[int(r[6]) - 1][1]}»' in probe.question}
        matching = labels.intersection(probe.options)
        if len(matching) == 1:
            return matching.pop(), 'UD'
    if probe.question.startswith('Какие слова дают другое написание имени'):
        for i, row in enumerate(gold):
            if row[7] != 'appos' or row[3] != 'X':
                continue
            parts = [row[1], *(r[1] for r in gold[i + 1:] if r[7] == 'flat:name' and r[6] == row[0])]
            label = ' '.join(parts)
            if label in probe.options:
                return label, 'control reading'
    if probe.question.startswith('Какое название в перечне относится к дате'):
        for i, row in enumerate(gold):
            if row[7] != 'list' or row[3] != 'PROPN':
                continue
            day = int(row[6]) - 1
            if f'«{" ".join(r[1] for r in gold[day:day + 3])}»' in probe.question and row[1] in probe.options:
                return row[1], 'UD'
    return previous_answer(identity, text, probe, gold)


cases = partial(batch, start=52, end=61)
evaluate = partial(compare, semantics=semantic_errors)
audit = partial(run, evaluate=evaluate, reference=answer, project=project, reject=True)


if __name__ == '__main__':
    main(cases, audit)
