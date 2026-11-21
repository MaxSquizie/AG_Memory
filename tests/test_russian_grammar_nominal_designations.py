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


def test_comma_between_nominal_homonym_and_agreeing_noun_requires_a_choice():
    for text, phrase in [('Иван участвовал в боевых, вылетах.', 'боевых, вылетах'),
                         ('Они пришли в белых, куртках.', 'белых, куртках')]:
        core = AHCore()
        reply = submit(core, text)
        assert reply.status == 'AMBIGUOUS' and not core.store.elements(Domain.H)
        assert reply.analysis.probes[-1].options == (phrase, 'сохранить все запятые')
    for ordinary in ('Иван участвовал в конкурсах, выставках.',
                     'Он наблюдал движение спутников, комет и метеоров.'):
        reply = submit(AHCore(), ordinary)
        assert reply.status == 'STORED' and not reply.analysis.probes
