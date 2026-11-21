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


def test_coordinated_participles_keep_their_agents_and_common_noun():
    sentence = 'Иван получил письмо, написанное Анной и подписанное Петром.'
    result = analyze(sentence)
    assert result.status == 'PARSED_FRAGMENT'
    tree, = result.analyses
    words = [token.surface for token in result.tokens]
    written, signed = words.index('написанное'), words.index('подписанное')
    assert tree[written].head == tree[signed].head == words.index('письмо')
    assert tree[signed].coord_head == written
    assert tree[words.index('Анной')].head == written
    assert tree[words.index('Петром')].head == signed
    assert analyze(sentence.replace('подписанное', 'подписанный')).status == 'UNRESOLVED'


def test_coordinated_modifiers_preserve_authors_and_conjunction_on_replay(tmp_path):
    journal = JournalChannel(tmp_path / 'grammar.log')
    statement = 'Если Мария придёт, Иван передаст сёстрам три книги, написанные Анной и прочитанные Ольгой.'
    record = submit(AHCore(), statement, journal=journal)
    assert record.status == 'STORED'
    reader = AHCore()
    question = 'Сколько книг, написанных Анной и прочитанных Ольгой, Иван передаст сёстрам, если Мария придёт?'
    answer = submit(reader, question, journal=journal)
    assert (answer.text, answer.observation_ref) == ('три', record.observation_ref)
    swapped = question.replace('Анной и прочитанных Ольгой', 'Ольгой и прочитанных Анной')
    assert submit(reader, swapped, journal=journal).status == 'UNKNOWN'
    assert submit(reader, question.replace(' и ', ' или '), journal=journal).status == 'UNKNOWN'
    assert journal.read_global_head() == 1


def test_one_attachment_choice_resolves_the_entire_participial_group():
    text = 'Анна говорила о портрете и рисунке, написанном братом и купленном сестрой.'
    result = analyze(text)
    assert result.status == 'AMBIGUOUS'
    probe, = result.probes
    assert set(probe.options) == {'портрете', 'рисунке'}
    for choice in probe.options:
        selected = analyze(text, lambda _: choice)
        assert selected.status == 'PARSED_FRAGMENT' and len(selected.probes) == 1
        tree, = selected.analyses
        words = [token.surface for token in selected.tokens]
        assert words[tree[words.index('написанном')].head] == choice
        assert words[tree[words.index('купленном')].head] == choice


def test_shared_agent_changes_only_after_a_word_choice(tmp_path):
    statement = 'Письмо, написанное и подписанное Анной, пропало.'
    probe, = analyze(statement).probes
    assert Probe.from_prompt(probe.prompt()).options == ('подписанное', 'написанное и подписанное')
    for index, choice in enumerate(probe.options):
        log = JournalChannel(tmp_path / f'agent-{index}.log')
        writer = AHCore()
        assert submit(writer, statement, lambda _: '?', journal=log).status == 'AMBIGUOUS'
        assert submit(writer, statement, lambda _: choice, journal=log).status == 'STORED'
        reader = AHCore()
        assert submit(reader, 'Пропало письмо, подписанное Анной?', journal=log).text == 'Да.'
        assert submit(reader, 'Пропало письмо, написанное Анной?', journal=log).text == ('Неизвестно.', 'Да.')[index]
        assert log.read_global_head() == 1


def test_nominalized_participle_and_its_dependents_in_a_coordinated_statement():
    from ah.model import Domain

    text = 'Станки отличаются от используемых в цехе и заменяют машины оборудованные рычагами.'
    core = AHCore()
    saved = submit(core, text, lambda probe: 'оборудованные' if 'оборудованные' in probe.options else '?')
    assert saved.status == 'STORED'
    group = core.store.get_element(Domain.H, saved.observation_ref)
    rows = [core.store.get_element(Domain.H, ref.uid).meta for ref in group.members]
    by_surface = {row['surface']: row for row in rows}
    assert rows[by_surface['заменяют']['controller']]['surface'] == 'Станки'
    assert rows[by_surface['оборудованные']['head']]['surface'] == 'машины'
    assert by_surface['используемых']['rule'] == 'PART.SUBSTANTIVE'
    for surface in ('используемых', 'цехе', 'оборудованные', 'рычагами'):
        assert by_surface[surface]['assertion_status'] == 'attributive'


def test_comma_between_modifier_and_noun_preserves_both_morphological_readings():
    text = 'Принятое, решение изменилось.'
    for choice, role, boundary in (('только признак', 'attribute', 'PUNCT.INTRAGROUP'),
                                  ('Принятое', 'participle', 'PART.PUNCT')):
        result = analyze(text, lambda _: choice)
        tree, = result.analyses
        assert (tree[0].role, tree[0].head, tree[1].rule) == (role, 2, boundary)


def test_substantive_subject_keeps_its_arguments_and_agreement():
    text = 'Прочитавшие книгу ушли.'
    tree, = analyze(text).analyses
    assert [(link.role, link.head) for link in tree] == [('subject', 2), ('object', 0), ('predicate', None)]
    assert tree[0].rule == 'PART.SUBSTANTIVE' and tree[0].morphology.voice == 'actv'
    tree, = analyze('Прочитавшие книгу студенты ушли.').analyses
    assert tree[0].role == 'participle' and tree[0].head == 2 and tree[2].role == 'subject'
    assert analyze('Вошедшая снял куртку.').status == 'UNRESOLVED'
    core = AHCore()
    assert submit(core, 'Вошедший читает книгу.').status == 'STORED'
    assert submit(core, 'Что читает вошедший?').text == 'книгу'
    assert submit(core, 'Вошедшая читает книгу?').status == 'UNKNOWN'


def test_verbal_noun_can_govern_an_instrumental_alongside_the_finite_verb():
    result = analyze('Шли командующие фронтами.')
    assert result.status == 'AMBIGUOUS'
    assert result.probes[-1].options == ('Шли', 'командующие')
    control = analyze('Шли люди фронтами.')
    assert all(link.rule != 'N.VERBAL.GOV' for tree in control.analyses for link in tree)
