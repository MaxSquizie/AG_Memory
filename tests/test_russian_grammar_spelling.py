from ah.core import AHCore
from ah.model import Domain
from ah.russian_grammar.memory import submit


def test_dictionary_spelling_needs_confirmation_and_preserves_occurrences():
    text = 'Иван посыллал письма.'
    core = AHCore()
    for refusal in ('?', '0', 'посыллал'):
        result = submit(core, text, lambda _: refusal)
        assert result.status in {'AMBIGUOUS', 'UNRESOLVED'}
        assert not core.store.elements(Domain.H)
    record = submit(core, text, lambda _: 'посылал')
    assert record.status == 'STORED'
    probe, = record.analysis.probes
    assert probe.options == ('посыллал', 'посылал')
    assert probe.context == text
    group = core.store.get_element(Domain.H, record.observation_ref)
    rows = [core.store.get_element(Domain.H, m.uid).meta for m in group.members]
    assert group.meta['verbatim'] == text
    for row in rows:
        assert text[row['start']:row['end']] == row['surface']
    assert rows[1]['recovery'] == {'original': 'посыллал', 'corrected': 'посылал'}
    assert rows[1]['lemma'] == 'посылать'
    assert submit(core, 'Иван посылал письма?').status == 'ANSWER'
