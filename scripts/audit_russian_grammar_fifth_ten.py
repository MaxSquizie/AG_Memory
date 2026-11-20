from fractions import Fraction
from functools import partial

from audit_russian_grammar_fourth_ten import answer as previous_answer, project
from audit_russian_grammar_third_ten import batch, compare, main, run


def semantic_errors(identity, words):
    errors = []
    by_word = {row['surface']: row for row in words}
    for row in words:
        if row.get('participant_ref'):
            errors.append(f"Unlicensed dialogue participant on {row['surface']}")
        if row.get('recovery') and row['recovery'].get('corrected', row['surface']) != row['surface']:
            errors.append(f"Changed spelling of {row['surface']}")
    if identity == 'test-s44':
        if by_word['Тор'].get('scope') != 'proper_name' or by_word['Эдде']['rule'] != 'NAME.GROUP':
            errors.append('Lost proper-name or title reading')
        if any((by_word[k].get('morphology') or {}).get('animacy') for k in ('Тор', 'Эдде')):
            errors.append('Unsupported animacy supplied by homonym')
        if by_word['Согласно'].get('scope') != 'qualification':
            errors.append('Attribution to a source lost')
        cook = by_word['зажарить']
        owner = by_word['себе'].get('antecedent')
        if cook['assertion_status'] == 'asserted':
            errors.append('Potential action asserted')
        if owner is None or words[owner]['surface'] != 'он':
            errors.append('Missing local reflexive participant')
        if by_word['проголодался'].get('scope') != 'condition':
            errors.append('Missing condition')
    if identity == 'test-s45' and (by_word['распространено'].get('morphology') or {}).get('voice') != 'pssv':
        errors.append('Missing passive voice')
    if identity == 'test-s46':
        if by_word['1'].get('quantity_kind') != 'ordinal' or by_word['1'].get('quantity') != '1':
            errors.append('Missing round number')
    if identity == 'test-s47':
        item = by_word['произведённое']
        controller = by_word['достоянием'].get('controller')
        if by_word['Все'].get('scope') != 'universal' or item['role'] != 'subject':
            errors.append('Lost universal nominal subject')
        if controller is None or words[controller]['surface'] != 'произведённое':
            errors.append('Missing bearer of the nominal predicate')
        if by_word['распределять']['assertion_status'] == 'asserted':
            errors.append('Permitted action asserted')
    if identity == 'test-s48':
        for first, second in [('24', '11'), ('14', '10')]:
            left, right = by_word[first], by_word[second]
            if (left.get('quantity') != first or right.get('quantity') != second
                    or right['head'] is None or words[right['head']]['surface'] != first):
                errors.append('Lost the observed numerical annotation')
    if identity == 'test-s49':
        if by_word['озвучивал']['assertion_status'] != 'parenthetical':
            errors.append('Past action lost its parenthetical scope')
        if any(by_word[s]['role'] != 'name_part' for s in ('Мазихин', 'Иващенко')):
            errors.append('Surname detached from its name')
    if identity == 'test-s50':
        if by_word['ширины'].get('case') != 'accs' or (by_word['ширины'].get('morphology') or {}).get('case') != 'gent':
            errors.append('Lost quantity-group case or surface genitive')
        if by_word['диаметром']['role'] != 'measure':
            errors.append('Lost nominal measurement')
        if Fraction(by_word['1/8'].get('quantity') or 0) != Fraction(1, 8):
            errors.append('Missing fractional quantity')
        controller = by_word['касающуюся'].get('controller')
        if controller is None or words[controller]['surface'] != 'окружность':
            errors.append('Missing participant of the attributive clause')
    return errors


def answer(identity, text, probe, gold):
    question = probe.question
    if 'передаёт оговорку' in question and identity == 'test-s44':
        choices = {o for o in probe.options if o.startswith('Согласно')}
    elif 'называет измеряемый признак' in question and identity == 'test-s50':
        return 'диаметром', 'control reading'
    elif 'числовой пометой' in question:
        choices = {r[1] for r in gold if r[7] == 'appos' and r[3] == 'NUM'}
    elif 'продолжает личное имя' in question:
        choices = {r[1] for r in gold if r[7] == 'flat:name'}
    elif 'входит в обозначение' in question:
        choices = {r[1] for r in gold if r[7] == 'nummod:entity'}
    elif 'управляется предлогом' in question:
        choices = {gold[int(r[6]) - 1][1] for r in gold if r[7] == 'case'}
    elif 'обозначение' in question:
        choices = {r[1] for r in gold if r[3] in {'PROPN', 'NOUN'} or 'Foreign=Yes' in r[5]}
    elif 'на кого направлено действие' in question:
        choices = {r[1] for r in gold if r[7] == 'obj'}
    else:
        choices = set()
    matches = choices.intersection(probe.options)
    if len(matches) == 1:
        return matches.pop(), 'control reading' if 'оговорку' in question else 'UD'
    return previous_answer(identity, text, probe, gold)


cases = partial(batch, start=42, end=51)
evaluate = partial(compare, semantics=semantic_errors)
audit = partial(run, evaluate=evaluate, reference=answer, project=project, reject=True)


if __name__ == '__main__':
    main(cases, audit)
