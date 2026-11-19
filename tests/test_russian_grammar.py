"""Behavioral and import-boundary checks for the independent entry point."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from ah.russian_grammar import analyze
from ah.russian_grammar.parser import Prefix
from ah.russian_grammar.rules import readings


@pytest.mark.parametrize('text', [
    'Иван читает новую книгу', 'Новую книгу читает Иван', 'Иван читает книгу новую',
    'Иван читает новую книгу?', 'Книгу новую Иван читает.',
])
def test_source_order_preserves_links(text):
    r = analyze(text, lambda _: pytest.fail('no choice needed'))
    assert r.status == 'PARSED_FRAGMENT'
    links, = r.analyses
    graph = {l.lemma: (l.rule, links[l.head].lemma if l.head is not None else None) for l in links}
    assert graph == {'иван': ('S1', 'читать'), 'читать': ('V1', None),
                     'новый': ('A1', 'книга'), 'книга': ('O1', 'читать')}
    assert all(text[t.start:t.end] == t.surface for t in r.tokens)


def test_incremental_agreement_before_and_after_head():
    p = Prefix()
    stages = []
    for token in 'маму грустную и сестру'.split():
        p = p.extend(readings(token)[0])
        stages.append(p.pairs)
    assert stages == [(), ((1, 0),), ((1, 0),), ((1, 0), (1, 3))]


def test_ambiguous_attribute_and_exact_probe():
    text = 'Я встретил маму и сестру грустную'
    r = analyze(text)
    assert r.status == 'AMBIGUOUS' and len(r.analyses) == 2
    probe, = r.probes
    assert probe.prompt() == (
        text + '\nWhich occurrence does «грустную» @25 describe?\n'
        '1. «маму» @11\n2. «сестру» @18\n0. None of these\n?. Cannot tell'
    )
    for n, host in [('1', 'маму'), ('2', 'сестру')]:
        resolved = analyze(text, lambda p: n)
        links, = resolved.analyses
        assert resolved.tokens[links[-1].head].surface == host
        assert len(resolved.probes) == 1


def test_two_cases_two_subjects_and_repeated_surface():
    for text in ('Мать любит дочь', 'Мать любит мать'):
        r = analyze(text)
        probe, = r.probes
        assert probe.question == 'Which occurrence is the subject of «любит» @5?'
        assert probe.options == ('«Мать» @0', f'«{r.tokens[-1].surface}» @11')
        for n, roles in [('1', ['subject', 'predicate', 'object']),
                         ('2', ['object', 'predicate', 'subject'])]:
            assert [l.role for l in analyze(text, lambda p: n).analyses[0]] == roles


@pytest.mark.parametrize('answer,expected,remaining', [
    ('?', 'OPEN_CHOICE', 2), ('0', 'OPTIONS_REJECTED', 0),
    ('1,2', 'INVALID_ANSWER', 2), ('19', 'INVALID_ANSWER', 2),
])
def test_selector_never_guesses(answer, expected, remaining):
    r = analyze('Мать любит дочь', lambda p: answer)
    assert r.reason == expected and len(r.analyses) == remaining


def test_multiple_choices_shrink_the_forest_and_preserve_unanswered_choices():
    text = 'Я встретил маму и сестру грустную печальную'
    assert len(analyze(text).analyses) == 4
    answers = iter(['2', '?'])
    result = analyze(text, lambda p: next(answers))
    assert len(result.analyses) == 2 and all(a[-2].head == 4 for a in result.analyses)
    answers = iter(['2', '1'])
    links, = analyze(text, lambda p: next(answers)).analyses
    assert (links[-2].head, links[-1].head) == (4, 2)


def test_provider_outage_keeps_evidence_and_source():
    def unavailable(probe):
        raise TimeoutError()
    text = '  Мать  любит дочь?'
    result = analyze(text, unavailable)
    assert result.source == text and result.reason == 'SELECTOR_UNAVAILABLE'
    assert len(result.analyses) == 2


def test_duration_competes_with_transitive_object():
    r = analyze('Иван читал ночь')
    probe, = r.probes
    assert probe.options == ('What the action is directed at', 'How long the action lasts')
    assert analyze('Иван читал ночь', lambda p: '2').analyses[0][-1].rule == 'T1'
    assert analyze('Я шёл день').analyses[0][-1].role == 'duration'


@pytest.mark.parametrize('text', [
    'Мария пришёл', 'Иван видит новые котов', 'Они читает', 'Иван сплю', 'Иван пришли', 'Иван спал книгу', 'Иван читает новое книгу',
    'Иван читает 3 книги', 'Иван читает шмумпозявку', 'Иван читает книгу, а Анна спит',
    'Иван сказал что Мария ушла', 'Слегка дремав, Иван, очень высокий, чуть было не упал',
    'Иван читал и', '', ' ', '!'])
def test_outside_fragment_never_returns_a_partial_tree(text):
    r = analyze(text, lambda p: pytest.fail(p.prompt()))
    assert r.status == 'UNRESOLVED' and not r.analyses


def test_budget_never_truncates_competing_structures():
    assert analyze('Мать любит дочь', budget=1).reason == 'PREFIX_BUDGET'
    r = analyze('Я встретил маму и сестру грустную', budget=1)
    assert r.reason == 'ANALYSIS_BUDGET' and not r.analyses


def test_new_entry_point_runs_when_every_other_ah_package_is_blocked():
    env = {**os.environ, 'PYTHONPATH': str(Path(__file__).resolve().parents[1] / 'src')}
    program = """
import importlib.abc, sys, runpy
class Isolate(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path, target=None):
        if name.startswith('ah.') and name.split('.')[1] != 'russian_grammar':
            raise AssertionError('Forbidden dependency: ' + name)
sys.meta_path.insert(0, Isolate())
from ah.russian_grammar import analyze
assert analyze('Мать любит дочь', lambda p: '0').status == 'UNRESOLVED'
assert analyze('Я читаю опфкцзык').status == 'UNRESOLVED'
sys.argv = ['grammar', 'Иван читает книгу']
runpy.run_module('ah.russian_grammar', run_name='__main__')
"""
    child = subprocess.run([sys.executable, '-c', program], env=env, check=True, capture_output=True, text=True)
    assert json.loads(child.stdout)['status'] == 'PARSED_FRAGMENT'
