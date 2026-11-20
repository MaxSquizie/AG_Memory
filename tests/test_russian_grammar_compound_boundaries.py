from ah.core import AHCore
from ah.model import Domain
from ah.russian_grammar.memory import submit


def test_unmarked_predicates_keep_their_subjects_and_fixed_causal_marker():
    text = 'Анна прочла письмо Вера открыла дверь так как Иван ушёл'
    core = AHCore()
    def choose(probe):
        if 'так как' in probe.options:
            return 'так как'
        return '?'
    result = submit(core, text, choose)
    assert result.status == 'STORED'
    group = core.store.get_element(Domain.H, result.observation_ref)
    rows = {row['surface']: row for ref in group.members for row in [core.store.get_element(Domain.H, ref.uid).meta]}
    labels = text.split()
    assert [(w, labels[rows[w]['head']]) for w in ('Анна', 'Вера', 'Иван')] == [
        ('Анна', 'прочла'), ('Вера', 'открыла'), ('Иван', 'ушёл')]
    assert rows['ушёл']['role'] == 'clause_adverbial' and rows['ушёл']['scope'] == 'cause'
    assert labels[rows['ушёл']['head']] == 'открыла'
    assert rows['как']['role'] == 'fixed' and labels[rows['как']['head']] == 'так'
