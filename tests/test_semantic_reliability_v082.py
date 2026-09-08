from __future__ import annotations

from pathlib import Path

from ah.config import LLMRoleSettings
from ah.llm import LLMResponse
from ah.perception import PredicateCandidate
from ah.perception.adaptive_parser import AdaptivePerceptionParser, AdaptiveSettings
from ah.perception.linguistic_candidates import LinguisticCandidateBuilder
from ah.perception.morphology import MorphInfo

PROJECT = Path(__file__).resolve().parents[1]


class Morphology:
    name = "v082-generic"

    def __init__(self, data):
        self.data = {key.casefold(): tuple(value) for key, value in data.items()}

    def analyze_all(self, word: str):
        return self.data.get(word.casefold(), ())

    def analyze(self, word: str):
        values = self.analyze_all(word)
        return values[0] if values else None


class AttachmentBackend:
    def generate(self, prompt, *, system="", override=None, role="generic"):
        assert role == "perception_modifier_attachment"
        return LLMResponse("EVENT", {})


def test_lexically_governed_modifier_with_internal_instrumental_pp_is_not_auto_ambiguous():
    morph = Morphology({
        "Ольга": (MorphInfo("Ольга", "NOUN", case="nomn", score=1.0),),
        "поставила": (MorphInfo("поставить", "VERB", score=1.0),),
        "коробку": (MorphInfo("коробка", "NOUN", case="accs", score=1.0),),
        "рядом": (MorphInfo("рядом", "ADVB", score=1.0),),
        "с": (MorphInfo("с", "PREP", score=1.0),),
        "шкафом": (MorphInfo("шкаф", "NOUN", case="ablt", score=1.0),),
    })
    parser = AdaptivePerceptionParser(
        AttachmentBackend(),
        AdaptiveSettings(
            prompt_dir=PROJECT / "prompts/perception",
            generation=LLMRoleSettings(max_new_tokens=24, temperature=0.0),
            retry_attempts=0,
            morphology_backend="none",
        ),
        morphology=morph,
    )
    text = "Ольга поставила коробку рядом с шкафом."
    tokens = parser._source_tokens(text)
    parser._candidate_graph = LinguisticCandidateBuilder(morph).build(text)
    pred = parser._resolve_span(text, tokens, 2, 2)
    modifier = parser._resolve_span(text, tokens, 4, 6)
    selected = parser._resolve_modifier_attachment(
        text, tokens, pred, PredicateCandidate("поставила", "поставить"), modifier
    )
    assert selected is not None
    assert selected.kind.value == "PREDICATE"


def test_pre_predicate_locative_pp_requires_bounded_attachment_vote():
    text = "рама в дальней комнате то дрожала"
    morph = Morphology({
        "рама": (MorphInfo("рама", "NOUN", case="nomn", number="sing", gender="femn", score=1.0),),
        "в": (MorphInfo("в", "PREP", score=1.0),),
        "дальней": (MorphInfo("дальний", "ADJF", case="loct", number="sing", gender="femn", score=1.0),),
        "комнате": (MorphInfo("комната", "NOUN", case="loct", number="sing", gender="femn", score=1.0),),
        "то": (MorphInfo("то", "PRCL", score=1.0),),
        "дрожала": (MorphInfo("дрожать", "VERB", mood="indc", number="sing", gender="femn", score=1.0),),
    })
    class NoCallBackend:
        def __init__(self):
            self.calls = []

        def generate(self, prompt, *, system="", override=None, role="generic"):
            self.calls.append((role, prompt))
            assert role == "perception_modifier_attachment"
            return LLMResponse("EVENT", {})

    backend = NoCallBackend()
    parser = AdaptivePerceptionParser(
        backend,
        AdaptiveSettings(
            prompt_dir=PROJECT / "prompts/perception",
            generation=LLMRoleSettings(max_new_tokens=24, temperature=0.0),
            retry_attempts=0,
            morphology_backend="none",
        ),
        morphology=morph,
    )
    parser._candidate_graph = LinguisticCandidateBuilder(morph).build(text)
    tokens = parser._source_tokens(text)
    predicate_span = parser._resolve_span(text, tokens, 6, 6)
    modifier = parser._resolve_span(text, tokens, 2, 4)
    selected = parser._resolve_modifier_attachment(
        text,
        tokens,
        predicate_span,
        PredicateCandidate("дрожала", "дрожать"),
        modifier,
    )
    assert selected is not None
    assert selected.kind.value == "PREDICATE"
    assert len(backend.calls) == 1
    assert backend.calls[0][0] == "perception_modifier_attachment"


def test_pre_predicate_locative_pp_uses_noun_head_case_not_ambiguous_adjective_case():
    text = "рама в дальней комнате то дрожала"
    morph = Morphology({
        "рама": (MorphInfo("рама", "NOUN", case="nomn", score=1.0),),
        "в": (MorphInfo("в", "PREP", score=1.0),),
        # The adjective is genuinely case-ambiguous in isolation.  Phrase case must
        # come from the nominal head instead of treating this weak ABLT reading as
        # an instrumental attachment ambiguity.
        "дальней": (
            MorphInfo("дальний", "ADJF", case="gent", score=0.2),
            MorphInfo("дальний", "ADJF", case="datv", score=0.2),
            MorphInfo("дальний", "ADJF", case="ablt", score=0.2),
            MorphInfo("дальний", "ADJF", case="loct", score=0.2),
        ),
        "комнате": (
            MorphInfo("комната", "NOUN", case="loct", score=0.82),
            MorphInfo("комната", "NOUN", case="datv", score=0.10),
        ),
        "то": (MorphInfo("то", "PRCL", score=1.0),),
        "дрожала": (MorphInfo("дрожать", "VERB", mood="indc", score=1.0),),
    })

    class NoCallBackend:
        def generate(self, prompt, *, system="", override=None, role="generic"):
            assert role == "perception_modifier_attachment"
            return LLMResponse("EVENT", {})

    parser = AdaptivePerceptionParser(
        NoCallBackend(),
        AdaptiveSettings(
            prompt_dir=PROJECT / "prompts/perception",
            generation=LLMRoleSettings(max_new_tokens=24, temperature=0.0),
            retry_attempts=0,
            morphology_backend="none",
        ),
        morphology=morph,
    )
    parser._candidate_graph = LinguisticCandidateBuilder(morph).build(text)
    tokens = parser._source_tokens(text)
    predicate_span = parser._resolve_span(text, tokens, 6, 6)
    modifier = parser._resolve_span(text, tokens, 2, 4)
    selected = parser._resolve_modifier_attachment(
        text,
        tokens,
        predicate_span,
        PredicateCandidate("дрожала", "дрожать"),
        modifier,
    )
    assert selected is not None
    assert selected.kind.value == "PREDICATE"
