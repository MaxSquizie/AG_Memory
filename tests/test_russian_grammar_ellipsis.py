import pytest

from ah.core.operations import AHCore
from ah.russian_grammar.memory import submit
from ah.russian_grammar.parser import analyze


def test_gap_has_two_events_and_preserves_real_offsets():
    core = AHCore()
    sentence = 'Анна купила книгу, а Иван — журнал.'
    stored = submit(core, sentence)
    assert stored.status == 'STORED'
    tree, = stored.analysis.analyses
    gap = next(i for i, link in enumerate(tree) if link.rule == 'GAP')
    token = stored.analysis.tokens[gap]
    assert sentence[token.start:token.end] == '—'
    assert tree[gap].lemma == tree[tree[gap].head].lemma == 'купить'
    assert [(v.role, v.lemma) for v in tree if v.head == gap and v.rule.startswith('GAP.')] == [
        ('subject', 'иван'), ('object', 'журнал')]
    assert submit(core, 'Что купил Иван?').text == 'журнал'
    assert submit(core, 'Что купила Анна?').text == 'книгу'


@pytest.mark.parametrize('sentence', [
    'Анна купила книгу, или Иван — журнал.',
    'Если Анна купила книгу, а Иван — журнал, Мария ушла.',
])
def test_scoped_gapping_does_not_assert_a_purchase(sentence):
    core = AHCore()
    assert submit(core, sentence).status == 'STORED'
    assert submit(core, 'Что купил Иван?').status == 'UNKNOWN'
    assert submit(core, 'Что купила Анна?').status == 'UNKNOWN'


def test_one_member_clauses():
    nominal, = analyze('Ночь.').analyses
    assert (nominal[0].lemma, nominal[0].case, nominal[0].rule) == ('ночь', 'nomn', 'NOM.EXIST')
    existential, = analyze('У меня нет книги.').analyses
    assert existential[2].scope == 'negated'
    assert (existential[1].lemma, existential[1].head, existential[3].case) == ('я', 0, 'gent')


def test_questions_preserve_groups_in_an_absence_claim():
    core = AHCore()
    assert submit(core, 'У маленькой девочки нет новой книги.').status == 'STORED'
    assert submit(core, 'У кого нет новой книги?').text == 'маленькой девочки'
    assert submit(core, 'Чего нет у маленькой девочки?').text == 'новой книги'
    assert submit(core, 'У кого нет книги?').status == 'UNKNOWN'
    assert submit(core, 'У маленькой девочки есть новая книга?').status in ('UNKNOWN', 'AMBIGUOUS')


def test_gapped_clause_with_extended_arguments():
    core = AHCore()
    assert submit(core, 'Анна купила новую книгу, а Иван — старый журнал.').status == 'STORED'
    assert submit(core, 'Что купил Иван?').text == 'старый журнал'
    assert submit(core, 'Что купила Анна?').text == 'новую книгу'


@pytest.mark.parametrize('sentence', [
    'Иван купил две книги, а Мария — три.',
    'Иван купил две книги а Мария три',
    'Иван купил две книги а Мария, три',
])
def test_gapped_count_reads_two_separate_purchases(sentence):
    from ah.model import Domain

    core = AHCore()
    stored = submit(core, sentence)
    assert stored.status == 'STORED'
    observation = core.store.get_element(Domain.H, stored.observation_ref)
    rows = [core.store.get_element(Domain.H, ref.uid).meta for ref in observation.members]
    i = next(i for i, row in enumerate(rows) if row['rule'] == 'GAP.NOUN')
    source = rows[i]['ellipsis_source']
    assert rows[i]['lemma'] == rows[source]['lemma'] == 'книга'
    assert rows[i]['start'] == rows[i]['end'] and rows[i]['surface'] == ''
    assert core.store.find_link('grammar.ellipsis_source', observation.members[i].uid, observation.members[source].uid)
    assert submit(core, 'Сколько книг купил Иван?').text == 'две'
    assert submit(core, 'Сколько книг купила Мария?').text == 'три'
    assert submit(core, 'Что купила Мария?').text == 'три книги'
    assert submit(core, 'Кто купил три книги?').text.casefold() == 'мария'


def test_gapped_count_inflects_an_unspoken_noun_and_preserves_alternative_scope():
    core = AHCore()
    assert submit(core, 'Иван купил пять книг а Мария двадцать одну').status == 'STORED'
    assert submit(core, 'Что купила Мария?').text == 'двадцать одну книгу'
    alternative = AHCore()
    assert submit(alternative, 'Иван купил пять книг или Мария две').status == 'STORED'
    assert submit(alternative, 'Сколько книг купила Мария?').status == 'UNKNOWN'


@pytest.mark.parametrize(('sentence', 'options'), [
    ('Иван купил две книги и три журнала, а Мария — пять.', ('книги', 'журнала')),
    ('Иван купил книгу, а Мария — журнал, а Пётр — три.', ('книгу', 'журнал')),
    ('Иван купил книгу, а Мария продала журнал, а Пётр — три.', ('купил', 'продала')),
])
def test_competing_ellipsis_sources_require_a_choice(sentence, options):
    core = AHCore()
    result = submit(core, sentence)
    assert result.status == 'AMBIGUOUS' and result.observation_ref is None
    assert result.analysis.probes[-1].options == options


def test_uncounted_source_and_scoped_source():
    core = AHCore()
    assert submit(core, 'Иван купил книгу, а Мария — три.').status == 'STORED'
    assert submit(core, 'Что купила Мария?').text == 'три книги'
    for assertion in ('Иван не купил две книги, а Мария — три.', 'Анна могла купить две книги, а Мария — три.'):
        result = submit(AHCore(), assertion)
        assert result.status == 'UNRESOLVED' and result.observation_ref is None


def test_unmarked_object_can_compete_with_a_nominal_predicate():
    result = submit(AHCore(), 'Иван купил книгу а Мария тетрадь')
    assert result.status == 'AMBIGUOUS' and result.analysis.probes[-1].options == ('купил', 'тетрадь')
    explicit = submit(AHCore(), 'Иван купил книгу, а Мария довольна.')
    assert explicit.status == 'STORED'
    assert all(link.rule != 'GAP' for link in explicit.analysis.analyses[0])
