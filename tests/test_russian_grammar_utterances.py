from ah.core import AHCore
from ah.russian_grammar.memory import submit


def test_quotation_preserves_reported_words_and_speaker_boundary():
    core = AHCore()
    assert submit(core, 'Иван сказал: «Я приду».').status == 'STORED'
    assert submit(core, 'Что сказал Иван?').text == '«Я приду»'
    assert submit(core, 'Иван придёт?').status == 'UNKNOWN'
    assert submit(core, 'Я приду?').status == 'UNKNOWN'
    assert submit(core, '«Кто придёт?» — спросила Ольга.').status == 'STORED'
    assert submit(core, 'Что спросила Ольга?').text == '«Кто придёт?»'


def test_parenthetical_and_address_change_the_status_of_an_utterance():
    core = AHCore()
    assert submit(core, 'Иван, открой окно.').status == 'DIRECTIVE'
    assert submit(core, 'Вероятно, Сергей уехал.').status == 'STORED'
    assert submit(core, 'Сергей уехал?').status == 'UNKNOWN'
    assert submit(core, 'Во-первых, Сергей уехал.').status == 'STORED'
    assert submit(core, 'Сергей уехал?').text == 'Да.'


def test_negation_stays_with_the_infinitive_of_purpose():
    core = AHCore()
    result = submit(core, 'Чтобы не опоздать, Иван пришёл.')
    assert result.status == 'STORED'
    tree, = result.analysis.analyses
    predicate = next(link for link in tree if link.rule == 'UTT.PURPOSE')
    assert predicate.scope == 'purpose_negated'
    assert submit(core, 'Зачем пришёл Иван?').text.casefold() == 'чтобы не опоздать'
    assert submit(core, 'Иван опоздал?').status == 'UNKNOWN'
