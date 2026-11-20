from ah.core import AHCore
from ah.model import Domain
from ah.russian_grammar.memory import submit


def test_asyndetic_properties_require_a_reading_and_answer_separately():
    core = AHCore()
    text = 'Воздух прохладный свежий.'
    ambiguous = submit(core, text, lambda p: '?')
    assert ambiguous.status == 'AMBIGUOUS' and not core.store.elements(Domain.H)
    assert ambiguous.analysis.probes[0].options == ('прохладный свежий', 'свежий')
    assert submit(core, text, lambda p: 'прохладный свежий').status == 'STORED'
    assert submit(core, 'Воздух прохладный?').text == 'Да.'
    assert submit(core, 'Воздух свежий?').text == 'Да.'


def test_coordinated_subject_requires_plural_and_an_instrumental_reading():
    from ah.russian_grammar.nominal_predicates import trees
    from ah.russian_grammar.parser import Occurrence, TOKEN

    def candidates(text):
        words = tuple(Occurrence(m[0], m.start(), m.end()) for m in TOKEN.finditer(text))
        return tuple(trees(words))

    assert not candidates('Проблемами является нехватка мест и очереди')
    alternatives = candidates('Проблемами являются нехватка мест и очереди')
    assert {(a[0].role, a[1].lemma) for a in alternatives} == {
        ('predicative_complement', 'являться'), ('oblique', 'являться')}
    assert all(t[0].controller == 2 for t in alternatives if t[0].role == 'predicative_complement')
