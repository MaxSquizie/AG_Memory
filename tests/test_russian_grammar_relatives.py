import pytest

from ah.core import AHCore
from ah.russian_grammar import analyze
from ah.russian_grammar.memory import submit


@pytest.mark.parametrize(('sentence', 'role', 'case'), [
    ('Книги, которые лежали, исчезли.', 'subject', 'nomn'),
    ('Дом, из которого Иван вышел, исчез.', 'governed', 'gent'),
    ('Человек, которому Иван передал письмо, ушёл.', 'recipient', 'datv'),
    ('Книга, которую Анна передала Ивану, исчезла.', 'object', 'accs'),
    ('Человек, с которым говорил Иван, ушёл.', 'governed', 'ablt'),
    ('Дом, о котором Иван говорил, исчез.', 'governed', 'loct'),
])
def test_relative_argument(sentence, role, case):
    result = analyze(sentence)
    assert result.status == 'PARSED_FRAGMENT'
    tree, = result.analyses
    reference, = [link for link in tree if link.rule == 'CL.NOMREF']
    assert (reference.antecedent, reference.role, reference.case) == (0, role, case)
    assert reference.morphology.case == case
    assert any(link.role == 'clause_relative' and link.head == 0 for link in tree)


def test_relative_attachment():
    nested = analyze('Книга, которую Анна передала человеку, который ушёл, исчезла.')
    assert nested.status == 'PARSED_FRAGMENT'
    assert [link.antecedent for link in nested.analyses[0] if link.rule == 'CL.NOMREF'] == [0, 5]
    ambiguous = analyze('Иван увидел брата друга, который ушёл.')
    assert ambiguous.status == 'AMBIGUOUS'
    assert ambiguous.probes[0].question == 'Which word does «который» refer to?'
    assert ambiguous.probes[0].options == ('брата', 'друга')
    assert {link.antecedent for tree in ambiguous.analyses for link in tree if link.rule == 'CL.NOMREF'} == {2, 3}
    assert analyze('Книга, которого Иван видел, исчезла.').status == 'UNRESOLVED'


def test_relative_and_indirect_question_memory():
    core = AHCore()
    observed = submit(core, 'Книга, которую Анна передала Ивану, исчезла.')
    assert observed.status == 'STORED'
    answer = submit(core, 'Что Анна передала Ивану?')
    assert (answer.text, answer.observation_ref) == ('Книга', observed.observation_ref)
    wh = submit(core, 'Я знаю, кто пришёл.')
    assert wh.status == 'STORED'
    assert wh.analysis.analyses[0][3].rule == 'CL.WH'
    assert submit(core, 'Кто пришёл?').status == 'UNKNOWN'


def test_indirect_marker_needs_an_argument_position():
    statement = analyze('Я знаю, что Иван передал сестре книгу.')
    assert statement.status == 'PARSED_FRAGMENT'
    assert statement.analyses[0][3].rule == 'CL.MARK'
    question = analyze('Я знаю, кого Иван увидел.')
    assert question.status == 'PARSED_FRAGMENT'
    assert (question.analyses[0][3].rule, question.analyses[0][3].role) == ('CL.WH', 'object')


def test_possessive_relative_in_a_caption_and_in_a_finite_sentence():
    caption = analyze('Экранизация произведения, автор которого -- Джей МакАйнерни.')
    assert caption.status == 'PARSED_FRAGMENT'
    tree, = caption.analyses
    assert (tree[0].rule, tree[1].head, tree[4].role, tree[4].head, tree[4].antecedent) == (
        'NOM.EXIST', 0, 'genitive_modifier', 3, 1)
    assert (tree[7].role, tree[7].head, tree[8].role, tree[8].head) == ('clause_relative', 1, 'name_part', 7)
    unknown = analyze('Экранизация произведения, автор которого -- Джей Квазинезнайк.')
    assert unknown.status == 'UNRESOLVED'
    finite = analyze('Книга, автор которой пришёл, исчезла.')
    assert finite.status == 'PARSED_FRAGMENT'
    link = finite.analyses[0][3]
    assert (link.role, link.case, link.head, link.antecedent) == ('genitive_modifier', 'gent', 2, 0)
    assert analyze('Книга, автор которого пришёл, исчезла.').status == 'UNRESOLVED'


@pytest.mark.parametrize("text", [
    "Каждая книга, которую Анна написала, исчезла.",
    "Иван не нашёл книгу, которую Анна написала.",
    "Если книга, которую Анна написала, исчезнет, Иван уйдёт.",
])
def test_restricted_relative_is_not_an_independent_observation(text):
    core = AHCore()
    assert submit(core, text).status == "STORED"
    assert submit(core, "Что Анна написала?").status == "UNKNOWN"


@pytest.mark.parametrize(('sentence', 'marker', 'host', 'predicate'), [
    ('Книга которую Анна передала Ивану исчезла', 1, 0, 3),
    ('Я знаю кто пришёл', 2, 1, 3),
])
def test_missing_clause_punctuation(sentence, marker, host, predicate):
    result = analyze(sentence)
    assert result.status == 'PARSED_FRAGMENT'
    tree, = result.analyses
    assert tuple(t.surface for t in result.tokens) == tuple(sentence.split())
    assert len(tree) == len(result.tokens)
    assert all(link.role != 'punctuation' for link in tree)
    assert tree[predicate].head == host
    assert tree[marker].head == predicate
    if tree[marker].rule == 'CL.NOMREF':
        assert tree[marker].antecedent == host


def test_missing_comma_preserves_antecedent_choice():
    result = analyze('Иван увидел брата друга который ушёл')
    assert result.status == 'AMBIGUOUS'
    assert result.probes[0].options == ('брата', 'друга')
