from ah.core import AHCore
from ah.model import Domain
from ah.russian_grammar.memory import submit


def stored(source):
    core = AHCore()
    result = submit(core, source)
    assert result.status == 'STORED', (result.analysis.reason, result.analysis.probes)
    observation = core.store.get_element(Domain.H, result.observation_ref)
    return core, [core.store.get_element(Domain.H, member.uid).meta for member in observation.members]


def test_dative_controls_an_impersonal_infinitive_in_either_order():
    for source in ('Мне пришлось уйти', 'Уйти пришлось врачу', 'Мне приходится уйти', 'Нам удалось вернуться'):
        core, rows = stored(source)
        experiencer = next(row for row in rows if row['role'] == 'experiencer')
        complement = next(row for row in rows if row['role'] == 'infinitive')
        assert rows[complement['controller']] == experiencer
        assert experiencer['head'] == complement['head']
        assert all(row['role'] != 'subject' for row in rows)
        assert submit(core, source + '?').text == 'Да.'
    _, rows = stored('Анна приходится мне сестрой')
    assert rows[0]['role'] == 'subject' and rows[1]['rule'] == 'V1'


def test_negative_pronominal_preposition_preserves_actor_and_scoped_predicate():
    for source in ('Ему не с кем поговорить', 'Ему не с кем было поговорить', 'Мне не о чем спорить'):
        core, rows = stored(source)
        predicate = next(row for row in rows if row['role'] == 'predicate')
        pronoun = next(row for row in rows if row['rule'] == 'NEG.PRON.ARG')
        assert rows[pronoun['head']]['head'] == rows.index(predicate)
        assert rows[predicate['controller']] == rows[0]
        assert predicate['assertion_status'] == 'unavailable'
        assert rows[rows[1]['head']] == pronoun
        if rows[0]['surface'] == 'Ему':
            assert rows[0]['lemma_alternatives'] == ['он', 'оно']
            assert rows[0]['morphology']['gender'] is None
        assert submit(core, source + '?').text == 'Да.'
        assert submit(core, 'Он поговорил?').status == 'UNKNOWN'

    core, _ = stored('Марии не с кем поговорить о работе.')
    assert submit(core, 'Кому не с кем поговорить о работе?').text == 'Марии'
    assert submit(core, 'Кому не с кем поговорить?').status == 'UNKNOWN'


def test_dative_ambiguity_and_punctuation_keep_memory_empty_until_selected():
    for source in ('Ему пришлось помочь.', 'Нам пришлось, уйти.', 'Ему не, с кем поговорить.'):
        core = AHCore()
        result = submit(core, source)
        assert result.status == 'AMBIGUOUS'
        assert not list(core.store.elements(Domain.H))
    for source in ('Мне приходятся уйти.', 'Он не с кем поговорить.'):
        core = AHCore()
        assert submit(core, source).status == 'UNRESOLVED'
        assert not list(core.store.elements(Domain.H))
