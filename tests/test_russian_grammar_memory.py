import pytest

from ah.core.journal import JournalChannel
from ah.core.operations import AHCore
from ah.model import Domain
from ah.russian_grammar.memory import ROOT_KEY, submit


def test_canonical_journal_recovers_scoped_observation_and_read_only_answers(tmp_path):
    journal = JournalChannel(tmp_path / 'events.log')
    original = 'Иван попросил Марию прочитать книгу.'
    stored = submit(AHCore(), original, journal=journal, source='user')
    assert stored.status == 'STORED'
    head = journal.read_global_head()

    core = AHCore()
    for question, expected in [
        ('Кого попросил Иван?', 'Марию'),
        ('Что Иван попросил Марию прочитать?', 'книгу'),
        ('Что попросил прочитать Иван?', 'книгу'),
    ]:
        reply = submit(core, question, journal=journal)
        assert (reply.text, reply.observation_ref) == (expected, stored.observation_ref)
    assert submit(core, 'Мария прочитала книгу?', journal=journal).status == 'UNKNOWN'
    assert submit(core, 'Иван увидел человека с биноклем?', journal=journal).status == 'AMBIGUOUS'
    assert submit(core, 'Прочитай книгу!', journal=journal).status == 'UNRESOLVED'
    assert journal.read_global_head() == head
    group = core.store.get_element(Domain.H, stored.observation_ref)
    assert (group.meta['source'], group.meta['verbatim']) == ('user', original)
    tokens = [core.store.get_element(Domain.H, m.uid).meta for m in group.members]
    assert tokens[3]['assertion_status'] == 'embedded'
    assert group.members[tokens[3]['controller']] == group.members[2]


def test_journal_failure_never_publishes_a_partial_observation(tmp_path, monkeypatch):
    journal = JournalChannel(tmp_path / 'events.log')
    core = AHCore()

    def fail(*args, **kwargs):
        raise OSError('disk full')

    monkeypatch.setattr(journal, 'append', fail)
    with pytest.raises(OSError, match='disk full'):
        submit(core, 'Мария прочитала книгу.', journal=journal)
    assert not core.store.find_elements_with_property(ROOT_KEY)
    assert not tuple(core.store.elements(Domain.H))
    assert journal.read_global_head() == 0


@pytest.mark.parametrize(('text', 'choose', 'expected'), [
    ('Слегка дремав, Иван чуть было не упал', None, {'дремать': 'asserted', 'упасть': 'averted'}),
    ('Иван не ушёл, а Мария осталась', None, {'уйти': 'negated', 'остаться': 'asserted'}),
    ('Иван сказал, что Мария не ушла, а Пётр остался', lambda _: 'ушла',
     {'сказать': 'asserted', 'уйти': 'embedded', 'остаться': 'embedded'}),
])
def test_sibling_predicates_keep_local_polarity_and_enclosing_report(text, choose, expected):
    core = AHCore()
    record = submit(core, text, choose)
    group = core.store.get_element(Domain.H, record.observation_ref)
    rows = [core.store.get_element(Domain.H, member.uid).meta for member in group.members]
    assert {row['lemma']: row['assertion_status'] for row in rows if row['lemma'] in expected} == expected


def test_full_personal_name_is_one_subject_and_one_answer():
    core = AHCore()
    reply = submit(core, 'Иван Смирнов ушёл')
    assert reply.status == 'STORED' and not reply.analysis.probes
    tree, = reply.analysis.analyses
    assert [(link.role, link.head) for link in tree] == [('subject', 2), ('name_part', 0), ('predicate', None)]
    assert submit(core, 'Кто ушёл?').text == 'Иван Смирнов'
    assert submit(core, 'Ушёл Саша Смирнова').status == 'UNRESOLVED'
