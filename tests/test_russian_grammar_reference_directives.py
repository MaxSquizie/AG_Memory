from ah.core import AHCore
from ah.model import Domain
from ah.russian_grammar.memory import submit


def test_reference_abbreviation_needs_confirmation_and_does_not_assert_its_content():
    for text in ('См. таблицу.', 'См таблицу', 'Ср. с рисунком «Дом художника», где дети видят окно.'):
        for response, expected in [('?', 'AMBIGUOUS'), ('0', 'UNRESOLVED'), ('select', 'DIRECTIVE')]:
            core = AHCore()
            reply = submit(core, text, lambda probe: probe.options[0] if response == 'select' else response)
            assert reply.status == expected
            assert not any(core.store.elements(domain) for domain in Domain)
            if response == 'select':
                tree, = reply.analysis.analyses
                assert tree[0].morphology.mood == 'impr'
                assert tree[0].morphology.number is None
                assert any('сокращение' in probe.question for probe in reply.analysis.probes)
