import pytest

from ah.core import AHCore
from ah.model import Domain
from ah.russian_grammar import analyze
from ah.russian_grammar.memory import submit


SENTENCE = ('Методика перевода естественно-языковых конструкций в элементы АГ-памяти '
            'задаёт переход от текста к структурированному представлению.')
PREFIX = 'Методика перевода конструкций'


def test_nominal_extensions_are_licensed_at_the_word_that_arrives():
    steps = []
    analyze(PREFIX + ' естественно-языковых выражений задаёт переход.', on_nominal_step=steps.append)
    assert steps[1].genitive_hosts == (0,)
    assert 1 in steps[2].genitive_hosts
    assert 2 in steps[3].attribute_hosts and steps[3].awaits_noun
    assert 3 in steps[4].attribute_dependents and 2 in steps[4].genitive_hosts

    steps.clear()
    analyze(PREFIX + ' из текста в элементы задаёт переход.', on_nominal_step=steps.append)
    assert 1 in steps[3].preposition_hosts and 1 in steps[5].preposition_hosts


@pytest.mark.parametrize('source', [SENTENCE, SENTENCE[:-1], SENTENCE.replace(' задаёт', ', задаёт')])
def test_read_back_every_dependency_of_the_method(source):
    def choose(probe):
        if 'только признак' in probe.options:
            return 'только признак'
        for fragment, host in [('«в элементы', 'перевода'), ('«АГ-памяти»', 'элементы'),
                               ('«от текста', 'переход'), ('«к структурированному', 'переход'),
                               ('«конструкций»', 'перевода')]:
            if fragment in probe.question and host in probe.options:
                return host
        pytest.fail(probe.prompt())

    core = AHCore()
    reply = submit(core, source, choose)
    assert reply.status == 'STORED'
    observation = core.store.get_element(Domain.H, reply.observation_ref)
    assert observation.meta['verbatim'] == source
    nodes = [core.store.get_element(Domain.H, ref.uid) for ref in observation.members]
    expected = {
        'Методика': 'задаёт', 'перевода': 'Методика', 'естественно-языковых': 'конструкций',
        'конструкций': 'перевода', 'в': 'перевода', 'элементы': 'в', 'АГ-памяти': 'элементы',
        'задаёт': None, 'переход': 'задаёт', 'от': 'переход', 'текста': 'от',
        'к': 'переход', 'структурированному': 'представлению', 'представлению': 'к',
    }
    heads = {}
    for node in nodes:
        row = node.meta
        assert source[row['start']:row['end']] == row['surface']
        if row['role'] == 'punctuation':
            continue
        edges = core.store.outgoing_links(node.uid, 'grammar.' + row['role'])
        head = row['head']
        assert [edge.target.uid for edge in edges] == ([] if head is None else [nodes[head].uid])
        heads[row['surface']] = None if head is None else nodes[head].meta['surface']
    assert heads == expected
    roles = {node.meta['surface']: node.meta['role'] for node in nodes}
    assert (roles['Методика'], roles['задаёт'], roles['переход']) == ('subject', 'predicate', 'object')


@pytest.mark.parametrize(('answer', 'expected'), [('0', 'UNRESOLVED'), ('?', 'AMBIGUOUS')])
def test_open_attachment_never_writes_the_partial_method(answer, expected):
    core = AHCore()
    assert submit(core, SENTENCE, lambda _: answer).status == expected
    assert not core.store.elements(Domain.H) and not core.store.links()


def test_case_government_keeps_a_homonymous_noun_open_for_genitive_extensions():
    dates = analyze('С начала 1960-х писал музыку к фильмам.')
    assert dates.analyses
    assert all(tree[2].head == 1 and tree[2].case == 'gent' and tree[2].quantity == '1960'
               and tree[2].morphology.number == 'plur' for tree in dates.analyses)
    deadlines = analyze('Она не должна составляться в последний день установленного срока её представления.')
    assert any(tree[8].head == 6 and tree[10].head == 8 and tree[7].head == 8
               and tree[9].head == 10 for tree in deadlines.analyses)
