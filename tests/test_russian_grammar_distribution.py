import pytest

from ah.core import AHCore
from ah.core.journal import JournalChannel
from ah.model import Domain
from ah.russian_grammar.distribution_graph import read
from ah.russian_grammar.memory import submit


@pytest.mark.parametrize('text', (
    'Иван и Мария весят по сто килограммов.',
    'Иван и Мария весят сто килограммов каждый.',
    'Иван и Мария — каждый из них весит сто килограммов.',
))
def test_one_assertion_answers_per_member_after_replay(tmp_path, text):
    journal = JournalChannel(tmp_path / 'distribution.log')
    record = submit(AHCore(), text, journal=journal)
    assert record.status == 'STORED' and not record.analysis.probes
    reader = AHCore()
    for question, result in (('Иван весит 100 килограммов?', 'Да.'),
                             ('Сколько весит Мария?', '100 килограммов'),
                             ('Сколько весит Пётр?', 'Неизвестно.'),
                             ('Иван весил сто килограммов?', 'Неизвестно.')):
        reply = submit(reader, question, journal=journal)
        assert reply.text == result and not reply.analysis.probes
        if reply.status == 'ANSWER':
            assert reply.support_refs == (record.observation_ref,)
    assert journal.read_global_head() == 1


def test_cardinality_bounds_and_partial_membership():
    core = AHCore()
    for text in ('Оба студента — Иван, Пётр и Олег — весят по сто килограммов.',
                 'Трое студентов — Иван и Пётр — весят по сто килограммов.'):
        assert submit(core, text).analysis.reason == 'GROUP_CARDINALITY_MISMATCH'
    assert not core.store.elements(Domain.H)
    reply = submit(core, 'Трое студентов — в том числе Иван и Пётр — весят по сто килограммов.')
    frame, = read(core, core.store.get_element(Domain.H, reply.observation_ref))
    domain, = frame.domains
    assert domain.cardinality == 3 and len(domain.members) == 2
    assert submit(core, 'Сколько весит Пётр?').text == '100 килограммов'
    assert submit(core, 'Сколько весит Олег?').status == 'UNKNOWN'


def test_group_and_class_have_distinct_grounds():
    core = AHCore()
    rule = submit(core, 'Каждый студент пришёл.')
    assert submit(core, 'Иван пришёл?').status == 'UNKNOWN'
    member = submit(core, 'Иван студент.')
    assert submit(core, 'Иван пришёл?').support_refs == (rule.observation_ref, member.observation_ref)
    for text in ('Иван и Мария вместе весят сто килограммов.', 'Трое весят по сто килограммов.'):
        assert submit(core, text).status == 'STORED'
    assert submit(core, 'Сколько весит Иван?').status == 'UNKNOWN'


def test_recorded_scope_choices_and_grounded_answers():
    import json
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / 'docs/evidence/russian_grammar_distribution/readings.json'
    for session in json.loads(path.read_text(encoding='utf8'))['cases']:
        core = AHCore()
        for step in session:
            cards = {card['prompt']: card['answer'] for card in step['probes']}
            reply = submit(core, step['text'], lambda p: cards.pop(p.prompt()))
            assert not cards
            assert (reply.status, reply.text) == (step['status'], step['reply'])
            if 'support_count' in step:
                assert len(reply.support_refs) == step['support_count']
            if 'domains' in step:
                observation = core.store.get_element(Domain.H, reply.observation_ref)
                frames = read(core, observation)
                assert [[{'role': d.role, 'head': reply.analysis.tokens[d.head].surface, 'size': d.cardinality}
                         for d in frame.domains] for frame in frames] == step['domains']


def test_quantity_can_grow_before_the_unit_arrives():
    from ah.russian_grammar import analyze

    steps = []
    result = analyze('Иван и Мария весят по сто двадцать пять килограммов.', on_distribution_step=steps.append)
    assert result.status == 'PARSED_FRAGMENT'
    assert [(s.surface, s.quantities) for s in steps if s.kind == 'quantity_candidate'] == [
        ('сто', ('100',)), ('двадцать', ('120',)), ('пять', ('125',))]
    assert (steps[-1].surface, steps[-1].quantities) == ('килограммов', ('125',))


@pytest.mark.parametrize(('statement', 'outer', 'inner'), (
    ('Каждый студент не пришёл.', False, True),
    ('Не каждый студент пришёл.', True, False),
    ('Не каждый студент не пришёл.', True, True),
))
def test_negative_universal_scope_survives_replay(tmp_path, statement, outer, inner):
    journal = JournalChannel(tmp_path / 'quantified.log')
    writer = AHCore()
    source = submit(writer, statement, journal=journal)
    assert source.status == 'STORED' and not source.analysis.probes
    obs = writer.store.get_element(Domain.H, source.observation_ref)
    frame, = read(writer, obs)
    assert (frame.quantifier_negated, frame.predicate_negated) == (outer, inner)
    reader = AHCore()
    question = 'Иван не пришёл?'
    assert submit(reader, question, journal=journal).status == 'UNKNOWN'
    member = submit(reader, 'Иван студент.', journal=journal)
    reply = submit(reader, question, journal=journal)
    if outer:
        assert reply.status == 'UNKNOWN'
    else:
        assert reply.text == 'Да.' and reply.support_refs == (source.observation_ref, member.observation_ref)
    assert submit(reader, 'Иван пришёл?', journal=journal).status == 'UNKNOWN'
    assert submit(reader, 'Пётр не пришёл?', journal=journal).status == 'UNKNOWN'


def test_negated_subject_with_second_quantifier_cannot_drop_outer_scope():
    core = AHCore()
    record = submit(core, 'Не каждый студент прочитал каждую книгу.')
    assert record.status == 'STORED'
    assert not read(core, core.store.get_element(Domain.H, record.observation_ref))
