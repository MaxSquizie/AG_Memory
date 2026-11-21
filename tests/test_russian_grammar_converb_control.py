from ah.core import AHCore
from ah.model import Domain
from ah.russian_grammar.memory import submit


def test_converb_instrumental_property_belongs_to_its_object():
    core = AHCore()
    reply = submit(core, 'Инженеры обновили аэропорт, сделав его привлекательным.', lambda _: 'его')
    assert reply.status == 'STORED'
    group = core.store.get_element(Domain.H, reply.observation_ref)
    rows = [core.store.get_element(Domain.H, ref.uid).meta for ref in group.members]
    assert rows[4]['role'] == 'converb' and rows[4]['controller'] == 0
    assert rows[6]['role'] == 'predicative_complement' and rows[6]['controller'] == 5
    assert rows[6]['head'] == rows[5]['head'] == 4


def test_unverified_agent_of_converb_is_not_recorded():
    for sentence, uncertain in [('Ремонт необходим, вернувшись домой.', 'Ремонт'),
                                ('Письмо получено, подписав расписку.', 'Письмо')]:
        core = AHCore()
        for answer, status in [('?', 'AMBIGUOUS'), ('0', 'UNRESOLVED')]:
            reply = submit(core, sentence, lambda _: answer)
            assert reply.status == status
            assert reply.analysis.probes[-1].options == (uncertain,)
            assert not core.store.elements(Domain.H)
    assert submit(AHCore(), 'Студент весел, закончив работу.').status == 'STORED'

    reply = submit(core, 'Мост разрушен, перекрыв дорогу.', lambda p: p.options[0])
    assert reply.status == 'STORED'
    group = core.store.get_element(Domain.H, reply.observation_ref)
    rows = [core.store.get_element(Domain.H, ref.uid).meta for ref in group.members]
    converb = next(row for row in rows if row['role'] == 'converb')
    assert converb['assertion_status'] == 'qualified'


def test_elliptical_noun_uses_a_word_as_its_source_without_equating_referents():
    core = AHCore()
    reply = submit(core, 'Необходим ремонт повреждённой и строительство новой школы.', lambda _: 'школы')
    assert reply.status == 'STORED'
    group = core.store.get_element(Domain.H, reply.observation_ref)
    row = core.store.get_element(Domain.H, group.members[2].uid).meta
    assert row['ellipsis_source'] == 6 and row['antecedent'] is None
    edges = {link.relation_id for link in core.store.links()
             if link.source == group.members[2] and link.target == group.members[6]}
    assert edges == {'grammar.ellipsis_source'}


def test_simple_converb_regions_stop_at_finite_predicates_and_clause_boundaries():
    from ah.russian_grammar import analyze
    from ah.russian_grammar.modifiers import _regions

    result = analyze('Мария пришла; Иван вышел, закрыв дверь.')
    tree, = result.analyses
    assert (tree[6].head, tree[6].controller) == (4, 3)
    unmarked = analyze('Иван закрыв дверь ушёл; Мария спала.')
    assert all(end <= 3 for _, end in _regions(unmarked.tokens, 1))
