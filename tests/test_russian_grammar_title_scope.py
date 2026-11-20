from ah.core import AHCore
from ah.model import Domain
from ah.russian_grammar.memory import submit


def test_count_and_capitals_only_propose_titles():
    core = AHCore()
    text = 'Имеется 2 магазина Восход Заря.'
    unresolved = submit(core, text, lambda p: '?')
    assert unresolved.status == 'AMBIGUOUS'
    assert unresolved.analysis.probes[-1].options == ('Восход Заря',)
    assert not core.store.elements(Domain.H)
    assert submit(core, text.replace('2', '3')).status == 'UNRESOLVED'
    assert not core.store.elements(Domain.H)
    reply = submit(core, text, lambda p: 'Восход Заря')
    group = core.store.get_element(Domain.H, reply.observation_ref)
    rows = [core.store.get_element(Domain.H, member.uid).meta for member in group.members]
    assert [(w['surface'], w['head'], w['assertion_status']) for w in rows[-2:]] == [
        ('Восход', 2, 'title'), ('Заря', 3, 'title')]


def test_translated_title_does_not_assert_personal_experience():
    core = AHCore()
    reply = submit(core, 'Маша решила написать книгу «Sky» («Я иду»).',
                   lambda p: 'Я иду', speaker_ref='user')
    group = core.store.get_element(Domain.H, reply.observation_ref)
    rows = [core.store.get_element(Domain.H, m.uid).meta for m in group.members]
    assert [(w['surface'], w['assertion_status'], w.get('participant_ref')) for w in rows
            if w['surface'] in ('Я', 'иду')] == [('Я', 'title', None), ('иду', 'title', None)]
