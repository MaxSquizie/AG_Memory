from ah.core import AHCore
from ah.core.journal import JournalChannel
from ah.gui.grammar_chat import GrammarChat
from ah.russian_grammar.memory import submit


def test_pending_choice_resumes_original_input_and_writes_once(tmp_path):
    chat = GrammarChat()
    core = AHCore()
    journal = JournalChannel(tmp_path / 'session.log')

    def send(text):
        return chat.send(text, lambda source, choose: submit(core, source, choose, journal=journal))

    sentence = 'Иван увидел человека с биноклем'
    send(sentence)
    assert chat.pending and set(chat.pending.options) == {'увидел', 'человека'}
    send('бинокль')
    assert chat.pending and journal.read_global_head() == 0
    send('?')
    assert chat.pending is None and journal.read_global_head() == 0
    send(sentence)
    send('человека')
    assert chat.pending is None and journal.read_global_head() == 1
    send(sentence + '?')
    assert send('человека') == 'Да.'
    assert journal.read_global_head() == 1
