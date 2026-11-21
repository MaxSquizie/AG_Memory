from ah.core import AHCore
from ah.model import Domain
from ah.russian_grammar.memory import submit


def test_calendar_date_attaches_to_event_and_checks_leap_year():
    core = AHCore()
    result = submit(core, '29 февраля 2024 года Анна открыла окно.')
    assert result.status == 'STORED'
    observation = core.store.get_element(Domain.H, result.observation_ref)
    rows = [core.store.get_element(Domain.H, member.uid).meta for member in observation.members]
    assert rows[rows[0]['head']]['surface'] == 'открыла'
    assert [row['surface'] for row in rows[:4]] == ['29', 'февраля', '2024', 'года']
    empty = AHCore()
    assert submit(empty, '29 февраля 2023 года Анна открыла окно.').status == 'UNRESOLVED'
    assert not empty.store.elements(Domain.H)


def test_calendar_ordinal_and_population_have_distinct_numeric_roles():
    core = AHCore()
    assert submit(core, 'В 2018 году было 235 человек').status == 'STORED'
    assert submit(core, 'Сколько человек было в 2018 году?').text == '235'
    assert submit(core, 'В 2017 году было 235 человек?').status == 'UNKNOWN'
    reply = submit(core, 'Иван ушёл в 1 году', lambda probe: '?')
    assert reply.status == 'AMBIGUOUS'
    assert {tree[3].quantity_kind for tree in reply.analysis.analyses} == {'ordinal', 'cardinal'}


def test_date_after_transitive_verb_can_be_the_object_or_the_time():
    text = 'Иван выбрал 12 июня 2020 года.'
    for answer, expected in [('12 июня 2020 года', 'object'), ('выбрал', 'temporal')]:
        core = AHCore()
        result = submit(core, text, lambda probe: answer)
        assert result.status == 'STORED'
        observation = core.store.get_element(Domain.H, result.observation_ref)
        rows = [core.store.get_element(Domain.H, member.uid).meta for member in observation.members]
        assert rows[2]['role'] == expected
        assert rows[2]['head'] == 1


def test_ordinal_interval_distinguishes_a_written_and_a_missing_dash():
    core = AHCore()
    result = submit(core, 'Храмы XII–XIV веков уничтожены.')
    assert result.status == 'STORED'
    group = core.store.get_element(Domain.H, result.observation_ref)
    rows = [core.store.get_element(Domain.H, member.uid).meta for member in group.members]
    assert (rows[1]['quantity_kind'], rows[1]['quantity'], rows[1]['head']) == ('ordinal_range', '12..14', 4)
    assert rows[3]['head'] == 1
    undecided = AHCore()
    result = submit(undecided, 'Храмы XII XIV веков уничтожены.')
    assert result.status == 'AMBIGUOUS'
    assert result.analysis.probes[-1].options == ('XII XIV веков',)
    assert not undecided.store.elements(Domain.H)


def test_accusative_quantity_marks_event_frequency_only_for_a_licensed_unit():
    for text, amount in [('Один раз алжирец появился.', '1'), ('Алжирец появился три раза.', '3')]:
        core = AHCore()
        reply = submit(core, text)
        assert reply.status == 'STORED'
        group = core.store.get_element(Domain.H, reply.observation_ref)
        rows = [core.store.get_element(Domain.H, member.uid).meta for member in group.members]
        number, = [row for row in rows if row['quantity'] == amount]
        freq = rows[number['head']]
        assert (freq['role'], rows[freq['head']]['lemma']) == ('frequency', 'появиться')
    result = submit(AHCore(), 'Одну книгу алжирец прочитал.')
    tree, = result.analysis.analyses
    assert tree[1].role == 'object'
    assert submit(AHCore(), 'Одну книгу алжирец появился.').status == 'UNRESOLVED'


def test_preposition_governs_the_calendar_year_and_retains_counted_years():
    from ah.russian_grammar.parser import analyze

    date, = analyze('Она работала с 1996 года.').analyses
    assert date[3].head == 4 and date[3].quantity_kind == 'ordinal'
    assert date[4].role == 'governed' and date[4].head == 2 and date[4].case == 'gent'
    spans = analyze('Башня простояла 1996 лет.').analyses
    assert spans and all(tree[2].quantity_kind == 'cardinal' and tree[2].head == 3 for tree in spans)


def test_four_digits_after_a_month_can_belong_to_a_following_counted_noun():
    from ah.russian_grammar.parser import analyze

    dated = analyze('В январе 1999 банк закрылся.').analyses
    assert dated and all(tree[2].rule == 'DATE.APPOS' and tree[2].head == 1 for tree in dated)
    counted, = analyze('В январе 1999 студентов сдали экзамен.').analyses
    assert counted[2].quantity_kind == 'cardinal' and counted[2].head == 3
