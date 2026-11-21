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


def test_nominal_parenthetical_keeps_literal_reading_open():
    for text in ('Как правило действует?', 'К примеру подошёл студент.'):
        reply = submit(AHCore(), text)
        assert reply.observation_ref is None
        roles = {tree[1].role for tree in reply.analysis.analyses}
        assert 'parenthetical' in roles
        assert roles & {'subject', 'governed'}


def test_pronominal_adjective_agrees_with_the_object_of_a_converb():
    reply = submit(AHCore(), 'Не участвует, координируя остальных ведьм.')
    assert reply.status == 'STORED'
    tree, = reply.analysis.analyses
    modifier = next(link for link in tree if link.lemma == 'остальной')
    assert modifier.role == 'attribute' and tree[modifier.head].role == 'object'
    converb = tree[tree[modifier.head].head]
    assert converb.role == 'converb' and converb.implicit_subject == 'unresolved'
    assert submit(AHCore(), 'Не участвует, координируя другую ведьм.').observation_ref is None


def test_unpunctuated_preposed_purpose_keeps_the_controller_in_the_matrix():
    reply = submit(AHCore(), 'Чтобы согреться Анна вернулась.')
    assert any(tree[1].role == 'clause_adverbial' and tree[1].scope == 'purpose'
               and (tree[1].head, tree[1].controller) == (3, 2) for tree in reply.analysis.analyses)
    assert submit(AHCore(), 'Чтобы согреться Анна.').observation_ref is None


def test_nominal_predicate_can_share_a_subject_with_a_following_finite_clause():
    from ah.russian_grammar.parser import analyze

    result = analyze('Исток — река в России, протекает в горах.')
    actor, verb = (next(i for i, token in enumerate(result.tokens) if token.surface == form)
                   for form in ('Исток', 'протекает'))
    assert any(tree[verb].controller == actor and tree[actor].role == 'subject' for tree in result.analyses)
    assert any(tree[verb].implicit_subject == 'unresolved' for tree in result.analyses)
