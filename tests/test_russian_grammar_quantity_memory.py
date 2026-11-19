from ah.core import AHCore
from ah.core.journal import JournalChannel
from ah.russian_grammar.memory import submit


def test_quantities_in_answers_and_journal_replay(tmp_path):
    journal = JournalChannel(tmp_path / 'quantities.log')
    writer = AHCore()
    for statement in ('Иван передал Марии две книги.', 'Иван помог трём студентам.'):
        assert submit(writer, statement, journal=journal).status == 'STORED'
    reader = AHCore()
    for question, answer in (
        ('Сколько книг Иван передал Марии?', 'две'),
        ('Что Иван передал Марии?', 'две книги'),
        ('Иван передал Марии 2 книги?', 'Да.'),
        ('Иван передал Марии три книги?', 'Неизвестно.'),
        ('Кому Иван помог?', 'трём студентам'),
        ('Кому помог?', 'трём студентам'),
        ('Скольким студентам Иван помог?', 'трём'),
    ):
        assert submit(reader, question, journal=journal).text == answer
    assert journal.read_global_head() == 2
    assert submit(reader, 'Олег помог брату.', journal=journal).status == 'STORED'
    assert submit(reader, 'Кому помог?', journal=journal).status == 'UNKNOWN'
    assert submit(reader, 'Помог брату?', journal=journal).status == 'UNKNOWN'


def test_compound_number_survives_conditional_scope():
    core = AHCore()
    assert submit(core, 'Если Мария придёт, Иван передаст брату двадцать две книги.').status == 'STORED'
    for question, answer in (
        ('Сколько книг Иван передаст брату, если Мария придёт?', 'двадцать две'),
        ('Иван передаст брату 22 книги, если Мария придёт?', 'Да.'),
        ('Иван передаст брату 23 книги, если Мария придёт?', 'Неизвестно.'),
        ('Сколько книг Иван передаст брату?', 'Неизвестно.'),
    ):
        assert submit(core, question).text == answer


def test_fraction_of_one_object_and_fraction_of_a_set():
    core = AHCore()
    assert submit(core, 'Я прочитал две трети книги.').status == 'STORED'
    assert submit(core, 'Я прочитал две трети книги?').text == 'Да.'
    assert submit(core, 'Я прочитал две трети книг?').status == 'UNKNOWN'
    assert submit(core, 'Что я прочитал?').text == 'две трети книги'
    other = AHCore()
    assert submit(other, 'Я прочитал две трети книг.').status == 'STORED'
    assert submit(other, 'Сколько книг я прочитал?').status == 'UNKNOWN'


def test_quantity_answers_preserve_bounds_and_uncertainty():
    for phrase, amount in (('примерно две книги', 'примерно две'), ('не менее двух книг', 'не менее двух'),
                           ('от двух до пяти книг', 'от двух до пяти'), ('несколько книг', 'несколько')):
        core = AHCore()
        assert submit(core, f'Иван передал Марии {phrase}.').status == 'STORED'
        assert submit(core, 'Сколько книг Иван передал Марии?').text == amount
        assert submit(core, 'Иван передал Марии две книги?').status == 'UNKNOWN'
        assert submit(core, 'Иван передал Марии много книг?').status == 'UNKNOWN'
        assert submit(core, 'Иван передал Марии ровно две книги.').status == 'STORED'
        assert submit(core, 'Иван передал Марии 2 книги?').text == 'Да.'
        assert submit(core, 'Сколько книг Иван передал Марии?').status == 'UNKNOWN'
