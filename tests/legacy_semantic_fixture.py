"""Compatibility helpers for pre-v0.20 scripted parser tests.

These answers live only in tests. They emulate the tiny semantic decisions that old
fixtures previously assumed Python morphology would make deterministically. Production
code must never import this module.
"""
from __future__ import annotations

import re


def _section(prompt: str, name: str) -> str:
    match = re.search(rf"(?:^|\n){re.escape(name)}:\n([^\n]*)", prompt)
    return match.group(1).strip() if match else ""


def legacy_semantic_answer(role: str, prompt: str) -> str | None:
    if role == "perception_modifier_attachment":
        # Generic attachment probe is intentionally ambiguity-preserving in the
        # legacy fixture. Individual tests that need a resolved reading can supply
        # an explicit answer through their Backend.
        return "UNCLEAR"

    if role == "perception_antecedent_choice":
        connector = _section(prompt, "RELATIVE CONNECTOR").casefold()
        if connector.startswith("котор"):
            # Old fixtures in this module use a matrix subject followed by the
            # modified object; choose the latter source candidate explicitly.
            return "C2" if "C2:" in prompt else "C1"
        return "UNCLEAR"

    if role == "perception_relative_clause_mode":
        connector = _section(prompt, "CONNECTOR").casefold()
        text = _section(prompt, "TEXT").casefold()
        if connector == "когда" and any(word in text for word in ("написала", "получила", "помню", "знаю")):
            return "SUBORDINATE"
        return "RELATIVE"

    if role == "perception_clause_subject_control":
        child = _section(prompt, "CHILD PREDICATE").casefold()
        # Compatibility for old scripted fixtures. Production asks the bounded
        # SAME_SUBJECT/INDEPENDENT semantic question and has no morphology shortcut.
        if child in {"получит", "получила", "прочитает", "напишет", "получил", "прочитал", "написал"}:
            return "SAME_SUBJECT"
        return "INDEPENDENT"

    if role == "perception_actant_start":
        # Select every structurally exposed phrase in turn. The parser removes a
        # selected span and renumbers the remaining positive options, so [1] means
        # "next remaining phrase"; once none remain, only [0] is present.
        positives = re.findall(r"^\[(\d+)\]\s+(.+)$", prompt, flags=re.MULTILINE)
        for index, _text in positives:
            if index != "0":
                return index
        return "0"

    if role == "perception_clause_subject_control":
        return "SAME_SUBJECT"

    if role == "perception_coordination_shared_actant":
        known_role = _section(prompt, "KNOWN SEMANTIC ROLE").upper()
        return "LOCAL" if known_role == "RECIPIENT" else "SHARED"

    if role == "semantic_nonfinite_assertion_status":
        # Historical fixtures only cover non-asserted complement infinitives
        # (want/request) and predate the v0.12.93 status probe. Production never
        # imports this helper; asserted-event cases are tested with explicit
        # scripted answers in test_narrative_identity_v093.py.
        matrix = _section(prompt, "MATRIX PREDICATE").casefold()
        if matrix.startswith(("хоч", "попрос")):
            return "NONASSERTED_CONTENT"
        return "UNCLEAR"

    if role == "perception_frame_relation":
        text = _section(prompt, "TEXT").casefold()
        choices_block = prompt.split("CHOICES:\n", 1)[1] if "CHOICES:\n" in prompt else ""
        choices = [line.strip() for line in choices_block.splitlines() if line.strip()]
        if any(marker in text for marker in ("потому что", "потому, что")) and "CAUSE_LINK" in choices:
            return "CAUSE_LINK"
        if any(marker in text for marker in (
            "после того как", "после того, как", "до того как", "до того, как",
            "перед тем как", "перед тем, как", "когда",
        )) and "TIME_LINK" in choices:
            return "TIME_LINK"
        if "чтобы" in text and "GOAL_LINK" in choices:
            return "GOAL_LINK"
        return None

    if role != "perception_role_cue":
        return None

    target = (_section(prompt, "TARGET") or _section(prompt, "MISSING INFORMATION")).casefold().strip(" .,!?:;\"'«»")
    predicate = _section(prompt, "PREDICATE").casefold()
    if not target:
        return None

    actor = {
        "иван", "мария", "анна", "лиза", "пётр", "петр", "сергей", "она", "он", "я",
        "дождь", "яблоки", "яблоко", "человек", "который", "никто",
        "иван и мария", "иван и пётр", "иван и петр",
    }
    affected = {
        "книга", "книгу", "чай", "советы", "совет", "текст", "документ", "документы",
        "письмо", "его", "её", "ее", "хлеб", "молоко", "комнату", "стул", "работу",
        "работа", "отзыв", "журнал", "новость", "пальто", "кофе", "дверь", "билет",
        "петра", "хлеб и молоко", "чай или кофе", "ключ",
    }
    receiver = {"марии", "петру", "пётру", "сергею", "адресату", "ему", "ей", "мне"}
    state = {
        "зелёные", "зеленые", "красные", "зелёные и красные", "зеленые и красные",
        "зелёные или красные", "зеленые или красные", "врач", "учитель", "новым", "новый",
        "холодно",
    }

    relative_match = re.fullmatch(r"(.+?) \(relative form: (.+?)\)", target)
    if relative_match:
        antecedent, rel_form = relative_match.groups()
        if rel_form in {"которую", "которого", "которых"}:
            return "AFFECTED_OR_CONTENT"
        if rel_form == "который":
            if predicate.startswith(("напис", "прочит", "увид")):
                return "AFFECTED_OR_CONTENT"
            return "ACTOR_OR_EXPERIENCER"

    if target == "потом":
        return "TIME_POINT"
    if target == "кто":
        return "ACTOR_OR_EXPERIENCER"
    if target == "что":
        return "AFFECTED_OR_CONTENT"
    if target == "кому":
        return "RECEIVER_OR_ADDRESSEE"
    if target in {"которую", "которого", "которых"}:
        return "AFFECTED_OR_CONTENT"
    if target == "который" and predicate.startswith(("напис", "прочит", "увид")):
        return "AFFECTED_OR_CONTENT"
    if predicate.startswith("попрос") and target in {"его", "марию", "петра", "её", "ее"}:
        return "RECEIVER_OR_ADDRESSEE"
    if target in actor:
        return "ACTOR_OR_EXPERIENCER"
    if target in receiver:
        return "RECEIVER_OR_ADDRESSEE"
    if target in affected:
        return "AFFECTED_OR_CONTENT"
    if target in state:
        return "PREDICATED_STATE"
    if target.startswith(("от ", "из ")):
        return "ORIGIN"
    if target.startswith("от "):
        return "ORIGIN"
    if target in {"биноклем"}:
        return "INSTRUMENT"
    if target in {"час", "часа", "два часа"}:
        return "ELAPSED_DURATION"
    if target in {"дома", "рядом"} or target.startswith("рядом с ") or target.startswith(("в ", "на ", "под ", "над ", "у ", "около ")):
        return "PLACE"
    if target.startswith("с ") and predicate == "увидел":
        return "INSTRUMENT"
    if target.startswith("с ") and predicate == "с":
        return "AFFECTED_OR_CONTENT"

    # Common inflectional fallback for old synthetic fixtures. This is deliberately
    # narrow and test-only; the production parser must still ask the semantic probe.
    if target.endswith(("ию", "рию")):
        return "AFFECTED_OR_CONTENT"
    if target.endswith(("ии", "ому", "ему")):
        return "RECEIVER_OR_ADDRESSEE"

    # Infinitival/nested content is represented by proposition refs, not this cue.
    return None
