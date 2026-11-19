"""Behavioral and import-boundary checks for the independent entry point."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from ah.russian_grammar import Probe, analyze
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
        text + '\n\nWhich word does «грустную» describe?\nAnswer options:\n'
        '- маму\n- сестру\n- 0 — None of the proposed answers fits.\n'
        '- ? — The sentence leaves the choice unclear.'
    )
    request = Probe.from_prompt(probe.prompt()).jev_request()
    assert request == probe.jev_request() == {
        'model': 'jev-latest', 'state': text, 'questions': {
            'grammar': {'type': 'choice', 'instructions': 'Which word does «грустную» describe?',
                        'criteria': {'маму': None, 'сестру': None,
                                     '0': 'None of the proposed answers fits.',
                                     '?': 'The sentence leaves the choice unclear.'}}}}
    for host in ['маму', 'сестру']:
        resolved = analyze(text, lambda p: host)
        links, = resolved.analyses
        assert resolved.tokens[links[-1].head].surface == host
        assert len(resolved.probes) == 1


@pytest.mark.parametrize('text,answers', [
    ('Мать любит дочь', ('Мать', 'дочь')),
    ('Мать любит мать', ('[Мать] любит', 'любит [мать]')),
])
def test_two_cases_two_subjects_and_repeated_surface(text, answers):
    probe, = analyze(text).probes
    assert probe.context == text and probe.question == 'Which word is the subject of «любит»?'
    assert probe.options == answers
    for answer, subject in zip(answers, (0, 2)):
        links, = analyze(text, lambda p: answer).analyses
        assert links[subject].role == 'subject' and links[2 - subject].role == 'object'


def test_repeated_word_alone_cannot_choose_an_occurrence():
    result = analyze('Мать любит мать', lambda p: 'мать')
    assert result.reason == 'INVALID_ANSWER' and len(result.analyses) == 2
    links, = analyze('Мать любит дочь', lambda p: '  ДОЧЬ\n').analyses
    assert links[-1].role == 'subject'


def test_lexical_choice_returns_the_original_word_and_preserves_other_readings():
    text = 'Мария спала ночь'
    probe, = analyze(text).probes
    assert probe.options == ('спала', 'no such word') and '«спасть»' in probe.question
    links, = analyze(text, lambda p: 'спала').analyses
    assert links[1].lemma == 'спасть'
    links, = analyze(text, lambda p: 'no such word').analyses
    assert links[1].lemma == 'спать'


@pytest.mark.parametrize('answer,expected,remaining', [
    ('?', 'OPEN_CHOICE', 2), ('0', 'OPTIONS_REJECTED', 0),
    ('1,2', 'INVALID_ANSWER', 2), ('1', 'INVALID_ANSWER', 2), ('2', 'INVALID_ANSWER', 2),
    ('дочери', 'INVALID_ANSWER', 2), ('Мать и дочь', 'INVALID_ANSWER', 2),
])
def test_selector_never_guesses(answer, expected, remaining):
    r = analyze('Мать любит дочь', lambda p: answer)
    assert r.reason == expected and len(r.analyses) == remaining


def test_multiple_choices_shrink_the_forest_and_preserve_unanswered_choices():
    text = 'Я встретил маму и сестру грустную печальную'
    assert len(analyze(text).analyses) == 4
    answers = iter(['сестру', '?'])
    result = analyze(text, lambda p: next(answers))
    assert len(result.analyses) == 2 and all(a[-2].head == 4 for a in result.analyses)
    answers = iter(['сестру', 'маму'])
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
    assert probe.options == ('ночь', 'no such word')
    assert analyze('Иван читал ночь', lambda p: 'no such word').analyses[0][-1].rule == 'O1'
    assert analyze('Иван читал ночь', lambda p: 'ночь').analyses[0][-1].rule == 'T1'
    assert analyze('Я шёл день').analyses[0][-1].role == 'duration'


@pytest.mark.parametrize('text', [
    'Мария пришёл', 'Иван видит новые котов', 'Они читает', 'Иван сплю', 'Иван пришли', 'Иван спал книгу', 'Иван читает новое книгу',
    'Иван читает 3 книгу', 'Иван читает шмумпозявку', 'Иван читает книгу, а Анна спят',
    'Иван сказал что Мария ушёл', 'Слегка дремав, Иван, очень высокая, чуть было не упал',
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
sys.argv = ['grammar', '--report', 'Иван читает книгу']
runpy.run_module('ah.russian_grammar', run_name='__main__')
"""
    child = subprocess.run([sys.executable, '-c', program], env=env, check=True, capture_output=True, text=True)
    assert json.loads(child.stdout)['status'] == 'PARSED_FRAGMENT'

