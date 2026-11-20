from ah.core import AHCore
from ah.model import Domain
from ah.russian_grammar.memory import submit


def test_expanded_nominal_mentions_do_not_supply_a_holder():
    core = AHCore()
    reply = submit(core, 'Тихая ночь.')
    assert reply.status == 'STORED'
    observation = core.store.get_element(Domain.H, reply.observation_ref)
    assert observation.meta['root_status'] == 'nominal'
    adjective, noun = [core.store.get_element(Domain.H, ref.uid).meta for ref in observation.members]
    assert adjective['head'] == 1 and noun['head'] is None
    assert not noun.get('implicit_subject') and not noun.get('participant_ref')


def test_pronoun_apposition_needs_confirmation_without_commas():
    text = 'Она наша учительница пришла'
    core = AHCore()
    pending = submit(core, text)
    assert pending.status == 'AMBIGUOUS'
    assert not core.store.elements(Domain.H)
    reply = submit(core, text, lambda probe: 'учительница')
    assert reply.status == 'STORED'
    tree, = reply.analysis.analyses
    assert tree[1].role == 'possessive' and tree[1].head == 2
    assert tree[2].role == 'apposition' and tree[2].head == 0
    assert [link.role for link in tree].count('subject') == 1
