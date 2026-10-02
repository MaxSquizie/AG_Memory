from __future__ import annotations

from types import SimpleNamespace

from ah.integration.contracts import TemplateRequest, TemplateSenseOption
from ah.integration.predicate_family_service import PredicateFamilyIntegrationService
from ah.integration.template_completion import TemplateCompletionService
from ah.perception.contracts import AssertionCandidate, PerceptionResult, PredicateCandidate
from ah.perception.morphology import MorphInfo


class _Morphology:
    def analyze_all(self, word: str):
        values = {
            "видеть": MorphInfo(
                "видеть",
                "INFN",
                transitivity="tran",
                grammemes=frozenset({"impf", "tran"}),
                score=1.0,
            ),
            "увидеть": MorphInfo(
                "увидеть",
                "INFN",
                transitivity="tran",
                grammemes=frozenset({"perf", "tran"}),
                score=1.0,
            ),
        }
        value = values.get(word.casefold())
        return () if value is None else (value,)

    def analyze(self, word: str):
        values = self.analyze_all(word)
        return values[0] if values else None


class _FamilyStore:
    def __init__(self):
        self.symbol = SimpleNamespace(uid="S_SEE", forms={"видеть", "видел"})

    def find_symbols_by_form(self, form: str):
        return (self.symbol,) if form.casefold() in {"видеть", "видел"} else ()


def test_prefixed_aspectual_predicate_exposes_existing_base_as_candidate_only() -> None:
    service = object.__new__(PredicateFamilyIntegrationService)
    service.core = SimpleNamespace(store=_FamilyStore())
    service._discourse_morphology = _Morphology()

    predicate = PredicateCandidate("увидел", normalized_hint="увидеть")
    candidates = service._predicate_symbol_candidates(predicate)

    assert tuple(item.uid for item in candidates) == ("S_SEE",)


def test_single_cross_lexeme_template_option_still_calls_semantic_resolver() -> None:
    predicate = PredicateCandidate("увидел", normalized_hint="увидеть")
    request = TemplateRequest(
        predicate=predicate,
        filled_roles=(),
        source_context="Сегодня я увидел стол",
        sense_options=(
            TemplateSenseOption(
                label="C1",
                template_uid="T_SEE",
                description="predicate: видеть; roles: SUBJECT, OBJECT",
            ),
        ),
    )

    symbol = SimpleNamespace(uid="S_SEE", forms={"видеть", "видел"})
    template = SimpleNamespace(uid="T_SEE", predicate=SimpleNamespace(uid="S_SEE"))

    class Store:
        def get_template(self, uid):
            assert uid == "T_SEE"
            return template

        def get_symbol(self, uid):
            assert uid == "S_SEE"
            return symbol

    class Integration:
        core = SimpleNamespace(store=Store())

        def template_requests(self, result):
            return (request,)

    class Perception:
        calls = 0

        def resolve_template_sense(self, source_text, candidate, filled_roles, role_bindings, options):
            self.calls += 1
            assert candidate.lookup_form == "увидеть"
            assert options == (("C1", "predicate: видеть; roles: SUBJECT, OBJECT"),)
            return "C1"

    perception = Perception()
    service = TemplateCompletionService(Integration(), perception)
    result = PerceptionResult(
        source_text="Сегодня я увидел стол",
        assertions=(AssertionCandidate("A1", predicate, ()),),
    )

    completed = service.complete(result)

    assert perception.calls == 1
    selection = completed.assertions[0].predicate.template_selection
    assert selection is not None
    assert selection.existing_template_uid == "T_SEE"
