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


def test_date_heading_and_named_list_remain_nonassertive_until_confirmed():
    core = AHCore()
    heading = submit(core, '2019 год, выставка картин.')
    assert heading.status == 'AMBIGUOUS' and heading.analysis.probes[-1].options == ('2019 год',)
    tree, = heading.analysis.analyses
    assert tree[1].scope == 'heading' and tree[3].role == 'list_item'
    listing = submit(core, 'Северный Бор, Зелёный Луг и Озёра.')
    assert listing.status == 'AMBIGUOUS' and not core.store.elements(Domain.H)
    tree, = listing.analysis.analyses
    assert tree[0].scope == 'heading' and '«Северный Бор», «Зелёный Луг», «Озёра»' in listing.analysis.probes[-1].question
    assert [w.role for w in tree].count('nominal_conjunct') == 2


def test_title_probe_offers_competing_heads_inside_the_same_name():
    core = AHCore()
    reply = submit(core, '2018 год, премия «Молодая пресса».')
    probe, = reply.analysis.probes
    assert probe.options == ('Молодая', 'пресса') and '«Молодая пресса»' in probe.question
    assert reply.status == 'AMBIGUOUS' and not core.store.elements(Domain.H)


def test_comma_can_split_an_unfamiliar_name_in_a_list_of_multiword_names():
    core = AHCore()
    reply = submit(core, 'Кочик, Башуй, Шеих Эли, Сарт и Акшек.')
    tree_roles = {tree[2].role for tree in reply.analysis.analyses}
    assert tree_roles == {'nominal_conjunct', 'name_part'}
    assert reply.analysis.probes[-1].options == ('одно название «Кочик Башуй»', 'два названия «Кочик» и «Башуй»')
    assert reply.status == 'AMBIGUOUS' and not core.store.elements(Domain.H)
