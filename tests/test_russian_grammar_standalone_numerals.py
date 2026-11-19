from ah.russian_grammar import analyze


def test_standalone_numerals_keep_the_expressed_participants():
    participants = analyze('Двое выбрали третьего.')
    assert participants.status == 'PARSED_FRAGMENT' and not participants.probes
    assert [(x.role, x.lemma, x.quantity, x.case) for x in participants.analyses[0] if x.quantity] == [
        ('subject', 'двое', '2', 'nomn'), ('object', 'третий', '3', 'accs')]

    command = analyze('Запиши двадцать пять!')
    predicate, amount, part = command.analyses[0]
    assert (predicate.implicit_subject, amount.role, amount.quantity) == ('addressee', 'object', '25')
    assert (part.lemma, part.role, part.head) == ('пять', 'numeral_part', 1)


def test_coordinate_counted_subjects_keep_each_argument_and_its_quantity():
    sentence = analyze('Два ученика и три учителя вернулись.')
    assert sentence.status == 'PARSED_FRAGMENT' and not sentence.probes
    first, student, conjunction, second, teacher, _ = sentence.analyses[0]
    assert (first.quantity, first.head, student.role, student.head) == ('2', 1, 'subject', 5)
    assert (second.quantity, second.head, teacher.role, teacher.head) == ('3', 4, 'nominal_conjunct', 1)
    assert conjunction.head == 4
    assert analyze('Двое и трое вернулся.').status == 'UNRESOLVED'
