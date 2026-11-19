from ah.core import AHCore
from ah.core.journal import JournalChannel
from ah.model import Domain
from ah.russian_grammar.memory import submit


def test_case_frames_and_analytic_future_survive_journal_replay(tmp_path):
    journal = JournalChannel(tmp_path / 'grammar.log')
    writer = AHCore()
    for text in ('Иван передал Марии книгу.', 'Буду читать книгу.', 'Анна гордится сестрой.',
                 'Я помог Ивану Смирнову и Петру Иванову.'):
        reply = submit(writer, text, journal=journal)
        assert reply.status == 'STORED' and not reply.analysis.probes
    reader = AHCore()
    checks = [
        ('Кому Иван передал книгу?', 'Марии'),
        ('Что Иван передал Марии?', 'книгу'),
        ('Кем гордится Анна?', 'сестрой'),
        ('Кому я помог?', 'Ивану Смирнову и Петру Иванову'),
        ('Я буду читать книгу?', 'Да.'),
        ('Что буду читать?', 'книгу'),
        ('Кто будет читать книгу?', 'Пользователь'),
        ('Иван будет читать книгу?', 'Неизвестно.'),
        ('Я читаю книгу?', 'Неизвестно.'),
    ]
    for question, expected in checks:
        assert submit(reader, question, journal=journal).text == expected
    assert submit(reader, 'Я буду читать книгу?', source='agent', journal=journal).status == 'UNKNOWN'
    assert submit(reader, 'Ты будешь читать книгу?', source='agent', journal=journal).text == 'Да.'
    assert submit(reader, 'Читай книгу!', journal=journal).status == 'DIRECTIVE'
    assert journal.read_global_head() == 4


def test_deixis_and_morphology_do_not_promote_an_embedded_event():
    core = AHCore()
    utterance = submit(core, 'Я читал книгу.', source='document')
    assert utterance.status == 'STORED'
    assert submit(core, 'Я читал книгу?').status == 'UNKNOWN'
    report = submit(core, 'Мария сказала, что Иван передал сестре книгу.')
    assert report.status == 'STORED'
    group = core.store.get_element(Domain.H, report.observation_ref)
    rows = [core.store.get_element(Domain.H, member.uid).meta for member in group.members]
    predicate, = (row for row in rows if row['surface'] == 'передал')
    assert predicate['assertion_status'] == 'embedded' and predicate['morphology']['tense'] == 'past'
    assert submit(core, 'Кому Иван передал книгу?').status == 'UNKNOWN'
    assert submit(core, 'Когда наступит вечер, я буду читать письмо.').status == 'STORED'
    assert submit(core, 'Когда наступит вечер, я буду читать письмо?').text == 'Да.'
    assert submit(core, 'Я буду читать письмо?').status == 'UNKNOWN'
    assert submit(core, 'Если Мария прочитает письмо, я передам книгу брату.').status == 'STORED'
    assert submit(core, 'Кому я передам книгу, если Мария прочитает письмо?').text == 'брату'
    assert submit(core, 'Кому я передам книгу, если Мария прочитает рассказ?').status == 'UNKNOWN'
    assert submit(core, 'Кому я передам книгу?').status == 'UNKNOWN'
