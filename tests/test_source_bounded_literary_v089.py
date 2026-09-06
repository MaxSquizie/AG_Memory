from __future__ import annotations

from pathlib import Path

from ah.config import LLMRoleSettings
from ah.model import ActantRole
from ah.perception import ActantCandidate, AssertionCandidate, EvidenceSpan, PredicateCandidate
from ah.perception.adaptive_parser import AdaptivePerceptionParser, AdaptiveSettings
from ah.perception.linguistic_candidates import LinguisticCandidateBuilder
from ah.perception.morphology import MorphInfo

PROJECT = Path(__file__).resolve().parents[1]


class StaticMorphology:
    name = "v089-static"

    def __init__(self, data):
        self.data = {key.casefold(): tuple(value) for key, value in data.items()}

    def analyze_all(self, word: str):
        return self.data.get(word.casefold(), ())

    def analyze(self, word: str):
        values = self.analyze_all(word)
        return values[0] if values else None


class NoModelBackend:
    def generate(self, prompt, *, system="", override=None, role="generic"):
        raise AssertionError(f"unexpected model call {role}:\n{prompt}")


def parser(morphology: StaticMorphology) -> AdaptivePerceptionParser:
    return AdaptivePerceptionParser(
        NoModelBackend(),
        AdaptiveSettings(
            prompt_dir=PROJECT / "prompts/perception",
            generation=LLMRoleSettings(max_new_tokens=24, temperature=0.0),
            retry_attempts=0,
            morphology_backend="none",
        ),
        morphology=morphology,
    )


def ev(text: str, needle: str) -> EvidenceSpan:
    start = text.index(needle)
    return EvidenceSpan(needle, start, start + len(needle))


def test_copular_holder_keeps_immediate_postnominal_possessive_inside_np():
    text = "Торжество его было недолгим."
    morph = StaticMorphology({
        "торжество": (MorphInfo("торжество", "NOUN", case="nomn", number="sing", gender="neut", score=1.0),),
        "его": (
            MorphInfo("он", "NPRO", case="accs", number="sing", gender="masc", grammemes=frozenset({"NPRO", "3per", "Anph", "accs", "sing", "masc"}), score=0.5),
            MorphInfo("его", "ADJF", grammemes=frozenset({"ADJF", "Anph", "Apro", "Fixd"}), score=0.5),
        ),
        "было": (MorphInfo("быть", "VERB", number="sing", gender="neut", mood="indc", grammemes=frozenset({"VERB", "past", "sing", "neut"}), score=1.0),),
        "недолгим": (MorphInfo("недолгий", "ADJF", case="ablt", number="sing", gender="neut", score=1.0),),
    })
    p = parser(morph)
    tokens = p._source_tokens(text)
    p._candidate_graph = LinguisticCandidateBuilder(morph).build(text)
    predicate = p._resolve_span(text, tokens, 3, 3)
    state = p._resolve_span(text, tokens, 4, 4)
    holder = p._deterministic_copular_holder_span(tokens, predicate, state)
    assert holder is not None
    assert holder.text == "Торжество его"


