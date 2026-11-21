from ah.core import AHCore
from ah.model import Domain
from ah.russian_grammar import analyze
from ah.russian_grammar.memory import submit


def test_number_pair_in_a_note_does_not_license_an_arbitrary_range():
    core = AHCore()
    text = 'Наградили врача Ивана Петрова (23-10).'
    reply = submit(core, text, lambda p: '23-10')
    assert reply.status == 'STORED'
    group = core.store.get_element(Domain.H, reply.observation_ref)
    words = [core.store.get_element(Domain.H, ref.uid).meta for ref in group.members]
    parts = {w['surface']: w for w in words}
    assert words[parts['23']['head']]['surface'] == 'врача'
    assert words[parts['10']['head']]['surface'] == '23'
    assert parts['23']['quantity'] == '23' and parts['10']['quantity'] == '10'
    assert analyze('Иван прочитал 5-3 книг.').reason == 'UNSUPPORTED_QUANTITY_RANGE'


def test_numeric_designation_can_follow_a_governed_name_elsewhere_in_the_clause():
    text = 'Иван выступил на Фестивале-2022.'
    reply = submit(AHCore(), text, lambda p: '2022')
    assert reply.status == 'STORED'
    tree, = reply.analysis.analyses
    assert tree[2].head == 1 and tree[3].head == 2 and tree[5].head == 3
    assert tree[5].role == 'designation' and tree[5].quantity_kind is None
    regular = analyze('Иван 5 книг прочитал.')
    assert not regular.probes and regular.analyses[0][1].role == 'numeral'


def test_unknown_governed_name_is_confirmed_as_a_whole():
    text = 'К Бынаты Хицау обращалась за помощью молодая невестка.'
    core = AHCore()
    reply = submit(core, text)
    assert reply.status == 'AMBIGUOUS' and not core.store.elements(Domain.H)
    probe, = reply.analysis.probes
    assert probe.options == ('Бынаты Хицау',)
    tree, = reply.analysis.analyses
    assert (tree[1].role, tree[1].case, tree[1].head) == ('governed', 'datv', 0)
    assert (tree[2].role, tree[2].head, tree[2].case) == ('name_part', 1, None)
