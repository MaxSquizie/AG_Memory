import pytest

from ah.core import AHCore
from ah.model import Domain
from ah.russian_grammar import analyze
from ah.russian_grammar.memory import submit


TARGET = 'Детерминированное решение принимается там, где доступные правила и основания определяют результат в заданной области.'


def choose(*labels):
    def select(probe):
        for label in labels:
            if label in probe.options:
                return label
        raise AssertionError(probe.prompt())
    return select


def stored(core, record):
    assert record.status == 'STORED'
    group = core.store.get_element(Domain.H, record.observation_ref)
    rows = [core.store.get_element(Domain.H, member.uid).meta for member in group.members]
    return group, rows


@pytest.mark.parametrize('sentence', [
    TARGET, TARGET.replace(',', '').rstrip('.'), TARGET.replace('ное решение', 'ное, решение'),
])
def test_spatial_restriction_survives_write_and_read(sentence):
    core = AHCore()
    reader = choose('определяют', 'только признак')
    record = submit(core, sentence, reader)
    group, rows = stored(core, record)
    anchor = next(i for i, w in enumerate(rows) if w['surface'] == 'там')
    marker = next(i for i, w in enumerate(rows) if w['surface'] == 'где')
    assert rows[marker]['antecedent'] == anchor
    assert rows[rows[marker]['head']]['surface'] == 'определяют'
    assert rows[rows[anchor]['head']]['assertion_status'] == 'asserted'
    edges = [(e.source, e.target) for e in core.store.links() if e.relation_id == 'grammar.antecedent']
    assert (group.members[marker], group.members[anchor]) in edges
    reply = submit(core, 'Где принимается детерминированное решение?', reader)
    assert reply.observation_ref == record.observation_ref
    assert reply.text == sentence[sentence.index('там'):].rstrip('.')


@pytest.mark.parametrize('choice', ['дом', 'озера', '0', '?'])
def test_competing_relative_anchors(choice):
    core = AHCore()
    text = 'Я покажу дом у озера, где мы жили.'

    def select(probe):
        if {'дом', 'озера'} <= set(probe.options):
            return choice
        if 'покадить' in probe.question:
            return 'no such word'
        return choose('дом')(probe)

    record = submit(core, text, select)
    assert any({'дом', 'озера'} <= set(p.options) for p in record.analysis.probes)
    if choice in ('0', '?'):
        assert record.status == {'0': 'UNRESOLVED', '?': 'AMBIGUOUS'}[choice]
        assert not any(list(core.store.elements(d)) for d in Domain) and not core.store.links()
    else:
        _, rows = stored(core, record)
        marker = next(w for w in rows if w['surface'] == 'где')
        assert rows[marker['antecedent']]['surface'] == choice


@pytest.mark.parametrize('sentence', [
    'Я знаю, где ключ.', 'Я знаю где ключ',
    'Он там спросил, где выход.', 'Он там спросил где выход',
])
def test_indirect_spatial_word_has_no_referent(sentence):
    core = AHCore()
    record = submit(core, sentence, choose('знаю', 'спросил'))
    _, rows = stored(core, record)
    marker = next(w for w in rows if w['surface'] == 'где')
    assert marker.get('antecedent') is None
    assert rows[marker['head']]['role'] == 'clause_complement'
    assert submit(core, 'Где ключ?' if 'ключ' in sentence else 'Где выход?').status == 'UNKNOWN'


@pytest.mark.parametrize(('choice', 'clause', 'role'), [
    ('того', 'clause_relative', 'object'),
    ('спросил', 'clause_complement', 'recipient'),
])
def test_person_or_question_content(choice, clause, role):
    core = AHCore()
    record = submit(core, 'Я спросил того, кто пришёл.', choose(choice))
    _, rows = stored(core, record)
    person = next(i for i, w in enumerate(rows) if w['surface'] == 'того')
    marker = next(w for w in rows if w['surface'] == 'кто')
    assert rows[person]['role'] == role
    assert rows[marker['head']]['role'] == clause
    assert marker.get('antecedent') == (person if choice == 'того' else None)


@pytest.mark.parametrize(('text', 'head'), [
    ('Где тонко, там и рвётся.', 'тонко'),
    ('Где горит свет, Иван остановился там.', 'горит'),
    ('Где горит свет Иван остановился там', 'горит'),
    ('Где горит свет, Иван, остановился там.', 'горит'),
])
def test_reverse_spatial_reference(text, head):
    core = AHCore()
    record = submit(core, text, choose('Иван, остановился'))
    _, rows = stored(core, record)
    reference = rows[0]
    assert rows[reference['antecedent']]['surface'] == 'там'
    assert rows[reference['head']]['surface'] == head


def test_outer_direction_controls_which_question_is_answered():
    core = AHCore()
    text = 'Иван пришёл оттуда, куда шла Анна.'
    observation = submit(core, text)
    _, rows = stored(core, observation)
    marker = next(w for w in rows if w['surface'] == 'куда')
    assert rows[marker['antecedent']]['surface'] == 'оттуда'
    assert submit(core, 'Откуда пришёл Иван?').text == 'оттуда, куда шла Анна'
    assert submit(core, 'Куда пришёл Иван?').status == 'UNKNOWN'


def test_embedded_spatial_references():
    core = AHCore()
    record = submit(core, 'Иван жил там, где стоял дом, где Анна работала.', choose('дом'))
    _, rows = stored(core, record)
    observed = [(rows[w['head']]['surface'], rows[w['antecedent']]['surface'])
                for w in rows if w['surface'] == 'где']
    assert observed == [('стоял', 'там'), ('работала', 'дом')]
    assert submit(core, 'Где стоял дом?').status == 'UNKNOWN'
    assert submit(core, 'Иван жил?').status == 'UNKNOWN'


def test_prefix_opens_and_extends_in_reading_order():
    prefix = 'Иван жил там'
    core = AHCore()
    _, rows = stored(core, submit(core, prefix))
    assert rows[-1]['role'] == 'adverb' and all(r.get('antecedent') is None for r in rows)
    assert submit(core, 'Где жил Иван?').text == 'там'

    for text, kinds in ((prefix + ', где стоял дом.', ('anchor', 'relative')),
                        ('Где тонко, там и рвётся.', ('relative', 'anchor'))):
        steps = []
        analyze(text, on_spatial_step=steps.append)
        first, second = steps
        assert (first.kind, second.kind) == kinds
        assert first.earlier_candidates == () and second.earlier_candidates == (first.start,)
        assert first.start < second.start