def test_predicative_adjective_is_not_personal_pronoun_antecedent():
    text = "Вера стояла сердитая. Она ушла."
    morph = StaticMorphology({
        "вера": (MorphInfo("вера", "NOUN", case="nomn", number="sing", gender="femn", score=1.0),),
        "стояла": (MorphInfo("стоять", "VERB", number="sing", gender="femn", mood="indc", grammemes=frozenset({"VERB", "past", "sing", "femn"}), score=1.0),),
        "сердитая": (MorphInfo("сердитый", "ADJF", case="nomn", number="sing", gender="femn", score=1.0),),
        "она": (MorphInfo("она", "NPRO", case="nomn", number="sing", gender="femn", grammemes=frozenset({"NPRO", "3per", "Anph", "nomn", "sing", "femn"}), score=1.0),),
        "ушла": (MorphInfo("уйти", "VERB", number="sing", gender="femn", mood="indc", grammemes=frozenset({"VERB", "past", "sing", "femn"}), score=1.0),),
    })
    p = parser(morph)
    p._entity_ref_counter = 0
    p._candidate_graph = LinguisticCandidateBuilder(morph).build(text)
    by_id = {
        "A1": AssertionCandidate(
            "A1", PredicateCandidate("стояла", "стоять", evidence=ev(text, "стояла")),
            (
                ActantCandidate(ActantRole.SUBJECT, mention="Вера", normalized_hint="Вера", evidence=ev(text, "Вера")),
                ActantCandidate(ActantRole.STATE, mention="сердитая", normalized_hint="сердитая", evidence=ev(text, "сердитая")),
            ),
        ),
        "A2": AssertionCandidate(
            "A2", PredicateCandidate("ушла", "уйти", evidence=ev(text, "ушла")),
            (ActantCandidate(ActantRole.SUBJECT, mention="Она", normalized_hint="она", evidence=ev(text, "Она")),),
        ),
    }
    p._resolve_pronoun_coreferences(by_id)
    vera = by_id["A1"].actants[0].entity_ref
    pronoun = by_id["A2"].actants[0].entity_ref
    assert vera is not None
    assert pronoun == vera
    assert not by_id["A2"].alternatives


def test_matrix_object_pronoun_prefers_unique_same_role_nonfinite_child_participant():
    text = "Алексей вошёл. Сняв плащ, Вера повесила его."
    morph = StaticMorphology({
        "алексей": (MorphInfo("алексей", "NOUN", case="nomn", number="sing", gender="masc", score=1.0),),
        "вошёл": (MorphInfo("войти", "VERB", number="sing", gender="masc", mood="indc", grammemes=frozenset({"VERB", "past", "sing", "masc"}), score=1.0),),
        "сняв": (MorphInfo("снять", "GRND", grammemes=frozenset({"GRND", "perf"}), score=1.0),),
        "плащ": (MorphInfo("плащ", "NOUN", case="accs", number="sing", gender="masc", animacy="inan", score=1.0),),
        "вера": (MorphInfo("вера", "NOUN", case="nomn", number="sing", gender="femn", score=1.0),),
        "повесила": (MorphInfo("повесить", "VERB", number="sing", gender="femn", mood="indc", grammemes=frozenset({"VERB", "past", "sing", "femn"}), score=1.0),),
        "его": (MorphInfo("он", "NPRO", case="accs", number="sing", gender="masc", grammemes=frozenset({"NPRO", "3per", "Anph", "accs", "sing", "masc"}), score=1.0),),
    })
    p = parser(morph)
    p._entity_ref_counter = 0
    p._candidate_graph = LinguisticCandidateBuilder(morph).build(text)
    by_id = {
        "A1": AssertionCandidate(
            "A1", PredicateCandidate("вошёл", "войти", evidence=ev(text, "вошёл")),
            (ActantCandidate(ActantRole.SUBJECT, mention="Алексей", normalized_hint="Алексей", evidence=ev(text, "Алексей")),),
        ),
        "A2": AssertionCandidate(
            "A2", PredicateCandidate("Сняв", "снять", evidence=ev(text, "Сняв")),
            (ActantCandidate(ActantRole.OBJECT, mention="плащ", normalized_hint="плащ", evidence=ev(text, "плащ")),),
        ),
        "A3": AssertionCandidate(
            "A3", PredicateCandidate("повесила", "повесить", evidence=ev(text, "повесила")),
            (
                ActantCandidate(ActantRole.SUBJECT, mention="Вера", normalized_hint="Вера", evidence=ev(text, "Вера")),
                ActantCandidate(ActantRole.OBJECT, mention="его", normalized_hint="он", evidence=ev(text, "его")),
            ),
        ),
    }
    p._resolve_pronoun_coreferences(by_id)
    cloak_ref = by_id["A2"].actants[0].entity_ref
    alexei_ref = by_id["A1"].actants[0].entity_ref
    object_ref = by_id["A3"].actants[1].entity_ref
    assert cloak_ref is not None
    assert object_ref == cloak_ref
    assert object_ref != alexei_ref
    assert not by_id["A3"].alternatives
