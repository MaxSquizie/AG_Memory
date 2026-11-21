from ah.core import AHCore
from ah.russian_grammar.memory import submit


def test_content_and_juxtaposition_are_distinct_readings_before_selection():
    for text in ('Я понял одно: поезд ушёл.', 'Я понял одно поезд ушёл.', 'Я понял поезд ушёл.'):
        core = AHCore()
        record = submit(core, text)
        assert record.status == 'AMBIGUOUS' and record.observation_ref is None
        readings = record.analysis.analyses
        assert {tree[-1].rule for tree in readings} == {'CONTENT.EXPL', 'UTT.PARATAXIS'}
        content, = [tree for tree in readings if tree[-1].rule == 'CONTENT.EXPL']
        host = content[content[-1].head]
        assert host.rule == ('CONTENT.ANCHOR' if 'одно' in text else 'V1')
        assert host.quantity is None and content[-1].scope == 'embedded'
        assert not core.store.links()


def test_colon_between_events_does_not_license_an_object():
    record = submit(AHCore(), 'Стемнело: мы вернулись.')
    assert record.status == 'STORED'
    tree, = record.analysis.analyses
    assert tree[-1].rule == 'UTT.PARATAXIS'


def test_nominal_explanation_returns_both_clauses_from_memory():
    import json
    from pathlib import Path
    from ah.model import Domain

    path = Path(__file__).resolve().parents[1] / 'docs/evidence/russian_grammar_s64/readings.json'
    for case in json.loads(path.read_text(encoding='utf-8'))['cases']:
        cards = {p['prompt']: p['answer'] for p in case['probes']}
        core = AHCore()
        reply = submit(core, case['text'], lambda probe: cards.pop(probe.prompt()))
        assert not cards and reply.status == 'STORED'
        stored = core.store.get_element(Domain.H, reply.observation_ref)
        rows = [core.store.get_element(Domain.H, ref.uid).meta for ref in stored.members]
        child, = [row for row in rows if row['rule'] == 'CONTENT.NOMINAL']
        assert rows[child['head']]['role'] == 'subject'
        conjunct, = [r for r in rows if r['role'] == 'clause_conjunct']
        assert rows[conjunct['head']] == child
        assert child['assertion_status'] == conjunct['assertion_status'] == 'embedded'
        answer = submit(core, case['question'])
        assert (answer.text, answer.observation_ref) == (case['answer'], reply.observation_ref)
