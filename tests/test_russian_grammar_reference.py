from ah.core import AHCore
from ah.core.journal import JournalChannel
from ah.model import Domain
from ah.russian_grammar.memory import submit


def test_event_reference_and_case_recovery_survive_replay(tmp_path):
    journal = JournalChannel(tmp_path / 'events.log')
    text = ('Слегка дремав, Иван, очень высокий, чуть было не упал со стула, '
            'что было бы очень больно из-за расстояние между его головой и полом.')

    def choose(probe):
        if 'dictionary form' in probe.question:
            return 'головой' if '«голова»' in probe.question else 'no such word'
        return next(word for word in ('Иван', 'расстояние', 'упал') if word in probe.options)

    core = AHCore()
    assert submit(core, text, journal=journal).status == 'AMBIGUOUS'
    record = submit(core, text, choose, journal=journal)
    news = submit(core, 'Мария опоздала, что удивило Анну.', journal=journal)
    assert record.status == news.status == 'STORED'
    restored = AHCore()
    answer = submit(restored, 'Что удивило Анну?', journal=journal)
    assert (answer.text, answer.observation_ref) == ('Мария опоздала', news.observation_ref)
    assert submit(restored, 'Мария опоздала?', journal=journal).text == 'Да.'
    assert submit(restored, 'Иван упал?', journal=journal).status == 'UNKNOWN'
    assert journal.read_global_head() == 2

    group = restored.store.get_element(Domain.H, record.observation_ref)
    assert group.meta['verbatim'] == text
    rows = [restored.store.get_element(Domain.H, member.uid).meta for member in group.members]
    tokens = {row['surface']: i for i, row in enumerate(rows)}
    for term, status in [('дремав', 'asserted'), ('упал', 'averted'), ('больно', 'conditional')]:
        assert rows[tokens[term]]['assertion_status'] == status
    for term, target in [('что', 'упал'), ('его', 'Иван')]:
        assert rows[tokens[term]]['antecedent'] == tokens[target]
        assert restored.store.find_link('grammar.antecedent', group.members[tokens[term]].uid,
                                        group.members[tokens[target]].uid) is not None
    assert rows[tokens['что']]['event_view'] == 'event'
    assert rows[tokens['расстояние']]['recovery'] == {
        'original': 'расстояние', 'corrected': 'расстояния', 'preposition': 'из-за',
        'lemma': 'расстояние', 'case': 'gent',
    }
    assert rows[tokens['головой']]['lemma'] == 'голова'
