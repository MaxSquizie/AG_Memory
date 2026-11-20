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
