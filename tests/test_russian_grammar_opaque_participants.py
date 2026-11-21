from ah.core import AHCore
from ah.model import Domain
from ah.russian_grammar.memory import submit


def test_opaque_name_needs_confirmation_before_passive_record_is_written():
    core = AHCore()
    text = 'Зумбаро была укреплена.'
    for answer in ('?', '0'):
        result = submit(core, text, lambda probe: answer)
        assert result.status in ('UNRESOLVED', 'AMBIGUOUS')
        assert not core.store.elements(Domain.H)
    result = submit(core, text, lambda probe: 'Зумбаро')
    assert result.status == 'STORED'
    group = core.store.get_element(Domain.H, result.observation_ref)
    rows = [core.store.get_element(Domain.H, m.uid).meta for m in group.members]
    assert (rows[0]['lemma'], rows[0]['role'], rows[0]['head']) == ('Зумбаро', 'subject', 2)
    assert rows[0]['morphology'] is None
    assert rows[2]['morphology']['voice'] == 'pssv'
    assert submit(AHCore(), 'Зумбаро были укреплена.', lambda p: p.options[0]).status != 'STORED'


def test_unknown_object_and_subject_of_a_coordinated_clause_keep_separate_links():
    core = AHCore()
    text = 'Мария пригласила Флюмаро, но Ольга осталась.'
    result = submit(core, text, lambda p: 'Флюмаро' if 'Флюмаро' in p.options else '?')
    assert result.status == 'STORED'
    group = core.store.get_element(Domain.H, result.observation_ref)
    rows = [core.store.get_element(Domain.H, m.uid).meta for m in group.members]
    assert (rows[2]['role'], rows[2]['head']) == ('object', 1)
    assert (rows[5]['role'], rows[5]['head']) == ('subject', 6)
    assert rows[6]['controller'] is None


def test_unknown_attribute_and_place_leave_both_passive_preposition_hosts_open():
    text = 'Выстроенный в греко-романском стиле город был населён греками из Файюма.'
    core = AHCore()
    result = submit(core, text)
    assert result.status == 'AMBIGUOUS'
    trees = result.analysis.analyses
    assert {tree[8].head for tree in trees} == {6, 7}
    assert all(tree[2].rule == 'OPAQUE.ATTRIBUTE' and tree[2].head == 3 for tree in trees)
    assert all(tree[9].rule == 'OPAQUE.GOVERNED' and tree[9].lemma == 'Файюма' for tree in trees)
    assert not core.store.elements(Domain.H)
