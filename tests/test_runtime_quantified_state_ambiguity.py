from __future__ import annotations

from pathlib import Path

from ah.config import LLMRoleSettings
from ah.llm import LLMResponse
from ah.model import ActantRole
from ah.perception.adaptive_parser import AdaptiveSettings
from ah.perception.morphology import MorphInfo
from ah.perception.runtime_semantics import RuntimeSemanticAdaptiveParser
from legacy_semantic_fixture import legacy_semantic_answer


PROJECT = Path(__file__).resolve().parents[1]


class AmbiguousQuantifiedStateMorphology:
    """Reproduce the material NOUN+ADJF ambiguity seen with live pymorphy."""

    name = "ambiguous-quantified-state"

    _MAP = {
        "каждое": (
            MorphInfo(
                "каждый", "ADJF", case="nomn", number="sing", gender="neut",
                grammemes=frozenset({"Apro"}), score=1.0,
            ),
        ),
        "животное": (
            MorphInfo(
                "животное", "NOUN", case="nomn", number="sing", gender="neut",
                score=0.68,
            ),
            MorphInfo(
                "животный", "ADJF", case="nomn", number="sing", gender="neut",
                score=0.32,
            ),
        ),
        "живое": (
            MorphInfo(
                "живой", "ADJF", case="nomn", number="sing", gender="neut",
                score=1.0,
            ),
        ),
    }

    def analyze_all(self, word: str):
        return self._MAP.get(word.casefold(), ())

    def analyze(self, word: str):
        values = self.analyze_all(word)
        return values[0] if values else None


class Backend:
    def generate(self, prompt, *, system="", override=None, role="generic"):
        if role == "perception_act_type":
            return LLMResponse("ASSERTION", {})
        fallback = legacy_semantic_answer(role, prompt)
        if fallback is not None:
            return LLMResponse(str(fallback), {})
        raise AssertionError(f"unexpected probe {role}:\n{prompt}")


def parser() -> RuntimeSemanticAdaptiveParser:
    return RuntimeSemanticAdaptiveParser(
        Backend(),
        AdaptiveSettings(
            prompt_dir=PROJECT / "prompts/perception",
            generation=LLMRoleSettings(max_new_tokens=24, temperature=0.0),
            retry_attempts=0,
            morphology_backend="none",
        ),
        morphology=AmbiguousQuantifiedStateMorphology(),
    )


def test_ambiguous_animal_morphology_keeps_binder_np_and_predicative_state():
    result = parser().parse("Каждое животное живое").perception

    assert len(result.assertions) == 1
    assertion = result.assertions[0]
    assert assertion.predicate.lookup_form == "быть"
    by_role = {item.role: item for item in assertion.actants}
    assert by_role[ActantRole.SUBJECT].evidence.text == "Каждое животное"
    assert by_role[ActantRole.STATE].evidence.text == "живое"
    assert ActantRole.OBJECT not in by_role

    assert len(result.quantifiers) == 1
    quantifier = result.quantifiers[0]
    assert quantifier.quantifier.value == "FORALL"
    assert quantifier.role is ActantRole.SUBJECT
    assert quantifier.restriction_predicate is not None
    assert quantifier.restriction_predicate.lookup_form == "животное"
