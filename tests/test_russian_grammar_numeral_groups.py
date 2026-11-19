import pytest

from ah.russian_grammar import analyze


def tree(text):
    result = analyze(text)
    assert result.status == 'PARSED_FRAGMENT' and not result.probes, (result.reason, result.probes)
    return dict(zip((t.surface for t in result.tokens), result.analyses[0]))


@pytest.mark.parametrize(('sentence', 'head', 'role', 'outer', 'inner', 'number', 'value'), [
    ('Иван передал Марии две книги.', 'книги', 'object', 'accs', 'gent', 'sing', '2'),
    ('Иван читает 3 книги.', 'книги', 'object', 'accs', 'gent', 'sing', '3'),
    ('Иван помог двум ученикам.', 'ученикам', 'beneficiary', 'datv', 'datv', 'plur', '2'),
    ('Пришло пять студентов.', 'студентов', 'subject', 'nomn', 'gent', 'plur', '5'),
    ('Анна передала Олегу 12 писем.', 'писем', 'object', 'accs', 'gent', 'plur', '12'),
    ('Пётр купил 1,5 литра.', 'литра', 'object', 'accs', 'gent', 'sing', '1.5'),
    ('Анна боится 5 собак.', 'собак', 'stimulus', 'gent', 'gent', 'plur', '5'),
])
def test_group_case_and_word_inflection(sentence, head, role, outer, inner, number, value):
    links = tree(sentence)
    noun = links[head]
    assert (noun.role, noun.case, noun.morphology.case, noun.morphology.number) == (role, outer, inner, number)
    amount, = [link for link in links.values() if link.role == 'numeral']
    assert amount.quantity == value and list(links)[amount.head] == head


def test_quantity_rejects_incompatible_inflections():
    for sentence in ('Я читаю две книгу.', 'Два ученика упала.', 'Я помог двум ученика.'):
        assert analyze(sentence).status == 'UNRESOLVED'
