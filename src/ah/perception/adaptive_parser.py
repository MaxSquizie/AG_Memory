from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable, Protocol, TypeVar
import re

from ah.config import LLMRoleSettings
from ah.llm.process_backend import LLMResponse
from ah.model import ActantRole

from .morphology import MorphInfo, Morphology, build_morphology, material_analyses, stable_normal_form
from .linguistic_candidates import (
    CoordinationKind,
    LinguisticCandidateBuilder,
    LinguisticCandidateGraph,
)

from .contracts import (
    ActantCandidate,
    ActantCompositionCandidate,
    CompositionMemberCandidate,
    CompositionOperator,
    AssertionCandidate,
    AssertionStatus,
    ConditionalCandidate,
    CommandCandidate,
    EvidenceSpan,
    PerceptionResult,
    PredicateCandidate,
    TemplateCandidate,
    QueryCandidate,
    QueryMode,
    SituationRelationCandidate,
    StructuralClarificationOption,
    StructuralClarificationSpec,
)


class TextGenerator(Protocol):
    def generate(
        self,
        prompt: str,
        *,
        system: str = "",
        override: dict[str, Any] | None = None,
        role: str = "generic",
    ) -> LLMResponse: ...


@dataclass(frozen=True, slots=True)
class AdaptiveSettings:
    prompt_dir: Path | None
    generation: LLMRoleSettings
    retry_attempts: int = 1
    max_acts: int = 4
    max_actants_per_act: int = 8
    predicate_symbol_language: str = "en"
    morphology_backend: str = "auto"
    verify_predicate_symbol: bool = True

    def __post_init__(self) -> None:
        if self.retry_attempts < 0 or self.retry_attempts > 2:
            raise ValueError("retry_attempts must be in [0, 2]")
        if self.max_acts <= 0:
            raise ValueError("max_acts must be > 0")
        if self.max_actants_per_act <= 0:
            raise ValueError("max_actants_per_act must be > 0")
        if self.predicate_symbol_language != "en":
            raise ValueError("predicate_symbol_language currently must be 'en'")
        if self.morphology_backend not in {"auto", "pymorphy3", "none"}:
            raise ValueError("morphology_backend must be auto, pymorphy3, or none")


@dataclass(frozen=True, slots=True)
class ProbeTrace:
    stage: str
    prompt: str
    raw_text: str
    normalized_answer: str | None
    retry_index: int
    error: str | None = None


@dataclass(frozen=True, slots=True)
class AdaptiveParseResult:
    perception: PerceptionResult
    traces: tuple[ProbeTrace, ...]


@dataclass(frozen=True, slots=True)
class AdaptiveTemplateResult:
    candidate: TemplateCandidate
    traces: tuple[ProbeTrace, ...]


@dataclass(frozen=True, slots=True)
class AdaptiveClarificationResult:
    option_index: int | None
    traces: tuple[ProbeTrace, ...]


class AdaptiveParseError(ValueError):
    def __init__(self, message: str, traces: tuple[ProbeTrace, ...] = ()) -> None:
        super().__init__(message)
        self.traces = traces


class AdaptiveStructuralClarificationRequired(AdaptiveParseError):
    def __init__(
        self,
        spec: StructuralClarificationSpec,
        traces: tuple[ProbeTrace, ...] = (),
    ) -> None:
        super().__init__(f"structural clarification required: {spec.mention}", traces)
        self.spec = spec


@dataclass(frozen=True, slots=True)
class _SourceToken:
    index: int
    text: str
    start: int
    end: int


@dataclass(frozen=True, slots=True)
class _Span:
    start_index: int
    end_index: int
    text: str
    evidence: EvidenceSpan

    @property
    def spec(self) -> str:
        return str(self.start_index) if self.start_index == self.end_index else f"{self.start_index}-{self.end_index}"

    def overlaps(self, other: "_Span") -> bool:
        return not (self.end_index < other.start_index or other.end_index < self.start_index)


T = TypeVar("T")


# adaptive_v3 keeps model work tiny and finite. Semantic uncertainty is reduced
# to short English labels; numeric outputs are reserved for literal token/span
# addressing. The model is never expected to construct AH objects or enumerate a
# full ontology. Python owns candidate construction, mapping and validation. Probe
# instructions are explicit files: a missing or empty instruction is a configuration
# error, never a reason to substitute hidden parser behavior.


_ACT_TYPE_CHOICES: dict[int, str] = {
    0: "NONE",
    1: "ASSERTION",
    2: "QUERY",
    3: "COMMAND",
}
_QUERY_MODE_CHOICES: dict[int, QueryMode | None] = {
    0: None,
    1: QueryMode.EXISTS,
    2: QueryMode.FILL_ROLE,
}

_ACT_TYPE_LABEL_CHOICES: dict[str, str] = {
    "NONE": "NONE",
    "ASSERTION": "ASSERTION",
    "QUERY": "QUERY",
    "COMMAND": "COMMAND",
}
_NEGATION_LABEL_CHOICES: dict[str, bool | None] = {
    "NO": False,
    "YES": True,
    "UNKNOWN": None,
}
_QUERY_MODE_LABEL_CHOICES: dict[str, QueryMode | None] = {
    "UNKNOWN": None,
    "EXISTS": QueryMode.EXISTS,
    "FILL_ROLE": QueryMode.FILL_ROLE,
}
_ORDINAL_LABELS = (
    "FIRST", "SECOND", "THIRD", "FOURTH",
    "FIFTH", "SIXTH", "SEVENTH", "EIGHTH",
)

# Fixed-choice log-likelihood margin used only as parser evidence. It is not AH
# truth confidence and never maps to w. Nearly tied fixed-choice scores are treated
# as unresolved semantic ambiguity by deterministic perception.
_CHOICE_MARGIN_THRESHOLD = 0.10

# Historical private names are kept as protocol-label aliases so older regression
# fixtures can describe the same semantic outcomes without reintroducing the removed
# likelihood-completion runtime path.
_EVENT_RECIPIENT_COMPLETION = "HAS_RECIPIENT_SLOT"
_EVENT_SOURCE_COMPLETION = "HAS_SOURCE_SLOT"
_EVENT_NONE_COMPLETION = "NO_RECIPIENT_SLOT"

_DISCOURSE_FOLLOW_MARKERS = frozenset({"потом", "затем", "после этого"})

_ROLE_GROUPS: dict[str, tuple[tuple[ActantRole, str], ...]] = {
    "participant": (
        (ActantRole.SUBJECT, "main entity that acts, has, is, or is being described"),
        (ActantRole.OBJECT, "entity or content directly acted on, perceived, possessed, or referred to"),
        (ActantRole.RECIPIENT, "receiver, beneficiary, or destination participant"),
        (ActantRole.SOURCE, "origin: from whom or from where something comes"),
        (ActantRole.ABSENTEE, "entity explicitly absent, missing, or not participating"),
        (ActantRole.AUXILLIARY, "secondary participant that does not fit a more specific participant role"),
    ),
    "description": (
        (ActantRole.STATE, "property, condition, class, status, or value"),
        (ActantRole.LOCATION, "place, position, or spatial destination"),
        (ActantRole.TIME, "time point, date, or when something happens"),
        (ActantRole.DURATION, "how long something lasts"),
        (ActantRole.AMOUNT, "quantity, count, size, or measure"),
    ),
    "circumstance": (
        (ActantRole.CAUSE, "reason or cause: why something happens"),
        (ActantRole.PURPOSE, "goal or intended result: what for"),
        (ActantRole.TOOL, "instrument or tool used"),
        (ActantRole.MATERIAL, "substance or material something is made from or uses"),
        (ActantRole.HOW_TO, "manner, method, or how something is done"),
    ),
}

_ROLE_FAMILY_DESCRIPTIONS = {
    "participant": "person/thing involved as actor, object, receiver, source, or missing participant",
    "description": "property/state, place, time, duration, or amount",
    "circumstance": "reason, goal, tool, material, or manner/method",
}

_TEMPLATE_ROLE_DESCRIPTIONS: dict[ActantRole, str] = {
    role: description
    for entries in _ROLE_GROUPS.values()
    for role, description in entries
}

# High-confidence question words that have a stable role independent of most syntax.
_DETERMINISTIC_WH_ROLES: dict[str, ActantRole] = {
    "кто": ActantRole.SUBJECT,
    "кого": ActantRole.OBJECT,
    "кому": ActantRole.RECIPIENT,
    "что": ActantRole.OBJECT,
    "чего": ActantRole.OBJECT,
    "чему": ActantRole.RECIPIENT,
    "где": ActantRole.LOCATION,
    "куда": ActantRole.LOCATION,
    "откуда": ActantRole.SOURCE,
    "когда": ActantRole.TIME,
    "сколько": ActantRole.AMOUNT,
    "почему": ActantRole.CAUSE,
    "отчего": ActantRole.CAUSE,
    "зачем": ActantRole.PURPOSE,
}
_QUESTION_WORDS = {
    "кто", "кого", "кому", "кем", "что", "чего", "чему", "чем",
    "где", "куда", "откуда", "когда", "сколько", "почему", "отчего", "зачем", "как",
}
_NEGATION_MARKERS = {"не", "нет", "никогда", "никто", "ничто", "никак", "нигде"}
_COORDINATORS = {"и", "или", "либо", "а", "но"}
_STRONG_BOUNDARY = {".", "!", "?", ";", ":"}
_SPATIAL_RELATION_ADVERBS = {"рядом", "близко", "неподалёку", "неподалеку"}
# Lexical spatial adverbs are linguistic evidence, not sentence-specific semantics.
# They can safely collapse the STATE/LOCATION ambiguity before the LLM role probe.
_SPATIAL_ADVERBS = {
    "дома", "здесь", "там", "тут", "внутри", "снаружи", "вверху", "внизу",
    "впереди", "позади", "рядом", "близко", "далеко", "неподалёку", "неподалеку",
}


