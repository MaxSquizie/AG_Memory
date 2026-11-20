from ah.core import AHCore
from ah.russian_grammar.memory import submit


def test_content_and_juxtaposition_are_distinct_readings_before_selection():
    for text in ('Я понял одно: поезд ушёл.', 'Я понял одно поезд ушёл.', 'Я понял поезд ушёл.'):
        core = AHCore()
        record = submit(core, text)
        assert record.status == 'AMBIGUOUS' and record.observation_ref is None
        readings = record.analysis.analyses
        assert {tree[-1].rule for tree in readings} == {'CONTENT.EXPL', 'UTT.PARATAXIS'}
        content, = [tree for tree in readings if tree[-1].rule == 'CONTENT.EXPL']
        host = content[content[-1].head]
        assert host.rule == ('CONTENT.ANCHOR' if 'одно' in text else 'V1')
        assert host.quantity is None and content[-1].scope == 'embedded'
        assert not core.store.links()


def test_colon_between_events_does_not_license_an_object():
    record = submit(AHCore(), 'Стемнело: мы вернулись.')
    assert record.status == 'STORED'
    tree, = record.analysis.analyses
    assert tree[-1].rule == 'UTT.PARATAXIS'
