from ah.core import AHCore
from ah.model import Domain
from ah.russian_grammar.memory import submit


def test_opaque_numeric_predicate_keeps_leading_zeroes():
    core = AHCore()
    reply = submit(core, 'Номер группы -- 0007.')
    assert reply.status == 'STORED'
    assert submit(core, 'Номер группы — 0007?').status == 'ANSWER'
    assert submit(core, 'Номер группы — 7?').status == 'UNKNOWN'


def test_nominal_heading_checks_agreement_without_asserting_an_event():
    core = AHCore()
    assert submit(core, '8 — Обслуживание дальними станциями.').status == 'UNRESOLVED'
    assert not core.store.elements(Domain.H)
    reply = submit(core, '8 — Обслуживание дальних станций.')
    group = core.store.get_element(Domain.H, reply.observation_ref)
    assert group.meta['root_status'] == 'heading'
    rows = [core.store.get_element(Domain.H, ref.uid).meta for ref in group.members]
    assert [(r['surface'], r['role']) for r in rows if r['head'] == 2] == [('8', 'label'), ('станций', 'genitive_modifier')]
