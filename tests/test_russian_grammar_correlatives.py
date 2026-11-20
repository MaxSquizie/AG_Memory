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


def test_comma_inside_case_government_keeps_personal_reference():
    core = AHCore()
    request = submit(core, 'Помоги, тому, кто упал.', choose('Помоги, тому'))
    assert request.status == 'DIRECTIVE' and request.observation_ref is None
    record = submit(core, 'Иван помог, тому, кто упал.', choose('помог, тому'))
    _, rows = stored(core, record)
    marker = next(w for w in rows if w['surface'] == 'кто')
    anchor = rows[marker['antecedent']]
    assert anchor['surface'] == 'тому' and anchor['case'] == 'datv'
    assert rows[marker['head']]['assertion_status'] == 'restrictive'


@pytest.mark.parametrize('sentence,question,answer', [
    ('Та, кто ушла, вернулась.', 'Кто вернулся?', 'Та, кто ушла'),
    ('Та кто ушёл вернулась', 'Кто вернулся?', 'Та кто ушёл'),
    ('Иван встретил ту, кто упала.', 'Кого встретил Иван?', 'ту, кто упала'),
])
def test_feminine_correlate_preserves_local_agreement(sentence, question, answer):
    core = AHCore()
    record = submit(core, sentence)
    _, rows = stored(core, record)
    assert not record.analysis.probes
    marker = next(row for row in rows if row['surface'] == 'кто')
    assert marker['role'] == 'subject' and marker['case'] == 'nomn'
    assert rows[marker['antecedent']]['morphology']['gender'] == 'femn'
    assert rows[marker['head']]['assertion_status'] == 'restrictive'
    assert submit(core, question).text == answer


def test_correlative_nominal_fragment_and_false_comma():
    core = AHCore()
    for text in ('та кто ушла', 'та, кто ушла', 'та, кто, ушла'):
        result = submit(core, text, choose('кто, ушла'))
        assert result.status == 'PARSED_FRAGMENT' and result.observation_ref is None
        tree, = result.analysis.analyses
        marker = next(link for link in tree if link.rule == 'CL.NOMREF')
        assert tree[marker.antecedent].role == 'nominal_head'
        assert tree[marker.head].lemma == 'уйти'
    assert not core.store.links() and not any(list(core.store.elements(d)) for d in Domain)


def test_local_subject_controls_gender():
    core = AHCore()
    for text in ('Тот, кто ушла, вернулся.', 'Та, кто ушла, вернулся.', 'Та, кого встретила Иван, ушла.'):
        assert submit(core, text).status == 'UNRESOLVED'
    record = submit(core, 'Та, кого встретил Иван, ушла.')
    _, rows = stored(core, record)
    assert next(row for row in rows if row['surface'] == 'кого')['role'] == 'object'


def test_syncretic_feminine_correlate_asks_for_outer_case():
    core = AHCore()
    record = submit(core, 'Иван помог той, кто упала.', choose('той'))
    _, rows = stored(core, record)
    probe, = record.analysis.probes
    assert 'кому?' in probe.question and 'кем?' in probe.question
    assert next(row for row in rows if row['surface'] == 'той')['case'] == 'datv'
    assert submit(core, 'Кому помог Иван?').text == 'той, кто упала'
