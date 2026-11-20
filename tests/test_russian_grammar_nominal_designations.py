from ah.core import AHCore
from ah.model import Domain
from ah.russian_grammar.memory import submit


def test_unknown_place_name_confirmation_and_nominal_anchor():
    core = AHCore()
    text = 'Знак относится к эмблеме города Нординг.'
    assert submit(core, text, lambda _: '?').status == 'AMBIGUOUS'
    assert not core.store.elements(Domain.H)
    record = submit(core, text, lambda p: 'Нординг' if 'Нординг' in p.options else '?')
    assert record.status == 'STORED'
    observation = core.store.get_element(Domain.H, record.observation_ref)
    rows = [core.store.get_element(Domain.H, r.uid).meta for r in observation.members]
    name = rows[-1]
    assert name['role'] == 'apposition' and rows[name['head']]['lemma'] == 'город'
    assert name['surface'] == name['lemma'] == 'Нординг' and name['case'] is None


def test_comma_preserves_the_choice_between_enumeration_and_genitive():
    text = 'Входит в состав, округа Шердинг.'
    for choice, role in [('состав, округа', 'genitive_modifier'), ('сохранить все запятые', 'nominal_conjunct')]:
        options = iter((choice, 'Шердинг'))
        reply = submit(AHCore(), text, lambda _: next(options))
        assert reply.status == 'STORED'
        assert reply.analysis.analyses[0][4].role == role
