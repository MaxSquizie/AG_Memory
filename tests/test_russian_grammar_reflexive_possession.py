from ah.core import AHCore
from ah.model import Domain
from ah.russian_grammar.memory import submit


def test_possessor_is_saved_independently_of_word_order():
    for sentence in ('Иван взял свою книгу.', 'Книгу свою взял Иван.'):
        core = AHCore()
        record = submit(core, sentence)
        assert record.status == 'STORED' and not record.analysis.probes
        group = core.store.get_element(Domain.H, record.observation_ref)
        tree, = record.analysis.analyses
        index = next(i for i, link in enumerate(tree) if link.role == 'possessive')
        owner = tree[index].antecedent
        assert tree[owner].lemma == 'иван' and tree[tree[index].head].lemma == 'книга'
        assert core.store.find_link('grammar.antecedent', group.members[index].uid, group.members[owner].uid)
        assert submit(core, 'Чью книгу Иван взял?').text == 'Иван'
        assert submit(core, 'Чью книгу Пётр взял?').status == 'UNKNOWN'


def test_infinitive_possessor_is_independent_of_control():
    core = AHCore()
    record = submit(core, 'Иван попросил Петра принести свою книгу.')
    assert record.status == 'AMBIGUOUS' and record.observation_ref is None
    owners = {tree[tree[4].antecedent].lemma for tree in record.analysis.analyses
              if tree[3].controller == 2 and tree[4].antecedent is not None}
    assert owners == {'иван', 'пётр'}
    record = submit(core, 'Мария сказала, что Иван взял свою книгу.')
    tree, = record.analysis.analyses
    modifier = next(link for link in tree if link.lemma == 'свой')
    assert tree[modifier.antecedent].lemma == 'иван'
    assert submit(core, 'Чью книгу Иван взял?').status == 'UNKNOWN'


def test_first_person_possessor_and_unknown_past_subject():
    core = AHCore()
    assert submit(core, 'Беру свою книгу.').status == 'STORED'
    assert submit(core, 'Чью книгу я беру?').text == 'Пользователь'
    assert submit(core, 'Взял свою книгу.').status == 'STORED'
    assert submit(core, 'Чью книгу Иван взял?').status == 'UNKNOWN'
