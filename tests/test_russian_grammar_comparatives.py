import pytest

from ah.russian_grammar.parser import analyze


@pytest.mark.parametrize(('source', 'roles', 'heads', 'case'), [
    ('Иван выше Петра.', ('subject', 'predicate', 'comparison_standard'), (1, None, 1), 'gent'),
    ('Иван работает быстрее Петра.', ('subject', 'predicate', 'comparative_adverb', 'comparison_standard'),
     (1, None, 1, 2), 'gent'),
    ('Сестра моложе, чем брат.', ('subject', 'predicate', 'punctuation', 'comparison_marker', 'comparison_standard'),
     (1, None, 1, 4, 1), 'nomn'),
])
def test_comparison_standard(source, roles, heads, case):
    result = analyze(source)
    assert result.analyses
    for tree in result.analyses:
        assert tuple(link.role for link in tree) == roles
        assert tuple(link.head for link in tree) == heads
        assert tree[roles.index('comparative_adverb') if 'comparative_adverb' in roles else 1].morphology.pos == 'COMP'
        assert tree[-1].morphology.case == case


def test_instrumental_predicate_with_semicopula():
    result = analyze('Она оказалась врачом.')
    assert result.status == 'PARSED_FRAGMENT'
    subject, copula, predicate = result.analyses[0]
    assert (subject.head, copula.role, copula.head) == (2, 'copula', 2)
    assert (predicate.role, predicate.morphology.case) == ('predicate', 'ablt')


def test_memory_preserves_both_sides_of_comparison():
    from ah.core.operations import AHCore
    from ah.russian_grammar.memory import submit

    core = AHCore()
    assert submit(core, 'Иван выше Петра.').status == 'STORED'
    assert submit(core, 'Кто выше Петра?').text == 'Иван'
    assert submit(core, 'Иван выше кого?').text == 'Петра'
    assert submit(core, 'Иван выше Сергея?').status == 'UNKNOWN'


def test_modified_standard_and_optional_standard():
    from ah.core.operations import AHCore
    from ah.russian_grammar.memory import submit

    core = AHCore()
    record = submit(core, 'Иван выше старшего брата.')
    tree, = record.analysis.analyses
    assert (tree[2].role, tree[2].head, tree[3].role) == ('attribute', 3, 'comparison_standard')
    assert submit(core, 'Иван выше Пётр.').status == 'UNRESOLVED'
    bare = submit(core, 'Иван выше.')
    assert bare.status == 'STORED'
    assert bare.analysis.analyses[0][1].rule == 'V.CMP'
    assert submit(core, 'Иван выше Петра?').status == 'UNKNOWN'


def test_comparison_standard_has_its_own_possessor():
    result = analyze('Мария пришла раньше, чем её старший брат.', lambda _: 'Мария')
    tree, = result.analyses
    assert (tree[5].role, tree[5].head, tree[5].antecedent) == ('possessive', 7, 0)
    assert (tree[6].role, tree[6].head, tree[7].role) == ('attribute', 7, 'comparison_standard')


@pytest.mark.parametrize(('sentence', 'reversed_order', 'subordinate'), [
    ('Иван читает быстрее, чем Мария пишет.', 'Мария пишет быстрее, чем Иван читает?', 'Мария пишет?'),
    ('Иван читает быстрее чем Мария пишет.', 'Мария пишет быстрее чем Иван читает?', 'Мария пишет?'),
    ('Мария медленнее работает, нежели Иван читает.', 'Иван медленнее читает, нежели Мария работает?', 'Иван читает?'),
])
def test_comparison_clause_attaches_to_degree_with_its_own_subject(sentence, reversed_order, subordinate):
    from ah.core import AHCore
    from ah.russian_grammar.memory import submit

    core = AHCore()
    record = submit(core, sentence)
    assert record.status == 'STORED' and not record.analysis.steps
    tree, = record.analysis.analyses
    degree, = (i for i, link in enumerate(tree) if link.rule == 'CMP.ADV')
    child, = (i for i, link in enumerate(tree) if link.rule == 'CL.COMPARISON')
    assert tree[child].head == degree and tree[child].scope == 'comparison'
    subjects = [link.head for link in tree if link.role == 'subject']
    assert subjects == [tree[degree].head, child]
    assert submit(core, sentence[:-1] + '?').text == 'Да.'
    assert submit(core, reversed_order).status == 'UNKNOWN'
    assert submit(core, subordinate).status == 'UNKNOWN'


@pytest.mark.parametrize(('sentence', 'clause_rule', 'scope'), [
    ('Иван знает, чем Мария пишет.', 'CL.COMP', 'embedded'),
    ('Иван ушёл прежде, чем Мария пришла.', 'CL.ADV', 'temporal'),
    ('Прежде чем Мария пришла, Иван ушёл.', 'CL.ADV', 'temporal'),
])
def test_noncomparative_chem_keeps_its_clause_relation(sentence, clause_rule, scope):
    result = analyze(sentence)
    tree, = result.analyses
    clause, = (link for link in tree if link.rule == clause_rule)
    assert clause.scope == scope
    assert all(link.rule != 'CL.COMPARISON' for link in tree)
