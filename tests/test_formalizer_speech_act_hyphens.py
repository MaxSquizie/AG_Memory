"""Speech-act tokenization must not promote part of a hyphenated word to a cue."""

import pytest

from ah.formalizer.speech_act import detect_negation, detect_speech_act


@pytest.mark.parametrize("text", [
    "Кто-то вошёл, и затем он сел.",
    "Письмо лежит где-то рядом.",
    "Иван когда-то приходил.",
    "Он как-то открыл окно.",
    "Мария принесла что-то.",
    "Он почему-то ушёл.",
    "Какой-то курьер пришёл.",
    "Кто\u2010то вошёл.",
    "Кто\u2011то вошёл.",
])
def test_intra_word_hyphen_does_not_create_question(text):
    readings = detect_speech_act(text)
    assert [(r.kind, r.grounded) for r in readings] == [("DECLARATIVE", True)]


@pytest.mark.parametrize("text", [
    "Кто пришёл?",
    "Где лежит письмо",
    "Когда пришёл Иван",
    "Кто-то вошёл?",
    "Иван пришёл?",
    "Кто — Иван или Пётр",
    "Кто - Иван или Пётр",
])
def test_question_cues_and_terminal_question_mark_are_preserved(text):
    readings = detect_speech_act(text)
    assert [(r.kind, r.grounded) for r in readings] == [("QUERY", True)]


def test_indirect_request_cues_remain_separate_words():
    readings = detect_speech_act("Ты не мог бы открыть окно?")
    assert [(r.kind, r.grounded) for r in readings] == [("QUERY", False), ("COMMAND", False)]
    assert detect_negation("Кто-то не вошёл.") is True
    assert detect_negation("Не-то появилось.") is False
