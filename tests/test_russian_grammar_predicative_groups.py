from ah.core import AHCore
from ah.model import Domain
from ah.russian_grammar.memory import submit


def test_instrumental_object_property_requires_number_agreement():
    core = AHCore()
    reply = submit(core, 'Машины начали делать прочными.')
    assert reply.status == 'STORED'
    group = core.store.get_element(Domain.H, reply.observation_ref)
    rows = [core.store.get_element(Domain.H, member.uid).meta for member in group.members]
    assert rows[0]['role'] == 'object' and rows[0]['head'] == 2
    assert rows[2]['scope'] == 'phase' and rows[2]['implicit_subject'] == 'unresolved'
    assert rows[3]['controller'] == 0 and rows[3]['head'] == 2
    other = AHCore()
    assert submit(other, 'Машину начали делать прочными.').status == 'UNRESOLVED'
    assert not other.store.elements(Domain.H)


def test_quantified_participle_can_fill_a_subject_slot_with_its_own_agreement():
    core = AHCore()
    reply = submit(core, 'Все прибывшие оказались врачами.')
    assert reply.status == 'STORED'
    group = core.store.get_element(Domain.H, reply.observation_ref)
    rows = [core.store.get_element(Domain.H, member.uid).meta for member in group.members]
    assert (rows[0]['scope'], rows[0]['head']) == ('universal', 1)
    assert (rows[1]['rule'], rows[1]['role'], rows[1]['head']) == ('PART.SUBSTANTIVE', 'subject', 3)
    assert rows[1]['morphology']['pos'] == 'PRTF' and rows[1]['assertion_status'] == 'attributive'
    assert rows[2]['role'] == 'copula' and rows[3]['lemma'] == 'врач'
    other = AHCore()
    assert submit(other, 'Все прибывшие вернулась.').status == 'UNRESOLVED'
    assert not other.store.elements(Domain.H)
