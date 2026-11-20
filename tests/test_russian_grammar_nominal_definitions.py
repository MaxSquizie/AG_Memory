from ah.core import AHCore
from ah.model import Domain
from ah.russian_grammar.memory import submit


def test_numeric_comparison_and_negative_participle_keep_their_own_hosts():
    core = AHCore()
    text = 'Свобо́дные величи́ны — числа, меньшие пяти, не являющиеся постоянными.'
    reply = submit(core, text, lambda probe: 'числа')
    assert reply.status == 'STORED'
    observation = core.store.get_element(Domain.H, reply.observation_ref)
    words = [core.store.get_element(Domain.H, ref.uid).meta for ref in observation.members]
    assert all(text[w['start']:w['end']] == w['surface'] for w in words)
    assert [w['lemma'] for w in words[:2]] == ['свободный', 'величина']
    root = next(i for i, word in enumerate(words) if word['role'] == 'predicate')
    by_surface = {w['surface']: i for i, w in enumerate(words)}
    limit = words[by_surface['пяти']]
    assert limit['role'] == 'comparison_standard' and limit['head'] == by_surface['меньшие']
    assert limit['quantity'] == '5' and words[by_surface['меньшие']]['head'] == root
    participle = words[by_surface['являющиеся']]
    assert participle['scope'] == 'negated' and participle['controller'] == root
    assert words[by_surface['постоянными']]['head'] == by_surface['являющиеся']
    assert words[root]['assertion_status'] == 'asserted'


def test_plain_qualitative_adjective_does_not_license_a_numeric_bound():
    core = AHCore()
    assert submit(core, 'Число — величина, красная 5.').status == 'UNRESOLVED'
    assert not core.store.elements(Domain.H)


def test_only_acute_after_a_russian_vowel_is_read_as_stress():
    from ah.russian_grammar.prepositions import TOKEN
    from ah.russian_grammar.rules import unaccented

    for accent in ('\u0301', '\u0341'):
        word = 'чи' + accent + 'сло'
        assert TOKEN.findall(word) == [word] and unaccented(word) == 'число'
    for word in ('чис\u0301ло', 'чи\u0300сло', 'cafe\u0301'):
        assert unaccented(word) == word and TOKEN.findall(word) != [word]
