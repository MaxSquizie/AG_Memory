from ah.core import AHCore
from ah.model import Domain
from ah.russian_grammar.memory import submit


def test_common_noun_with_initial_capital_can_remain_common_or_name_an_unspecified_entity():
    for choice, scope, animacy in [('нарицательное существительное', None, 'inan'),
                                  ('Шар', 'proper_name', None)]:
        core = AHCore()
        result = submit(core, 'Вчера Шар упал.', lambda p: choice if choice in p.options else '?')
        assert result.status == 'STORED'
        group = core.store.get_element(Domain.H, result.observation_ref)
        word = core.store.get_element(Domain.H, group.members[1].uid).meta
        assert word['scope'] == scope and word['morphology']['animacy'] == animacy


def test_named_span_preserves_surface_and_does_not_identify_the_kind_of_entity():
    core = AHCore()
    result = submit(core, 'Иван жил в Новой Александрии.',
                    lambda p: 'Новой Александрии' if 'Новой Александрии' in p.options else '?')
    assert result.status == 'STORED'
    group = core.store.get_element(Domain.H, result.observation_ref)
    rows = [core.store.get_element(Domain.H, member.uid).meta for member in group.members]
    assert rows[3]['head'] == 4 and rows[4]['scope'] == 'proper_name'
    assert rows[4]['morphology']['animacy'] is None
