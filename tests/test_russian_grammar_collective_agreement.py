from ah.core import AHCore
from ah.russian_grammar.memory import submit


def test_collective_preserves_quantity_and_number():
    core = AHCore()
    stored = submit(core, 'Большинство студентов вернулись.')
    assert stored.status == 'STORED' and not stored.analysis.probes
    subject, members, verb = stored.analysis.analyses[0]
    assert subject.morphology.number == 'sing' and subject.head == 2
    assert members.morphology.number == verb.morphology.number == 'plur'
    assert members.case == 'gent' and members.head == 0
    assert submit(core, 'Кто вернулся?').text == 'Большинство студентов'
    assert submit(core, 'Большинство студентов вернулось?').text == 'Да.'
    assert submit(core, 'Студенты вернулись?').status == 'UNKNOWN'
    assert submit(core, 'Кто вернётся?').status == 'UNKNOWN'


def test_collective_keeps_both_moods_only_when_licensed():
    pending = submit(AHCore(), 'Большинство студентов пришли.')
    assert pending.status == 'AMBIGUOUS' and pending.observation_ref is None
    assert {tree[2].lemma for tree in pending.analysis.analyses} == {'прийти', 'прислать'}
    assert submit(AHCore(), 'Книга студентов вернулись.').status == 'UNRESOLVED'
    true_order = submit(AHCore(), 'Пришли мне список студентов.')
    assert all(tree[0].rule == 'V.IMP' for tree in true_order.analysis.analyses)
