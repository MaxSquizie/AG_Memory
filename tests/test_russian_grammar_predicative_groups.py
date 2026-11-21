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


def test_fronted_instrumental_retains_its_controller_across_negative_particles():
    for sentence in ('Врачом она так и не стала.', 'Врачом она так и не стала'):
        core = AHCore()
        reply = submit(core, sentence)
        assert reply.status == 'AMBIGUOUS' and not core.store.elements(Domain.H)
        assert {tree[0].role for tree in reply.analysis.analyses} == {'predicative_complement', 'oblique'}
        for tree in reply.analysis.analyses:
            assert tree[0].head == tree[1].head == tree[2].head == tree[3].head == tree[4].head == 5
            assert tree[3].role == tree[4].role == 'particle' and tree[5].scope == 'negated'
            if tree[0].role == 'predicative_complement':
                assert tree[0].controller == 1


def test_prenegative_particle_attaches_to_the_denied_nominal_predicate():
    core = AHCore()
    reply = submit(core, 'Учителем он тоже не оказался.')
    assert reply.status == 'STORED'
    group = core.store.get_element(Domain.H, reply.observation_ref)
    rows = [core.store.get_element(Domain.H, member.uid).meta for member in group.members]
    assert rows[0]['assertion_status'] == 'negated'
    assert (rows[2]['role'], rows[2]['head']) == ('particle', 0)
    assert (rows[4]['role'], rows[4]['head']) == ('copula', 0)