class AdaptivePerceptionParser:
    """Weak-model-oriented adaptive semantic recognizer.

    The LLM receives no AH objects, UIDs, templates, graph structure, or parser state.
    Each call solves one small natural-language decision. Python owns tokenization,
    candidate enumeration, exclusions, span assembly, role mapping, validation and
    PerceptionResult construction. Model outputs are bounded protocol values: short English semantic labels,
    one finite generative TemplateCandidate cue, or numeric token/span addresses. Predicate identity itself is deterministic: the
    normalized source-language lexical form is used directly as the language-level
    S identity, while the observed surface form remains evidence/R_text.
    """

    _EN_SYMBOL_RE = re.compile(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)*")
    _IRREGULAR_EN = {
        "am": "be", "is": "be", "are": "be", "was": "be", "were": "be",
        "been": "be", "being": "be", "has": "have", "had": "have",
        "does": "do", "did": "do",
    }
    def __init__(
        self,
        backend: TextGenerator,
        settings: AdaptiveSettings,
        *,
        morphology: Morphology | None = None,
    ) -> None:
        self.backend = backend
        self.settings = settings
        self.morphology = morphology or build_morphology(settings.morphology_backend)
        self._traces: list[ProbeTrace] = []
        self._morph_cache: dict[str, MorphInfo | None] = {}
        self._morph_all_cache: dict[str, tuple[MorphInfo, ...]] = {}
        self._candidate_graph: LinguisticCandidateGraph | None = None
        self._entity_ref_counter = 0
        self._structural_resolution: str | None = None
        self._pending_nominal_with: list[tuple[ActantCandidate, _Span]] = []

    def propose_template_candidate(
        self,
        source_text: str,
        predicate: PredicateCandidate,
        filled_roles: tuple[ActantRole, ...],
        role_bindings: tuple[tuple[ActantRole, str], ...] = (),
    ) -> AdaptiveTemplateResult:
        """Build a runtime TemplateCandidate from explicit semantic evidence only.

        v0.12.39 removes one-shot hidden valency prediction from the production
        template path.  ``filled_roles`` has already been extracted by Perception
        from the current assertion/query/command (including an explicitly requested
        query role).  Integration may later monotonically expand canonical T when a
        new validated explicit role is observed.

        Hidden-valency generation remains available only to the standalone model
        capability diagnostic; it has no authority over canonical schema creation.
        """
        del source_text, predicate, role_bindings
        self._traces = []
        explicit = set(filled_roles)
        ordered = tuple(role for role in ActantRole if role in explicit)
        self._deterministic_trace(
            "template_candidate_explicit_roles",
            "VALIDATED EXPLICIT SEMANTIC ROLES",
            [role.value for role in ordered],
        )
        return AdaptiveTemplateResult(TemplateCandidate(ordered), tuple(self._traces))

    @staticmethod
    def _template_role_label(role: ActantRole) -> str:
        if role is ActantRole.AUXILLIARY:
            return "OTHER_PARTICIPANT"
        if role is ActantRole.HOW_TO:
            return "MANNER"
        return role.value

    def interpret_clarification_answer(
        self,
        answer_text: str,
        option_labels: tuple[str, ...],
    ) -> AdaptiveClarificationResult:
        """Extract which already-presented option the user explicitly identifies.

        This probe does *not* revisit the original ambiguous sentence and does not
        choose a canonical AH entity by plausibility. It only interprets the user's
        new clarification utterance against user-visible labels; deterministic code
        later validates the selected index against ``k_AMBIGUOUS.members``.
        """
        self._traces = []
        if len(option_labels) < 2:
            raise AdaptiveParseError("clarification requires at least two options")
        numeric_choices: dict[int, int | None] = {0: None}
        label_choices: dict[str, int | None] = {"NONE": None}
        option_lines = ["NONE: the answer does not explicitly identify one listed option"]
        for index, label in enumerate(option_labels, start=1):
            numeric_choices[index] = index
            ordinal = _ORDINAL_LABELS[index - 1]
            label_choices[ordinal] = index
            option_lines.append(f"{ordinal}: {label}")
        prompt = (
            f"CLARIFICATION ANSWER:\n{answer_text}\n"
            "QUESTION:\nWhich ONE listed referent does this answer explicitly identify? "
            "Do not infer from the earlier ambiguous sentence. Choose NONE if the answer "
            "does not clearly identify exactly one option.\nOPTIONS:\n"
            + "\n".join(option_lines)
        )
        selected = self._probe(
            "clarification_answer",
            prompt,
            lambda raw: self._label_or_number_choice(raw, label_choices, numeric_choices),
            max_new_tokens=2,
            choice_outputs=tuple(label_choices),
        )
        return AdaptiveClarificationResult(selected, tuple(self._traces))

    def parse(
        self,
        text: str,
        *,
        structural_resolution: str | None = None,
    ) -> AdaptiveParseResult:
        self._traces = []
        self._entity_ref_counter = 0
        self._structural_resolution = structural_resolution
        self._pending_nominal_with = []
        tokens = self._source_tokens(text)
        self._candidate_graph = LinguisticCandidateBuilder(self.morphology).build(text)
        if not tokens:
            return AdaptiveParseResult(PerceptionResult(source_text=text), ())

        assertions: list[AssertionCandidate] = []
        assertion_spans: dict[str, _Span | None] = {}
        queries: list[QueryCandidate] = []
        commands: list[CommandCandidate] = []
        used_predicates: list[_Span] = []
        sentence_act_types: dict[int, str] = {}

        try:
            for act_index in range(1, self.settings.max_acts + 1):
                morph_candidates = self._predicate_morph_candidates(tokens, used_predicates)
                candidate_sentence_ids: set[int] = set()
                if self._candidate_graph is not None:
                    for index in morph_candidates:
                        clause = self._candidate_graph.clause_for_token(index)
                        if clause is not None:
                            candidate_sentence_ids.add(clause.sentence_id)
                sentence_id = next(iter(candidate_sentence_ids)) if len(candidate_sentence_ids) == 1 else None
                if sentence_id is not None and sentence_id in sentence_act_types:
                    act_choice = sentence_act_types[sentence_id]
                    self._deterministic_trace(
                        "act_type", self._act_type_prompt(text, tokens, used_predicates), act_choice
                    )
                else:
                    deterministic_act = (
                        self._deterministic_act_type(tokens, morph_candidates, sentence_id)
                        if morph_candidates or not used_predicates
                        else None
                    )
                    if deterministic_act is not None:
                        act_choice = deterministic_act
                        self._deterministic_trace(
                            "act_type", self._act_type_prompt(text, tokens, used_predicates), act_choice
                        )
                    else:
                        act_choice = self._probe(
                            "act_type",
                            self._act_type_prompt(text, tokens, used_predicates),
                            lambda raw: self._label_or_number_choice(
                                raw, _ACT_TYPE_LABEL_CHOICES, _ACT_TYPE_CHOICES
                            ),
                            max_new_tokens=2,
                            choice_outputs=tuple(_ACT_TYPE_LABEL_CHOICES),
                        )
                    if sentence_id is not None and act_choice != "NONE":
                        sentence_act_types[sentence_id] = act_choice
                act_type = act_choice
                if act_type == "NONE":
                    break

                implicit_copula = self._deterministic_implicit_copula(tokens, used_predicates, morph_candidates)
                if implicit_copula:
                    predicate_start = 0
                    self._deterministic_trace(
                        "predicate_start",
                        self._predicate_start_prompt(text, tokens, used_predicates, morph_candidates),
                        0,
                    )
                elif morph_candidates:
                    # Morphology/candidate-graph candidates are parsed in source order.
                    # This is only scheduling: it does not assert that the first verb is
                    # semantically "main". Later frame-composition decides whether frames
                    # are independent, coordinated or nested. Asking a weak LLM to choose
                    # a "main predicate" would discard valid frames and add uncertainty.
                    predicate_start = min(morph_candidates)
                    self._deterministic_trace(
                        "predicate_start",
                        self._predicate_start_prompt(text, tokens, used_predicates, morph_candidates),
                        predicate_start,
                    )
                else:
                    candidate_filter = None
                    predicate_start = self._probe(
                        "predicate_start",
                        self._predicate_start_prompt(text, tokens, used_predicates, candidate_filter),
                        lambda raw: self._predicate_start_choice(raw, tokens, used_predicates, candidate_filter),
                        max_new_tokens=1,
                    )
                if predicate_start == -2:
                    raise AdaptiveParseError("predicate selection abstained")
                if predicate_start == -1:
                    if act_index == 1:
                        raise AdaptiveParseError("act classified but no meaningful predicate was selected")
                    break

                predicate_span: _Span | None
                predicate_lemma: str | None = None
                if predicate_start == 0:
                    predicate_span = None
                    target_text = text
                    predicate_lemma = "быть" if implicit_copula else None
                else:
                    if self._atomic_morph_predicate(predicate_start, tokens):
                        predicate_end = predicate_start
                        end_choices = {predicate_end: predicate_end}
                        self._deterministic_trace(
                            "predicate_end",
                            self._predicate_end_prompt(text, tokens, predicate_start, end_choices),
                            predicate_end,
                        )
                    else:
                        end_choices = self._predicate_end_choices(text, tokens, predicate_start, used_predicates)
                        if len(end_choices) == 1:
                            predicate_end = next(iter(end_choices))
                            self._deterministic_trace(
                                "predicate_end", self._predicate_end_prompt(text, tokens, predicate_start, end_choices), predicate_end
                            )
                        else:
                            end_probe_choices: dict[int, int | None] = {0: None}
                            end_probe_choices.update(end_choices)
                            predicate_end = self._probe(
                                "predicate_end",
                                self._predicate_end_prompt(text, tokens, predicate_start, end_choices),
                                lambda raw: self._number_choice(raw, end_probe_choices),
                                max_new_tokens=1,
                            )
                            if predicate_end is None:
                                raise AdaptiveParseError("predicate boundary unresolved")
                    predicate_span = self._resolve_span(text, tokens, predicate_start, predicate_end)
                    if any(predicate_span.overlaps(old) for old in used_predicates):
                        raise AdaptiveParseError("predicate overlaps an already parsed predicate")
                    used_predicates.append(predicate_span)
                    target_text = predicate_span.text
                    predicate_lemma = self._predicate_lemma(
                        tokens, predicate_start, predicate_end, act_type=act_type
                    )

                symbol_prompt = self._predicate_symbol_prompt(
                    text, tokens, predicate_span, target_text,
                    implicit=predicate_span is None, lemma=predicate_lemma,
                )
                lexical_symbol = self._deterministic_predicate_symbol(predicate_lemma)
                if lexical_symbol is not None or self.settings.verify_predicate_symbol:
                    canonical = self._canonical_predicate_form(predicate_lemma, target_text)
                    self._deterministic_trace("predicate_symbol", symbol_prompt, canonical)
                else:
                    # Compatibility for the older adaptive_v1/v2 protocols only.
                    # adaptive_v3 never delegates lexical identity to free generation.
                    canonical = self._probe(
                        "predicate_symbol", symbol_prompt, self._english_symbol, max_new_tokens=8
                    )
                predicate = PredicateCandidate(
                    surface=(target_text if predicate_span is not None else canonical),
                    normalized_hint=canonical,
                    sense_hint=("IMPLICIT" if predicate_span is None else None),
                    evidence=(predicate_span.evidence if predicate_span is not None else None),
                )

                contrastive = (
                    self._contrastive_negation_frames(text, tokens, predicate_span, predicate)
                    if act_type == "ASSERTION" else None
                )
                if contrastive is not None:
                    for frame_actants, frame_negated in contrastive:
                        local_id = f"A{len(assertions) + 1}"
                        assertions.append(
                            AssertionCandidate(
                                local_id=local_id,
                                predicate=predicate,
                                actants=frame_actants,
                                evidence=self._assertion_evidence(text, tokens, predicate_span),
                                negated=frame_negated,
                            )
                        )
                        assertion_spans[local_id] = predicate_span
                    if predicate_span is None:
                        break
                    if self.morphology.name != "none" and not self._predicate_morph_candidates(tokens, used_predicates):
                        break
                    continue

                negated = False
                query_mode = QueryMode.EXISTS
                requested_role: ActantRole | None = None
                requested_span: _Span | None = None

                if act_type == "ASSERTION":
                    negation_text = self._predicate_local_text(text, tokens, predicate_span)
                    deterministic_negation = self._deterministic_negation(tokens, predicate_span)
                    if deterministic_negation is not None:
                        negated = deterministic_negation
                        self._deterministic_trace(
                            "negation", self._negation_prompt(negation_text, predicate), 1 if negated else 0
                        )
                    else:
                        negation_choice = self._probe(
                            "negation",
                            self._negation_prompt(negation_text, predicate),
                            lambda raw: self._label_or_number_choice(
                                raw, _NEGATION_LABEL_CHOICES, {0: False, 1: True, 2: None}
                            ),
                            max_new_tokens=2,
                            choice_outputs=tuple(_NEGATION_LABEL_CHOICES),
                        )
                        if negation_choice is None:
                            raise AdaptiveParseError("negation scope unresolved")
                        negated = negation_choice
                elif act_type == "QUERY":
                    if self._explicit_question_word(tokens) is not None:
                        query_mode = QueryMode.FILL_ROLE
                        self._deterministic_trace("query_mode", self._query_mode_prompt(text, predicate), query_mode.value)
                    else:
                        query_mode_choice = self._probe(
                            "query_mode",
                            self._query_mode_prompt(text, predicate),
                            lambda raw: self._label_or_number_choice(
                                raw, _QUERY_MODE_LABEL_CHOICES, _QUERY_MODE_CHOICES
                            ),
                            max_new_tokens=3,
                            choice_outputs=tuple(_QUERY_MODE_LABEL_CHOICES),
                        )
                        if query_mode_choice is None:
                            raise AdaptiveParseError("query mode unresolved")
                        query_mode = query_mode_choice
                    if query_mode is QueryMode.FILL_ROLE:
                        requested_role, requested_span = self._requested_query_role(text, tokens, predicate)

                actants, _selected_spans = self._extract_actants(
                    text,
                    tokens,
                    predicate_span,
                    predicate,
                    act_type=act_type,
                    requested_role=requested_role,
                    requested_span=requested_span,
                )

                if act_type == "ASSERTION":
                    local_id = f"A{len(assertions) + 1}"
                    assertions.append(
                        AssertionCandidate(
                            local_id=local_id,
                            predicate=predicate,
                            actants=actants,
                            evidence=self._assertion_evidence(text, tokens, predicate_span),
                            negated=negated,
                        )
                    )
                    assertion_spans[local_id] = predicate_span
                elif act_type == "QUERY":
                    queries.append(
                        QueryCandidate(
                            predicate=predicate,
                            actants=actants,
                            requested_role=requested_role,
                            query_mode=query_mode,
                        )
                    )
                else:
                    commands.append(CommandCandidate(predicate=predicate, actants=actants))

                if predicate_span is None:
                    break
                # With morphology available, do not ask the model whether the same
                # already-parsed simple clause is another act. Continue only when a
                # distinct unparsed predicate head still exists.
                if self.morphology.name != "none" and not self._predicate_morph_candidates(tokens, used_predicates):
                    break

        except AdaptiveStructuralClarificationRequired as exc:
            traces = exc.traces or tuple(self._traces)
            raise AdaptiveStructuralClarificationRequired(exc.spec, traces) from exc
        except AdaptiveParseError as exc:
            traces = tuple(self._traces)
            if exc.traces:
                traces = exc.traces
            raise AdaptiveParseError(str(exc), traces) from exc

        assertions, assertion_spans = self._materialize_nominal_with_assertions(
            assertions, assertion_spans
        )
        assertions = self._attach_nested_assertions(assertions, assertion_spans)
        conditionals = self._derive_conditionals(assertions, assertion_spans)
        assertions = self._mark_conditional_statuses(assertions, conditionals)
        relations = self._derive_situation_relations(assertions, assertion_spans)
        assertions = self._strip_structural_relation_actants(assertions, relations)
        result = PerceptionResult(
            source_text=text,
            assertions=tuple(assertions),
            queries=tuple(queries),
            commands=tuple(commands),
            diagnostics=(),
            relations=relations,
            conditionals=conditionals,
        )
        return AdaptiveParseResult(result, tuple(self._traces))

    def _deterministic_act_type(
        self,
        tokens: tuple[_SourceToken, ...],
        predicate_candidates: tuple[int, ...],
        sentence_id: int | None,
    ) -> str | None:
        """Classify obvious speech acts from punctuation and morphology.

        This is deliberately conservative.  Questions with an explicit question
        mark, assertions with an explicit nominative subject, and unambiguous
        imperative clauses need no semantic judgment from the LLM.  Only genuinely
        unresolved clause force remains eligible for a tiny finite probe.
        """
        graph = self._candidate_graph
        if graph is not None and sentence_id is not None:
            clauses = [c for c in graph.clauses if c.sentence_id == sentence_id]
            if clauses:
                start = min(c.span.start_index for c in clauses)
                end = max(c.span.end_index for c in clauses)
            else:
                start, end = 1, len(tokens)
        elif predicate_candidates:
            start, end = self._clause_bounds(
                self._resolve_span_from_source(tokens, predicate_candidates[0], predicate_candidates[0]),
                tokens,
            )
        else:
            start, end = 1, len(tokens)

        # Clause spans deliberately omit terminal punctuation.  Speech-act force
        # belongs to the containing sentence, so inspect the strong-boundary window
        # around the active predicate rather than only the semantic clause span.
        focus_index = predicate_candidates[0] if predicate_candidates else start
        sent_start, sent_end = 1, len(tokens)
        for token in tokens:
            if token.index < focus_index and token.text in {".", "!", "?", ";"}:
                sent_start = token.index + 1
            elif token.index >= focus_index and token.text in {".", "!", "?", ";"}:
                sent_end = token.index
                break
        if any(tokens[i - 1].text == "?" for i in range(sent_start, sent_end + 1)):
            return "QUERY"

        explicit_subject = any(
            self._has_structural_morph(tokens[i - 1], poses={"NOUN", "NPRO"}, case="nomn")
            for i in range(start, end + 1)
            if self._is_word_token(tokens[i - 1])
        )
        if explicit_subject:
            return "ASSERTION"

        moods: set[str] = set()
        for index in predicate_candidates:
            if index < start or index > end:
                continue
            for info in self._material_morph_analyses(tokens[index - 1]):
                if info.pos == "VERB" and info.mood:
                    moods.add(info.mood)
        if moods == {"impr"}:
            return "COMMAND"
        if predicate_candidates:
            if "indc" in moods or not moods:
                return "ASSERTION"
            return None
        return None

    def _assertion_evidence(
        self,
        text: str,
        tokens: tuple[_SourceToken, ...],
        predicate_span: _Span | None,
    ) -> EvidenceSpan:
        """Return the smallest deterministic clause evidence for one frame."""
        if predicate_span is None or self._candidate_graph is None:
            return EvidenceSpan(text, 0, len(text))
        clause = self._candidate_graph.clause_for_token(predicate_span.start_index)
        if clause is None:
            return EvidenceSpan(text, 0, len(text))
        start, end = self._predicate_argument_bounds(predicate_span, tokens)
        return self._resolve_span(text, tokens, start, end).evidence

    def _derive_conditionals(
        self,
        assertions: list[AssertionCandidate],
        assertion_spans: dict[str, _Span | None],
    ) -> tuple[ConditionalCandidate, ...]:
        """Build runtime conditional dependencies without asserting either branch.

        Clause recognition owns the surface language (currently e.g. Russian
        conditional subordinators); this compiler only consumes the normalized
        `parent_role_hint == CONDITION` relation.  Both fronted and postposed
        subordinate clauses therefore use the same semantic path.
        """
        graph = self._candidate_graph
        if graph is None or len(assertions) < 2:
            return ()

        clause_to_locals: dict[str, list[str]] = {}
        for local_id, span in assertion_spans.items():
            if span is None:
                continue
            clause = graph.clause_for_token(span.start_index)
            if clause is None:
                continue
            clause_to_locals.setdefault(clause.clause_id, []).append(local_id)
        for values in clause_to_locals.values():
            values.sort(
                key=lambda lid: assertion_spans[lid].start_index
                if assertion_spans[lid] is not None else 10**9
            )

        out: list[ConditionalCandidate] = []
        seen: set[tuple[tuple[str, ...], tuple[str, ...]]] = set()
        clauses = list(graph.clauses)
        clause_index = {item.clause_id: i for i, item in enumerate(clauses)}
        for clause in clauses:
            if clause.parent_role_hint != "CONDITION" or clause.parent_clause_id is None:
                continue
            antecedent_ids: list[str] = list(clause_to_locals.get(clause.clause_id, ()))
            child_i = clause_index.get(clause.clause_id, -1)
            parent_i = clause_index.get(clause.parent_clause_id, -1)
            # Fronted conditional regions may contain coordinated sibling clauses:
            # "Если A и B, C".  The builder attaches the conditional child to C;
            # every predicate-bearing clause between the child and C remains part
            # of the antecedent region unless it is itself subordinate elsewhere.
            if 0 <= child_i < parent_i:
                for sibling in clauses[child_i + 1:parent_i]:
                    if sibling.sentence_id != clause.sentence_id:
                        break
                    if sibling.parent_clause_id not in {None, clause.clause_id}:
                        continue
                    antecedent_ids.extend(clause_to_locals.get(sibling.clause_id, ()))
            antecedent = tuple(dict.fromkeys(antecedent_ids))
            consequent = tuple(clause_to_locals.get(clause.parent_clause_id, ()))
            if not antecedent or not consequent:
                continue
            key = (antecedent, consequent)
            if key in seen:
                continue
            seen.add(key)
            out.append(
                ConditionalCandidate(
                    antecedent_refs=antecedent,
                    consequent_refs=consequent,
                    evidence=(clause.connector_span.evidence if clause.connector_span is not None else None),
                )
            )
            self._deterministic_trace(
                "conditional_relation",
                "ANTECEDENT:\n" + " | ".join(antecedent)
                + "\nCONSEQUENT:\n" + " | ".join(consequent),
                "CONDITION",
            )
        return tuple(out)

    @staticmethod
    def _mark_conditional_statuses(
        assertions: list[AssertionCandidate],
        conditionals: tuple[ConditionalCandidate, ...],
    ) -> list[AssertionCandidate]:
        conditional_ids = {
            ref
            for conditional in conditionals
            for ref in (*conditional.antecedent_refs, *conditional.consequent_refs)
        }
        if not conditional_ids:
            return assertions
        return [
            replace(item, status=AssertionStatus.CONDITIONAL)
            if item.local_id in conditional_ids else item
            for item in assertions
        ]

    def _derive_situation_relations(
        self,
        assertions: list[AssertionCandidate],
        assertion_spans: dict[str, _Span | None],
    ) -> tuple[SituationRelationCandidate, ...]:
        """Preserve directional clause-connective semantics as canonical L candidates.

        A generic TIME actant says that two situations are temporally related, but it
        cannot distinguish AFTER from BEFORE. Russian compound connectives with a
        stable ordering meaning therefore also emit a directional FOLLOW candidate.
        `N1 FOLLOW N2` means N1 precedes N2.
        """
        graph = self._candidate_graph
        if graph is None or len(assertions) < 2:
            return ()

        clause_to_locals: dict[str, list[str]] = {}
        for local_id, span in assertion_spans.items():
            if span is None:
                continue
            clause = graph.clause_for_token(span.start_index)
            if clause is not None:
                clause_to_locals.setdefault(clause.clause_id, []).append(local_id)
        for values in clause_to_locals.values():
            values.sort(
                key=lambda lid: assertion_spans[lid].start_index
                if assertion_spans[lid] is not None else 10**9
            )

        # Values encode which local situation precedes the other.
        directions = {
            "после_того_как": ("child", "parent"),
            "до_того_как": ("parent", "child"),
            "перед_тем_как": ("parent", "child"),
        }
        result: list[SituationRelationCandidate] = []
        seen: set[tuple[str, str, str]] = set()

        # CAUSE is semantic, not merely lexical. Whenever frame composition has
        # already established parent.CAUSE -> child, emit the corresponding
        # canonical directed situation relation independently of which surface
        # connective (or ambiguity-resolution probe) produced that attachment.
        # This keeps the relation compiler general: child CAUSE parent.
        for parent in assertions:
            for actant in parent.actants:
                if actant.role != ActantRole.CAUSE or actant.candidate_ref is None:
                    continue
                source_id = actant.candidate_ref
                target_id = parent.local_id
                key = ("CAUSE", source_id, target_id)
                if key in seen or source_id == target_id:
                    continue
                seen.add(key)
                result.append(
                    SituationRelationCandidate(
                        relation_id="CAUSE",
                        source_ref=source_id,
                        target_ref=target_id,
                        evidence=self._relation_evidence_for_child(source_id, assertion_spans),
                    )
                )
        for clause in graph.clauses:
            direction = directions.get(clause.marker or "")
            if direction is None or clause.parent_clause_id is None:
                continue
            child_ids = clause_to_locals.get(clause.clause_id, [])
            parent_ids = clause_to_locals.get(clause.parent_clause_id, [])
            if not child_ids or not parent_ids:
                continue
            child_id = child_ids[0]
            parent_id = parent_ids[-1]
            source_id = child_id if direction[0] == "child" else parent_id
            target_id = parent_id if direction[1] == "parent" else child_id
            key = ("FOLLOW", source_id, target_id)
            if key in seen or source_id == target_id:
                continue
            seen.add(key)
            result.append(
                SituationRelationCandidate(
                    relation_id="FOLLOW",
                    source_ref=source_id,
                    target_ref=target_id,
                    evidence=(clause.connector_span.evidence if clause.connector_span is not None else None),
                )
            )

        # Sentence-initial sequencing adverbs such as "потом" are discourse
        # operators, not persistent TIME entities.  When they modify a later
        # situation, derive FOLLOW from source order and let the structural-actant
        # cleanup below remove the temporary TIME phrase.
        ordered_assertions = sorted(
            (item for item in assertions if assertion_spans.get(item.local_id) is not None),
            key=lambda item: assertion_spans[item.local_id].start_index,
        )
        for previous, current in zip(ordered_assertions, ordered_assertions[1:]):
            marker = next(
                (
                    actant for actant in current.actants
                    if actant.role == ActantRole.TIME
                    and (actant.lookup_text or "").casefold() in _DISCOURSE_FOLLOW_MARKERS
                ),
                None,
            )
            if marker is None:
                continue
            key = ("FOLLOW", previous.local_id, current.local_id)
            if key in seen:
                continue
            seen.add(key)
            result.append(
                SituationRelationCandidate(
                    relation_id="FOLLOW",
                    source_ref=previous.local_id,
                    target_ref=current.local_id,
                    evidence=marker.evidence,
                )
            )
        return tuple(result)

    @staticmethod
    def _strip_structural_relation_actants(
        assertions: list[AssertionCandidate],
        relations: tuple[SituationRelationCandidate, ...],
    ) -> list[AssertionCandidate]:
        """Do not encode one inter-situation relation twice as both N actant and L.

        CAUSE and directional temporal connectives are canonical structural
        relations between complete situations.  A CAUSE/TIME candidate_ref used
        only to discover that relation is removed once the corresponding L
        candidate exists.  Entity-valued CAUSE/TIME actants are untouched.
        """
        relation_pairs = {
            (rel.canonical_relation_id, rel.source_ref, rel.target_ref)
            for rel in relations
        }
        result: list[AssertionCandidate] = []
        for assertion in assertions:
            kept: list[ActantCandidate] = []
            for actant in assertion.actants:
                ref = actant.candidate_ref
                redundant = False
                if ref is not None and actant.role == ActantRole.CAUSE:
                    redundant = ("CAUSE", ref, assertion.local_id) in relation_pairs
                elif ref is not None and actant.role == ActantRole.TIME:
                    redundant = (
                        ("FOLLOW", ref, assertion.local_id) in relation_pairs
                        or ("FOLLOW", assertion.local_id, ref) in relation_pairs
                    )
                elif (
                    actant.role == ActantRole.TIME
                    and (actant.lookup_text or "").casefold() in _DISCOURSE_FOLLOW_MARKERS
                ):
                    redundant = any(
                        relation_id == "FOLLOW" and target_id == assertion.local_id
                        for relation_id, _source_id, target_id in relation_pairs
                    )
                if not redundant:
                    kept.append(actant)
            result.append(replace(assertion, actants=tuple(kept)))
        return result

    def _relation_evidence_for_child(
        self,
        child_id: str,
        assertion_spans: dict[str, _Span | None],
    ) -> EvidenceSpan | None:
        """Return the clause connective that licensed a nested situation relation."""
        graph = self._candidate_graph
        span = assertion_spans.get(child_id)
        if graph is None or span is None:
            return None
        clause = graph.clause_for_token(span.start_index)
        if clause is None or clause.connector_span is None:
            return None
        return clause.connector_span.evidence

    def _next_entity_ref(self) -> str:
        self._entity_ref_counter += 1
        return f"E{self._entity_ref_counter}"

    def _ensure_actant_entity_ref(
        self,
        by_id: dict[str, AssertionCandidate],
        assertion_id: str,
        actant: ActantCandidate,
        *,
        entity_ref: str | None = None,
    ) -> str | None:
        if actant.candidate_ref is not None or actant.composition is not None:
            return None
        ref_id = actant.entity_ref or entity_ref or self._next_entity_ref()
        if actant.entity_ref == ref_id:
            return ref_id
        assertion = by_id[assertion_id]
        replaced = False
        new_actants: list[ActantCandidate] = []
        for current in assertion.actants:
            if not replaced and current == actant:
                new_actants.append(replace(current, entity_ref=ref_id))
                replaced = True
            else:
                new_actants.append(current)
        if not replaced:
            return None
        by_id[assertion_id] = replace(assertion, actants=tuple(new_actants))
        return ref_id

    def _materialize_nominal_with_assertions(
        self,
        assertions: list[AssertionCandidate],
        assertion_spans: dict[str, _Span | None],
    ) -> tuple[list[AssertionCandidate], dict[str, _Span | None]]:
        """Compile an explicitly selected object-attached ``с + instrumental``.

        The lexical preposition is represented as an ordinary predicate realization
        rather than a new opaque L relation: ``WITH(SUBJECT=object, OBJECT=companion)``.
        Exact source evidence on the copied SUBJECT lets the existing turn-local
        identity binder reuse the same entity as the main assertion's OBJECT.
        """
        if not self._pending_nominal_with:
            return assertions, assertion_spans

        out = list(assertions)
        spans = dict(assertion_spans)
        for object_actant, pp_span in self._pending_nominal_with:
            local_id = f"A{len(out) + 1}"
            object_evidence = object_actant.evidence
            start = object_evidence.start if object_evidence is not None else pp_span.evidence.start
            end = pp_span.evidence.end
            evidence = None
            if start is not None and end is not None and self._candidate_graph is not None:
                evidence = EvidenceSpan(self._candidate_graph.text[start:end], start, end)

            subject = replace(
                object_actant,
                role=ActantRole.SUBJECT,
                candidate_ref=None,
                composition=None,
            )
            companion = self._make_actant(ActantRole.OBJECT, pp_span)
            prep_end = pp_span.evidence.start + 1 if pp_span.evidence.start is not None else None
            predicate_evidence = (
                EvidenceSpan("с", pp_span.evidence.start, prep_end)
                if pp_span.evidence.start is not None and prep_end is not None
                else None
            )
            out.append(
                AssertionCandidate(
                    local_id=local_id,
                    predicate=PredicateCandidate(
                        surface="с",
                        normalized_hint="с",
                        sense_hint="STRUCTURAL_OBJECT_ATTACHMENT",
                        evidence=predicate_evidence,
                    ),
                    actants=(subject, companion),
                    evidence=evidence,
                )
            )
            # This relation is semantically part of the same clause.  Reusing the
            # nearest source predicate span keeps conditional compilation able to
            # include it in the same branch when such a construction occurs there.
            owner_span = None
            if object_evidence is not None and object_evidence.start is not None:
                owner_span = next(
                    (
                        span
                        for item in assertions
                        if (span := assertion_spans.get(item.local_id)) is not None
                        and item.evidence is not None
                        and item.evidence.start is not None
                        and item.evidence.end is not None
                        and item.evidence.start <= object_evidence.start <= item.evidence.end
                    ),
                    None,
                )
            spans[local_id] = owner_span
        self._pending_nominal_with = []
        return out, spans

    def _attach_nested_assertions(
        self,
        assertions: list[AssertionCandidate],
        assertion_spans: dict[str, _Span | None],
    ) -> list[AssertionCandidate]:
        graph = self._candidate_graph
        if graph is None or len(assertions) < 2:
            return assertions
        clause_to_locals: dict[str, list[str]] = {}
        for local_id, span in assertion_spans.items():
            if span is None:
                continue
            clause = graph.clause_for_token(span.start_index)
            if clause is not None:
                clause_to_locals.setdefault(clause.clause_id, []).append(local_id)
        for values in clause_to_locals.values():
            values.sort(key=lambda lid: assertion_spans[lid].start_index if assertion_spans[lid] else 10**9)

        by_id = {item.local_id: item for item in assertions}

        # Resolve clause-local linguistic dependencies before frame nesting.
        # Relative pronouns bind an antecedent entity into the child frame, while
        # adverbial child clauses may inherit an omitted subject from their parent.
        self._resolve_relative_antecedents(by_id, clause_to_locals)
        self._bind_relative_matrix_subjects(by_id, clause_to_locals)
        self._inherit_omitted_clause_subjects(by_id, clause_to_locals)
        # Resolve the explicit source pronoun before copying it into a neighbouring
        # coordinated frame. Otherwise assigning a fresh id to the copied pronoun
        # would hide the stronger antecedent relation already available in context.
        self._resolve_pronoun_coreferences(by_id)
        self._inherit_coordinated_predicate_subjects(
            by_id, clause_to_locals, assertion_spans
        )
        # Repeated copies of the same source span must retain the identity that was
        # established above. Exact evidence-span identity is deterministic.
        self._bind_reused_source_mentions(by_id)
        # A resolved object pronoun immediately before a coordinator can license
        # object ellipsis in the following coordinated finite predicate.  This is
        # deliberately narrower than generic "copy the previous object" fallback.
        self._inherit_coordinated_object_ellipsis(
            by_id, clause_to_locals, assertion_spans
        )

        def attach(parent_id: str, child_id: str, role: ActantRole) -> bool:
            parent = by_id[parent_id]
            if parent_id == child_id or any(a.candidate_ref == child_id for a in parent.actants):
                return False
            if any(a.role == role for a in parent.actants):
                return False
            by_id[parent_id] = AssertionCandidate(
                local_id=parent.local_id,
                predicate=parent.predicate,
                actants=parent.actants + (ActantCandidate(role=role, candidate_ref=child_id),),
                evidence=parent.evidence,
                alternatives=parent.alternatives,
                negated=parent.negated,
            )
            return True

        def free_nested_object_slot(parent_id: str, child_id: str) -> bool:
            """Make room for a proven proposition-valued OBJECT, if justified.

            Ordinary accusative participants are kept deterministic OBJECT during
            surface extraction.  Only after the child has independently been
            classified as semantic content do we face a real role conflict.  At
            that point Python has narrowed the remaining question to one bounded
            semantic distinction: is the existing animate participant the
            addressee/receiver endpoint of that already-known content?

            This avoids asking the model to classify every animate accusative or
            pronoun before coreference/nesting are known, while still supporting
            constructions such as ``попросил Марию прочитать`` without lexical
            verb tables.
            """
            parent = by_id[parent_id]
            existing = [a for a in parent.actants if a.role == ActantRole.OBJECT]
            if not existing:
                return True
            if len(existing) != 1 or any(a.role == ActantRole.RECIPIENT for a in parent.actants):
                return False
            participant = existing[0]
            if participant.candidate_ref is not None or participant.composition is not None:
                return False
            if not self._plausible_recipient_participant(participant):
                return False

            child = by_id[child_id]
            source_text = self._candidate_graph.text if self._candidate_graph is not None else ""
            prompt = (
                f"TEXT:\n{source_text}\n"
                f"PARENT PREDICATE:\n{parent.predicate.surface}\n"
                f"PARTICIPANT:\n{participant.lookup_text or participant.mention or '?'}\n"
                f"KNOWN CONTENT:\n{child.predicate.surface}\n"
                "QUESTION:\nDoes the PARENT predicate direct the KNOWN CONTENT to PARTICIPANT "
                "as the person being asked, told, advised, instructed, or otherwise addressed?\n"
                "CHOICES:\nCONTENT_ADDRESSEE\nNOT_CONTENT_ADDRESSEE"
            )
            decision, _margin = self._fixed_choice_probe(
                "content_addressee", prompt, ("CONTENT_ADDRESSEE", "NOT_CONTENT_ADDRESSEE")
            )
            if decision != "CONTENT_ADDRESSEE":
                return False

            replaced_once = False
            rewritten: list[ActantCandidate] = []
            for actant in parent.actants:
                if not replaced_once and actant == participant:
                    rewritten.append(replace(actant, role=ActantRole.RECIPIENT))
                    replaced_once = True
                else:
                    rewritten.append(actant)
            if not replaced_once:
                return False
            by_id[parent_id] = replace(parent, actants=tuple(rewritten))
            return True

        role_map = {
            "OBJECT": ActantRole.OBJECT,
            "PURPOSE": ActantRole.PURPOSE,
            "CAUSE": ActantRole.CAUSE,
            "TIME": ActantRole.TIME,
            "LOCATION": ActantRole.LOCATION,
            "SOURCE": ActantRole.SOURCE,
        }

        # Cross-clause links. Stable markers are deterministic. Ambiguous markers
        # are resolved by one finite semantic classification. Low-margin evidence
        # is an explicit ambiguity/error: Perception must not silently drop a link.
        for clause in graph.clauses:
            if clause.parent_clause_id is None or clause.relative:
                continue
            children = clause_to_locals.get(clause.clause_id, [])
            parents = clause_to_locals.get(clause.parent_clause_id, [])
            if not children or not parents:
                continue
            child_id = children[0]
            parent_id = parents[-1]
            if clause.parent_role_hint is not None:
                role = role_map.get(clause.parent_role_hint)
                if role is not None:
                    attach(parent_id, child_id, role)
                continue
            allowed = (ActantRole.OBJECT,) if clause.marker == "что" else ()
            if not allowed:
                continue
            role = self._choose_frame_relation(by_id[parent_id], by_id[child_id], allowed)
            if role is not None:
                attach(parent_id, child_id, role)

        # Multiple predicates inside one clause are treated as separate frames.
        # Adjacent frames can be nested (verb + infinitive / gerund etc.). The model
        # only chooses from canonical relations that are still available.
        for clause_id, local_ids in clause_to_locals.items():
            if len(local_ids) < 2:
                continue
            for parent_id, child_id in zip(local_ids, local_ids[1:]):
                parent = by_id[parent_id]
                child = by_id[child_id]
                if any(a.candidate_ref == child_id for a in parent.actants):
                    continue
                if child.predicate.sense_hint == "STRUCTURAL_OBJECT_ATTACHMENT":
                    # An explicitly selected nominal attachment is a sibling lexical
                    # relation (e.g. ``с(Petr, binoculars)``), not proposition-valued
                    # content of the preceding verb.  Never run frame-relation probes
                    # over this deterministic clarification result.
                    continue
                parent_span = assertion_spans.get(parent_id)
                child_span = assertion_spans.get(child_id)
                if (
                    parent.predicate.lookup_form == child.predicate.lookup_form
                    and parent.predicate.evidence is not None
                    and child.predicate.evidence is not None
                    and parent.predicate.evidence.start == child.predicate.evidence.start
                    and parent.predicate.evidence.end == child.predicate.evidence.end
                ):
                    # One source predicate can expand into several proposition
                    # variants (for example contrastive negation). They are siblings,
                    # never nested situations.
                    continue
                if self._frames_are_coordinated_or_separated(parent_span, child_span):
                    continue
                # Proposition-valued OBJECT is allowed to compete even when the
                # surface frame currently contains one entity-valued OBJECT.  A
                # positive CONTENT decision then triggers the much narrower
                # participant-role reconciliation above.  Other occupied roles stay
                # unavailable as before.
                available_list: list[ActantRole] = []
                for role in (ActantRole.OBJECT, ActantRole.PURPOSE, ActantRole.CAUSE, ActantRole.HOW_TO):
                    occupied = [a for a in parent.actants if a.role == role]
                    if not occupied or (
                        role == ActantRole.OBJECT
                        and len(occupied) == 1
                        and occupied[0].candidate_ref is None
                        and occupied[0].composition is None
                    ):
                        available_list.append(role)
                available = tuple(available_list)
                if not available:
                    continue
                role = self._choose_frame_relation(parent, child, available, allow_none=True)
                if role == ActantRole.OBJECT and any(a.role == ActantRole.OBJECT for a in by_id[parent_id].actants):
                    if free_nested_object_slot(parent_id, child_id):
                        parent = by_id[parent_id]
                    else:
                        # CONTENT_LINK is already a positive semantic decision. A
                        # failure to reconcile the occupied entity-valued OBJECT
                        # does not license reclassifying the same child as PURPOSE
                        # (or another relation). That would let a downstream role
                        # probe overwrite an earlier semantic result. Keep the
                        # architecture fail-closed instead: preserve the proven
                        # content hypothesis and reject an unresolved canonical
                        # role conflict.
                        raise AdaptiveParseError(
                            "unresolved OBJECT-content participant role conflict between "
                            f"{by_id[parent_id].predicate.lookup_form!r} and "
                            f"{child.predicate.lookup_form!r}",
                            tuple(self._traces),
                        )
                if role is not None:
                    attach(parent_id, child_id, role)

        self._resolve_control_subjects(by_id, assertion_spans)
        return [by_id[item.local_id] for item in assertions]

    def _plausible_recipient_participant(self, actant: ActantCandidate) -> bool:
        """Conservatively gate post-structural OBJECT→RECIPIENT repair.

        This is not hidden valency discovery.  The participant is already explicit
        in the sentence and a proposition-valued OBJECT has already been established.
        Morphology only answers whether the explicit participant is a plausible
        addressee/receiver candidate before the LLM gets the final binary choice.
        """
        # Morphology must inspect the actual source form (e.g. ``его``), not a
        # normalized pronoun lemma such as ``он`` that may not preserve case and
        # may not even be present in a lightweight morphology fixture.
        text = (actant.mention or actant.lookup_text or "").strip()
        if not text:
            return False
        token = text.split()[-1]
        try:
            analyses = tuple(self.morphology.analyze_all(token))
        except AttributeError:
            one = self.morphology.analyze(token)
            analyses = () if one is None else (one,)
        material = tuple(material_analyses(analyses))
        if any(item.pos == "NPRO" for item in material):
            return True
        if any(item.animacy == "anim" for item in material):
            return True
        explicit_animacy = {item.animacy for item in material if item.animacy is not None}
        if explicit_animacy and explicit_animacy <= {"inan"}:
            return False
        # Proper-name orthography is only a conservative fallback for lightweight
        # morphologies that omit animacy; it does not by itself canonicalize role.
        return bool(token[:1].isupper())

    def _resolve_control_subjects(
        self,
        by_id: dict[str, AssertionCandidate],
        assertion_spans: dict[str, _Span | None],
    ) -> None:
        """Resolve omitted subjects of nested non-finite situations.

        Frame nesting already determines which child situation belongs to which
        parent.  Controller identity is a separate local decision.  Python narrows
        candidates to participant mentions that occur before the child predicate;
        one candidate is deterministic, several are presented to the weak model as
        one finite choice.  No lexical verb table or sentence-specific rule is used.
        """
        for parent_id, parent in tuple(by_id.items()):
            child_refs = [
                (actant.candidate_ref, actant.role)
                for actant in parent.actants
                if actant.candidate_ref is not None
                and actant.role in {
                    ActantRole.OBJECT, ActantRole.PURPOSE,
                    ActantRole.CAUSE, ActantRole.HOW_TO,
                }
            ]
            for child_id, child_relation_role in child_refs:
                if child_id is None or child_id not in by_id:
                    continue
                child = by_id[child_id]
                if any(a.role == ActantRole.SUBJECT for a in child.actants):
                    continue
                child_span = assertion_spans.get(child_id)
                if child_span is None:
                    continue
                controllers: list[ActantCandidate] = []
                for actant in parent.actants:
                    if (
                        actant.candidate_ref is not None
                        or actant.composition is not None
                        or actant.role not in {
                            ActantRole.SUBJECT, ActantRole.OBJECT,
                            ActantRole.RECIPIENT, ActantRole.AUXILLIARY,
                        }
                        or actant.evidence is None
                        or actant.evidence.start >= child_span.evidence.start
                    ):
                        continue
                    controllers.append(actant)
                # Deduplicate copied/source-identical mentions.
                unique: dict[tuple[object, ...], ActantCandidate] = {}
                for item in controllers:
                    if item.entity_ref:
                        key = ("entity", item.entity_ref)
                    elif item.evidence:
                        key = ("span", item.evidence.start, item.evidence.end)
                    else:
                        key = ("text", item.lookup_text)
                    unique.setdefault(key, item)
                controllers = list(unique.values())
                if not controllers:
                    continue
                chosen: ActantCandidate | None
                if len(controllers) == 1:
                    chosen = controllers[0]
                    self._deterministic_trace(
                        "control_subject",
                        f"PARENT:\n{parent.predicate.surface}\nCHILD:\n{child.predicate.surface}",
                        chosen.lookup_text or "",
                    )
                else:
                    def display_controller(item: ActantCandidate) -> str:
                        surface = item.lookup_text or item.mention or "participant"
                        if item.entity_ref is None:
                            return surface
                        anchors: list[tuple[int, str]] = []
                        for other_assertion in by_id.values():
                            for other in other_assertion.actants:
                                if (
                                    other.entity_ref != item.entity_ref
                                    or other.candidate_ref is not None
                                    or other.composition is not None
                                    or not (other.mention or other.normalized_hint)
                                ):
                                    continue
                                label = other.lookup_text or other.mention or ""
                                if not label:
                                    continue
                                try:
                                    morph = self.morphology.analyze_all(label.split()[-1])
                                except AttributeError:
                                    one = self.morphology.analyze(label.split()[-1])
                                    morph = () if one is None else (one,)
                                pronoun = any(x.pos == "NPRO" for x in morph)
                                position = other.evidence.start if other.evidence is not None else 10**9
                                anchors.append((position + (10**8 if pronoun else 0), label))
                        if not anchors:
                            return surface
                        anchor = min(anchors, key=lambda pair: pair[0])[1]
                        if anchor.casefold() == surface.casefold():
                            return surface
                        return f"{anchor} (surface here: {surface})"

                    parent_roles = [
                        f"{a.role.value} = {display_controller(a)}"
                        for a in parent.actants
                        if a.candidate_ref is None and a.composition is None
                    ]
                    child_roles = [
                        f"{a.role.value} = {a.lookup_text or a.mention or '?'}"
                        for a in child.actants
                        if a.candidate_ref is None and a.composition is None
                    ]
                    source_text = self._candidate_graph.text if self._candidate_graph is not None else ""
                    if len(controllers) > len(_ORDINAL_LABELS):
                        controllers = controllers[:len(_ORDINAL_LABELS)]
                    labels = _ORDINAL_LABELS[:len(controllers)]
                    participants = "\n".join(
                        f"{label} = {display_controller(candidate)}"
                        for label, candidate in zip(labels, controllers)
                    )
                    choices = "\n".join(labels)
                    prompt = (
                        f"TEXT:\n{source_text}\n"
                        f"PARENT PREDICATE:\n{parent.predicate.surface}\n"
                        "PARENT KNOWN ROLES:\n" + ("\n".join(parent_roles) or "none") + "\n"
                        f"CHILD PREDICATE:\n{child.predicate.surface}\n"
                        "CHILD KNOWN ROLES:\n" + ("\n".join(child_roles) or "none") + "\n"
                        f"PARTICIPANTS:\n{participants}\n"
                        f"CHOICES:\n{choices}\n"
                        "QUESTION:\nWhich participant performs the CHILD predicate in this text?"
                    )
                    decision, _margin = self._fixed_choice_probe(
                        "control_subject", prompt, tuple(labels)
                    )
                    chosen = None if decision is None else controllers[labels.index(decision)]
                if chosen is None:
                    # LLM abstention is not permission to emit a silently incomplete
                    # child frame.  Perception preserves each structurally valid
                    # controller as a runtime alternative; deterministic Integration
                    # later resolves those local readings to canonical m/k.
                    current_child = by_id[child_id]
                    variants: list[AssertionCandidate] = []
                    for controller in controllers:
                        entity_ref = controller.entity_ref or self._ensure_actant_entity_ref(
                            by_id, parent_id, controller
                        )
                        if entity_ref is None:
                            continue
                        copied = ActantCandidate(
                            role=ActantRole.SUBJECT,
                            mention=controller.mention,
                            normalized_hint=controller.normalized_hint,
                            semantic_hint=controller.semantic_hint,
                            entity_ref=entity_ref,
                            evidence=controller.evidence,
                        )
                        for base in current_child.alternatives or (replace(current_child, alternatives=()),):
                            if any(a.role == ActantRole.SUBJECT for a in base.actants):
                                continue
                            variants.append(
                                replace(base, actants=base.actants + (copied,), alternatives=())
                            )
                    if variants:
                        by_id[child_id] = replace(current_child, alternatives=tuple(variants))
                        self._deterministic_trace(
                            "control_subject_alternatives",
                            f"PARENT:\n{parent.predicate.surface}\nCHILD:\n{child.predicate.surface}",
                            str(len(variants)),
                        )
                    continue
                entity_ref = chosen.entity_ref or self._ensure_actant_entity_ref(
                    by_id, parent_id, chosen
                )
                current_child = by_id[child_id]
                copied = ActantCandidate(
                    role=ActantRole.SUBJECT,
                    mention=chosen.mention,
                    normalized_hint=chosen.normalized_hint,
                    semantic_hint=chosen.semantic_hint,
                    entity_ref=entity_ref,
                    evidence=chosen.evidence,
                )
                by_id[child_id] = replace(
                    current_child, actants=current_child.actants + (copied,)
                )

    def _resolve_relative_antecedents(
        self,
        by_id: dict[str, AssertionCandidate],
        clause_to_locals: dict[str, list[str]],
    ) -> None:
        graph = self._candidate_graph
        if graph is None:
            return
        tokens = self._source_tokens(graph.text)
        clauses = {item.clause_id: item for item in graph.clauses}

        for clause in graph.clauses:
            if not clause.relative or clause.parent_clause_id is None:
                continue
            child_ids = clause_to_locals.get(clause.clause_id, [])
            parent_clause = clauses.get(clause.parent_clause_id)
            if not child_ids or parent_clause is None or clause.connector_span is None:
                continue
            parent_ids = clause_to_locals.get(parent_clause.clause_id, [])
            antecedent = self._nearest_antecedent_span(
                graph.text, tokens, parent_clause.span.start_index, parent_clause.span.end_index
            )
            if antecedent is None:
                continue

            # Reuse the already-recognized parent entity.  A parent semantic
            # actant may include a relational marker around the noun (for example
            # ``рядом с журналом``), while the relative antecedent span contains
            # only the noun (``журналом``).  Exact span equality is therefore too
            # strong.  Prefer exact evidence; otherwise accept only a containing
            # parent actant whose normalized semantic head matches the antecedent.
            antecedent_entity_ref: str | None = None
            antecedent_normalized = self._semantic_actant_text(antecedent)[1].casefold()
            matches: list[tuple[int, int, str, ActantCandidate]] = []
            for parent_rank, parent_id in enumerate(reversed(parent_ids)):
                parent = by_id[parent_id]
                for parent_actant in parent.actants:
                    if parent_actant.candidate_ref is not None or parent_actant.composition is not None:
                        continue
                    evidence = parent_actant.evidence
                    if evidence is None:
                        continue
                    exact = (
                        evidence.start == antecedent.evidence.start
                        and evidence.end == antecedent.evidence.end
                    )
                    contains = (
                        evidence.start <= antecedent.evidence.start
                        and evidence.end >= antecedent.evidence.end
                    )
                    if not contains:
                        continue
                    normalized = (parent_actant.lookup_text or "").strip().casefold()
                    if not exact and normalized != antecedent_normalized:
                        continue
                    width = evidence.end - evidence.start
                    matches.append((0 if exact else 1, width, parent_rank, parent_id, parent_actant))

            if matches:
                matches.sort(key=lambda item: (item[0], item[1], item[2]))
                best = matches[0]
                # Equal best candidates would make identity attachment ambiguous;
                # do not silently merge them. A fresh local ref keeps the reading
                # non-canonical until later resolution instead.
                equally_best = [m for m in matches if m[:3] == best[:3]]
                if len(equally_best) == 1:
                    antecedent_entity_ref = self._ensure_actant_entity_ref(
                        by_id, best[3], best[4]
                    )

            if antecedent_entity_ref is None:
                antecedent_entity_ref = self._next_entity_ref()

            relative_index = clause.connector_span.start_index
            relative_span = self._resolve_span(graph.text, tokens, relative_index, relative_index)

            for child_id in child_ids:
                child = by_id[child_id]
                occupied = {item.role for item in child.actants}
                role = self._deterministic_relative_role(tokens, relative_index, occupied)
                if role is None:
                    role = self._choose_relative_role(
                        graph.text, child, relative_span, antecedent, occupied
                    )
                if role is None or role in occupied:
                    continue
                by_id[child_id] = replace(
                    child,
                    actants=child.actants + (
                        ActantCandidate(
                            role=role,
                            mention=antecedent.text,
                            normalized_hint=self._semantic_actant_text(antecedent)[1],
                            entity_ref=antecedent_entity_ref,
                            evidence=antecedent.evidence,
                        ),
                    ),
                )
                self._deterministic_trace(
                    "relative_coreference",
                    f"RELATIVE:\n{relative_span.text}\nANTECEDENT:\n{antecedent.text}\nPREDICATE:\n{child.predicate.surface}",
                    f"{role.value}:{antecedent.text}",
                )

    def _bind_relative_matrix_subjects(
        self,
        by_id: dict[str, AssertionCandidate],
        clause_to_locals: dict[str, list[str]],
    ) -> None:
        """Bind a head noun to the matrix predicate after its relative clause.

        Russian noun-relative constructions often split into three deterministic
        clause fragments: antecedent NP, relative clause, then matrix predicate.
        The relative child already carries the antecedent identity.  Reuse that
        identity as SUBJECT of the first subjectless matrix frame following the
        relative clause instead of inheriting the relative clause's own subject.
        """
        graph = self._candidate_graph
        if graph is None:
            return
        clauses = list(graph.clauses)
        for idx, clause in enumerate(clauses):
            if not clause.relative or clause.parent_clause_id is None:
                continue
            child_ids = clause_to_locals.get(clause.clause_id, [])
            if not child_ids:
                continue
            parent_clause = next(
                (item for item in clauses if item.clause_id == clause.parent_clause_id),
                None,
            )
            if parent_clause is None:
                continue
            antecedent = self._nearest_antecedent_span(
                graph.text, self._source_tokens(graph.text),
                parent_clause.span.start_index, parent_clause.span.end_index,
            )
            if antecedent is None:
                continue
            antecedent_ref = None
            for child_id in child_ids:
                for actant in by_id[child_id].actants:
                    if (
                        actant.entity_ref is not None
                        and actant.evidence is not None
                        and actant.evidence.start == antecedent.evidence.start
                        and actant.evidence.end == antecedent.evidence.end
                    ):
                        antecedent_ref = actant.entity_ref
                        break
                if antecedent_ref is not None:
                    break
            if antecedent_ref is None:
                continue
            matrix_clause = next(
                (item for item in clauses[idx + 1:]
                 if item.sentence_id == clause.sentence_id
                 and not item.relative
                 and item.parent_clause_id is None
                 and clause_to_locals.get(item.clause_id)),
                None,
            )
            if matrix_clause is None:
                continue
            matrix_id = clause_to_locals[matrix_clause.clause_id][0]
            matrix = by_id[matrix_id]
            if any(a.role == ActantRole.SUBJECT for a in matrix.actants):
                continue
            copied = ActantCandidate(
                role=ActantRole.SUBJECT,
                mention=antecedent.text,
                normalized_hint=self._semantic_actant_text(antecedent)[1],
                entity_ref=antecedent_ref,
                evidence=antecedent.evidence,
            )
            by_id[matrix_id] = replace(matrix, actants=matrix.actants + (copied,))
            self._deterministic_trace(
                "relative_matrix_subject",
                f"ANTECEDENT:\n{antecedent.text}\nMATRIX PREDICATE:\n{matrix.predicate.surface}",
                copied.lookup_text or "",
            )

    def _nearest_antecedent_span(
        self,
        text: str,
        tokens: tuple[_SourceToken, ...],
        start: int,
        end: int,
    ) -> _Span | None:
        for index in range(end, start - 1, -1):
            token = tokens[index - 1]
            if not self._has_morph(token, poses={"NOUN", "NPRO"}):
                continue
            left = index
            cursor = index - 1
            while cursor >= start and self._has_morph(tokens[cursor - 1], poses={"ADJF", "PRTF", "NUMR"}):
                left = cursor
                cursor -= 1
            return self._resolve_span(text, tokens, left, index)
        return None

    def _deterministic_relative_role(
        self,
        tokens: tuple[_SourceToken, ...],
        relative_index: int,
        occupied: set[ActantRole],
    ) -> ActantRole | None:
        token = tokens[relative_index - 1]
        candidates: set[ActantRole] = set()
        for info in self._material_morph_analyses(token):
            if info.case == "nomn":
                candidates.add(ActantRole.SUBJECT)
            elif info.case in {"accs", "gen2"}:
                candidates.add(ActantRole.OBJECT)
            elif info.case == "gent":
                candidates.add(ActantRole.OBJECT)
            elif info.case == "datv":
                candidates.add(ActantRole.RECIPIENT)
            elif info.case == "loct":
                candidates.add(ActantRole.LOCATION)
            elif info.case == "ablt":
                candidates.add(ActantRole.TOOL)
        candidates.difference_update(occupied)
        if len(candidates) == 1:
            return next(iter(candidates))
        return None

    def _choose_relative_role(
        self,
        text: str,
        child: AssertionCandidate,
        relative_span: _Span,
        antecedent: _Span,
        occupied: set[ActantRole],
    ) -> ActantRole | None:
        descriptions = {
            ActantRole.SUBJECT: "antecedent is the main entity that acts or is described",
            ActantRole.OBJECT: "antecedent is the entity or content directly acted on or referred to",
            ActantRole.RECIPIENT: "antecedent is the receiver, beneficiary, or destination participant",
            ActantRole.SOURCE: "antecedent is the origin from whom or from where something comes",
            ActantRole.LOCATION: "antecedent is the place or spatial position",
            ActantRole.TOOL: "antecedent is the instrument or tool used",
        }
        allowed = [role for role in descriptions if role not in occupied]
        if not allowed:
            return None
        numeric_choices: dict[int, ActantRole | None] = {0: None}
        label_choices: dict[str, ActantRole | None] = {"NONE": None}
        option_lines = ["NONE: cannot determine the relation reliably"]
        for number, role in enumerate(allowed, start=1):
            numeric_choices[number] = role
            label = self._template_role_label(role)
            label_choices[label] = role
            option_lines.append(f"{label}: {descriptions[role]}")
        prompt = (
            f"TEXT:\n{text}\nRELATIVE_WORD:\n{relative_span.text}\n"
            f"ANTECEDENT:\n{antecedent.text}\nPREDICATE:\n{child.predicate.surface}\n"
            "OPTIONS:\n" + "\n".join(option_lines)
        )
        return self._probe(
            "relative_role", prompt,
            lambda raw: self._label_or_number_choice(raw, label_choices, numeric_choices),
            max_new_tokens=3,
            choice_outputs=tuple(label_choices),
        )

    def _inherit_coordinated_predicate_subjects(
        self,
        by_id: dict[str, AssertionCandidate],
        clause_to_locals: dict[str, list[str]],
        assertion_spans: dict[str, _Span | None],
    ) -> None:
        """Share an established subject across coordinated finite predicates.

        Predicate-local argument windows intentionally exclude the surface region
        owned by a neighbouring predicate.  Therefore a later coordinated frame
        must receive the common subject from the preceding frame, not rediscover it
        by scanning the whole clause.  The transfer is licensed only by an explicit
        coordinating conjunction between two finite predicate heads in one clause.
        """
        graph = self._candidate_graph
        if graph is None:
            return
        finite_heads = {item.token_index for item in graph.predicates if item.finite}
        coordinators = {"и", "да", "или", "либо"}

        for local_ids in clause_to_locals.values():
            if len(local_ids) < 2:
                continue
            for left_id, right_id in zip(local_ids, local_ids[1:]):
                left_span = assertion_spans.get(left_id)
                right_span = assertion_spans.get(right_id)
                if left_span is None or right_span is None:
                    continue
                left_clause = graph.clause_for_token(left_span.start_index)
                right_clause = graph.clause_for_token(right_span.start_index)
                if (
                    left_clause is None
                    or right_clause is None
                    or left_clause.clause_id != right_clause.clause_id
                    or left_span.start_index not in finite_heads
                    or right_span.start_index not in finite_heads
                ):
                    continue

                between = [
                    token for token in graph.tokens
                    if left_span.end_index < token.index < right_span.start_index
                ]
                coordinator_positions = [
                    token.index for token in between
                    if token.text.casefold() in coordinators
                ]
                if not coordinator_positions:
                    continue
                coordinator_index = coordinator_positions[-1]

                # An explicit nominative after the coordinator starts a new subject
                # domain even if morphology/clause preprocessing did not split it.
                if any(
                    token.has_case("nomn", poses={"NOUN", "NPRO"})
                    for token in graph.tokens
                    if coordinator_index < token.index < right_span.start_index
                ):
                    continue

                right = by_id[right_id]
                if any(item.role == ActantRole.SUBJECT for item in right.actants):
                    continue
                left_subjects = [
                    item for item in by_id[left_id].actants
                    if item.role == ActantRole.SUBJECT and item.candidate_ref is None
                ]
                if len(left_subjects) != 1:
                    continue

                source = left_subjects[0]
                if source.composition is None and source.entity_ref is None:
                    self._ensure_actant_entity_ref(by_id, left_id, source)
                    source = next(
                        item for item in by_id[left_id].actants
                        if item.role == ActantRole.SUBJECT
                    )

                by_id[right_id] = replace(right, actants=right.actants + (source,))
                self._deterministic_trace(
                    "coordinated_subject_inheritance",
                    f"SUBJECT:\n{source.lookup_text}\nLEFT PREDICATE:\n"
                    f"{by_id[left_id].predicate.surface}\nRIGHT PREDICATE:\n"
                    f"{right.predicate.surface}",
                    source.lookup_text or "",
                )

    def _inherit_coordinated_object_ellipsis(
        self,
        by_id: dict[str, AssertionCandidate],
        clause_to_locals: dict[str, list[str]],
        assertion_spans: dict[str, _Span | None],
    ) -> None:
        """Carry a resolved pronominal object into the next coordinated frame.

        The licensed surface pattern is intentionally strict: two adjacent finite
        predicates in one clause, a shared established subject, an explicit
        pronominal OBJECT after the left predicate, and a coordinator between that
        object and the right predicate.  This covers discourse ellipsis such as
        ``открыла её и прочитала`` without turning every intransitive coordinated
        verb into a transitive one.
        """
        graph = self._candidate_graph
        if graph is None:
            return
        finite_heads = {item.token_index for item in graph.predicates if item.finite}
        coordinators = {"и", "да"}

        def subject_key(actant: ActantCandidate) -> tuple[object, ...]:
            if actant.entity_ref is not None:
                return ("entity", actant.entity_ref)
            if actant.composition is not None:
                return ("composition", repr(actant.composition))
            if actant.evidence is not None:
                return ("span", actant.evidence.start, actant.evidence.end)
            return ("text", (actant.normalized_hint or actant.mention or "").casefold())

        def is_resolved_pronoun(actant: ActantCandidate) -> bool:
            if actant.entity_ref is None or actant.evidence is None:
                return False
            value = actant.mention or actant.normalized_hint
            if not value:
                return False
            words = re.findall(r"[\w-]+", value, flags=re.UNICODE)
            if not words:
                return False
            try:
                analyses = self.morphology.analyze_all(words[-1])
            except AttributeError:
                item = self.morphology.analyze(words[-1])
                analyses = () if item is None else (item,)
            return any(
                item.pos == "NPRO"
                and item.normal_form.casefold() in {"он", "она", "оно", "они"}
                for item in analyses
            )

        for local_ids in clause_to_locals.values():
            if len(local_ids) < 2:
                continue
            for left_id, right_id in zip(local_ids, local_ids[1:]):
                left_span = assertion_spans.get(left_id)
                right_span = assertion_spans.get(right_id)
                if left_span is None or right_span is None:
                    continue
                left_clause = graph.clause_for_token(left_span.start_index)
                right_clause = graph.clause_for_token(right_span.start_index)
                if (
                    left_clause is None
                    or right_clause is None
                    or left_clause.clause_id != right_clause.clause_id
                    or left_span.start_index not in finite_heads
                    or right_span.start_index not in finite_heads
                ):
                    continue

                left = by_id[left_id]
                right = by_id[right_id]
                if any(a.role == ActantRole.OBJECT for a in right.actants):
                    continue
                left_subjects = [a for a in left.actants if a.role == ActantRole.SUBJECT]
                right_subjects = [a for a in right.actants if a.role == ActantRole.SUBJECT]
                if len(left_subjects) != 1 or len(right_subjects) != 1:
                    continue
                if subject_key(left_subjects[0]) != subject_key(right_subjects[0]):
                    continue

                left_objects = [
                    a for a in left.actants
                    if a.role == ActantRole.OBJECT
                    and a.candidate_ref is None
                    and a.composition is None
                ]
                if len(left_objects) != 1:
                    continue
                source = left_objects[0]
                if not is_resolved_pronoun(source):
                    continue
                if source.evidence is None or source.evidence.start < left_span.evidence.end:
                    continue

                between = [
                    token for token in graph.tokens
                    if source.evidence.end <= token.start < right_span.evidence.start
                ]
                if not any(token.text.casefold() in coordinators for token in between):
                    continue

                copied = ActantCandidate(
                    role=ActantRole.OBJECT,
                    mention=source.mention,
                    normalized_hint=source.normalized_hint,
                    semantic_hint=source.semantic_hint,
                    entity_ref=source.entity_ref,
                    evidence=None,
                )
                by_id[right_id] = replace(
                    right, actants=right.actants + (copied,)
                )
                self._deterministic_trace(
                    "coordinated_object_ellipsis",
                    f"LEFT PREDICATE:\n{left.predicate.surface}\n"
                    f"RIGHT PREDICATE:\n{right.predicate.surface}\n"
                    f"RESOLVED OBJECT:\n{source.lookup_text}",
                    source.entity_ref or source.lookup_text or "OBJECT",
                )

    def _inherit_omitted_clause_subjects(
        self,
        by_id: dict[str, AssertionCandidate],
        clause_to_locals: dict[str, list[str]],
    ) -> None:
        graph = self._candidate_graph
        if graph is None:
            return

        def is_nonfinite_frame(local_id: str) -> bool:
            predicate_evidence = by_id[local_id].predicate.evidence
            if predicate_evidence is None:
                return False
            token = next(
                (item for item in graph.tokens if item.start == predicate_evidence.start),
                None,
            )
            if token is None:
                return False
            head = next(
                (item for item in graph.predicates if item.token_index == token.index),
                None,
            )
            return head is not None and not head.finite

        def inherit(
            parent_ids: list[str],
            child_ids: list[str],
            *,
            all_children: bool,
            stage: str,
        ) -> None:
            if not parent_ids or not child_ids:
                return
            parent_subjects: list[tuple[str, ActantCandidate]] = []
            for parent_id in parent_ids:
                parent_subjects.extend(
                    (parent_id, actant)
                    for actant in by_id[parent_id].actants
                    if actant.role == ActantRole.SUBJECT
                    and (actant.mention or actant.normalized_hint)
                )
            signatures = {
                (actant.normalized_hint or actant.mention or "").casefold()
                for _, actant in parent_subjects
            }
            if len(signatures) != 1 or not parent_subjects:
                return
            if all_children:
                targets = [
                    child_id for child_id in child_ids
                    if not is_nonfinite_frame(child_id)
                    and not any(
                        actant.role == ActantRole.SUBJECT
                        for actant in by_id[child_id].actants
                    )
                ]
            else:
                first_child = child_ids[0]
                if is_nonfinite_frame(first_child) or any(
                    actant.role == ActantRole.SUBJECT
                    for actant in by_id[first_child].actants
                ):
                    return
                targets = [first_child]
            if not targets:
                return

            inherited_parent_id, inherited = parent_subjects[-1]
            entity_ref = self._ensure_actant_entity_ref(
                by_id, inherited_parent_id, inherited
            )
            inherited = next(
                actant for actant in by_id[inherited_parent_id].actants
                if actant.role == ActantRole.SUBJECT
                and (actant.normalized_hint or actant.mention or "").casefold() in signatures
            )
            for child_id in targets:
                child = by_id[child_id]
                copied = ActantCandidate(
                    role=ActantRole.SUBJECT,
                    mention=inherited.mention,
                    normalized_hint=inherited.normalized_hint,
                    semantic_hint=inherited.semantic_hint,
                    entity_ref=entity_ref,
                    evidence=inherited.evidence,
                )
                by_id[child_id] = replace(child, actants=child.actants + (copied,))
                self._deterministic_trace(
                    stage,
                    f"PARENT SUBJECT:\n{copied.lookup_text}\nCHILD PREDICATE:\n{child.predicate.surface}",
                    copied.lookup_text or "",
                )

        # Explicit adverbial/control relations have a structurally identified
        # parent clause, so every subjectless frame in that child can inherit the
        # unique parent subject.
        inheritable = {"TIME", "CAUSE", "PURPOSE", "CONDITION"}
        for clause in graph.clauses:
            if (
                clause.relative
                or clause.parent_clause_id is None
                or clause.parent_role_hint not in inheritable
            ):
                continue
            inherit(
                clause_to_locals.get(clause.parent_clause_id, []),
                clause_to_locals.get(clause.clause_id, []),
                all_children=True,
                stage="subject_inheritance",
            )

        # Russian serial predicates are often separated by a comma with the
        # subject written only once: "Лиза взяла книгу, открыла её и прочитала".
        # This is not a generic "previous subject" heuristic.  It is licensed only
        # for adjacent clauses in one sentence separated by comma punctuation, with
        # no subordinate/relative connector and no explicit subject in the next
        # frame.  The first inherited frame can then feed ordinary coordinated
        # predicate inheritance inside its own clause.
        for left, right in zip(graph.clauses, graph.clauses[1:]):
            if left.sentence_id != right.sentence_id:
                continue
            if (
                left.relative
                or left.parent_clause_id is not None
                or right.relative
                or right.connector_span is not None
                or right.parent_clause_id is not None
            ):
                continue
            between = [
                token.text
                for token in graph.tokens
                if left.span.end_index < token.index < right.span.start_index
            ]
            if "," not in between or any(mark in _STRONG_BOUNDARY for mark in between):
                continue
            inherit(
                clause_to_locals.get(left.clause_id, []),
                clause_to_locals.get(right.clause_id, []),
                all_children=False,
                stage="paratactic_subject_inheritance",
            )


    def _bind_reused_source_mentions(
        self,
        by_id: dict[str, AssertionCandidate],
    ) -> None:
        """Give actants that reuse one exact source occurrence one entity id.

        Coordinated predicates often share a surface subject only once in the
        sentence. The parser intentionally copies that actant into each semantic
        frame. Those copies must denote one entity, not merely equal strings.
        Exact evidence-span identity is stronger than text equality and therefore
        safe to resolve deterministically.
        """
        groups: dict[tuple[int, int], list[tuple[str, ActantCandidate]]] = {}
        for assertion_id, assertion in by_id.items():
            for actant in assertion.actants:
                if (
                    actant.candidate_ref is not None
                    or actant.composition is not None
                    or actant.evidence is None
                    or not (actant.mention or actant.normalized_hint)
                ):
                    continue
                key = (actant.evidence.start, actant.evidence.end)
                groups.setdefault(key, []).append((assertion_id, actant))

        for (start, end), members in groups.items():
            if len(members) < 2:
                continue
            existing = [actant.entity_ref for _aid, actant in members if actant.entity_ref]
            # Conflicting refs for one exact source occurrence are an internal
            # semantic inconsistency. Never continue with two established identities
            # for the same evidence span.
            if len(set(existing)) > 1:
                raise AdaptiveParseError(
                    f"conflicting entity refs for source span {start}:{end}"
                )
            entity_ref = existing[0] if existing else self._next_entity_ref()
            changed = False
            for assertion_id, original in members:
                if original.entity_ref == entity_ref:
                    continue
                current = by_id[assertion_id]
                new_actants: list[ActantCandidate] = []
                replaced = False
                for actant in current.actants:
                    if not replaced and actant == original:
                        new_actants.append(replace(actant, entity_ref=entity_ref))
                        replaced = True
                    else:
                        new_actants.append(actant)
                if replaced:
                    by_id[assertion_id] = replace(current, actants=tuple(new_actants))
                    changed = True
            if changed:
                self._deterministic_trace(
                    "source_coreference",
                    f"SOURCE_SPAN:\n{start}:{end}",
                    entity_ref,
                )

    def _resolve_pronoun_coreferences(
        self,
        by_id: dict[str, AssertionCandidate],
    ) -> None:
        """Resolve unique local pronoun bindings or preserve runtime alternatives.

        Morphology/syntax may bind a unique turn-local entity_ref. When several
        structurally compatible antecedents remain, Perception emits complete local
        AssertionCandidate alternatives and never asks the LLM to choose a canonical
        entity. Canonical collapse or k_AMBIGUOUS creation belongs to Integration.
        """
        third_person_lemmas = {"он", "она", "оно", "они"}

        def morphs(value: str | None) -> tuple[MorphInfo, ...]:
            if not value:
                return ()
            words = re.findall(r"[\w-]+", value, flags=re.UNICODE)
            if not words:
                return ()
            word = words[-1]
            try:
                return tuple(self.morphology.analyze_all(word))
            except AttributeError:
                item = self.morphology.analyze(word)
                return () if item is None else (item,)

        def pronoun_infos(value: str | None) -> tuple[MorphInfo, ...]:
            return tuple(
                info for info in morphs(value)
                if info.pos == "NPRO" and info.normal_form.casefold() in third_person_lemmas
            )

        def compatible(pronoun: tuple[MorphInfo, ...], candidate: ActantCandidate) -> bool:
            candidate_infos = material_analyses(morphs(candidate.normalized_hint or candidate.mention))
            if not candidate_infos:
                return True
            nominal_pos = {"NOUN", "NPRO", "ADJF", "ADJS", "PRTF", "PRTS"}
            if not any(info.pos in nominal_pos for info in candidate_infos):
                return False
            p_numbers = {x.number for x in pronoun if x.number}
            c_numbers = {x.number for x in candidate_infos if x.number}
            if p_numbers and c_numbers and p_numbers.isdisjoint(c_numbers):
                return False
            p_genders = {x.gender for x in pronoun if x.gender}
            c_genders = {x.gender for x in candidate_infos if x.gender}
            if p_genders and c_genders and p_genders.isdisjoint(c_genders):
                return False
            p_animacy = {x.animacy for x in pronoun if x.animacy}
            c_animacy = {x.animacy for x in candidate_infos if x.animacy}
            if p_animacy and c_animacy and p_animacy.isdisjoint(c_animacy):
                return False
            return True

        # Snapshot the original source order. `by_id` itself stays mutable because
        # binding the antecedent may have to allocate its local entity_ref first.
        ordered: list[tuple[int, str, ActantCandidate]] = []
        for assertion_id, assertion in by_id.items():
            for actant in assertion.actants:
                if (
                    actant.candidate_ref is not None
                    or actant.composition is not None
                    or actant.evidence is None
                    or not (actant.mention or actant.normalized_hint)
                ):
                    continue
                start = actant.evidence.start
                if start is None:
                    continue
                ordered.append((start, assertion_id, actant))
        ordered.sort(key=lambda item: item[0])

        for position, assertion_id, original_pronoun in tuple(ordered):
            p_infos = pronoun_infos(original_pronoun.mention or original_pronoun.normalized_hint)
            if not p_infos or original_pronoun.entity_ref is not None:
                continue

            prior: list[tuple[int, str, ActantCandidate]] = []
            for candidate_position, candidate_id, candidate in ordered:
                if candidate_position >= position:
                    break
                if candidate_id == assertion_id and candidate == original_pronoun:
                    continue
                if not compatible(p_infos, candidate):
                    continue
                # Do not use an unresolved third-person pronoun as a fresh anchor.
                # A previously bound pronoun is safe because its entity_ref already
                # identifies the antecedent exactly.
                c_pronoun = pronoun_infos(candidate.mention or candidate.normalized_hint)
                if c_pronoun and candidate.entity_ref is None:
                    continue
                prior.append((candidate_position, candidate_id, candidate))

            # Same-role preference is safe only inside one non-subordinate
            # sentence region (for example a conditional antecedent followed by
            # its main clause).  Across sentence boundaries or inside an embedded
            # complement, other matrix participants remain legitimate antecedents.
            graph = self._candidate_graph
            current_clause = None
            if graph is not None:
                pe = by_id[assertion_id].predicate.evidence
                if pe is not None:
                    token = next((t for t in graph.tokens if t.start == pe.start), None)
                    if token is not None:
                        current_clause = graph.clause_for_token(token.index)
            cross_sentence = False
            if graph is not None and current_clause is not None:
                for _pos, candidate_id, _candidate in prior:
                    pe = by_id[candidate_id].predicate.evidence
                    if pe is None:
                        continue
                    token = next((t for t in graph.tokens if t.start == pe.start), None)
                    clause = graph.clause_for_token(token.index) if token is not None else None
                    if clause is not None and clause.sentence_id != current_clause.sentence_id:
                        cross_sentence = True
                        break
            if current_clause is not None and current_clause.parent_clause_id is None and not cross_sentence:
                same_role = [item for item in prior if item[2].role == original_pronoun.role]
                pool = same_role if same_role else prior
            elif graph is not None and current_clause is not None and cross_sentence:
                # Explicit continuation markers license a conservative discourse
                # salience rule in the deterministic resolver: first keep only the
                # immediately preceding sentence, then prefer the same grammatical
                # role when it is uniquely represented there.  Without such a
                # marker we preserve all compatible readings as runtime alternatives.
                first_word = next(
                    (graph.token(i).text.casefold() for i in range(
                        current_clause.span.start_index, current_clause.span.end_index + 1
                    ) if re.search(r"\w", graph.token(i).text)),
                    "",
                )
                if first_word in {"потом", "затем", "тогда", "далее"}:
                    sentence_items: list[tuple[int, tuple[int, str, ActantCandidate]]] = []
                    for item in prior:
                        pe = by_id[item[1]].predicate.evidence
                        if pe is None:
                            continue
                        token = next((t for t in graph.tokens if t.start == pe.start), None)
                        clause = graph.clause_for_token(token.index) if token is not None else None
                        if clause is not None and clause.sentence_id < current_clause.sentence_id:
                            sentence_items.append((clause.sentence_id, item))
                    if sentence_items:
                        latest_sentence = max(x[0] for x in sentence_items)
                        recent = [item for sid, item in sentence_items if sid == latest_sentence]
                        same_role = [item for item in recent if item[2].role == original_pronoun.role]
                        pool = same_role if len(same_role) == 1 else recent
                    else:
                        pool = prior
                else:
                    pool = prior
            else:
                pool = prior

            # Several semantic frames may reuse the same single source mention.
            # Once `_bind_reused_source_mentions` has assigned one entity_ref, they
            # are one antecedent candidate, not an ambiguity.
            unique_pool: dict[tuple[object, ...], tuple[int, str, ActantCandidate]] = {}
            for item in pool:
                candidate = item[2]
                if candidate.entity_ref is not None:
                    key = ("entity", candidate.entity_ref)
                elif candidate.evidence is not None:
                    key = ("span", candidate.evidence.start, candidate.evidence.end)
                else:
                    key = ("item", item[0], item[1], id(candidate))
                unique_pool.setdefault(key, item)
            if not unique_pool:
                continue
            if len(unique_pool) == 1:
                _, antecedent_id, antecedent = next(iter(unique_pool.values()))
            else:
                # Perception is allowed to expose several local semantic readings,
                # but canonical entity choice belongs to deterministic Integration.
                # Preserve one complete AssertionCandidate per compatible antecedent
                # instead of asking the LLM to choose a canonical referent or failing
                # before the architecture's Ambiguity Handling stage.
                current = by_id[assertion_id]
                variants: list[AssertionCandidate] = []
                for _pos, antecedent_id, antecedent in unique_pool.values():
                    entity_ref = antecedent.entity_ref or self._ensure_actant_entity_ref(
                        by_id, antecedent_id, antecedent
                    )
                    if entity_ref is None:
                        continue
                    latest = by_id[assertion_id]
                    base_variants = latest.alternatives or (replace(latest, alternatives=()),)
                    for base in base_variants:
                        replaced = False
                        actants: list[ActantCandidate] = []
                        for actant in base.actants:
                            if not replaced and actant == original_pronoun:
                                actants.append(replace(actant, entity_ref=entity_ref))
                                replaced = True
                            else:
                                actants.append(actant)
                        if replaced:
                            variants.append(replace(base, actants=tuple(actants), alternatives=()))
                if not variants:
                    continue
                # Deduplicate equivalent local readings while preserving source order.
                unique_variants: list[AssertionCandidate] = []
                seen: set[tuple[object, ...]] = set()
                for variant in variants:
                    signature = tuple(
                        (a.role, a.entity_ref, a.candidate_ref, a.lookup_text)
                        for a in variant.actants
                    )
                    if signature in seen:
                        continue
                    seen.add(signature)
                    unique_variants.append(variant)
                by_id[assertion_id] = replace(
                    by_id[assertion_id], alternatives=tuple(unique_variants)
                )
                self._deterministic_trace(
                    "pronoun_alternatives",
                    f"PRONOUN:\n{original_pronoun.mention or original_pronoun.normalized_hint}",
                    str(len(unique_variants)),
                )
                continue

            entity_ref = antecedent.entity_ref or self._ensure_actant_entity_ref(
                by_id, antecedent_id, antecedent
            )
            if entity_ref is None:
                continue

            current = by_id[assertion_id]
            replaced = False
            new_actants: list[ActantCandidate] = []
            for actant in current.actants:
                if not replaced and actant == original_pronoun:
                    new_actants.append(replace(actant, entity_ref=entity_ref))
                    replaced = True
                else:
                    new_actants.append(actant)
            if not replaced:
                continue
            by_id[assertion_id] = replace(current, actants=tuple(new_actants))
            self._deterministic_trace(
                "pronoun_binding",
                f"PRONOUN:\n{original_pronoun.mention}\nANTECEDENT:\n{antecedent.lookup_text}",
                entity_ref,
            )

    def _frames_are_coordinated_or_separated(
        self,
        parent_span: _Span | None,
        child_span: _Span | None,
    ) -> bool:
        if parent_span is None or child_span is None or self._candidate_graph is None:
            return False
        left, right = sorted((parent_span, child_span), key=lambda item: item.start_index)
        tokens = self._candidate_graph.tokens
        between = tokens[left.end_index:right.start_index - 1]
        separators = {"и", "или", "либо", "а", "но", "однако", ",", ";"}
        return any(token.text.casefold() in separators for token in between)

    def _choose_frame_relation(
        self,
        parent: AssertionCandidate,
        child: AssertionCandidate,
        allowed: tuple[ActantRole, ...],
        *,
        allow_none: bool = False,
    ) -> ActantRole | None:
        """Resolve a tiny ordered set of relation hypotheses.

        Python proposes each canonical relation from syntax. The SLM answers one
        relation-specific semantic distinction. A confident negative may advance to
        the next hypothesis; a low-margin decision is never treated as "no link".
        That preserves the architecture invariant: valid graph or explicit
        ambiguity/error, never silently degraded semantics.
        """
        if not allowed:
            return None
        if allow_none:
            # A syntactically selected child situation is first tested as semantic
            # content/complement.  PURPOSE is reserved for a genuine goal of
            # performing the parent action, not for wanted/requested content.
            priority = (
                ActantRole.OBJECT, ActantRole.PURPOSE,
                ActantRole.HOW_TO, ActantRole.CAUSE,
            )
        else:
            priority = (
                ActantRole.OBJECT, ActantRole.CAUSE,
                ActantRole.PURPOSE, ActantRole.HOW_TO,
            )
        ordered = [role for role in priority if role in allowed]
        ordered.extend(role for role in allowed if role not in ordered)
        for role in ordered:
            positive, negative = self._frame_relation_choice_labels(role)
            decision, _margin = self._fixed_choice_probe(
                "frame_relation",
                self._frame_relation_prompt(parent, child, role),
                (positive, negative),
            )
            if decision is None:
                raise AdaptiveParseError(
                    f"ambiguous {role.value} attachment between "
                    f"{parent.predicate.lookup_form!r} and {child.predicate.lookup_form!r}",
                    tuple(self._traces),
                )
            if decision == positive:
                return role
        return None

    @staticmethod
    def _frame_relation_choice_labels(role: ActantRole) -> tuple[str, str]:
        return {
            ActantRole.OBJECT: ("CONTENT_LINK", "NOT_CONTENT"),
            ActantRole.PURPOSE: ("GOAL_LINK", "NOT_GOAL"),
            ActantRole.CAUSE: ("CAUSE_LINK", "NOT_CAUSE"),
            ActantRole.HOW_TO: ("MANNER_LINK", "NOT_MANNER"),
        }.get(role, ("LINKED", "SEPARATE"))

    def _frame_relation_prompt(
        self,
        parent: AssertionCandidate,
        child: AssertionCandidate,
        role: ActantRole,
    ) -> str:
        questions = {
            ActantRole.OBJECT: (
                "Is the CHILD situation the semantic content or selected complement "
                "of the PARENT predicate: what is said, thought, perceived, wanted, "
                "requested, attempted, started, or otherwise taken as its content?"
            ),
            ActantRole.PURPOSE: (
                "Is the CHILD situation the purpose or intended result for which the "
                "PARENT action itself is performed, rather than the PARENT's content?"
            ),
            ActantRole.CAUSE: (
                "Does the CHILD situation cause or explain why the PARENT situation happens?"
            ),
            ActantRole.HOW_TO: (
                "Does the CHILD situation describe how the PARENT action is performed?"
            ),
        }
        positive, negative = self._frame_relation_choice_labels(role)
        source_text = self._candidate_graph.text if self._candidate_graph is not None else ""
        return (
            f"TEXT:\n{source_text}\n"
            f"PARENT VERB:\n{parent.predicate.surface}\n"
            f"CHILD VERB:\n{child.predicate.surface}\n"
            f"QUESTION:\n{questions.get(role, 'Does the child fill this relation of the parent?')}\n"
            "Choose only between the two labels below.\n"
            f"CHOICES:\n{positive}\n{negative}"
        )

    def _contrastive_negation_frames(
        self,
        text: str,
        tokens: tuple[_SourceToken, ...],
        predicate_span: _Span | None,
        predicate: PredicateCandidate,
    ) -> tuple[tuple[tuple[ActantCandidate, ...], bool], ...] | None:
        """Expand ``не X, а Y`` into FALSE(P(...X)) plus P(...Y).

        The transformation is licensed by the contrastive coordinator and parallel
        role structure, not by any particular sentence or predicate.  If the two
        contrasted phrases cannot be isolated deterministically, normal parsing is
        used instead and may fail explicitly rather than guessing.
        """
        if predicate_span is None:
            return None
        start, end = self._predicate_argument_bounds(predicate_span, tokens)
        ne = next(
            (t.index for t in tokens
             if predicate_span.end_index < t.index <= end and t.text.casefold() == "не"),
            None,
        )
        if ne is None:
            return None
        contrast = next(
            (t.index for t in tokens
             if ne < t.index <= end and t.text.casefold() == "а"),
            None,
        )
        if contrast is None:
            return None
        subject_span = self._deterministic_subject_span(tokens, predicate_span, None)
        selected = [subject_span] if subject_span is not None else []
        candidates = self._candidate_phrase_spans(
            text, tokens, predicate_span, selected, requested_span=None
        )
        left = [c for c in candidates if ne < c.start_index and c.end_index < contrast]
        right = [c for c in candidates if contrast < c.start_index <= end]
        if len(left) != 1 or len(right) != 1:
            return None
        left_roles = self._deterministic_role_candidates(tokens, predicate_span, predicate, left[0])
        if len(left_roles) != 1:
            return None
        role = left_roles[0]
        right_roles = self._deterministic_role_candidates(tokens, predicate_span, predicate, right[0])
        if right_roles and role not in right_roles:
            return None

        prefix: list[ActantCandidate] = []
        if subject_span is not None and role != ActantRole.SUBJECT:
            prefix.append(self._make_actant(ActantRole.SUBJECT, subject_span))
        negative = tuple(prefix + [self._make_actant(role, left[0])])
        positive = tuple(prefix + [self._make_actant(role, right[0])])
        self._deterministic_trace(
            "contrastive_negation",
            f"PREDICATE:\n{predicate.surface}\nNEGATED:\n{left[0].text}\nASSERTED:\n{right[0].text}",
            role.value,
        )
        return ((negative, True), (positive, False))

    def _extract_actants(
        self,
        text: str,
        tokens: tuple[_SourceToken, ...],
        predicate_span: _Span | None,
        predicate: PredicateCandidate,
        *,
        act_type: str,
        requested_role: ActantRole | None,
        requested_span: _Span | None,
    ) -> tuple[tuple[ActantCandidate, ...], tuple[_Span, ...]]:
        spans: list[_Span] = []
        roles: set[ActantRole] = set()
        actants: list[ActantCandidate] = []

        subject_span = None
        if requested_role != ActantRole.SUBJECT:
            subject_span = self._deterministic_subject_span(tokens, predicate_span, requested_span)
        if subject_span is not None:
            self._trace_deterministic_actant(text, tokens, predicate_span, subject_span, ActantRole.SUBJECT)
            spans.append(subject_span)
            roles.add(ActantRole.SUBJECT)
            actants.append(self._make_actant(ActantRole.SUBJECT, subject_span))

        state_span = None
        if requested_role != ActantRole.STATE and ActantRole.STATE not in roles:
            state_span = self._deterministic_copular_state_span(
                text, tokens, predicate_span, predicate, spans, requested_span
            )
        if state_span is not None:
            self._trace_deterministic_actant(text, tokens, predicate_span, state_span, ActantRole.STATE)
            spans.append(state_span)
            roles.add(ActantRole.STATE)
            actants.append(self._make_actant(ActantRole.STATE, state_span))

        for _ in range(self.settings.max_actants_per_act):
            candidates = self._candidate_phrase_spans(
                text, tokens, predicate_span, spans, requested_span=requested_span
            )
            if not candidates:
                self._deterministic_trace(
                    "actant_start",
                    self._actant_phrase_prompt(text, predicate_span, spans, (), requested_span),
                    0,
                )
                break

            # If morphology gives several independent unambiguous actants at once
            # (for example DATV recipient + ACCS object), there is no reason to ask
            # the LLM which one should be processed first. Select the leftmost
            # candidate whose semantic role is unique among the remaining phrases.
            # If two candidates compete for the same role, keep the ambiguity for
            # the probe instead of resolving it by word order.
            deterministic_items: list[tuple[_Span, tuple[ActantRole, ...]]] = []
            role_frequency: dict[ActantRole, int] = {}
            for candidate_span in candidates:
                role_candidates = self._deterministic_role_candidates(
                    tokens, predicate_span, predicate, candidate_span
                )
                if len(role_candidates) != 1:
                    continue
                role_candidate = role_candidates[0]
                if role_candidate in roles or role_candidate == requested_role:
                    continue
                deterministic_items.append((candidate_span, role_candidates))
                role_frequency[role_candidate] = role_frequency.get(role_candidate, 0) + 1

            deterministic = next(
                (item for item in deterministic_items if role_frequency[item[1][0]] == 1),
                None,
            )

            if deterministic is not None:
                span, allowed_roles = deterministic
                self._deterministic_trace(
                    "actant_start",
                    self._actant_phrase_prompt(text, predicate_span, spans, candidates, requested_span),
                    span.spec,
                )
            elif len(candidates) == 1:
                span = candidates[0]
                allowed_roles = self._deterministic_role_candidates(tokens, predicate_span, predicate, span)
                self._deterministic_trace(
                    "actant_start",
                    self._actant_phrase_prompt(text, predicate_span, spans, candidates, requested_span),
                    span.spec,
                )
            else:
                choices: dict[int, _Span | None] = {-1: None, 0: None}
                for option, candidate_span in enumerate(candidates, start=1):
                    choices[option] = candidate_span
                chosen = self._probe(
                    "actant_start",
                    self._actant_phrase_prompt(text, predicate_span, spans, candidates, requested_span),
                    lambda raw: self._number_choice(raw, choices),
                    max_new_tokens=1,
                )
                if chosen is None:
                    break
                span = chosen
                allowed_roles = self._deterministic_role_candidates(tokens, predicate_span, predicate, span)

            attachment_mode = self._validate_prepositional_attachment(
                text, tokens, predicate, span, actants
            )
            if attachment_mode == "OBJECT_ATTACHMENT":
                object_actant = next(
                    (item for item in actants if item.role is ActantRole.OBJECT), None
                )
                if object_actant is None:
                    raise AdaptiveParseError("object attachment selected without an OBJECT actant")
                self._pending_nominal_with.append((object_actant, span))
                spans.append(span)
                self._deterministic_trace(
                    "structural_attachment",
                    f"ATTACHMENT: {span.text}",
                    "OBJECT_ATTACHMENT",
                )
                continue

            if allowed_roles and len(allowed_roles) == 1 and allowed_roles[0] not in roles:
                role = allowed_roles[0]
                self._deterministic_trace(
                    "role_family",
                    self._requested_role_prompt(text, predicate, span),
                    role.value,
                )
            else:
                # A deterministic morphology hint is not allowed to violate the
                # one-role-per-frame contract.  If its only suggested role is
                # already occupied, classify only among the remaining canonical
                # roles rather than emitting an invalid duplicate actant.
                filtered_allowed = (
                    {item for item in allowed_roles if item not in roles}
                    if allowed_roles else None
                )
                role = self._classify_role(
                    text,
                    predicate,
                    span,
                    used_roles=roles,
                    forbidden_role=requested_role if act_type == "QUERY" else None,
                    requested=False,
                    allowed_roles=filtered_allowed,
                )
                if role is None:
                    break
            spans.append(span)
            roles.add(role)
            actants.append(self._make_actant(role, span))

        # A weak model is allowed to stop actant enumeration, but it is not
        # allowed to make a structurally ambiguous attachment disappear.  Recheck
        # unconsumed phrase candidates through the ambiguity gate before accepting
        # the frame.
        remaining_candidates = self._candidate_phrase_spans(
            text, tokens, predicate_span, spans, requested_span=requested_span
        )
        for remaining in remaining_candidates:
            attachment_mode = self._validate_prepositional_attachment(
                text, tokens, predicate, remaining, actants
            )
            if attachment_mode == "OBJECT_ATTACHMENT":
                object_actant = next(
                    (item for item in actants if item.role is ActantRole.OBJECT), None
                )
                if object_actant is None:
                    raise AdaptiveParseError("object attachment selected without an OBJECT actant")
                self._pending_nominal_with.append((object_actant, remaining))
                spans.append(remaining)
                self._deterministic_trace(
                    "structural_attachment",
                    f"ATTACHMENT: {remaining.text}",
                    "OBJECT_ATTACHMENT",
                )
                continue
            if attachment_mode == "PREDICATE_ATTACHMENT":
                allowed = self._deterministic_role_candidates(
                    tokens, predicate_span, predicate, remaining
                )
                filtered = {item for item in allowed if item not in roles} if allowed else None
                role = self._classify_role(
                    text,
                    predicate,
                    remaining,
                    used_roles=roles,
                    forbidden_role=requested_role if act_type == "QUERY" else None,
                    requested=False,
                    allowed_roles=filtered,
                )
                if role is not None and role not in roles:
                    spans.append(remaining)
                    roles.add(role)
                    actants.append(self._make_actant(role, remaining))
                    self._deterministic_trace(
                        "structural_attachment",
                        f"ATTACHMENT: {remaining.text}",
                        "PREDICATE_ATTACHMENT",
                    )

        return tuple(actants), tuple(spans)

    def _make_actant(self, role: ActantRole, span: _Span) -> ActantCandidate:
        composition = self._composition_for_span(span)
        mention, normalized_hint = self._semantic_actant_text(span)
        return ActantCandidate(
            role=role,
            mention=mention,
            normalized_hint=normalized_hint,
            evidence=span.evidence,
            composition=composition,
        )

    def _semantic_actant_text(self, span: _Span) -> tuple[str, str | None]:
        """Return source mention plus deterministic nominal lookup form.

        Prepositions stay in evidence but are removed from entity identity.  A
        single nominal is normalized even without a preposition, so inflectional
        forms such as Мария/Марии/Марию resolve through one canonical lookup key.
        """
        graph = self._candidate_graph
        if graph is None:
            return span.text, None
        tokens = [
            graph.token(i) for i in range(span.start_index, span.end_index + 1)
            if re.search(r"\w", graph.token(i).text)
        ]
        if not tokens:
            return span.text, None
        if (
            len(tokens) >= 3
            and tokens[0].text.casefold() in _SPATIAL_RELATION_ADVERBS
            and tokens[1].text.casefold() == "с"
        ):
            tokens = tokens[2:]
        elif tokens[0].has_pos("PREP"):
            tokens = tokens[1:]
        if not tokens:
            return span.text, None
        mention = graph.text[tokens[0].start:tokens[-1].end]
        normalized_hint: str | None = None
        if len(tokens) == 1:
            normalized_hint = stable_normal_form(
                self._morph_all(tokens[0]), poses={"NOUN", "NPRO"}
            )
            if normalized_hint is not None:
                if tokens[0].text[:1].isupper():
                    normalized_hint = normalized_hint[:1].upper() + normalized_hint[1:]
        return mention, normalized_hint

    def _composition_for_span(self, span: _Span) -> ActantCompositionCandidate | None:
        graph = self._candidate_graph
        if graph is None:
            return None
        matches = [
            item for item in graph.coordinations
            if item.span.start_index == span.start_index and item.span.end_index == span.end_index
        ]
        if len(matches) != 1:
            return None
        item = matches[0]
        operator = CompositionOperator.AND if item.operator is CoordinationKind.AND else CompositionOperator.OR
        members = tuple(
            CompositionMemberCandidate(
                mention=self._semantic_actant_text(
                    self._resolve_span(graph.text, self._source_tokens(graph.text), member.start_index, member.end_index)
                )[0],
                normalized_hint=self._semantic_actant_text(
                    self._resolve_span(graph.text, self._source_tokens(graph.text), member.start_index, member.end_index)
                )[1],
                evidence=member.evidence,
            )
            for member in item.member_spans
        )
        return ActantCompositionCandidate(operator=operator, members=members)

    def _candidate_phrase_spans(
        self,
        text: str,
        tokens: tuple[_SourceToken, ...],
        predicate: _Span | None,
        selected: list[_Span],
        *,
        requested_span: _Span | None,
    ) -> tuple[_Span, ...]:
        clause_start, clause_end = self._predicate_argument_bounds(predicate, tokens)
        blocked: set[int] = set()
        if predicate is not None:
            blocked.update(range(predicate.start_index, predicate.end_index + 1))
        if requested_span is not None:
            blocked.update(range(requested_span.start_index, requested_span.end_index + 1))
        for item in selected:
            blocked.update(range(item.start_index, item.end_index + 1))
        # Other predicate heads are semantic-frame candidates, not entity phrases.
        # They can later be attached through candidate_ref instead of being turned
        # into accidental m nodes containing a verb token.
        if self._candidate_graph is not None:
            current_predicate_positions = set()
            if predicate is not None:
                current_predicate_positions.update(range(predicate.start_index, predicate.end_index + 1))
            for head in self._candidate_graph.predicates:
                if head.token_index not in current_predicate_positions:
                    blocked.add(head.token_index)

        # Reuse deterministic coordination spans as indivisible phrase candidates.
        graph = self._candidate_graph
        coordination_by_start: dict[int, _Span] = {}
        if graph is not None:
            # Clause connectives (single or multi-word) are operators over frames,
            # not entity/state actants.  Block their tokens generically so forms
            # such as relative pronouns and "после того, как" cannot become
            # SUBJECT/RECIPIENT/etc.
            for clause in graph.clauses:
                connector = clause.connector_span
                if connector is None:
                    continue
                for i in range(max(clause_start, connector.start_index), min(clause_end, connector.end_index) + 1):
                    blocked.add(i)
            for item in graph.coordinations:
                if item.span.start_index < clause_start or item.span.end_index > clause_end:
                    continue
                if any(i in blocked for i in range(item.span.start_index, item.span.end_index + 1)):
                    continue
                coordination_by_start[item.span.start_index] = self._resolve_span(
                    text, tokens, item.span.start_index, item.span.end_index
                )

        result: list[_Span] = []
        consumed: set[int] = set()
        index = clause_start
        while index <= clause_end:
            if index in blocked or index in consumed:
                index += 1
                continue
            token = tokens[index - 1]
            low = token.text.casefold()
            if not self._is_word_token(token) or low in _COORDINATORS or low in {"что", "чтобы", "если", "когда", "где", "куда", "откуда"}:
                index += 1
                continue

            # Function words/operators are allowed inside a larger phrase but must
            # never become standalone semantic actant heads. In particular, a
            # negation particle such as Russian ``не`` is already consumed by the
            # predicate-negation analysis and must not later become OBJECT/STATE.
            # Keep content-bearing negative pronouns/adverbs (``никто``, ``нигде``,
            # ``никогда``) because their morphology is NPRO/ADVB rather than PRCL.
            analyses = self._morph_all(token)
            structural_analyses = self._material_morph_analyses(token)
            known_poses = {item.pos for item in structural_analyses if item.pos is not None}
            if known_poses and known_poses.issubset({"PRCL", "CONJ", "INTJ"}):
                index += 1
                continue
            coord = coordination_by_start.get(index)
            if coord is not None:
                result.append(coord)
                consumed.update(range(coord.start_index, coord.end_index + 1))
                index = coord.end_index + 1
                continue

            # Relational spatial adverb + prepositional complement is one
            # LOCATION phrase (``рядом с журналом``), not two unrelated actants.
            if (
                low in _SPATIAL_RELATION_ADVERBS
                and index + 2 <= clause_end
                and tokens[index].text.casefold() == "с"
                and self._has_morph(tokens[index], poses={"PREP"})
            ):
                cursor = index + 2
                end = index + 1
                while cursor <= clause_end and cursor not in blocked:
                    current = tokens[cursor - 1]
                    if current.text in _STRONG_BOUNDARY or current.text == ",":
                        break
                    if current.text.casefold() in _COORDINATORS:
                        break
                    if self._is_word_token(current):
                        end = cursor
                        if self._has_morph(current, poses={"NOUN", "NPRO"}):
                            break
                    cursor += 1
                if end >= index + 2:
                    span = self._resolve_span(text, tokens, index, end)
                    result.append(span)
                    consumed.update(range(index, end + 1))
                    index = end + 1
                    continue

            if self._has_morph(token, poses={"PREP"}):
                end = index
                cursor = index + 1
                while cursor <= clause_end and cursor not in blocked:
                    current = tokens[cursor - 1]
                    if current.text in _STRONG_BOUNDARY or current.text == ",":
                        break
                    if current.text.casefold() in _COORDINATORS:
                        break
                    if self._is_word_token(current):
                        end = cursor
                        if self._has_morph(current, poses={"NOUN", "NPRO"}):
                            break
                    cursor += 1
                if end > index:
                    span = self._resolve_span(text, tokens, index, end)
                    result.append(span)
                    consumed.update(range(index, end + 1))
                    index = end + 1
                    continue
                # A bare preposition is not an actant. It can only participate as
                # part of a prepositional phrase with a content-bearing complement.
                index += 1
                continue

            if self._has_morph(token, poses={"NOUN", "NPRO"}):
                start = index
                cursor = index - 1
                while cursor >= clause_start and cursor not in blocked:
                    prev = tokens[cursor - 1]
                    if self._has_morph(prev, poses={"ADJF", "PRTF", "NUMR"}):
                        start = cursor
                        cursor -= 1
                        continue
                    break
                end = index
                cursor = index + 1
                # Include a short genitive complement only for a nominal head.
                # Pronouns such as ``его`` must not absorb the following dative/
                # genitive participant (``его Марии``) into one fake entity span.
                head_is_noun = self._has_structural_morph(token, poses={"NOUN"})
                while head_is_noun and cursor <= clause_end and cursor not in blocked:
                    nxt = tokens[cursor - 1]
                    if self._has_structural_morph(nxt, poses={"NOUN", "NPRO"}, case="gent"):
                        end = cursor
                        cursor += 1
                        continue
                    break
                span = self._resolve_span(text, tokens, start, end)
                if not any(span.overlaps(old) for old in result):
                    result.append(span)
                    consumed.update(range(start, end + 1))
                index = max(index + 1, end + 1)
                continue

            if self._has_morph(token, poses={"ADJF", "ADJS", "PRTF", "PRTS", "PRED", "ADVB", "NUMR"}):
                span = self._resolve_span(text, tokens, index, index)
                result.append(span)
                consumed.add(index)
                index += 1
                continue

            # Unknown content word stays available as a minimal candidate instead of
            # being silently discarded. The LLM may reject it via the stop option.
            span = self._resolve_span(text, tokens, index, index)
            result.append(span)
            consumed.add(index)
            index += 1

        unique: dict[tuple[int, int], _Span] = {}
        for item in result:
            if any(item.overlaps(old) for old in selected):
                continue
            unique[(item.start_index, item.end_index)] = item
        return tuple(unique[key] for key in sorted(unique))

    def _validate_prepositional_attachment(
        self,
        text: str,
        tokens: tuple[_SourceToken, ...],
        predicate: PredicateCandidate,
        span: _Span,
        existing_actants: list[ActantCandidate],
    ) -> str | None:
        """Return a user-grounded structural attachment decision when required.

        ``с + instrumental`` after a direct object has two materially different
        readings: the phrase can modify the predicate (tool/company) or the object
        noun phrase.  Deterministic syntax can detect the ambiguity but cannot pick
        one reading.  The first pass therefore emits a clarification spec instead
        of asking the LLM to guess.  A later explicit user choice is replayed through
        ``structural_resolution`` and only then reaches canonical Integration.
        """
        words = [tokens[i - 1].text.casefold() for i in range(span.start_index, span.end_index + 1)]
        if not words or words[0] != "с":
            return None
        object_actant = next(
            (item for item in existing_actants if item.role is ActantRole.OBJECT), None
        )
        if object_actant is None:
            return None
        if not any(
            self._has_structural_morph(tokens[i - 1], poses={"NOUN", "NPRO"}, case="ablt")
            for i in range(span.start_index, span.end_index + 1)
        ):
            return None

        if self._structural_resolution in {"PREDICATE_ATTACHMENT", "OBJECT_ATTACHMENT"}:
            return self._structural_resolution

        object_label = object_actant.mention or object_actant.normalized_hint or "объект"
        spec = StructuralClarificationSpec(
            ambiguity_type="WITH_ATTACHMENT",
            mention=span.text,
            source_text=text,
            options=(
                StructuralClarificationOption(
                    "PREDICATE_ATTACHMENT",
                    f"«{span.text}» относится к действию «{predicate.surface}»",
                ),
                StructuralClarificationOption(
                    "OBJECT_ATTACHMENT",
                    f"«{span.text}» описывает «{object_label}»",
                ),
            ),
        )
        raise AdaptiveStructuralClarificationRequired(spec)

    @staticmethod
    def _is_copular_lookup(value: str) -> bool:
        return value in {
            "be", "become", "remain", "seem",
            "быть", "бывать", "являться", "стать", "становиться",
            "остаться", "оставаться", "казаться",
        }

    def _deterministic_role_candidates(
        self,
        tokens: tuple[_SourceToken, ...],
        predicate_span: _Span | None,
        predicate: PredicateCandidate,
        span: _Span,
    ) -> tuple[ActantRole, ...]:
        first = tokens[span.start_index - 1]
        words = [tokens[i - 1].text.casefold() for i in range(span.start_index, span.end_index + 1)]
        before_predicate = predicate_span is not None and span.end_index < predicate_span.start_index
        passive = self._is_passive_predicate(predicate_span, tokens)
        if passive and any(
            self._has_structural_morph(tokens[i - 1], poses={"NOUN", "NPRO"}, case="ablt")
            for i in range(span.start_index, span.end_index + 1)
        ):
            return (ActantRole.SUBJECT,)
        if passive and any(
            self._has_structural_morph(tokens[i - 1], poses={"NOUN", "NPRO"}, case="nomn")
            for i in range(span.start_index, span.end_index + 1)
        ):
            return (ActantRole.OBJECT,)

        # A coordinated nominal phrase following a predicate with an already
        # structurally available pre-verbal subject is the direct-object region,
        # even when Russian case syncretism makes each member individually both
        # NOM and ACC (``Иван купил хлеб и молоко``).
        if predicate_span is not None and span.start_index > predicate_span.end_index and self._candidate_graph is not None:
            coordination = next(
                (item for item in self._candidate_graph.coordinations
                 if item.span.start_index == span.start_index
                 and item.span.end_index == span.end_index
                 and item.operator is CoordinationKind.AND),
                None,
            )
            if coordination is not None:
                subject = self._deterministic_subject_span(tokens, predicate_span, None)
                members_nominal = all(
                    any(
                        self._has_structural_morph(tokens[i - 1], poses={"NOUN", "NPRO"})
                        for i in range(member.start_index, member.end_index + 1)
                    )
                    for member in coordination.member_spans
                )
                if subject is not None and members_nominal:
                    return (ActantRole.OBJECT,)

        if before_predicate and any(
            self._has_structural_morph(tokens[i - 1], poses={"NOUN", "NPRO"}, case="nomn")
            for i in range(span.start_index, span.end_index + 1)
        ):
            return (ActantRole.SUBJECT,)
        if (
            any(word in _SPATIAL_ADVERBS for word in words)
            and any(
                self._has_structural_morph(tokens[i - 1], poses={"ADVB"})
                for i in range(span.start_index, span.end_index + 1)
            )
        ):
            return (ActantRole.LOCATION,)
        if self._is_copular_lookup(predicate.lookup_form) and any(
            self._has_morph(tokens[i - 1], poses={"ADJF", "ADJS", "PRTF", "PRTS", "PRED"})
            for i in range(span.start_index, span.end_index + 1)
        ):
            return (ActantRole.STATE,)
        if self._is_copular_lookup(predicate.lookup_form) and any(
            self._has_structural_morph(tokens[i - 1], poses={"ADVB"})
            for i in range(span.start_index, span.end_index + 1)
        ):
            # A copular/remain-like predicate followed by an adverbial phrase is
            # descriptive context, never a generic participant merely because the
            # surface form also has a noun reading (e.g. Russian case/adverb
            # homography).  Keep the actual semantic distinction finite.
            return (
                ActantRole.STATE,
                ActantRole.LOCATION,
                ActantRole.TIME,
                ActantRole.DURATION,
            )
        if (
            len(words) >= 3
            and words[0] in _SPATIAL_RELATION_ADVERBS
            and words[1] == "с"
        ):
            return (ActantRole.LOCATION,)
        if words and words[0] == "с" and any(
            self._has_structural_morph(tokens[i - 1], poses={"NOUN", "NPRO"}, case="ablt")
            for i in range(span.start_index, span.end_index + 1)
        ):
            return (ActantRole.TOOL, ActantRole.AUXILLIARY)
        if words and words[0] in {"в", "на", "около", "возле", "под", "над", "между"}:
            return (ActantRole.LOCATION,)
        if words and words[0] in {"из", "от"}:
            return (ActantRole.SOURCE,)
        if words and words[0] in {"для", "ради"}:
            return (ActantRole.PURPOSE,)
        if words and words[0] in {"из-за", "изза"}:
            return (ActantRole.CAUSE,)
        if any(word in {"сегодня", "вчера", "завтра", "сейчас", "позже", "раньше", "потом", "затем"} for word in words):
            return (ActantRole.TIME,)
        if any(self._has_morph(tokens[i - 1], poses={"NUMR"}) for i in range(span.start_index, span.end_index + 1)):
            return (ActantRole.AMOUNT,)
        if any(self._has_structural_morph(tokens[i - 1], poses={"NOUN", "NPRO"}, case="datv") for i in range(span.start_index, span.end_index + 1)):
            return (ActantRole.RECIPIENT,)
        if any(self._has_structural_morph(tokens[i - 1], poses={"NOUN", "NPRO"}, case="accs") for i in range(span.start_index, span.end_index + 1)):
            # Surface accusative is a direct participant of the current predicate.
            # Keep it deterministic here.  A narrow post-structural repair may
            # reclassify an animate OBJECT to RECIPIENT only when a nested
            # proposition has already been independently established as the
            # predicate's semantic OBJECT/content.  Asking the LLM here, before
            # coreference and frame nesting are known, makes pronouns such as
            # ``его`` needlessly ambiguous and was shown to create positional
            # semantic errors in ordinary transitive clauses.
            return (ActantRole.OBJECT,)
        return ()

    def _actant_phrase_prompt(
        self,
        text: str,
        predicate: _Span | None,
        selected: list[_Span],
        candidates: tuple[_Span, ...],
        requested_span: _Span | None,
    ) -> str:
        options = {
            -1: "cannot choose reliably from the remaining phrases",
            0: "no more relevant phrase remains",
        }
        for option, span in enumerate(candidates, start=1):
            options[option] = span.text
        lines = [f"TEXT:\n{text}"]
        if predicate is not None:
            lines.append(f"PREDICATE:\n{predicate.text}")
        if selected:
            lines.append("ALREADY_SELECTED:\n" + " | ".join(span.text for span in selected))
        if requested_span is not None:
            lines.append("QUESTION_PLACEHOLDER:\n" + requested_span.text)
        lines.append("OPTIONS:\n" + self._options_lines(options))
        return "\n".join(lines)

    def _clause_bounds(
        self,
        predicate_span: _Span | None,
        tokens: tuple[_SourceToken, ...],
    ) -> tuple[int, int]:
        if self._candidate_graph is not None:
            target_index = predicate_span.start_index if predicate_span is not None else None
            if target_index is not None:
                clause = self._candidate_graph.clause_for_token(target_index)
                if clause is not None:
                    return clause.span.start_index, clause.span.end_index
            for clause in self._candidate_graph.clauses:
                return clause.span.start_index, clause.span.end_index
        return 1, len(tokens)

    def _predicate_argument_bounds(
        self,
        predicate_span: _Span | None,
        tokens: tuple[_SourceToken, ...],
    ) -> tuple[int, int]:
        """Return the token window whose surface arguments belong to one frame.

        A ClauseCandidate may intentionally contain several coordinated predicates
        that share a subject (``X read a document and wrote a text``).  Clause-wide
        actant extraction lets the first frame consume arguments of the second and
        vice versa.  This method carves a conservative predicate-local window at
        the coordinator nearest each neighbouring predicate head.

        The shared subject is resolved separately by `_deterministic_subject_span`,
        so a later coordinated predicate does not need the preceding surface region
        in its ordinary argument candidate pool.
        """
        clause_start, clause_end = self._clause_bounds(predicate_span, tokens)
        graph = self._candidate_graph
        if predicate_span is None or graph is None:
            return clause_start, clause_end

        clause = graph.clause_for_token(predicate_span.start_index)
        if clause is None:
            return clause_start, clause_end
        sibling_heads = sorted(
            head.token_index
            for head in clause.predicate_heads
            if clause.span.start_index <= head.token_index <= clause.span.end_index
        )
        if predicate_span.start_index not in sibling_heads or len(sibling_heads) < 2:
            return clause_start, clause_end

        separators = {"и", "или", "либо", "а", "но", "однако"}
        current = predicate_span.start_index
        pos = sibling_heads.index(current)
        heads_by_index = {head.token_index: head for head in clause.predicate_heads}

        if pos > 0:
            previous = sibling_heads[pos - 1]
            between = [
                token for token in graph.tokens
                if previous < token.index < current
                and token.text.casefold() in separators
            ]
            if between:
                # The coordinator nearest the current predicate separates the
                # previous frame from this one; nominal coordinators farther left
                # stay with the previous frame.
                clause_start = max(clause_start, between[-1].index + 1)
            elif not heads_by_index[current].finite:
                # A non-finite child directly governed by a preceding predicate
                # owns only its post-predicate surface arguments.  Participants
                # before the infinitive belong to the parent frame and are later
                # considered as controller candidates by `_resolve_control_subjects`.
                clause_start = max(clause_start, current + 1)

        if pos + 1 < len(sibling_heads):
            following = sibling_heads[pos + 1]
            between = [
                token for token in graph.tokens
                if current < token.index < following
                and token.text.casefold() in separators
            ]
            if between:
                # Symmetrically, the coordinator nearest the following predicate
                # terminates this frame's surface-argument window.
                clause_end = min(clause_end, between[-1].index - 1)
            elif not heads_by_index[following].finite:
                # Finite parent + directly governed infinitive/gerund.  Stop the
                # parent window immediately before the child predicate so child
                # arguments cannot leak into the parent as a second OBJECT.
                clause_end = min(clause_end, following - 1)

        if clause_start > clause_end:
            # A governed non-finite predicate can have no own surface arguments.
            # Keep a valid empty-effective window anchored on the predicate token;
            # the token itself is blocked from actant extraction.
            return current, current
        return clause_start, clause_end

    def _resolve_span_from_source(
        self,
        tokens: tuple[_SourceToken, ...],
        start: int,
        end: int,
    ) -> _Span:
        text = self._candidate_graph.text if self._candidate_graph is not None else " ".join(t.text for t in tokens)
        return self._resolve_span(text, tokens, start, end)

    def _is_nonfinite_predicate(self, predicate_span: _Span | None) -> bool:
        if predicate_span is None or self._candidate_graph is None:
            return False
        head = next(
            (item for item in self._candidate_graph.predicates
             if predicate_span.start_index <= item.token_index <= predicate_span.end_index),
            None,
        )
        return head is not None and not head.finite

    def _is_passive_predicate(
        self, predicate_span: _Span | None, tokens: tuple[_SourceToken, ...]
    ) -> bool:
        if predicate_span is None:
            return False
        for i in range(predicate_span.start_index, predicate_span.end_index + 1):
            if any(info.pos == "PRTS" for info in self._material_morph_analyses(tokens[i - 1])):
                return True
        return False

    def _deterministic_subject_span(
        self,
        tokens: tuple[_SourceToken, ...],
        predicate_span: _Span | None,
        requested_span: _Span | None,
    ) -> _Span | None:
        clause_start, clause_end = self._clause_bounds(predicate_span, tokens)
        if self._is_passive_predicate(predicate_span, tokens) or self._is_nonfinite_predicate(predicate_span):
            return None
        connector_indices: set[int] = set()
        if predicate_span is not None and self._candidate_graph is not None:
            clause = self._candidate_graph.clause_for_token(predicate_span.start_index)
            if clause is not None and clause.connector_span is not None:
                connector_indices.update(
                    range(clause.connector_span.start_index, clause.connector_span.end_index + 1)
                )

        def nominal_candidates(
            left: int, right: int, *, exclude_preposition_governed: bool = False
        ) -> list[int]:
            result: list[int] = []
            for token in tokens:
                if token.index < left or token.index > right or token.index in connector_indices:
                    continue
                if self._span_contains(requested_span, token.index):
                    continue
                if (
                    exclude_preposition_governed
                    and token.index > clause_start
                    and self._has_morph(tokens[token.index - 2], poses={"PREP"})
                ):
                    continue
                if self._has_structural_morph(token, poses={"NOUN", "NPRO"}, case="nomn"):
                    result.append(token.index)
            return result

        if predicate_span is None:
            candidates = nominal_candidates(clause_start, clause_end)
        else:
            # Canonical Russian order gives us a very strong pre-predicate subject.
            # If none exists, allow one unambiguous post-verbal nominative (e.g.
            # ``шёл дождь``) instead of blindly inheriting a subject from a parent
            # clause.  This remains morphology+clause structure only.
            candidates = nominal_candidates(clause_start, predicate_span.start_index - 1)
            if not candidates:
                candidates = nominal_candidates(
                    predicate_span.end_index + 1, clause_end, exclude_preposition_governed=True
                )
        if len(candidates) != 1:
            return None
        head = candidates[0]
        start = head
        cursor = head - 1
        while cursor >= clause_start and cursor not in connector_indices:
            token = tokens[cursor - 1]
            if not self._has_structural_morph(token, poses={"ADJF", "PRTF", "NUMR"}):
                break
            start = cursor
            cursor -= 1
        return self._resolve_span_from_source(tokens, start, head)

    def _deterministic_copular_state_span(
        self,
        text: str,
        tokens: tuple[_SourceToken, ...],
        predicate_span: _Span | None,
        predicate: PredicateCandidate,
        selected: list[_Span],
        requested_span: _Span | None,
    ) -> _Span | None:
        if not self._is_copular_lookup(predicate.lookup_form):
            return None
        clause_start, clause_end = self._clause_bounds(predicate_span, tokens)
        lower_bound = predicate_span.end_index + 1 if predicate_span is not None else clause_start
        starts: list[int] = []
        for token in tokens:
            if token.index < lower_bound or token.index > clause_end:
                continue
            if self._span_contains(requested_span, token.index):
                continue
            if any(span.start_index <= token.index <= span.end_index for span in selected):
                continue
            if self._has_morph(token, poses={"ADJF", "ADJS", "PRTS", "PRTF", "PRED"}):
                # Do not start on the second member of an adjective coordination.
                if token.index >= 3 and tokens[token.index - 2].text.casefold() in _COORDINATORS:
                    if self._has_morph(tokens[token.index - 3], poses={"ADJF", "ADJS", "PRTS", "PRTF", "PRED"}):
                        continue
                starts.append(token.index)
        if len(starts) != 1:
            return None
        start = starts[0]
        if self._candidate_graph is not None:
            coord_matches = [
                item for item in self._candidate_graph.coordinations
                if item.span.start_index == start and item.span.end_index <= clause_end
            ]
            if len(coord_matches) == 1:
                item = coord_matches[0]
                return self._resolve_span(text, tokens, item.span.start_index, item.span.end_index)
        end = start
        base_analyses = self._morph_all(tokens[start - 1])
        base_poses = {a.pos for a in base_analyses if a.pos in {"ADJF", "ADJS", "PRTS", "PRTF", "PRED"}}
        cursor = start + 1
        while cursor + 1 <= clause_end:
            coordinator = tokens[cursor - 1].text.casefold()
            if coordinator not in {"и", "или", "либо"}:
                break
            next_token = tokens[cursor]
            next_poses = {a.pos for a in self._morph_all(next_token) if a.pos}
            if not (base_poses & next_poses):
                break
            end = cursor + 1
            cursor += 2
        return self._resolve_span(text, tokens, start, end)

    def _trace_deterministic_actant(
        self,
        text: str,
        tokens: tuple[_SourceToken, ...],
        predicate_span: _Span | None,
        span: _Span,
        role: ActantRole,
    ) -> None:
        predicate_text = predicate_span.text if predicate_span is not None else "<implicit>"
        context = (
            f"TEXT:\n{text}\nTOKENS:\n{self._tokens_text(tokens)}\n"
            f"PREDICATE:\n{predicate_text}\nTARGET:\n{span.text}"
        )
        self._traces.append(
            ProbeTrace(
                stage="actant_deterministic",
                prompt=context,
                raw_text=f"<deterministic:{self.morphology.name}>",
                normalized_answer=f"{role.value}:{span.spec}",
                retry_index=0,
                error=None,
            )
        )

    def _explicit_question_word(
        self, tokens: tuple[_SourceToken, ...]
    ) -> _SourceToken | None:
        connector_indices: set[int] = set()
        if self._candidate_graph is not None:
            for clause in self._candidate_graph.clauses:
                if clause.connector_span is not None:
                    connector_indices.update(
                        range(clause.connector_span.start_index, clause.connector_span.end_index + 1)
                    )
        first_predicate = None
        if self._candidate_graph is not None and self._candidate_graph.predicates:
            first_predicate = min(item.token_index for item in self._candidate_graph.predicates)
        for token in tokens:
            if token.text.casefold() not in _QUESTION_WORDS:
                continue
            # A sentence-initial interrogative such as ``Что Иван ...?`` can also
            # be tagged as a subordinating connector by the lexical candidate graph.
            # Before the first predicate it is speech-act syntax, not clause linking.
            if token.index in connector_indices and not (first_predicate is not None and token.index < first_predicate):
                continue
            return token
        return None

    def _requested_query_role(
        self,
        text: str,
        tokens: tuple[_SourceToken, ...],
        predicate: PredicateCandidate,
    ) -> tuple[ActantRole, _Span | None]:
        wh = self._explicit_question_word(tokens)
        wh_tokens = [] if wh is None else [wh]
        if not wh_tokens:
            # No explicit question word. Ask for the missing role using the whole question
            # as target; this remains a discrete role-choice tree.
            pseudo = _Span(1, len(tokens), text, EvidenceSpan(text, 0, len(text)))
            role = self._classify_role(text, predicate, pseudo, set(), None, requested=True)
            if role is None:
                raise AdaptiveParseError("requested role unresolved")
            return role, None

        token = wh_tokens[0]
        word = token.text.casefold()
        span = self._resolve_span(text, tokens, token.index, token.index)
        direct = _DETERMINISTIC_WH_ROLES.get(word)
        if direct is not None:
            self._deterministic_trace(
                "requested_role",
                self._requested_role_prompt(text, predicate, span),
                direct.value,
            )
            return direct, span

        # Russian кто/что/как/чем forms can be syntactically ambiguous. Use the same
        # role decision tree as ordinary actants, with plain-language options.
        role = self._classify_role(text, predicate, span, set(), None, requested=True)
        if role is None:
            raise AdaptiveParseError("requested role unresolved")
        return role, span

    def _classify_role(
        self,
        text: str,
        predicate: PredicateCandidate,
        span: _Span,
        used_roles: set[ActantRole],
        forbidden_role: ActantRole | None,
        *,
        requested: bool,
        allowed_roles: set[ActantRole] | None = None,
    ) -> ActantRole | None:
        available_groups: list[tuple[str, tuple[tuple[ActantRole, str], ...]]] = []
        for group_name, entries in _ROLE_GROUPS.items():
            filtered = tuple(
                (role, desc)
                for role, desc in entries
                if role not in used_roles
                and role != forbidden_role
                and (allowed_roles is None or role in allowed_roles)
            )
            if filtered:
                available_groups.append((group_name, filtered))
        if not available_groups:
            raise AdaptiveParseError("no canonical roles remain available")

        mode = "MISSING INFORMATION" if requested else "TARGET"
        if len(available_groups) == 1:
            group_name, entries = available_groups[0]
            self._deterministic_trace(
                "role_family",
                f"TEXT:\n{text}\nPREDICATE:\n{predicate.surface}\n{mode}:\n{span.text}",
                group_name,
            )
        else:
            family_labels = tuple(group.upper() for group, _ in available_groups)
            family_options = "\n".join(
                f"{group.upper()}: {_ROLE_FAMILY_DESCRIPTIONS[group]}"
                for group, _ in available_groups
            )
            family_prompt = (
                f"TEXT:\n{text}\nPREDICATE:\n{predicate.surface}\n{mode}:\n{span.text}\n"
                f"ROLE FAMILY OPTIONS:\n{family_options}\n"
                "QUESTION:\nWhich role family best describes the target in this sentence?"
            )
            family_decision, _margin = self._fixed_choice_probe(
                "role_family", family_prompt, family_labels
            )
            if family_decision is None:
                return None
            group_name = family_decision.lower()
            entries = dict(available_groups)[group_name]

        stage = f"role_{group_name}"
        if len(entries) == 1:
            role = entries[0][0]
            self._deterministic_trace(
                stage,
                f"TEXT:\n{text}\nPREDICATE:\n{predicate.surface}\n{mode}:\n{span.text}",
                role.value,
            )
            return role

        label_to_role: dict[str, ActantRole] = {}
        option_lines: list[str] = []
        for role, description in entries:
            label = self._template_role_label(role)
            label_to_role[label] = role
            option_lines.append(f"{label}: {description}")
        role_prompt = (
            f"TEXT:\n{text}\nPREDICATE:\n{predicate.surface}\n{mode}:\n{span.text}\n"
            f"ROLE OPTIONS:\n{'\n'.join(option_lines)}\n"
            "QUESTION:\nWhich role best describes the target in this sentence?"
        )
        role_decision, _margin = self._fixed_choice_probe(
            stage, role_prompt, tuple(label_to_role)
        )
        if role_decision is None:
            return None
        return label_to_role[role_decision]

    def _fixed_choice_probe(
        self,
        stage: str,
        prompt: str,
        choices: tuple[str, ...],
        *,
        margin_threshold: float = _CHOICE_MARGIN_THRESHOLD,
    ) -> tuple[str | None, float]:
        """Resolve a bounded semantic choice without letting scorer heuristics vote.

        Binary probes use ordinary deterministic generation because the selected
        local model has demonstrated exact, order-invariant two-label generation.
        The answer must be exactly one supplied label; malformed output fails
        closed.  Legacy exact-continuation scoring is retained only for choices
        with more than two alternatives until those paths are separately audited.
        """
        if not choices or len(set(choices)) != len(choices):
            raise AdaptiveParseError(f"{stage} requires unique fixed choices")
        instruction = self._instruction(stage)
        user_prompt = self._compose_probe_prompt(prompt, instruction)

        if len(choices) == 2:
            response = self.backend.generate(
                user_prompt,
                system=self._probe_system(),
                override=self._generation_override(8),
                role=f"perception_{stage}",
            )
            raw = response.text.strip()
            label = raw.upper()
            if label not in choices:
                self._traces.append(
                    ProbeTrace(
                        stage, user_prompt, raw, None, 0,
                        f"expected exactly one of: {', '.join(choices)}",
                    )
                )
                raise AdaptiveParseError(
                    f"{stage} expected exactly one of: {', '.join(choices)}"
                )
            self._traces.append(ProbeTrace(stage, user_prompt, raw, label, 0, None))
            return label, float("inf")

        override = self._generation_override(3)
        override["choice_outputs"] = list(choices)
        override["return_choice_scores"] = True
        override["decision_margin_threshold"] = margin_threshold
        response = self.backend.generate(
            user_prompt,
            system=self._probe_system(),
            override=override,
            role=f"perception_{stage}",
        )
        raw = response.text.strip()
        label = self._scalar(raw).upper()
        if label not in choices:
            raise AdaptiveParseError(
                f"{stage} expected one of: {', '.join(choices)}"
            )
        raw_meta = getattr(response, "raw", {}) or {}
        try:
            margin = float(raw_meta.get("choice_margin"))
        except (TypeError, ValueError):
            margin = float("inf")
        if margin < margin_threshold:
            self._traces.append(
                ProbeTrace(
                    stage, user_prompt, raw, "AMBIGUOUS", 0,
                    f"fixed-choice margin {margin:.4f} < {margin_threshold:.4f}",
                )
            )
            return None, margin
        self._traces.append(ProbeTrace(stage, user_prompt, raw, label, 0, None))
        return label, margin

    def _probe(
        self,
        stage: str,
        prompt: str,
        validator: Callable[[str], T],
        *,
        max_new_tokens: int,
        constrain_fixed_choices: bool = True,
        choice_outputs: tuple[str, ...] | None = None,
    ) -> T:
        instruction = self._instruction(stage)
        user_prompt = self._compose_probe_prompt(prompt, instruction)
        last_error = "invalid answer"
        for retry_index in range(self.settings.retry_attempts + 1):
            override = self._generation_override(max_new_tokens)
            fixed_choices = re.findall(r"^\[(-?\d+)\]\s", prompt, flags=re.MULTILINE)
            if choice_outputs is not None:
                override["choice_outputs"] = list(choice_outputs)
            elif constrain_fixed_choices and fixed_choices:
                override["choice_outputs"] = list(dict.fromkeys(fixed_choices))
            response = self.backend.generate(
                user_prompt,
                system=self._probe_system(),
                override=override,
                role=f"perception_{stage}",
            )
            raw = response.text.strip()
            try:
                value = validator(raw)
            except (AdaptiveParseError, ValueError) as exc:
                last_error = str(exc)
                self._traces.append(
                    ProbeTrace(stage, user_prompt, raw, None, retry_index, last_error)
                )
                continue
            normalized = self._display_answer(value)
            self._traces.append(
                ProbeTrace(stage, user_prompt, raw, normalized, retry_index, None)
            )
            return value
        raise AdaptiveParseError(
            f"{stage} failed after {self.settings.retry_attempts + 1} attempt(s): {last_error}"
        )

    def _deterministic_trace(self, stage: str, prompt: str, value: Any) -> None:
        self._traces.append(
            ProbeTrace(
                stage=stage,
                prompt=prompt.strip(),
                raw_text="<deterministic>",
                normalized_answer=self._display_answer(value),
                retry_index=0,
                error=None,
            )
        )

    def _generation_override(self, stage_max: int) -> dict[str, Any]:
        g = self.settings.generation
        return {
            "max_new_tokens": min(g.max_new_tokens, stage_max),
            "temperature": 0.0,
            "repetition_penalty": 1.0,
            "no_repeat_ngram_size": 0,
            "use_cache": g.use_cache,
        }

    def _required_prompt_text(self, filename: str) -> str:
        if self.settings.prompt_dir is None:
            raise AdaptiveParseError("adaptive parser prompt_dir is required")
        path = self.settings.prompt_dir / filename
        try:
            text = path.read_text(encoding="utf-8").strip()
        except FileNotFoundError as exc:
            raise AdaptiveParseError(f"required adaptive prompt is missing: {path}") from exc
        if not text:
            raise AdaptiveParseError(f"required adaptive prompt is empty: {path}")
        return text

    def _probe_system(self) -> str:
        return self._required_prompt_text("probe_system.txt")

    def _instruction(self, stage: str) -> str:
        return self._required_prompt_text(f"{stage}.txt")

    @staticmethod
    def _compose_probe_prompt(context: str, instruction: str) -> str:
        context = context.strip()
        return f"{context}\n\nTASK:\n{instruction.strip()}" if context else f"TASK:\n{instruction.strip()}"

    @staticmethod
    def _source_tokens(text: str) -> tuple[_SourceToken, ...]:
        return tuple(
            _SourceToken(i, m.group(0), m.start(), m.end())
            for i, m in enumerate(re.finditer(r"\w+|[^\w\s]", text, flags=re.UNICODE), start=1)
        )

    @staticmethod
    def _tokens_text(tokens: tuple[_SourceToken, ...]) -> str:
        return "\n".join(f"[{t.index}] {t.text}" for t in tokens)

    @staticmethod
    def _is_word_token(token: _SourceToken) -> bool:
        return bool(re.search(r"\w", token.text, flags=re.UNICODE))

    @classmethod
    def _scalar(cls, raw: str) -> str:
        lines = [line.strip() for line in raw.strip().splitlines() if line.strip()]
        if not lines:
            raise AdaptiveParseError("expected exactly one short answer")

        def clean(value: str) -> str:
            if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"', "`"}:
                value = value[1:-1].strip()
            return re.sub(r"[\s\.\,\:;!\?…]+$", "", value).strip()

        cleaned = [clean(line) for line in lines]
        if any(not value for value in cleaned):
            raise AdaptiveParseError("expected exactly one short answer")
        # Weak generators sometimes repeat the same one-token answer several times.
        # This carries no semantic ambiguity, so collapse only exact-equivalent
        # repetitions. Different answers are still rejected.
        if len({value.casefold() for value in cleaned}) != 1:
            raise AdaptiveParseError("expected exactly one short answer")
        return cleaned[0]

    @classmethod
    def _integer(cls, raw: str) -> int:
        # Weak local models often echo the visual option wrapper (e.g. ``[1]``)
        # or begin an option line and stop after its separator (e.g. ``1 =``).
        # These are format-only artifacts: accept them only when the entire answer
        # contains one integer plus structural punctuation. Never extract a number
        # from explanatory prose such as ``I choose 1`` or ``1 = claim``.
        lines = [line.strip() for line in raw.strip().splitlines() if line.strip()]
        if len(lines) != 1:
            raise AdaptiveParseError("expected one integer option number")
        value = lines[0].replace("−", "-").strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"', "`"}:
            value = value[1:-1].strip()
        match = re.fullmatch(
            r"[\[\(\{]?\s*(-?\d+)\s*[\]\)\}]?\s*[\s\.\,\:;!\?…=]*",
            value,
        )
        if match is None:
            raise AdaptiveParseError("expected one integer option number")
        return int(match.group(1))

    @classmethod
    def _number_choice(cls, raw: str, choices: dict[int, T]) -> T:
        number = cls._integer(raw)
        if number not in choices:
            allowed = ", ".join(str(n) for n in sorted(choices))
            raise AdaptiveParseError(f"expected one option number: {allowed}")
        return choices[number]

    @classmethod
    def _word_choice(cls, raw: str, choices: dict[str, T]) -> T:
        value = cls._scalar(raw).upper().replace("-", "_").replace(" ", "_")
        normalized = {key.upper(): item for key, item in choices.items()}
        if value not in normalized:
            allowed = ", ".join(choices)
            raise AdaptiveParseError(f"expected one English option label: {allowed}")
        return normalized[value]

    @classmethod
    def _label_or_number_choice(
        cls,
        raw: str,
        label_choices: dict[str, T],
        numeric_choices: dict[int, T],
    ) -> T:
        """Prefer English protocol labels; accept legacy numeric fixtures only."""
        try:
            return cls._word_choice(raw, label_choices)
        except AdaptiveParseError:
            return cls._number_choice(raw, numeric_choices)


    @classmethod
    def _english_symbol(cls, raw: str) -> str:
        value = cls._scalar(raw).strip().lower().replace("-", "_").replace(" ", "_")
        value = cls._IRREGULAR_EN.get(value, value)
        if value in {"unknown", "unclear", "none", "predicate", "verb", "na", "n_a"}:
            raise AdaptiveParseError("predicate symbol unresolved")
        if cls._EN_SYMBOL_RE.fullmatch(value) is None:
            raise AdaptiveParseError("expected one lowercase English ASCII predicate label")
        return value

    @staticmethod
    def _display_answer(value: Any) -> str:
        if isinstance(value, ActantRole):
            return value.value
        if isinstance(value, QueryMode):
            return value.value
        if isinstance(value, _Span):
            return value.spec
        return str(value)

    def _predicate_start_choice(
        self,
        raw: str,
        tokens: tuple[_SourceToken, ...],
        excluded: list[_Span],
        candidate_indices: tuple[int, ...] | None = None,
    ) -> int:
        choices = {-2: -2, -1: -1, 0: 0}
        allowed = set(candidate_indices) if candidate_indices else None
        for token in tokens:
            if not self._is_word_token(token):
                continue
            if allowed is not None and token.index not in allowed:
                continue
            if any(span.start_index <= token.index <= span.end_index for span in excluded):
                continue
            choices[token.index] = token.index
        return self._number_choice(raw, choices)

    def _morph_all(self, token: _SourceToken) -> tuple[MorphInfo, ...]:
        key = token.text.casefold()
        if key not in self._morph_all_cache:
            try:
                values = tuple(self.morphology.analyze_all(token.text))
            except AttributeError:
                single = self.morphology.analyze(token.text)
                values = () if single is None else (single,)
            self._morph_all_cache[key] = values
        return self._morph_all_cache[key]

    def _morph(self, token: _SourceToken) -> MorphInfo | None:
        key = token.text.casefold()
        if key not in self._morph_cache:
            values = self._morph_all(token)
            self._morph_cache[key] = values[0] if values else None
        return self._morph_cache[key]

    def _material_morph_analyses(self, token: _SourceToken) -> tuple[MorphInfo, ...]:
        """Return morphology readings strong enough for structural decisions.

        Pymorphy intentionally exposes rare dictionary readings. They remain
        available to semantic disambiguation, but a 0.01% NOUN reading of a
        conjunction must not create a subject or a predicate head. A reading is
        structural when it is reasonably competitive with the best analysis.
        Test morphologies that do not provide scores keep all readings.
        """
        analyses = self._morph_all(token)
        if not analyses:
            return ()
        top = max((item.score for item in analyses), default=0.0)
        if top <= 0.0:
            return analyses
        floor = top * 0.30
        return tuple(item for item in analyses if item.score >= floor)

    def _has_structural_morph(
        self,
        token: _SourceToken,
        *,
        poses: set[str] | None = None,
        case: str | None = None,
    ) -> bool:
        for info in self._material_morph_analyses(token):
            if poses is not None and info.pos not in poses:
                continue
            if case is not None and info.case != case:
                continue
            return True
        return False

    def _has_morph(
        self,
        token: _SourceToken,
        *,
        poses: set[str] | None = None,
        case: str | None = None,
    ) -> bool:
        for info in self._morph_all(token):
            if poses is not None and info.pos not in poses:
                continue
            if case is not None and info.case != case:
                continue
            return True
        return False

    def _predicate_morph_candidates(
        self,
        tokens: tuple[_SourceToken, ...],
        excluded: list[_Span],
    ) -> tuple[int, ...]:
        excluded_positions = {
            i
            for span in excluded
            for i in range(span.start_index, span.end_index + 1)
        }
        if self._candidate_graph is not None:
            available = [
                item for item in self._candidate_graph.predicates
                if item.token_index not in excluded_positions
            ]
            if not available:
                return ()
            clauses_with_candidates = [
                clause
                for clause in self._candidate_graph.clauses
                if any(
                    clause.span.start_index <= item.token_index <= clause.span.end_index
                    for item in available
                )
            ]
            if clauses_with_candidates:
                first_clause = min(clauses_with_candidates, key=lambda c: c.span.start_index)
                available = [
                    item for item in available
                    if first_clause.span.start_index <= item.token_index <= first_clause.span.end_index
                ]
            strongest = max(item.strength for item in available)
            return tuple(item.token_index for item in available if item.strength == strongest)

        tagged: list[tuple[_SourceToken, tuple[MorphInfo, ...]]] = []
        for token in tokens:
            if not self._is_word_token(token) or token.index in excluded_positions:
                continue
            analyses = self._material_morph_analyses(token)
            if analyses:
                tagged.append((token, analyses))
        if not tagged:
            return ()
        tiers = ({"VERB", "PRED"}, {"INFN", "GRND", "ADJS", "PRTS"})
        for positions in tiers:
            matches = tuple(
                token.index
                for token, analyses in tagged
                if any(info.pos in positions for info in analyses)
            )
            if matches:
                return matches
        return ()

    def _deterministic_implicit_copula(
        self,
        tokens: tuple[_SourceToken, ...],
        excluded: list[_Span],
        predicate_candidates: tuple[int, ...],
    ) -> bool:
        if predicate_candidates:
            return False
        available = [
            token for token in tokens
            if self._is_word_token(token)
            and not any(span.start_index <= token.index <= span.end_index for span in excluded)
        ]
        has_subject = any(
            self._has_morph(token, poses={"NOUN", "NPRO"}, case="nomn")
            for token in available
        )
        has_description = any(
            self._has_morph(token, poses={"ADJF", "ADJS", "PRTS", "PRTF", "PRED"})
            for token in available
        )
        return has_subject and has_description

    def _atomic_morph_predicate(
        self,
        index: int,
        tokens: tuple[_SourceToken, ...],
    ) -> bool:
        if index < 1 or index > len(tokens):
            return False
        return self._has_morph(
            tokens[index - 1], poses={"VERB", "PRED", "INFN", "GRND", "ADJS", "PRTS"}
        )

    def _predicate_lemma(
        self,
        tokens: tuple[_SourceToken, ...],
        start: int,
        end: int,
        *,
        act_type: str | None = None,
    ) -> str | None:
        """Choose one source-language predicate lexeme from morphology.

        Dictionary morphology can return equally probable homographs whose
        grammatical features disagree.  Never use analyser order as a semantic
        tie-break.  First constrain by predicate POS, then by sentence force and
        explicit subject-number agreement.  If two distinct lexemes remain
        equally compatible, fail explicitly rather than silently choosing the
        first dictionary reading.
        """
        if start != end:
            return None
        token = tokens[start - 1]
        analyses = self._material_morph_analyses(token)
        for positions in ({"VERB", "PRED"}, {"INFN", "GRND", "ADJS", "PRTS"}):
            candidates = [item for item in analyses if item.pos in positions]
            if not candidates:
                continue

            expected_number = self._explicit_subject_number(tokens, start)

            def compatibility(info: MorphInfo) -> tuple[int, int, float]:
                mood_score = 0
                if act_type == "ASSERTION":
                    if info.mood == "indc":
                        mood_score = 2
                    elif info.mood == "impr":
                        mood_score = -2
                elif act_type == "COMMAND":
                    if info.mood == "impr":
                        mood_score = 2
                    elif info.mood == "indc":
                        mood_score = -1

                number_score = 0
                if expected_number is not None and info.number is not None:
                    number_score = 1 if info.number == expected_number else -1
                return mood_score, number_score, info.score

            best_key = max(compatibility(item) for item in candidates)
            best = [item for item in candidates if compatibility(item) == best_key]
            forms = {item.normal_form.casefold(): item.normal_form for item in best}
            if len(forms) == 1:
                return next(iter(forms.values()))
            raise AdaptiveParseError(
                f"ambiguous predicate morphology: {token.text} -> "
                + ", ".join(sorted(forms.values(), key=str.casefold))
            )
        return analyses[0].normal_form if analyses else None

    def _explicit_subject_number(
        self,
        tokens: tuple[_SourceToken, ...],
        predicate_index: int,
    ) -> str | None:
        """Return structurally explicit subject number for one predicate.

        A coordinated nominative NP is plural even though each member is singular.
        Otherwise use the nearest unambiguous nominative noun/pronoun in the same
        clause before the predicate.  This is grammatical agreement only; it does
        not resolve semantic subject identity.
        """
        graph = self._candidate_graph
        if graph is not None:
            clause = graph.clause_for_token(predicate_index)
            if clause is not None:
                for coordination in graph.coordinations:
                    if (
                        coordination.operator is CoordinationKind.AND
                        and clause.span.start_index <= coordination.span.start_index
                        and coordination.span.end_index < predicate_index
                        and coordination.span.end_index <= clause.span.end_index
                    ):
                        nominative_members = True
                        for member in coordination.member_spans:
                            if not any(
                                self._has_structural_morph(
                                    tokens[i - 1], poses={"NOUN", "NPRO"}, case="nomn"
                                )
                                for i in range(member.start_index, member.end_index + 1)
                            ):
                                nominative_members = False
                                break
                        if nominative_members and len(coordination.member_spans) >= 2:
                            return "plur"
                left = clause.span.start_index
            else:
                left = 1
        else:
            left = 1

        for index in range(predicate_index - 1, left - 1, -1):
            token = tokens[index - 1]
            values = [
                item.number
                for item in self._material_morph_analyses(token)
                if item.pos in {"NOUN", "NPRO"} and item.case == "nomn" and item.number
            ]
            numbers = set(values)
            if len(numbers) == 1:
                return next(iter(numbers))
        return None

    @classmethod
    def _deterministic_predicate_symbol(cls, lemma: str | None) -> str | None:
        if lemma is None or not lemma.strip():
            return None
        # Predicate S is a language-level lexical symbol, not an English semantic
        # label.  Using the source-language normal form makes predicate recognition
        # converge with TextSensoryService on the same <UID, R_text> symbol instead
        # of creating parallel ``читает``/``read`` or ``написал``/``write`` trees.
        return lemma.strip().casefold()

    @classmethod
    def _canonical_predicate_form(cls, lemma: str | None, surface: str) -> str:
        lexical = cls._deterministic_predicate_symbol(lemma)
        if lexical is not None:
            return lexical
        normalized_surface = " ".join(surface.strip().casefold().split())
        if not normalized_surface:
            raise AdaptiveParseError("predicate has no lexical form")
        return normalized_surface

    @classmethod
    def _resolve_span(
        cls,
        text: str,
        tokens: tuple[_SourceToken, ...],
        start: int,
        end: int,
    ) -> _Span:
        if start < 1 or end < start or end > len(tokens):
            raise AdaptiveParseError(f"span {start}-{end} outside token range")
        first = tokens[start - 1]
        last = tokens[end - 1]
        value = text[first.start:last.end]
        return _Span(start, end, value, EvidenceSpan(value, first.start, last.end))

    @staticmethod
    def _span_contains(span: _Span | None, index: int) -> bool:
        return span is not None and span.start_index <= index <= span.end_index

    @classmethod
    def _predicate_end_choices(
        cls,
        text: str,
        tokens: tuple[_SourceToken, ...],
        start: int,
        excluded: list[_Span],
    ) -> dict[int, int]:
        choices: dict[int, int] = {}
        for index in range(start, len(tokens) + 1):
            token = tokens[index - 1]
            if index != start and any(span.start_index <= index <= span.end_index for span in excluded):
                break
            if index != start and token.text in _STRONG_BOUNDARY:
                break
            if cls._is_word_token(token) and token.text.casefold() not in _COORDINATORS:
                choices[index] = index
        if start not in choices:
            choices[start] = start
        return choices

    @classmethod
    def _actant_start_choices(
        cls,
        tokens: tuple[_SourceToken, ...],
        predicate: _Span | None,
        selected: list[_Span],
        *,
        requested_span: _Span | None,
    ) -> tuple[int, ...]:
        result: list[int] = []
        for token in tokens:
            if not cls._is_word_token(token):
                continue
            if token.text.casefold() in _COORDINATORS:
                continue
            if cls._span_contains(predicate, token.index):
                continue
            if cls._span_contains(requested_span, token.index):
                continue
            if any(span.start_index <= token.index <= span.end_index for span in selected):
                continue
            result.append(token.index)
        return tuple(result)

    @classmethod
    def _actant_end_choices(
        cls,
        text: str,
        tokens: tuple[_SourceToken, ...],
        start: int,
        predicate: _Span | None,
        selected: list[_Span],
        *,
        requested_span: _Span | None,
    ) -> dict[int, int]:
        choices: dict[int, int] = {}
        for index in range(start, len(tokens) + 1):
            token = tokens[index - 1]
            if index != start and cls._span_contains(predicate, index):
                break
            if index != start and cls._span_contains(requested_span, index):
                break
            if index != start and any(span.start_index <= index <= span.end_index for span in selected):
                break
            if index != start and token.text in _STRONG_BOUNDARY:
                break
            if cls._is_word_token(token) and token.text.casefold() not in _COORDINATORS:
                choices[index] = index
        if start not in choices:
            choices[start] = start
        return choices

    @classmethod
    def _validate_actant_span(
        cls,
        candidate: _Span,
        predicate: _Span | None,
        selected: list[_Span],
        requested_span: _Span | None,
    ) -> None:
        if predicate is not None and candidate.overlaps(predicate):
            raise AdaptiveParseError("actant overlaps predicate")
        if requested_span is not None and candidate.overlaps(requested_span):
            raise AdaptiveParseError("actant overlaps the question-word placeholder")
        if any(candidate.overlaps(span) for span in selected):
            raise AdaptiveParseError("actant overlaps an already selected actant")

    def _deterministic_negation(
        self,
        tokens: tuple[_SourceToken, ...],
        predicate: _Span | None,
    ) -> bool | None:
        # Negation is predicate-frame scoped. A marker attached to a matrix or
        # neighbouring coordinated predicate must never leak into this frame.
        # Candidate-graph clause bounds are further narrowed around coordinated
        # predicate heads before any LLM ambiguity probe is allowed.
        clause_start, clause_end = self._predicate_argument_bounds(predicate, tokens)

        markers = [
            token
            for token in tokens
            if clause_start <= token.index <= clause_end
            and token.text.casefold() in _NEGATION_MARKERS
        ]
        if not markers:
            return False

        if predicate is not None:
            previous = predicate.start_index - 1
            if (
                previous >= clause_start
                and tokens[previous - 1].text.casefold() == "не"
            ):
                return True
            if any(
                token.text.casefold() == "не"
                and predicate.start_index <= token.index <= predicate.end_index
                for token in markers
            ):
                return True

        if any(token.text.casefold() == "нет" for token in markers):
            return True

        # Other negative pronouns/adverbs inside this clause can interact with
        # predicate scope; only then is a tiny local LLM probe permitted.
        return None

    @staticmethod
    def _options_lines(options: dict[int, str]) -> str:
        return "\n".join(f"[{number}] {description}" for number, description in options.items())

    @staticmethod
    def _label_options_lines(options: dict[str, str]) -> str:
        return "\n".join(f"{label}: {description}" for label, description in options.items())

    def _act_type_prompt(self, text: str, tokens: tuple[_SourceToken, ...], excluded: list[_Span]) -> str:
        options = {
            "NONE": "none or unclear",
            "ASSERTION": "states information as a claim/fact",
            "QUERY": "asks for information",
            "COMMAND": "requests or orders an action",
        }
        focus = text
        graph = self._candidate_graph
        if graph is not None:
            excluded_positions = {
                i for span in excluded for i in range(span.start_index, span.end_index + 1)
            }
            remaining = [p for p in graph.predicates if p.token_index not in excluded_positions]
            if remaining:
                sentence_ids = [
                    clause.sentence_id
                    for p in remaining
                    if (clause := graph.clause_for_token(p.token_index)) is not None
                ]
                if sentence_ids:
                    sentence_id = min(sentence_ids)
                    clauses = [c for c in graph.clauses if c.sentence_id == sentence_id]
                    if clauses:
                        start_i = min(c.span.start_index for c in clauses)
                        end_i = max(c.span.end_index for c in clauses)
                        focus = self._resolve_span(text, tokens, start_i, end_i).text
        lines = [f"TEXT:\n{focus}"]
        lines.append("OPTIONS:\n" + self._label_options_lines(options))
        return "\n".join(lines)

    def _predicate_start_prompt(
        self,
        text: str,
        tokens: tuple[_SourceToken, ...],
        excluded: list[_Span],
        candidate_indices: tuple[int, ...] | None = None,
    ) -> str:
        options: dict[int, str] = {
            -2: "cannot choose reliably from the shown candidates",
            -1: "no meaningful predicate exists",
            0: "predicate is understood but not written as a token",
        }
        allowed = set(candidate_indices) if candidate_indices else None
        for token in tokens:
            if not self._is_word_token(token):
                continue
            if allowed is not None and token.index not in allowed:
                continue
            if any(span.start_index <= token.index <= span.end_index for span in excluded):
                continue
            info = self._morph(token)
            suffix = f"; morphology={info.pos}" if info is not None and info.pos else ""
            options[token.index] = f"token {token.index}: {token.text}{suffix}"
        lines = [f"TEXT:\n{text}", f"TOKENS:\n{self._tokens_text(tokens)}", "OPTIONS:\n" + self._options_lines(options)]
        return "\n".join(lines)

    def _predicate_end_prompt(
        self,
        text: str,
        tokens: tuple[_SourceToken, ...],
        start: int,
        choices: dict[int, int],
    ) -> str:
        options = {0: "cannot determine the predicate boundary reliably"}
        options.update({
            end: f"end at token {end}: {self._resolve_span(text, tokens, start, end).text}"
            for end in choices
        })
        return (
            f"TEXT:\n{text}\nTOKENS:\n{self._tokens_text(tokens)}\n"
            f"PREDICATE_START: [{start}] {tokens[start - 1].text}\nOPTIONS:\n{self._options_lines(options)}"
        )

    def _predicate_local_text(
        self,
        text: str,
        tokens: tuple[_SourceToken, ...],
        predicate_span: _Span | None,
    ) -> str:
        if predicate_span is None or self._candidate_graph is None:
            return text
        start, end = self._predicate_argument_bounds(predicate_span, tokens)
        return self._resolve_span(text, tokens, start, end).text

    def _predicate_symbol_prompt(
        self,
        text: str,
        tokens: tuple[_SourceToken, ...],
        predicate_span: _Span | None,
        target: str,
        *,
        implicit: bool,
        lemma: str | None = None,
    ) -> str:
        local_text = self._predicate_local_text(text, tokens, predicate_span)
        marker = "implicit predicate" if implicit else target
        lines = [f"TEXT:\n{local_text}", f"TARGET:\n{marker}"]
        if lemma:
            lines.append(f"RUSSIAN_LEMMA:\n{lemma}")
        return "\n".join(lines)

    @staticmethod
    def _predicate_symbol_verify_prompt(text: str, target: str, candidate: str) -> str:
        return (
            f"TEXT:\n{text}\nTARGET:\n{target}\nCANDIDATE:\n{candidate}\nOPTIONS:\n"
            "NO_MATCH: meaning does not match or is unclear\n"
            "MATCH: meaning matches TARGET in TEXT"
        )

    @staticmethod
    def _negation_prompt(text: str, predicate: PredicateCandidate) -> str:
        return (
            f"TEXT:\n{text}\nPREDICATE:\n{predicate.surface}\nOPTIONS:\n"
            "NO: not negated\n"
            "YES: explicitly negated\n"
            "UNKNOWN: cannot determine negation reliably"
        )

    @staticmethod
    def _query_mode_prompt(text: str, predicate: PredicateCandidate) -> str:
        return (
            f"TEXT:\n{text}\nPREDICATE:\n{predicate.surface}\nOPTIONS:\n"
            "UNKNOWN: cannot determine the question type reliably\n"
            "EXISTS: asks whether the proposition is true / exists (yes-no)\n"
            "FILL_ROLE: asks for one missing participant, property, circumstance, place, time, cause, purpose, manner, or amount"
        )

    def _actant_start_prompt(
        self,
        text: str,
        tokens: tuple[_SourceToken, ...],
        predicate: _Span | None,
        selected: list[_Span],
        choices: dict[int, int],
        requested_span: _Span | None,
    ) -> str:
        options: dict[int, str] = {0: "no more relevant phrase remains"}
        for number in choices:
            if number == 0:
                continue
            options[number] = f"token {number}: {tokens[number - 1].text}"
        lines = [f"TEXT:\n{text}", f"TOKENS:\n{self._tokens_text(tokens)}"]
        if predicate is not None:
            lines.append(f"PREDICATE: {predicate.text}")
        if selected:
            lines.append("ALREADY_SELECTED: " + " | ".join(span.text for span in selected))
        if requested_span is not None:
            lines.append("QUESTION_PLACEHOLDER: " + requested_span.text + " (do not select it as known information)")
        lines.append("OPTIONS:\n" + self._options_lines(options))
        return "\n".join(lines)

    def _actant_end_prompt(
        self,
        text: str,
        tokens: tuple[_SourceToken, ...],
        start: int,
        choices: dict[int, int],
    ) -> str:
        options = {
            end: f"end at token {end}: {self._resolve_span(text, tokens, start, end).text}"
            for end in choices
        }
        return (
            f"TEXT:\n{text}\nTOKENS:\n{self._tokens_text(tokens)}\n"
            f"ACTANT_START: {start} = {tokens[start - 1].text}\nOPTIONS:\n{self._options_lines(options)}"
        )

    @staticmethod
    def _role_family_binary_prompt(
        text: str,
        predicate: PredicateCandidate,
        span: _Span,
        group_name: str,
        *,
        requested: bool,
    ) -> str:
        mode = "MISSING INFORMATION" if requested else "TARGET"
        return (
            f"TEXT:\n{text}\nPREDICATE:\n{predicate.surface}\n{mode}:\n{span.text}\n"
            f"CANDIDATE FAMILY:\n{group_name.upper()}\n"
            f"FAMILY MEANING:\n{_ROLE_FAMILY_DESCRIPTIONS[group_name]}\n"
            "QUESTION:\nDoes the target belong to this role family in this sentence?"
        )

    @classmethod
    def _role_exact_binary_prompt(
        cls,
        text: str,
        predicate: PredicateCandidate,
        span: _Span,
        group_name: str,
        role: ActantRole,
        description: str,
        *,
        requested: bool,
    ) -> str:
        mode = "MISSING INFORMATION" if requested else "TARGET"
        return (
            f"TEXT:\n{text}\nPREDICATE:\n{predicate.surface}\n{mode}:\n{span.text}\n"
            f"CANDIDATE ROLE:\n{cls._template_role_label(role)}\n"
            f"ROLE MEANING:\n{description}\n"
            "QUESTION:\nDoes the target have this role in this sentence?"
        )

    @staticmethod
    def _requested_role_prompt(text: str, predicate: PredicateCandidate, span: _Span) -> str:
        return f"TEXT:\n{text}\nPREDICATE:\n{predicate.surface}\nQUESTION_WORD:\n{span.text}"
