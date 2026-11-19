from dataclasses import replace

from ah.core import AHCore
from ah.core.journal import JournalChannel
from ah.russian_grammar import analyze
from ah.russian_grammar import memory
from ah.russian_grammar.prepositions import GOVERNMENT


def test_required_slot_before_journal_and_optional_object(tmp_path):
    journal = JournalChannel(tmp_path / 'memory.log')
    core = AHCore()
    missing = memory.submit(core, 'Иван положил.', journal=journal)
    assert (missing.status, missing.analysis.reason, journal.read_global_head()) == (
        'UNRESOLVED', 'MISSING_REQUIRED_ARGUMENT', 0)
    for sentence in ('Иван положил книгу.', 'Иван читает.', 'Иван выше.'):
        assert memory.submit(core, sentence, journal=journal).status == 'STORED'
    assert journal.read_global_head() == 3


def test_corrupt_comparative_cannot_be_written(monkeypatch, tmp_path):
    journal = JournalChannel(tmp_path / 'memory.log')
    result = analyze('Иван выше Петра.')
    subject, adjective, standard = result.analyses[0]
    invalid = (replace(subject, head=2), replace(adjective, role='adverb', rule='V2.MOD', head=2),
               replace(standard, role='predicate', rule='V2', head=None))
    monkeypatch.setattr(memory, 'analyze', lambda *args, **kwargs: replace(result, analyses=(invalid,)))
    reply = memory.submit(AHCore(), result.source, journal=journal)
    assert reply.analysis.reason == 'INVALID_NOMINAL_PREDICATE'
    assert journal.read_global_head() == 0


def test_missing_government_cannot_be_supplied_by_a_selector(monkeypatch):
    monkeypatch.setitem(GOVERNMENT, 'на', frozenset())
    choices = []
    result = analyze('На столе лежит арбуз', lambda probe: choices.append(probe) or probe.options[0])
    assert result.reason == 'UNKNOWN_GOVERNMENT' and not choices


def test_probe_trace_distinguishes_selection_from_abstention():
    text = 'Иван сказал, что Мария ушла, а Пётр остался.'
    for answer, expected, outcome in [('?', 2, 'open'), ('ушла', 1, 'selected'), ('0', 0, 'rejected')]:
        result = analyze(text, lambda _: answer)
        step, = result.steps
        assert (step.before, step.after, step.outcome) == (2, expected, outcome)


def test_reflexive_argument_in_a_report_has_a_local_subject():
    result = memory.submit(AHCore(), 'Мария сказала, что Иван увидел себя.')
    assert result.status == 'STORED'
    tree, = result.analysis.analyses
    assert result.analysis.tokens[tree[-1].antecedent].surface == 'Иван'
