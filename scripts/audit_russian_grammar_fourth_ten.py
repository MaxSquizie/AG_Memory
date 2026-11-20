from functools import partial
from audit_russian_grammar_third_ten import batch, compare, main, projection, reference_answer, run


def semantic_errors(identity, words):
    form = {word['surface']: word for word in words}
    errors = []
    roles = {
        'test-s32': {'деятель': {'predicate'}, 'искусств': {'genitive_modifier'}},
        'test-s33': {'писать': {'infinitive'}, '1943': {'apposition'}},
        'test-s34': {'синтезируют': {'clause_conjunct'}, 'служит': {'clause_adverbial'}, 'основой': {'predicative_complement'}},
        'test-s35': {'тренером': {'clause_conjunct'}, 'играли': {'clause_conjunct'}, 'её': {'possessive'}},
        'test-s36': {'1467': {'numeral'}, 'человек': {'subject'}},
        'test-s37': {'день': {'apposition'}},
        'test-s38': {'волость': {'apposition'}},
        'test-s39': {'являющееся': {'participle'}, '1': {'comparison_standard'}, 'простым': {'predicative_complement'}},
        'test-s40': {'Отразив': {'converb'}},
        'test-s41': {'играл': {'clause_relative'}, 'перейти': {'clause_adverbial'}},
    }
    for token, options in roles[identity].items():
        if form[token]['role'] not in options:
            errors.append(f"{token}: unexpected role {form[token]['role']}")
    scopes = {
        'test-s33': {'писать': 'phase'},
        'test-s34': {'служит': 'cause'},
        'test-s37': {'тот': 'demonstrative'},
        'test-s38': {'волость': 'title'},
        'test-s39': {'являющееся': 'negated'},
        'test-s41': {'Унион': 'title'},
    }
    for token, value in scopes.get(identity, {}).items():
        if value not in (form[token].get('scope') or '').split('_'):
            errors.append(f'{token}: expected scope {value}')
    references = {
        'test-s34': [('основой', 'controller', 'оно')],
        'test-s39': [('являющееся', 'controller', 'число'), ('простым', 'controller', 'число')],
        'test-s40': [('Отразив', 'controller', 'войска')],
        'test-s41': [('где', 'antecedent', 'Льеж'), ('играл', 'controller', 'Франсуа'),
                     ('перейти', 'controller', 'Франсуа')],
    }
    for token, field, target in references.get(identity, ()):
        anchor = form[token].get(field)
        if anchor is None or words[anchor]['surface'] != target:
            errors.append(f'{token}: expected {field} to {target}')
    quantities = {
        'test-s33': [('12', 'cardinal', '12'), ('1943', 'ordinal', '1943')],
        'test-s34': [('XIX', 'ordinal', '19')],
        'test-s36': [('1467', 'cardinal', '1467'), ('2005', 'ordinal', '2005')],
        'test-s40': [('8', 'ordinal', '8')],
        'test-s41': [('десяти', 'cardinal', '10')],
    }
    for token, kind, value in quantities.get(identity, ()):
        if any(w.get('quantity_kind') != kind or str(w.get('quantity')) != value for w in words if w['surface'] == token):
            errors.append(f'{token}: expected {kind} {value}')
    if identity == 'test-s32' and any(w.get('participant_ref') or w['role'] == 'subject' or
                                     w['assertion_status'] != 'nominal' for w in words if w['role'] != 'punctuation'):
        errors.append('Nominal fragment asserted or bound to a participant')
    if identity == 'test-s34' and not any(
            w['lemma'] == 'век' and w['surface'].rstrip('.').casefold() == 'в' for w in words):
        errors.append('Abbreviation did not identify a century')
    if identity == 'test-s33' and form['начал'].get('participant_ref'):
        errors.append('Missing agent assigned a dialogue participant')
    if identity == 'test-s37' and form['и'].get('scope') != 'focus':
        errors.append('Focus particle read as a conjunction')
    if any(w.get('recovery') and (w['recovery'].get('corrected') or w['surface']) != w['surface'] for w in words):
        errors.append('Lexical spelling was changed')
    return errors


def project(words, gold):
    result = projection(words, gold)
    kept = [i for i, row in enumerate(gold[:len(words)]) if row[3] != 'PUNCT']
    starts = {words[i]['start']: j for j, i in enumerate(kept)}
    for i, item in zip(kept, result):
        if words[i].get('focus_offsets'):
            item['focus_members'] = [starts[offset] for offset in words[i]['focus_offsets']]
        if item['surface'].endswith('.') and item['surface'][:-1].isalpha():
            item['surface'] = item['surface'][:-1]
    return result


def answer(identity, text, probe, gold):
    if 'if it describes a future action' in probe.question:
        records = [r for r in gold if f'«{r[1]}»' in probe.question and 'Tense=' in r[5]]
        labels = {r[1] if 'Tense=Fut' in r[5].split('|') else 'no such word' for r in records}
        if len(labels) == 1 and labels <= set(probe.options):
            return labels.pop(), 'UD'
    if 'несмотря на запятую между ними' in probe.question:
        for i, row in enumerate(gold):
            if row[9] != 'InjectedComma=Yes':
                continue
            left, right = gold[i - 1], gold[i + 1]
            if left[6] == right[0] or right[6] == left[0]:
                for label in (f'{left[1]}, {right[1]}', f'{left[1]}, {right[1].removesuffix(".")}'):
                    if label in probe.options:
                        return label, 'UD'
    confirmations = {
        'test-s33': [('Какое число указывает календарный год', '1943')],
        'test-s34': [('Какое сочетание содержит сокращение слова', 'XIX в'),
                     ('Какое сочетание содержит сокращение слова', 'XIX в.'),
                     ('Какое сочетание содержит сокращение слова', 'XIX, в')],
        'test-s35': [('Какое слово продолжает личное имя', 'Луз'),
                     ('Which word does the possessive «её» refer to?', 'Хелен')],
        'test-s37': [('Какое существительное здесь поясняет', 'день')],
        'test-s38': [('Какие слова вместе образуют название?', 'Шелковская волость')],
        'test-s40': [('Какое слово управляется предлогом', 'ретраншаменту')],
        'test-s41': [('Какие слова вместе образуют название?', 'Унион Ла Каламине')],
    }
    for prompt, label in confirmations.get(identity, ()):
        if probe.question.startswith(prompt) and label in probe.options:
            return label, 'control reading'
    return reference_answer(identity, text, probe, gold)


cases = partial(batch, start=32, end=41)
evaluate = partial(compare, semantics=semantic_errors)
audit = partial(run, evaluate=evaluate, reference=answer, project=project, reject=True)


if __name__ == '__main__':
    main(cases, audit)