@pytest.mark.parametrize('choice,expected', [('дочь', 'SIMPLE_CLAUSE'), ('?', 'OPEN_CHOICE'),
                                             ('0', 'OPTIONS_REJECTED'), ('2', 'INVALID_ANSWER')])
def test_native_choice_response_in_analyzer(choice, expected):
    result = analyze('Мать любит дочь', lambda probe: {
        'model': 'jev-1.13.0', 'answers': {'grammar': {'type': 'choice', 'choice': choice}},
    })
    assert result.reason == expected
    if choice == 'дочь':
        assert result.analyses[0][2].role == 'subject'


@pytest.mark.parametrize('response', [
    {'answers': []}, {'answers': {'wrong_id': {'type': 'choice', 'choice': 'дочь'}}},
    {'answers': {'grammar': {'type': 'score', 'choice': 'дочь'}}},
    {'answers': {'grammar': {'probabilities': {'дочь': 1.0}}}},
    {'answers': {'grammar': {'type': 'choice', 'choice': []}}},
])
def test_malformed_jev_response_preserves_the_forest(response):
    result = analyze('Мать любит дочь', lambda probe: response)
    assert result.reason == 'INVALID_ANSWER' and len(result.analyses) == 2


@pytest.mark.parametrize('text,choices', [
    ('  Мать\nлюбит мать?', ('[Мать] любит', 'любит [мать]')),
    ('Иван читал ночь', ('ночь', 'no such word')),
])
def test_cli_emits_parseable_text_and_exports_only_on_request(text, choices, monkeypatch, capsys):
    from ah.russian_grammar.__main__ import main
    monkeypatch.setattr(sys, 'argv', ['grammar', text])
    main()
    readable = capsys.readouterr().out
    parsed = Probe.from_prompt(readable)
    assert parsed.context == text and parsed.options == choices
    request = parsed.jev_request('jev-1.13.0')
    monkeypatch.setattr(sys, 'argv', ['grammar', '--report', text])
    main()
    assert json.loads(capsys.readouterr().out)['probes'] == [parsed.prompt()]
    monkeypatch.setattr(sys, 'argv', ['grammar', '--jev', '--model', 'jev-1.13.0', text])
    main()
    assert json.loads(capsys.readouterr().out) == request
    assert request['state'] == text and request['model'] == 'jev-1.13.0'
    assert tuple(request['questions']['grammar']['criteria']) == (*choices, '0', '?')
    monkeypatch.setattr(sys, 'argv', ['grammar', '--jev', 'Иван читает книгу'])
    main()
    assert capsys.readouterr().out == ''


def test_jev_criteria_limit_counts_control_choices():
    words = tuple(f'word{i}' for i in range(253))
    assert len(Probe('Pick', words, 'text').jev_request()['questions']['grammar']['criteria']) == 255
    with pytest.raises(ValueError):
        Probe('Pick', (*words, 'extra'), 'text').jev_request()

def test_prompt_parser_preserves_multiline_context_even_with_literal_headers():
    context = '  начало\r\nAnswer options:\n- маму\n\nконец  \n'
    probe = Probe('Which word fits?', ('маму', 'сестру'), context)
    assert Probe.from_prompt(probe.prompt()) == probe
    windows_probe = Probe('Which word fits?', ('маму', 'сестру'), 'маму\r\nсестру')
    wire = windows_probe.prompt().replace('\r\n', '\n').replace('\n', '\r\n')
    assert Probe.from_prompt(wire + '\r\n') == windows_probe


@pytest.mark.parametrize('replacement', ['- Мать\n- мать', '- 0', 'дочь', ''])
def test_malformed_or_ambiguous_answer_lists_are_rejected(replacement):
    prompt = analyze('Мать любит дочь').probes[0].prompt()
    with pytest.raises(ValueError):
        Probe.from_prompt(prompt.replace('- Мать\n- дочь', replacement))
