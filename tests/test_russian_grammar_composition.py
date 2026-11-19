from ah.russian_grammar import Probe, analyze


def parsed(source, choose=None):
    result = analyze(source, choose)
    assert result.status == 'PARSED_FRAGMENT', (result.reason, result.probes)
    tree, = result.analyses
    return {token.surface: link for token, link in zip(result.tokens, tree)}, [
        token.surface for token in result.tokens
    ]


def test_nominal_predicate_attribute_and_impersonal_infinitive():
    for source, predicate in [('Иван высокий', 'высокий'), ('Иван был высоким', 'высоким')]:
        links, words = parsed(source)
        assert links[predicate].head is None
        assert words[links['Иван'].head] == predicate
        if 'был' in links:
            assert links['был'].role == 'copula' and words[links['был'].head] == predicate

    links, words = parsed('Высокий Иван ушёл')
    assert links['Высокий'].role == 'attribute' and words[links['Высокий'].head] == 'Иван'
    links, words = parsed('Можно прочитать книгу')
    assert all(link.role != 'subject' for link in links.values())
    assert words[links['прочитать'].head] == 'Можно' and words[links['книгу'].head] == 'прочитать'


def test_controller_choice_is_readable_and_selects_the_occurrence():
    source = 'Иван предложил Марии уехать'
    result = analyze(source)
    probe, = result.probes
    assert probe.prompt() == (
        'Иван предложил Марии уехать\n\nWho is to perform the action «уехать»?\nAnswer options:\n'
        '- Иван\n- Марии\n- 0 — None of the proposed answers fits.\n'
        '- ? — The sentence leaves the choice unclear.'
    )
    assert Probe.from_prompt(probe.prompt()) == probe
    assert result.reason == 'OPEN_CHOICE' and len(result.analyses) == 2
    for answer in ('Иван', 'Марии'):
        links, words = parsed(source, lambda _: {'answers': {'grammar': {'type': 'choice', 'choice': answer}}})
        assert words[links['уехать'].controller] == answer


def test_recipient_controls_both_nested_infinitives():
    links, words = parsed('Иван попросил Марию начать читать книгу')
    assert links['Иван'].role == 'subject' and words[links['Иван'].head] == 'попросил'
    assert links['начать'].scope == 'embedded' and words[links['начать'].head] == 'попросил'
    assert links['читать'].scope == 'phase' and words[links['читать'].head] == 'начать'
    assert words[links['начать'].controller] == words[links['читать'].controller] == 'Марию'
    assert words[links['книгу'].head] == 'читать'


def test_averted_scope_is_local_to_the_matrix_predicate():
    links, words = parsed('Слегка дремав, Иван, очень высокий, чуть было не упал со стула')
    assert links['упал'].scope == 'averted'
    assert all(words[links[word].head] == 'упал' for word in ('чуть', 'было', 'не'))
    assert words[links['дремав'].controller] == 'Иван' and links['дремав'].scope is None
    assert words[links['Слегка'].head] == 'дремав'
    assert words[links['очень'].head] == 'высокий' and words[links['высокий'].head] == 'Иван'
    assert parsed('Иван не упал')[0]['упал'].scope == 'negated'


def test_coordination_preserves_matrix_and_embedded_subjects():
    source = 'Иван сказал, что Мария ушла, а Пётр остался'
    result = analyze(source)
    probe, = result.probes
    assert probe.options == ('сказал', 'ушла')
    for answer in probe.options:
        links, words = parsed(source, lambda _: answer)
        assert words[links['остался'].head] == answer
        assert [words[links[name].head] for name in ('Иван', 'Мария', 'Пётр')] == [
            'сказал', 'ушла', 'остался'
        ]
