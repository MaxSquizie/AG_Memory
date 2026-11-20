from ah.core import AHCore
from ah.model import Domain
from ah.russian_grammar.memory import submit
from ah.russian_grammar.probe import Probe


def test_modal_groups_preserve_attachment_and_control_in_memory():
    core = AHCore()
    choices = iter(('должна', 'ехать'))
    questions = []

    def choose(probe):
        assert Probe.from_prompt(probe.prompt()) == probe
        questions.append(probe.question)
        return next(choices)

    reply = submit(core, 'Но в ту же ночь Анна должна как будто ехать к озеру, к лесу.', choose)
    assert reply.status == 'STORED'
    assert len(questions) == 2 and 'к озеру, к лесу' in questions[1]
    group = core.store.get_element(Domain.H, reply.observation_ref)
    rows = [core.store.get_element(Domain.H, member.uid).meta for member in group.members]
    motion = rows[9]
    assert motion['assertion_status'] == 'modal'
    assert rows[motion['controller']]['surface'] == 'Анна'
    assert rows[rows[10]['head']]['surface'] == 'ехать'
    assert rows[rows[14]['head']]['surface'] == 'озеру'
    assert rows[rows[8]['head']]['surface'] == 'как'


def test_reject_disagreement_between_modal_and_subject():
    core = AHCore()
    reply = submit(core, 'В ту же ночь Анна должны ехать к озеру.')
    assert reply.status == 'UNRESOLVED'
    assert not core.store.elements(Domain.H)


def test_unpunctuated_repeated_preposition_keeps_both_readings():
    sentence = 'Анна должна ехать к озеру к лесу'
    for answer in ('к лесу', 'нет такого продолжения', '?'):
        core = AHCore()
        questions = []

        def choose(probe):
            if probe.options == ('к лесу', 'нет такого продолжения'):
                questions.append(probe.question)
                return answer
            return 'ехать'

        reply = submit(core, sentence, choose)
        assert questions == ['Какие слова продолжают перечисление после «озеру»?']
        if answer == '?':
            assert reply.status == 'AMBIGUOUS' and not core.store.elements(Domain.H)
            continue
        assert reply.status == 'STORED'
        group = core.store.get_element(Domain.H, reply.observation_ref)
        rows = [core.store.get_element(Domain.H, member.uid).meta for member in group.members]
        assert rows[2]['assertion_status'] == 'modal'
        assert rows[3]['head'] == 2
        if answer == 'к лесу':
            assert rows[6]['role'] == 'nominal_conjunct' and rows[6]['head'] == 4
        else:
            assert rows[5]['head'] == 2 and rows[6]['head'] == 5
