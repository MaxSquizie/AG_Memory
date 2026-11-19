"""Case government and attachment in the independent Russian grammar module."""
import pytest

from ah.russian_grammar import Probe, analyze


@pytest.mark.parametrize('text,noun,case', [
    ('На столе лежит арбуз', 'стол', 'loct'),
    ('Иван прыгнул на стол', 'стол', 'accs'),
    ('Во дворе играл Иван', 'двор', 'loct'),
    ('К ней подошёл Иван', 'она', 'datv'),
    ('Из комнаты вышел Иван', 'комната', 'gent'),
    ('Иван шёл без шапки', 'шапка', 'gent'),
    ('Иван шёл со мной', 'я', 'ablt'),
    ('Под мостом лежит арбуз', 'мост', 'ablt'),
    ('О сестре мечтал Иван', 'сестра', 'loct'),
])
def test_group_binds_the_actual_case_and_attaches_to_the_verb(text, noun, case):
    r = analyze(text, lambda p: pytest.fail(p.prompt()))
    tree, = r.analyses
    complement, = [link for link in tree if link.role == 'governed']
    assert (complement.lemma, complement.case, complement.rule) == (noun, case, 'P1')
    prep = tree[complement.head]
    assert prep.rule == 'P2' and tree[prep.head].role == 'predicate'


def test_watermelon_only_needs_lexical_reading():
    text = 'На столе стоит арбуз'
    r = analyze(text)
    probe, = r.probes
    assert '«стоит»' in probe.question and '«стоить»' in probe.question
    assert {tree[2].lemma for tree in r.analyses} == {'стоить', 'стоять'}
    for tree in r.analyses:
        assert [(l.role, l.head) for l in tree] == [
            ('preposition', 2), ('governed', 0), ('predicate', None), ('subject', 2)]
    tree, = analyze(text, lambda p: 'no such word').analyses
    assert tree[2].lemma == 'стоять'


@pytest.mark.parametrize('text,modifier,noun', [
    ('На толстом льду лежит мяч', 1, 2), ('На льду толстом лежит мяч', 2, 1),
    ('На толстом прозрачном льду лежит мяч', 2, 3),
])
def test_adjective_agrees_with_second_locative_and_stays_in_its_group(text, modifier, noun):
    tree, = analyze(text).analyses
    assert tree[modifier].rule == 'A1' and tree[modifier].head == noun
    assert tree[noun].case == 'loc2'


def test_postpositive_modifier_keeps_both_grammatically_possible_hosts():
    r = analyze('Иван положил книгу на полку красную')
    assert {tree[-1].head for tree in r.analyses} == {2, 4}
    assert r.probes[0].options == ('книгу', 'полку')


def test_probe_selects_external_head_without_reopening_the_group():
    text = 'Иван увидел человека с тяжёлым\nбиноклем'
    r = analyze(text)
    probe, = r.probes
    assert Probe.from_prompt(probe.prompt()) == probe
    assert probe.question == 'Which word does the phrase «с тяжёлым биноклем» depend on?'
    assert probe.context == 'увидел человека с тяжёлым\nбиноклем' and probe.options == ('увидел', 'человека')
    for answer, host in [('увидел', 1), ('человека', 2)]:
        resolved = analyze(text, lambda p: answer)
        tree, = resolved.analyses
        assert len(resolved.probes) == 1
        assert tree[3].head == host and tree[4].head == 5 and tree[5].head == 3
    assert analyze(text, lambda p: '0').reason == 'OPTIONS_REJECTED'


def test_each_following_group_can_attach_only_to_an_open_phrase():
    text = 'Иван увидел человека под мостом с биноклем'
    r = analyze(text)
    assert {(a[3].head, a[5].head) for a in r.analyses} == {
        (1, 1), (1, 4), (2, 1), (2, 2), (2, 4)}
    answers = iter(['человека', 'мостом'])
    tree, = analyze(text, lambda p: next(answers)).analyses
    assert tree[3].head == 2 and tree[5].head == 4
    assert analyze(text, budget=2).reason == 'ANALYSIS_BUDGET'


def test_repeated_group_is_identified_in_each_question():
    r = analyze('Иван увидел человека с биноклем с биноклем', lambda p: 'увидел')
    assert r.status == 'PARSED_FRAGMENT'
    assert [p.question for p in r.probes] == [
        'Which word does the phrase «[с биноклем] с» depend on?',
        'Which word does the phrase «биноклем [с биноклем]» depend on?',
    ]


def test_syncretic_governed_cases_remain_distinct_and_each_answer_makes_progress():
    text = 'Иван шёл с леди'
    r = analyze(text)
    assert {tree[-1].case for tree in r.analyses} == {'ablt', 'gent', 'accs'}
    assert {tree[-1].lemma for tree in r.analyses} == {'леди'}
    resolved = analyze(text, lambda p: 'no such word')
    assert resolved.status == 'PARSED_FRAGMENT' and len(resolved.probes) == 2


@pytest.mark.parametrize('text,reason', [
    ('Иван пришёл к шмумпозявке', 'NO_GOVERNED_READING'),
    ('Иван подошёл к их', 'NO_GOVERNED_READING'),
    ('Иван шёл с тяжёлой биноклем', 'GROUP_AGREEMENT'),
    ('Иван подбежал к', 'INCOMPLETE_PREPOSITIONAL_GROUP'),
    ('Иван увидел человека с тяжёлым', 'INCOMPLETE_PREPOSITIONAL_GROUP'),
    ('На столе арбуз', 'NO_COMPLETE_CLAUSE'),
])
def test_incomplete_or_incompatible_group_never_yields_a_partial_tree(text, reason):
    r = analyze(text)
    assert r.status == 'UNRESOLVED' and r.reason.split()[0] == reason
    assert not r.analyses and not r.probes

def test_compound_preposition_and_ordinary_reading_share_the_prefix():
    compound, = analyze('В течение дня Иван работал').analyses
    assert (compound[0].lemma, compound[1].role, compound[2].case) == ('в течение', 'prep_part', 'gent')
    assert any(t[-1].lemma == 'течение' and t[-1].role == 'governed'
               for t in analyze('Лодка попала в течение').analyses)
    expanded = analyze('Высокий Иван увидел человека с биноклем')
    assert expanded.probes[0].context == expanded.source


def test_case_recovery_keeps_the_original_and_partitions_valid_inflections():
    result = analyze('Иван упал под столу')
    probe, = result.probes
    assert set(probe.options) == {'стол', 'столом'}
    assert analyze(result.source, lambda _: '?').status == 'AMBIGUOUS'
    for choice, case in [('стол', 'accs'), ('столом', 'ablt')]:
        restored = analyze(result.source, lambda _: choice)
        tree, = restored.analyses
        evidence = tree[-1].recovery
        assert restored.tokens[-1].surface == evidence.original == 'столу'
        assert (evidence.corrected, evidence.case, evidence.lemma, evidence.preposition) == (choice, case, 'стол', 'под')
