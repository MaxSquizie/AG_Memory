from ah.core import AHCore
from ah.core.journal import JournalChannel
from ah.russian_grammar import Probe, analyze
from ah.russian_grammar.memory import submit


def heads(sentence, choose=None):
    result = analyze(sentence, choose)
    assert result.status == 'PARSED_FRAGMENT', (result.reason, result.probes)
    tree, = result.analyses
    words = [token.surface for token in result.tokens]
    return {word: (words[link.head] if link.head is not None else None)
            for word, link in zip(words, tree)}


def test_participial_agreement_and_dependents():
    for text, participle, noun in (
        ('Анна передала запечатанное письмо Петру.', 'запечатанное', 'письмо'),
        ('Анна показала фотографию сестры, сделанную летом.', 'сделанную', 'фотографию'),
        ('Анна показала портрет брата, написанный летом.', 'написанный', 'портрет'),
    ):
        links = heads(text)
        assert links[participle] == noun
        if 'летом' in links:
            assert links['летом'] == participle
    links = heads('Анна передала письмо, написанное братом, сестре.')
    assert links['братом'] == 'написанное' and links['сестре'] == 'передала'
    links = heads('Иван увидел двух девочек, читавших книгу.')
    assert links['книгу'] == 'читавших' and links['читавших'] == 'девочек'
    assert analyze('Анна передала запечатанный письмо Петру.').status == 'UNRESOLVED'


def test_short_passive_with_and_without_copula():
    for text in ('Письма отправлены братом.', 'Письма были отправлены братом.'):
        links = heads(text)
        assert links['отправлены'] is None
        assert links['Письма'] == links['братом'] == 'отправлены'
        if 'были' in links:
            assert links['были'] == 'отправлены'


def test_participle_attachment_offers_both_words():
    sentence = 'Анна говорила о портрете и рисунке, написанном летом.'
    result = analyze(sentence)
    assert result.status == 'AMBIGUOUS'
    probe, = result.probes
    assert set(probe.options) == {'портрете', 'рисунке'}
    assert Probe.from_prompt(probe.prompt()) == probe
    for choice in probe.options:
        assert heads(sentence, lambda _: choice)['написанном'] == choice


def test_quantity_keeps_author_and_condition_after_replay(tmp_path):
    journal = JournalChannel(tmp_path / 'grammar.log')
    saved = submit(AHCore(), 'Если Мария придёт, Иван передаст сёстрам три книги, написанные Анной.',
                   journal=journal)
    assert saved.status == 'STORED'
    restored = AHCore()
    question = 'Сколько книг, написанных Анной, Иван передаст сёстрам, если Мария придёт?'
    answer = submit(restored, question, journal=journal)
    assert (answer.text, answer.observation_ref) == ('три', saved.observation_ref)
    assert submit(restored, question.replace('Анной', 'Ольгой'), journal=journal).status == 'UNKNOWN'
    assert submit(restored, 'Сколько книг, написанных Анной, Иван передаст сёстрам?',
                  journal=journal).status == 'UNKNOWN'
    assert journal.read_global_head() == 1
