import pytest

from ah.core.operations import AHCore
from ah.russian_grammar.memory import submit
from ah.russian_grammar.parser import analyze


@pytest.mark.parametrize('fact,query,answer', [
    ('Иван живёт в Москве.', 'Где живёт Иван?', 'в Москве'),
    ('Иван приехал в Москву.', 'Куда приехал Иван?', 'в Москву'),
    ('Иван приехал из Москвы.', 'Откуда приехал Иван?', 'из Москвы'),
    ('Иван приехал вчера.', 'Когда приехал Иван?', 'вчера'),
    ('Иван приехал в понедельник.', 'Когда приехал Иван?', 'в понедельник'),
    ('Иван говорил с трудом.', 'Как говорил Иван?', 'с трудом'),
    ('Иван улыбнулся от радости.', 'Почему улыбнулся Иван?', 'от радости'),
    ('Иван говорил тихо.', 'Как говорил Иван?', 'тихо'),
    ('Иван остался из-за дождя.', 'Почему остался Иван?', 'из-за дождя'),
    ('Иван приехал для отдыха.', 'Зачем приехал Иван?', 'для отдыха'),
])
def test_adjunct_answer(fact, query, answer):
    core = AHCore()
    record = submit(core, fact)
    assert record.status == 'STORED'
    reply = submit(core, query)
    assert (reply.text, reply.observation_ref) == (answer, record.observation_ref)


@pytest.mark.parametrize('fact,query', [
    ('Иван не живёт в Москве.', 'Где живёт Иван?'),
    ('Иван мечтает о доме.', 'Где мечтает Иван?'),
    ('Иван приехал из Москвы.', 'Куда приехал Иван?'),
])
def test_adjunct_scope_and_semantics(fact, query):
    core = AHCore()
    assert submit(core, fact).status == 'STORED'
    assert submit(core, query).status == 'UNKNOWN'


@pytest.mark.parametrize('phrase,count', [('улыбаясь', 1), ('улыбаясь и размахивая рукой', 2)])
def test_shared_converb_actor(phrase, count):
    result = analyze(f'Мальчик вошёл, {phrase}.')
    tree, = result.analyses
    members = [link for link in tree if link.role == 'converb']
    assert [(link.head, link.controller) for link in members] == [(1, 0)] * count
    if count == 2:
        assert tree[-1].head == len(tree) - 2


@pytest.mark.parametrize(('fact', 'why', 'answer', 'independent'), [
    ('Олег пришёл, чтобы прочитать книгу.', 'Зачем пришёл Олег?', 'чтобы прочитать книгу', 'Олег прочитал книгу?'),
    ('Олег ушёл, потому что начался дождь.', 'Почему ушёл Олег?', 'потому что начался дождь', 'Начался дождь?'),
])
def test_typed_clause_answer(fact, why, answer, independent):
    core = AHCore()
    record = submit(core, fact)
    assert record.status == 'STORED'
    result = submit(core, why)
    assert (result.text, result.observation_ref) == (answer, record.observation_ref)
    assert submit(core, independent).status == 'UNKNOWN'


def test_parataxis_does_not_supply_a_cause():
    core = AHCore()
    assert submit(core, 'Олег ушёл: начался дождь.').status == 'STORED'
    assert submit(core, 'Почему ушёл Олег?').status == 'UNKNOWN'


@pytest.mark.parametrize(('fact', 'query', 'answer'), [
    ('Иван пошёл в библиотеку.', 'Куда пошёл Иван?', 'в библиотеку'),
    ('На стол Анна положила книгу.', 'Куда Анна положила книгу?', 'На стол'),
    ('Анна работает в химической лаборатории.', 'Где работает Анна?', 'в химической лаборатории'),
    ('Книга лежит на столе.', 'Где лежит книга?', 'на столе'),
    ('Иван верит в дружбу.', 'Куда верит Иван?', 'Неизвестно.'),
    ('Иван жил в восторге.', 'Где жил Иван?', 'Неизвестно.'),
])
def test_spatial_frames_and_nominal_evidence(fact, query, answer):
    core = AHCore()
    assert submit(core, fact).status == 'STORED'
    assert submit(core, query).text == answer


def test_attested_noun_in_unpunctuated_prefixed_converb():
    text = 'Проходя через галоклин стремитесь перемешать слои.'
    ambiguous = analyze(text)
    assert ambiguous.status == 'AMBIGUOUS'
    assert 'стремитесь' in ambiguous.probes[0].options
    command = submit(AHCore(), text, lambda probe: 'стремитесь')
    assert command.status == 'DIRECTIVE'
    tree, = command.analysis.analyses
    assert (tree[0].role, tree[0].head, tree[0].implicit_subject) == ('converb', 3, 'addressee_group')
    assert (tree[2].lemma, tree[2].head, tree[2].case) == ('галоклин', 1, 'accs')
    assert (tree[4].role, tree[5].head) == ('infinitive', 4)
