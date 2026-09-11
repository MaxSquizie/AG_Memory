from __future__ import annotations

from dataclasses import dataclass, replace
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Protocol, TypeVar
import re

from ah.config import LLMRoleSettings
from ah.llm.process_backend import LLMResponse
from ah.model import ActantRole
from ah.temporal import TemporalMode, TransitionOperator

from .morphology import (
    MorphInfo,
    Morphology,
    build_morphology,
    material_analyses,
    stable_normal_form,
    stable_transitivity,
)
from .event_normalizer import EventNormalizer
from .quantifier_formalization import (
    QuantifierFormalizationError,
    QuantifierFormalizer,
)
from .lexical_recovery import (
    LexicalRecovery,
    LexicalRecoveryStatus,
    SemanticCandidateReranker,
)
from .linguistic_candidates import (
    CoordinationKind,
    EllipsisKind,
    FrameDependencyKind,
    LinguisticCandidateBuilder,
    LinguisticCandidateGraph,
    PredicateHeadCandidate,
)

from .contracts import (
    ActDependencyCandidate,
    ActDependencyKind,
    ActRelationCandidate,
    ActantCandidate,
    NominalRelationCandidate,
    NominalRelationKind,
    ActantCompositionCandidate,
    CompositionMemberCandidate,
    CompositionOperator,
    AssertionCandidate,
    AssertionStatus,
    ConditionalCandidate,
    CommandCandidate,
    DiscourseRelationDecision,
    EvidenceSpan,
    PerceptionResult,
    PredicateCandidate,
    PropositionExprCandidate,
    PropositionOperator,
    QuantifierProbeDecision,
    TemplateCandidate,
    QueryCandidate,
    QueryMode,
    SituationRelationCandidate,
    SituationRelationHintCandidate,
    SituationRelationHintKind,
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


class RuntimeRoleCue(str, Enum):
    """Non-canonical semantic cue returned by the perception model.

    These labels never enter AH.  They are an adapter protocol between one
    bounded semantic decision and deterministic Python mapping to ActantRole.
    """

    ACTOR_OR_EXPERIENCER = "ACTOR_OR_EXPERIENCER"
    AFFECTED_OR_CONTENT = "AFFECTED_OR_CONTENT"
    RECEIVER_OR_ADDRESSEE = "RECEIVER_OR_ADDRESSEE"
    ORIGIN = "ORIGIN"
    ABSENT_ENTITY = "ABSENT_ENTITY"
    SECONDARY_PARTICIPANT = "SECONDARY_PARTICIPANT"
    PLACE = "PLACE"
    PREDICATED_STATE = "PREDICATED_STATE"
    TIME_POINT = "TIME_POINT"
    ELAPSED_DURATION = "ELAPSED_DURATION"
    CAUSE = "CAUSE"
    INTENDED_GOAL = "INTENDED_GOAL"
    INSTRUMENT = "INSTRUMENT"
    CONSTITUENT_MATERIAL = "CONSTITUENT_MATERIAL"
    QUANTITY_OR_MEASURE = "QUANTITY_OR_MEASURE"
    MANNER_OR_PROCEDURE = "MANNER_OR_PROCEDURE"
    TRANSITION_OPERATOR = "TRANSITION_OPERATOR"


@dataclass(frozen=True, slots=True)
class AdaptiveSettings:
    prompt_dir: Path | None
    generation: LLMRoleSettings
    retry_attempts: int = 1
    max_actants_per_act: int = 8
    predicate_symbol_language: str = "en"
    morphology_backend: str = "auto"
    verify_predicate_symbol: bool = True

    def __post_init__(self) -> None:
        if self.retry_attempts < 0 or self.retry_attempts > 2:
            raise ValueError("retry_attempts must be in [0, 2]")
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
class AdaptiveTemplateSenseResult:
    choice_label: str | None
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
    raw_text: str | None = None


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


class _AttachmentTargetKind(str, Enum):
    PREDICATE = "PREDICATE"
    NOMINAL = "NOMINAL"


@dataclass(frozen=True, slots=True)
class _AttachmentTarget:
    kind: _AttachmentTargetKind
    key: str
    label: str
    nominal_span: _Span | None = None


@dataclass(frozen=True, slots=True)
class _PendingNominalModifier:
    owner_span: _Span
    modifier_span: _Span
    predicate: PredicateCandidate
    modifier_role: ActantRole


@dataclass(frozen=True, slots=True)
class _RelativeAntecedentCandidate:
    span: _Span
    assertion_id: str | None = None
    actant: ActantCandidate | None = None


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

# Historical private names are kept as protocol-label aliases so older regression
# fixtures can describe the same semantic outcomes without reintroducing the removed
# likelihood-completion runtime path.
_EVENT_RECIPIENT_COMPLETION = "HAS_RECIPIENT_SLOT"
_EVENT_SOURCE_COMPLETION = "HAS_SOURCE_SLOT"
_EVENT_NONE_COMPLETION = "NO_RECIPIENT_SLOT"

_DISCOURSE_FOLLOW_MARKERS = frozenset({"потом", "затем", "после этого"})

_ROLE_GROUPS: dict[str, tuple[tuple[ActantRole, str], ...]] = {
    "participant": (
        (
            ActantRole.SUBJECT,
            "TARGET is the actor, holder, experiencer, or entity whose state/action PREDICATE describes; being the person something is given/sent/shown/said TO does not by itself make TARGET SUBJECT",
        ),
        (
            ActantRole.OBJECT,
            "TARGET is the direct semantic target: an entity/content affected, perceived, possessed, selected, summoned, or referred to by PREDICATE; a person can be OBJECT when the action directly targets that person (for example, someone is summoned/selected/seen), not when the person is merely the addressee contacted by speech, telephone, or messaging",
        ),
        (
            ActantRole.RECIPIENT,
            "TARGET is the receiver/addressee/beneficiary/destination that receives an object, information, communication, or benefit; this includes the person being addressed or contacted by speech, telephone, or messaging even when no separate message OBJECT is stated; mere personhood does not make TARGET a RECIPIENT, and a person directly seen/met/summoned/selected is normally the direct semantic target instead",
        ),
        (
            ActantRole.SOURCE,
            "TARGET is the origin from which another participant, object, or information comes, moves, is removed, or is obtained; TARGET does not become a constituent of the result",
        ),
        (
            ActantRole.ABSENTEE,
            "TARGET itself is explicitly represented as absent from, excluded from, or not participating in the event (for example, the event happens without TARGET); ordinary negation of the predicate/event or contrastive negation of another filler does NOT make TARGET an absentee",
        ),
        (
            ActantRole.AUXILLIARY,
            "TARGET is a secondary co-participant that is not the actor, direct object, receiver, source, or absent entity",
        ),
    ),
    "description": (
        (
            ActantRole.STATE,
            "TARGET is a property, condition, class, status, or value predicated of a participant",
        ),
        (
            ActantRole.LOCATION,
            "TARGET specifies where or to what place the event/participant is located or moves; it is not the origin it comes from",
        ),
        (
            ActantRole.TIME,
            "TARGET locates the event on a timeline and answers when it happens; it does not describe how the event is performed",
        ),
        (
            ActantRole.DURATION,
            "TARGET specifies the elapsed temporal length of the event/state and answers how long it lasts",
        ),
        (
            ActantRole.AMOUNT,
            "TARGET specifies quantity, count, size, degree, or non-temporal measure; it is not elapsed duration",
        ),
    ),
    "circumstance": (
        (
            ActantRole.CAUSE,
            "TARGET is the reason or prior circumstance that causes/explains why the event happens",
        ),
        (
            ActantRole.PURPOSE,
            "TARGET is the intended goal or result for which the event is performed",
        ),
        (
            ActantRole.TOOL,
            "TARGET is an instrument or tool used as a separate implement/device/object to perform the event; it remains an instrument rather than becoming material of the result",
        ),
        (
            ActantRole.MATERIAL,
            "TARGET is a substance or material constituent/component from which an affected or resulting entity is made, formed, or composed; it is not a separate implement and not an origin of motion",
        ),
        (
            ActantRole.HOW_TO,
            "TARGET describes the manner, procedure, or method by which the event is carried out, rather than naming a separate tool or constituent material; a concrete implement such as a hammer/pencil/key is TOOL",
        ),
    ),
}

_TEMPLATE_ROLE_DESCRIPTIONS: dict[ActantRole, str] = {
    role: description
    for entries in _ROLE_GROUPS.values()
    for role, description in entries
}

# Runtime role selection is one bounded semantic decision about one TARGET.
# The model returns a runtime semantic cue, never a canonical ActantRole or AH
# element. Python owns the one-to-one cue -> canonical role mapping.  This
# deliberately replaces the lossy family/decision-tree routers: repeated
# intermediate A/B decisions compounded semantic error and could discard the
# correct role before it was ever compared directly.
_ROLE_CUE_SPECS: tuple[tuple[RuntimeRoleCue, ActantRole, str], ...] = (
    (RuntimeRoleCue.ACTOR_OR_EXPERIENCER, ActantRole.SUBJECT, _TEMPLATE_ROLE_DESCRIPTIONS[ActantRole.SUBJECT]),
    (RuntimeRoleCue.AFFECTED_OR_CONTENT, ActantRole.OBJECT, _TEMPLATE_ROLE_DESCRIPTIONS[ActantRole.OBJECT]),
    (RuntimeRoleCue.RECEIVER_OR_ADDRESSEE, ActantRole.RECIPIENT, _TEMPLATE_ROLE_DESCRIPTIONS[ActantRole.RECIPIENT]),
    (RuntimeRoleCue.ORIGIN, ActantRole.SOURCE, _TEMPLATE_ROLE_DESCRIPTIONS[ActantRole.SOURCE]),
    (RuntimeRoleCue.ABSENT_ENTITY, ActantRole.ABSENTEE, _TEMPLATE_ROLE_DESCRIPTIONS[ActantRole.ABSENTEE]),
    (RuntimeRoleCue.SECONDARY_PARTICIPANT, ActantRole.AUXILLIARY, _TEMPLATE_ROLE_DESCRIPTIONS[ActantRole.AUXILLIARY]),
    (RuntimeRoleCue.PLACE, ActantRole.LOCATION, _TEMPLATE_ROLE_DESCRIPTIONS[ActantRole.LOCATION]),
    (RuntimeRoleCue.PREDICATED_STATE, ActantRole.STATE, _TEMPLATE_ROLE_DESCRIPTIONS[ActantRole.STATE]),
    (RuntimeRoleCue.TIME_POINT, ActantRole.TIME, _TEMPLATE_ROLE_DESCRIPTIONS[ActantRole.TIME]),
    (RuntimeRoleCue.ELAPSED_DURATION, ActantRole.DURATION, _TEMPLATE_ROLE_DESCRIPTIONS[ActantRole.DURATION]),
    (RuntimeRoleCue.CAUSE, ActantRole.CAUSE, _TEMPLATE_ROLE_DESCRIPTIONS[ActantRole.CAUSE]),
    (RuntimeRoleCue.INTENDED_GOAL, ActantRole.PURPOSE, _TEMPLATE_ROLE_DESCRIPTIONS[ActantRole.PURPOSE]),
    (RuntimeRoleCue.INSTRUMENT, ActantRole.TOOL, _TEMPLATE_ROLE_DESCRIPTIONS[ActantRole.TOOL]),
    (RuntimeRoleCue.CONSTITUENT_MATERIAL, ActantRole.MATERIAL, _TEMPLATE_ROLE_DESCRIPTIONS[ActantRole.MATERIAL]),
    (RuntimeRoleCue.QUANTITY_OR_MEASURE, ActantRole.AMOUNT, _TEMPLATE_ROLE_DESCRIPTIONS[ActantRole.AMOUNT]),
    (RuntimeRoleCue.MANNER_OR_PROCEDURE, ActantRole.HOW_TO, _TEMPLATE_ROLE_DESCRIPTIONS[ActantRole.HOW_TO]),
)
_ROLE_CUE_TO_ROLE: dict[RuntimeRoleCue, ActantRole] = {
    cue: role for cue, role, _description in _ROLE_CUE_SPECS
}
_ROLE_TO_CUE: dict[ActantRole, RuntimeRoleCue] = {
    role: cue for cue, role, _description in _ROLE_CUE_SPECS
}

# WH morphology is evidence about the surface question form, not a canonical
# semantic role.  In particular, grammatical nominative ``кто`` can denote the
# semantic OBJECT of a passive predicate (``кто был побеждён?``).  Requested AH
# roles are therefore resolved by the same bounded semantic relation probe as
# ordinary actants; prepositions/case may narrow impossibilities but never assign
# SUBJECT/OBJECT/RECIPIENT/etc. by themselves.
_QUESTION_WORDS = {
    "кто", "кого", "кому", "кем", "что", "чего", "чему", "чем",
    "где", "куда", "откуда", "когда", "сколько", "почему", "отчего", "зачем", "как",
}
_NEGATION_MARKERS = {"не", "нет", "никогда", "никто", "ничто", "никак", "нигде"}
_COORDINATORS = {"и", "или", "либо", "а", "но"}
_STRONG_BOUNDARY = {".", "!", "?", ";", ":"}
_SPATIAL_RELATION_ADVERBS = {"рядом", "близко", "неподалёку", "неподалеку"}

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
        semantic_reranker: SemanticCandidateReranker | None = None,
    ) -> None:
        self.backend = backend
        self.settings = settings
        self.morphology = morphology or build_morphology(settings.morphology_backend)
        self.semantic_reranker = semantic_reranker
        self._traces: list[ProbeTrace] = []
        self._morph_cache: dict[str, MorphInfo | None] = {}
        self._morph_all_cache: dict[str, tuple[MorphInfo, ...]] = {}
        self._candidate_graph: LinguisticCandidateGraph | None = None
        self._active_implicit_clause_id: str | None = None
        self._entity_ref_counter = 0
        self._structural_resolution: str | None = None
        self._pending_nominal_modifiers: list[_PendingNominalModifier] = []
        self._runtime_compositions: dict[
            tuple[int, int], tuple[CoordinationKind, tuple[_Span, ...]]
        ] = {}
        # Per-utterance contextual lexical narrowing. Dictionary morphology may
        # expose several materially plausible lexemes for the same surface token.
        # The analyser score is evidence, not truth; a tiny A/B semantic probe may
        # select one lexeme before syntax/canonical identity consumes its features.
        self._contextual_nominal_lemmas: dict[int, str] = {}
        self._genitive_attachment_cache: dict[tuple[int, int, int], bool] = {}
        self._postnominal_possessive_cache: dict[tuple[int, int, int], bool] = {}
        self._asserted_nonfinite_refs: set[str] = set()
        self._classified_nonfinite_pairs: set[tuple[str, str]] = set()
        self._scoped_nonfinite_pairs: set[tuple[str, str]] = set()
        self._transition_classified_refs: set[str] = set()
        self._transition_cue_token_indices: set[int] = set()

    def classify_act_relation(
        self,
        source_text: str,
        act_ref: str,
        predicate: PredicateCandidate,
        actants: tuple[ActantCandidate, ...],
    ) -> ActRelationCandidate | None:
        """Classify one already-parsed act as a known structural relation.

        Python first narrows possible endpoints from semantic roles. The model only
        decides whether the proposition/query expresses the already-registered
        taxonomic relation IS-A and, if so, its orientation. No surface keyword is
        an authority signal and no canonical UID is exposed.
        """
        if not act_ref.strip():
            raise AdaptiveParseError("act relation classification requires local act ref")

        endpoint_roles = {
            ActantRole.SUBJECT, ActantRole.OBJECT, ActantRole.AUXILLIARY, ActantRole.STATE
        }
        direct = [
            item for item in actants
            if item.role in endpoint_roles
            and item.candidate_ref is None
            and item.proposition is None
            and item.composition is None
            and (item.lookup_text is not None or item.entity_ref is not None)
        ]
        if len(direct) < 2:
            return None

        # Roles are canonical semantic slots and CandidateValidator requires them
        # to be unique inside one act, so role pairs are stable local endpoints.
        pairs: list[tuple[ActantRole, ActantRole, str, str]] = []
        for source in direct:
            for target in direct:
                if source.role is target.role:
                    continue
                source_text_value = source.lookup_text or source.entity_ref or source.role.value
                target_text_value = target.lookup_text or target.entity_ref or target.role.value
                pairs.append((source.role, target.role, source_text_value, target_text_value))
        if not pairs:
            return None

        labels: dict[str, tuple[ActantRole, ActantRole]] = {}
        option_lines = [
            "NONE: this act does not state/ask a taxonomic class-membership or subtype relation"
        ]
        for index, (source_role, target_role, source_value, target_value) in enumerate(pairs, 1):
            label = f"R{index}"
            labels[label] = (source_role, target_role)
            option_lines.append(
                f"{label}: {source_role.value}={source_value!r} IS-A "
                f"{target_role.value}={target_value!r}"
            )

        prompt = (
            f"TEXT:\n{source_text}\n"
            f"PREDICATE:\n{predicate.surface}\n"
            "SEMANTIC ARGUMENTS:\n"
            + "\n".join(
                f"{item.role.value} = {item.lookup_text or item.entity_ref or '?'}"
                for item in direct
            )
            + "\nQUESTION:\nDoes this semantic act itself state or ask that one listed "
              "referent is an instance/member/subtype of another listed class/type? "
              "Do not choose IS-A for a temporary state, job/role, attribute, location, "
              "possession, event participation, comparison, naming, or ordinary predicate.\n"
            + "CHOICES:\n" + "\n".join(option_lines)
        )
        choice, _ = self._exact_choice_probe(
            "act_relation", prompt, tuple(["NONE", *labels.keys()])
        )
        if choice == "NONE":
            return None
        source_role, target_role = labels[choice]
        return ActRelationCandidate("IS-A", act_ref, source_role, target_role)

    def classify_discourse_relation(
        self,
        narrative_context: str,
        prior_events: tuple[str, ...],
        current_events: tuple[str, ...],
        *,
        excluded_pairs: tuple[tuple[int, int], ...] = (),
    ) -> DiscourseRelationDecision | None:
        """Select one source-grounded cross-turn CAUSE/FOLLOW relation.

        Candidate generation is deliberately outside the model: callers provide a
        bounded narrative window plus semantic strings for canonical events that
        are already cognitively accessible.  This method never sees AH refs.  The
        model performs three small choices only: which current event has a direct
        discourse dependency, which prior event is its source, and whether that
        dependency is CAUSE or FOLLOW.  NONE/UNCLEAR fails closed.

        ``excluded_pairs`` addresses the supplied option lists by zero-based local
        indexes.  It lets deterministic orchestration avoid asking for a relation
        already materialized without exposing canonical identity.
        """
        self._traces = []
        if not narrative_context.strip() or not prior_events or not current_events:
            return None

        excluded = set(excluded_pairs)
        current_available = tuple(
            index for index in range(len(current_events))
            if any((prior, index) not in excluded for prior in range(len(prior_events)))
        )
        if not current_available:
            return None

        prior_lines = "\n".join(
            f"P{index + 1}: {text}" for index, text in enumerate(prior_events)
        )
        current_lines = "\n".join(
            f"C{index + 1}: {text}" for index, text in enumerate(current_events)
        )
        excluded_lines = "\n".join(
            f"P{prior + 1} -> C{current + 1}"
            for prior, current in sorted(excluded)
            if 0 <= prior < len(prior_events) and 0 <= current < len(current_events)
        ) or "none"

        current_labels = tuple(f"C{index + 1}" for index in current_available)
        current_choices = (*current_labels, "NONE", "UNCLEAR")
        current_prompt = (
            f"NARRATIVE WINDOW:\n{narrative_context}\n"
            f"PRIOR ACTIVE EVENTS:\n{prior_lines}\n"
            f"CURRENT EVENTS:\n{current_lines}\n"
            f"ALREADY EXCLUDED PAIRS:\n{excluded_lines}\n"
            "QUESTION:\nWhich CURRENT event, if any, is presented as having one direct "
            "cross-turn dependency on a PRIOR ACTIVE event? Select a current event only "
            "for a direct causal reaction/result or a direct continuation/next phase of "
            "an earlier activity. Same actor, same topic, or mere later occurrence is not enough.\n"
            "CHOICES:\n" + "\n".join(current_choices)
        )
        current_label, _ = self._deep_semantic_choice_probe(
            "discourse_current_event",
            current_prompt,
            current_choices,
            optional=True,
        )
        if current_label in {None, "NONE", "UNCLEAR"}:
            return None
        current_index = int(current_label[1:]) - 1

        prior_available = tuple(
            index for index in range(len(prior_events))
            if (index, current_index) not in excluded
        )
        if not prior_available:
            return None
        prior_choices = tuple(f"P{index + 1}" for index in prior_available) + (
            "NONE", "UNCLEAR"
        )
        source_prompt = (
            f"NARRATIVE WINDOW:\n{narrative_context}\n"
            f"SELECTED CURRENT EVENT:\nC{current_index + 1}: {current_events[current_index]}\n"
            f"PRIOR ACTIVE EVENTS:\n{prior_lines}\n"
            f"ALREADY EXCLUDED PAIRS:\n{excluded_lines}\n"
            "QUESTION:\nWhich ONE PRIOR event is the source of the direct cross-turn "
            "dependency for the selected current event? Prefer the narratively established "
            "initiating event/activity rather than a merely more recent incidental step. "
            "Choose NONE if no listed prior event has that relation.\n"
            "CHOICES:\n" + "\n".join(prior_choices)
        )
        prior_label, _ = self._deep_semantic_choice_probe(
            "discourse_prior_event",
            source_prompt,
            prior_choices,
            optional=True,
        )
        if prior_label in {None, "NONE", "UNCLEAR"}:
            return None
        prior_index = int(prior_label[1:]) - 1

        pair_prompt = (
            f"NARRATIVE WINDOW:\n{narrative_context}\n"
            f"PRIOR EVENT:\n{prior_events[prior_index]}\n"
            f"CURRENT EVENT:\n{current_events[current_index]}\n"
            "QUESTION:\nWhat direct relation, if any, does the narrative establish from "
            "PRIOR EVENT to CURRENT EVENT?\n"
            "CAUSE: CURRENT is a reaction, response, consequence, or result triggered by PRIOR.\n"
            "FOLLOW: CURRENT is a direct continuation/next phase of PRIOR, without asserting causation.\n"
            "NO_RELATION: the events are only in the same narrative/episode or merely ordered in time.\n"
            "UNCLEAR: the text does not determine the relation safely.\n"
            "CHOICES:\nCAUSE\nFOLLOW\nNO_RELATION\nUNCLEAR"
        )
        relation, _ = self._deep_semantic_choice_probe(
            "discourse_relation",
            pair_prompt,
            ("CAUSE", "FOLLOW", "NO_RELATION", "UNCLEAR"),
            optional=True,
        )
        if relation not in {"CAUSE", "FOLLOW"}:
            return None
        return DiscourseRelationDecision(relation, prior_index, current_index)

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

    def resolve_template_sense(
        self,
        source_text: str,
        predicate: PredicateCandidate,
        filled_roles: tuple[ActantRole, ...],
        role_bindings: tuple[tuple[ActantRole, str], ...],
        options: tuple[tuple[str, str], ...],
    ) -> AdaptiveTemplateSenseResult:
        """Choose one local existing T profile, NEW, or explicit ambiguity.

        Canonical UIDs are deliberately absent. Integration builds UID-free usage
        profiles, the model returns one exact local label, and deterministic
        orchestration maps that label back to a T. ``sense_hint`` is only an
        additional semantic cue; it never becomes a canonical identity key.
        """
        if not options:
            raise AdaptiveParseError("template sense resolution requires existing options")
        labels = tuple(label for label, _description in options)
        if len(set(labels)) != len(labels):
            raise AdaptiveParseError("template sense option labels must be unique")
        self._traces = []
        bindings = "\n".join(
            f"{role.value} = {value}" for role, value in role_bindings
        ) or "none"
        profiles = "\n".join(
            f"{label} = {description}" for label, description in options
        )
        choices = (*labels, "NEW", "UNCLEAR")
        prompt = (
            f"TEXT:\n{source_text}\n"
            f"PREDICATE:\n{predicate.surface}\n"
            f"NORMALIZED PREDICATE:\n{predicate.lookup_form}\n"
            f"CURRENT SENSE CUE:\n{predicate.sense_hint or 'none'}\n"
            "CURRENT SEMANTIC ROLES:\n"
            + (", ".join(role.value for role in filled_roles) or "none")
            + f"\nCURRENT ROLE BINDINGS:\n{bindings}\n"
            + f"EXISTING SENSE OPTIONS:\n{profiles}\n"
            + "QUESTION:\nWhich existing option has the same predicate meaning in this text? "
              "Different optional participants or circumstances (for example TIME, TOOL, LOCATION) "
              "do not by themselves create a new predicate sense; they may extend the valency of the same option. "
              "Answer NEW only when the predicate meaning itself is distinct from every existing option. "
              "Answer UNCLEAR if the text does not determine this safely.\n"
            + "CHOICES:\n" + "\n".join(choices)
        )
        decision, _ = self._exact_choice_probe(
            "template_sense", prompt, choices
        )
        if decision == "UNCLEAR":
            return AdaptiveTemplateSenseResult(None, tuple(self._traces))
        return AdaptiveTemplateSenseResult(decision, tuple(self._traces))

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
        self._pending_nominal_modifiers = []
        self._runtime_compositions = {}
        self._contextual_nominal_lemmas = {}
        self._genitive_attachment_cache = {}
        self._postnominal_possessive_cache = {}
        self._asserted_nonfinite_refs: set[str] = set()
        self._classified_nonfinite_pairs: set[tuple[str, str]] = set()
        self._scoped_nonfinite_pairs: set[tuple[str, str]] = set()
        self._transition_classified_refs: set[str] = set()
        self._transition_cue_token_indices: set[int] = set()
        self._runtime_blocked_token_indices: set[int] = set()
        recovery = LexicalRecovery(
            self.morphology,
            semantic_reranker=self.semantic_reranker,
        )
        candidate_builder = LinguisticCandidateBuilder(
            self.morphology,
            lexical_recovery=recovery,
        )
        self._nominal_subject_spans: dict[int, _Span] = {}
        self._nominal_linker_tokens: set[int] = set()
        base_graph = candidate_builder.build(text)
        base_graph = self._resolve_nominal_predication_modes(candidate_builder, base_graph)
        self._candidate_graph = self._resolve_relative_adverb_clause_modes(
            candidate_builder, base_graph
        )
        lexical_decisions = tuple(
            token.recovery
            for token in self._candidate_graph.tokens
            if token.recovery is not None
        )
        tokens = self._source_tokens_from_graph(self._candidate_graph)
        self._active_implicit_clause_id = None
        if not tokens:
            return AdaptiveParseResult(
                PerceptionResult(source_text=text, lexical_recovery=lexical_decisions),
                (),
            )
        for decision in lexical_decisions:
            if decision.status is LexicalRecoveryStatus.EXACT:
                continue
            answer = (
                decision.normalized_text
                if decision.normalized_text is not None
                else decision.status.value
            )
            self._deterministic_trace(
                "lexical_recovery",
                (
                    f"TOKEN:{decision.token_index}\nRAW:{decision.raw_text}\n"
                    f"CANDIDATES:{','.join(decision.alternatives) or '-'}"
                ),
                answer,
            )
        ambiguous = tuple(
            item for item in lexical_decisions
            if item.status is LexicalRecoveryStatus.AMBIGUOUS
        )
        if ambiguous:
            details = "; ".join(
                f"{item.raw_text} -> {', '.join(item.alternatives) or '?'}"
                for item in ambiguous
            )
            raise AdaptiveParseError(
                f"ambiguous lexical recovery: {details}", tuple(self._traces)
            )

        assertions: list[AssertionCandidate] = []
        assertion_spans: dict[str, _Span | None] = {}
        queries: list[QueryCandidate] = []
        query_spans: dict[str, _Span | None] = {}
        commands: list[CommandCandidate] = []
        command_spans: dict[str, _Span | None] = {}
        used_predicates: list[_Span] = []
        used_implicit_clauses: set[str] = set()

        try:
            act_index = 0
            while True:
                act_index += 1
                morph_candidates = self._predicate_morph_candidates(tokens, used_predicates)
                implicit_clause = (
                    None if morph_candidates else self._next_implicit_copula_clause(used_implicit_clauses)
                )
                focus_clause_id: str | None = None
                if morph_candidates and self._candidate_graph is not None:
                    clause = self._candidate_graph.clause_for_token(morph_candidates[0])
                    focus_clause_id = clause.clause_id if clause is not None else None
                elif implicit_clause is not None:
                    focus_clause_id = implicit_clause.clause_id

                deterministic_act = (
                    self._deterministic_act_type(tokens, morph_candidates, focus_clause_id)
                    if morph_candidates or implicit_clause is not None or not used_predicates
                    else None
                )
                act_prompt = self._act_type_prompt(
                    text, tokens, used_predicates, focus_clause_id=focus_clause_id
                )
                if deterministic_act is not None:
                    act_choice = deterministic_act
                    self._deterministic_trace("act_type", act_prompt, act_choice)
                else:
                    act_choice = self._probe(
                        "act_type",
                        act_prompt,
                        lambda raw: self._label_or_number_choice(
                            raw, _ACT_TYPE_LABEL_CHOICES, _ACT_TYPE_CHOICES
                        ),
                        max_new_tokens=2,
                    )
                act_type = act_choice
                if act_type == "NONE":
                    break

                implicit_copula = implicit_clause is not None
                self._active_implicit_clause_id = (
                    implicit_clause.clause_id if implicit_clause is not None else None
                )
                if implicit_copula:
                    predicate_start = 0
                    self._deterministic_trace(
                        "predicate_start",
                        self._predicate_start_prompt(text, tokens, used_predicates, morph_candidates),
                        0,
                    )
                elif morph_candidates:
                    # ClauseFrameGraph has already deferred embedded children whose
                    # structural parent is still unparsed. Source order is used only
                    # as a stable queue order among the remaining dependency-ready
                    # peers; it no longer defines semantic parent/child orientation.
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
                        max_new_tokens=4,
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
                                max_new_tokens=4,
                            )
                            if predicate_end is None:
                                raise AdaptiveParseError("predicate boundary unresolved")
                    predicate_span = self._resolve_span(text, tokens, predicate_start, predicate_end)
                    if any(predicate_span.overlaps(old) for old in used_predicates):
                        raise AdaptiveParseError("predicate overlaps an already parsed predicate")
                    used_predicates.append(predicate_span)
                    target_text = self._semantic_token_range_text(
                        tokens,
                        predicate_span.start_index,
                        predicate_span.end_index,
                    )
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
                    sense_hint=(
                        "IMPLICIT"
                        if predicate_span is None
                        else "NOMINAL_PREDICATION"
                        if predicate_span.start_index in self._nominal_subject_spans
                        else None
                    ),
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
                        if self._active_implicit_clause_id is not None:
                            used_implicit_clauses.add(self._active_implicit_clause_id)
                        self._active_implicit_clause_id = None
                        if not self._has_remaining_frame_candidates(
                            tokens, used_predicates, used_implicit_clauses
                        ):
                            break
                        continue
                    if self.morphology.name != "none" and not self._predicate_morph_candidates(tokens, used_predicates):
                        if self._next_implicit_copula_clause(used_implicit_clauses) is None:
                            break
                    continue

                negated = False
                query_mode = QueryMode.EXISTS
                requested_roles: tuple[ActantRole, ...] = ()
                requested_spans: tuple[_Span, ...] = ()

                if act_type in {"ASSERTION", "COMMAND"}:
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
                        )
                        if negation_choice is None:
                            raise AdaptiveParseError("negation scope unresolved")
                        negated = negation_choice
                elif act_type == "QUERY":
                    # Query mode is structural syntax, not a semantic guess. An
                    # explicit interrogative span creates a role gap; otherwise a
                    # fully specified interrogative clause is a polar/EXISTS query.
                    # Delegating this binary distinction to the model allowed simple
                    # questions such as ``Крипл — это ИИ?`` to become FILL_ROLE and
                    # silently lose their proof obligation.
                    if self._explicit_question_words(tokens, predicate_span):
                        query_mode = QueryMode.FILL_ROLE
                    else:
                        query_mode = QueryMode.EXISTS
                    self._deterministic_trace(
                        "query_mode", self._query_mode_prompt(text, predicate), query_mode.value
                    )
                    if query_mode is QueryMode.FILL_ROLE:
                        # Resolve only the source WH spans here. Their semantic
                        # roles are intentionally delayed until the known actants
                        # have been extracted, so one bad early WH guess cannot
                        # forbid the correct role for an explicit participant.
                        requested_spans = self._requested_query_spans(
                            text, tokens, predicate_span
                        )

                actants, _selected_spans = self._extract_actants(
                    text,
                    tokens,
                    predicate_span,
                    predicate,
                    act_type=act_type,
                    requested_roles=(),
                    requested_spans=requested_spans,
                )

                if act_type == "QUERY" and query_mode is QueryMode.FILL_ROLE:
                    requested_roles, requested_spans = self._requested_query_roles(
                        text,
                        tokens,
                        predicate,
                        predicate_span,
                        used_roles={actant.role for actant in actants},
                        requested_spans=requested_spans,
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
                    local_id = f"Q{len(queries) + 1}"
                    queries.append(
                        QueryCandidate(
                            predicate=predicate,
                            actants=actants,
                            requested_roles=requested_roles,
                            query_mode=query_mode,
                            local_id=local_id,
                        )
                    )
                    query_spans[local_id] = predicate_span
                else:
                    local_id = f"C{len(commands) + 1}"
                    commands.append(
                        CommandCandidate(
                            predicate=predicate, actants=actants, local_id=local_id, negated=negated
                        )
                    )
                    command_spans[local_id] = predicate_span

                if predicate_span is None:
                    if self._active_implicit_clause_id is not None:
                        used_implicit_clauses.add(self._active_implicit_clause_id)
                    self._active_implicit_clause_id = None
                    if not self._has_remaining_frame_candidates(
                        tokens, used_predicates, used_implicit_clauses
                    ):
                        break
                    continue
                self._active_implicit_clause_id = None
                # With morphology available, do not ask the model whether the same
                # already-parsed simple clause is another act. Continue only when a
                # distinct unparsed predicate or implicit copula clause still exists.
                if self.morphology.name != "none" and not self._predicate_morph_candidates(tokens, used_predicates):
                    if self._next_implicit_copula_clause(used_implicit_clauses) is None:
                        break

        except AdaptiveStructuralClarificationRequired as exc:
            traces = exc.traces or tuple(self._traces)
            raise AdaptiveStructuralClarificationRequired(exc.spec, traces) from exc
        except AdaptiveParseError as exc:
            traces = tuple(self._traces)
            if exc.traces:
                traces = exc.traces
            raise AdaptiveParseError(str(exc), traces) from exc

        # There is deliberately no semantic cap on the number of acts in one
        # perception unit. Every successful iteration consumes a distinct source
        # predicate span or implicit copular clause, so the source itself provides
        # the finite structural bound. A model-emitted NONE is never permission to
        # commit a partial parse: if deterministic frames remain, fail closed.
        if self._has_remaining_frame_candidates(tokens, used_predicates, used_implicit_clauses):
            raise AdaptiveParseError(
                "incomplete parse: model stopped while meaningful predicate frames remain",
                tuple(self._traces),
            )

        # Establish source-frame dependency structure before ellipsis recovery.
        # A parallel tail may repeat an entire matrix/content subgraph, not merely
        # one leaf predicate.  The later call is retained for frames created by
        # recovery and nominal projection; attachment is idempotent.
        if (
            self._candidate_graph is not None
            and (
                any(
                    clause.ellipsis_kind is not None
                    for clause in self._candidate_graph.clauses
                )
                or any(
                    edge.kind is FrameDependencyKind.NONFINITE
                    for edge in self._candidate_graph.frame_graph.dependencies
                )
            )
        ):
            assertions = self._attach_nested_assertions(assertions, assertion_spans)
        assertions, assertion_spans = self._normalize_transition_occurrences(
            assertions, assertion_spans
        )
        assertions = self._complete_contrastive_repeated_frames(
            assertions, assertion_spans
        )
        assertions, assertion_spans = self._recover_ellipsis_assertions(
            text, tokens, assertions, assertion_spans
        )
        assertions, assertion_spans = self._materialize_nominal_modifier_assertions(
            assertions, assertion_spans
        )
        assertions, assertion_spans = self._materialize_nominal_subject_projections(
            text, tokens, assertions, assertion_spans
        )
        assertions = self._attach_nested_assertions(assertions, assertion_spans)
        assertions, participant_projection_diagnostics = self._project_orphan_subordinate_participants(assertions)
        conditionals = self._derive_conditionals(assertions, assertion_spans)
        assertions = self._mark_conditional_statuses(assertions, conditionals)
        assertions = self._mark_embedded_statuses(assertions)
        assertions, factivity_diagnostics = self._promote_factive_embedded_content(assertions)
        relations = self._derive_situation_relations(assertions, assertion_spans)
        assertions = self._strip_structural_relation_actants(assertions, relations)
        act_dependencies = self._derive_act_dependencies(
            assertion_spans, query_spans, command_spans
        )
        assertions, queries, commands = self._mark_quoted_acts(
            assertions, queries, commands, act_dependencies,
            assertion_spans, query_spans, command_spans,
        )

        # Event normalization is a runtime perception boundary, not a canonical
        # write.  It can recover independently asserted gerund/result-state
        # situations and conservative FOLLOW edges from the already-built
        # linguistic frame graph.  Weaker narrative causality stays in
        # relation_hints and is intentionally invisible to Integration.
        event_diagnostics: tuple[str, ...] = (
            *participant_projection_diagnostics,
            *factivity_diagnostics,
        )
        relation_hints = ()
        if self._candidate_graph is not None and assertions:
            normalized = EventNormalizer(self._candidate_graph, self.morphology).normalize(
                tuple(assertions), relations
            )
            assertions = list(normalized.assertions)
            relations = normalized.relations
            relation_hints = normalized.relation_hints
            relations, relation_hints, causal_diagnostics = self._resolve_narrative_causal_candidates(
                assertions, relations, relation_hints
            )
            event_diagnostics = (
                *participant_projection_diagnostics,
                *factivity_diagnostics,
                *normalized.diagnostics,
                *causal_diagnostics,
            )
            # EventNormalizer can add a result-state assertion that deliberately
            # reuses the exact source NP evidence of an existing assertion.  Run
            # the same deterministic source-span identity binder once more so the
            # new state and the matrix fact resolve to one entity even when the
            # original mention did not previously need an entity_ref.
            normalized_by_id = {item.local_id: item for item in assertions}
            self._bind_reused_source_mentions(normalized_by_id)
            assertions = [normalized_by_id.get(item.local_id, item) for item in assertions]

        # Dependency-ready traversal is only an internal scheduling strategy.
        # Expose acts in source order so consumers never infer textual order from
        # graph-topological parse order. Local ids remain stable references.
        assertions.sort(key=lambda item: (
            item.evidence.start if item.evidence is not None else 10**12,
            item.evidence.end if item.evidence is not None else 10**12,
            item.local_id,
        ))
        queries.sort(key=lambda item: (
            item.predicate.evidence.start if item.predicate.evidence is not None else 10**12,
            item.local_id or "",
        ))
        commands.sort(key=lambda item: (
            item.predicate.evidence.start if item.predicate.evidence is not None else 10**12,
            item.local_id or "",
        ))

        result = PerceptionResult(
            source_text=text,
            assertions=tuple(assertions),
            queries=tuple(queries),
            commands=tuple(commands),
            diagnostics=event_diagnostics,
            relations=relations,
            conditionals=conditionals,
            act_dependencies=act_dependencies,
            relation_hints=relation_hints,
            lexical_recovery=lexical_decisions,
        )
        try:
            result = QuantifierFormalizer(self.morphology).formalize(
                result,
                resolver=self._resolve_quantifier_candidate,
            )
        except QuantifierFormalizationError as exc:
            raise AdaptiveParseError(str(exc), tuple(self._traces)) from exc
        return AdaptiveParseResult(result, tuple(self._traces))

    def _resolve_quantifier_candidate(
        self,
        source_context: str,
        predicate: PredicateCandidate,
        actant: ActantCandidate,
        predicate_negated: bool,
    ) -> QuantifierProbeDecision:
        """Classify one already-built actant through a closed semantic protocol.

        Python has fixed the predicate frame, semantic role and target mention.
        The model does not construct a formula or choose canonical objects; it
        decides only whether this source occurrence introduces a binder and where
        source negation belongs.  This deliberately replaces surface-marker tables
        so paraphrases and inflected expressions share one semantic boundary.
        """

        evidence = actant.evidence
        phrase = (
            evidence.text
            if evidence is not None and evidence.text.strip()
            else (actant.mention or actant.normalized_hint or "")
        ).strip()
        prompt = (
            f"TEXT:\n{source_context}\n"
            f"EVENT PREDICATE:\n{predicate.surface}\n"
            f"EVENT NEGATED:\n{'YES' if predicate_negated else 'NO'}\n"
            f"TARGET ROLE:\n{actant.role.value}\n"
            f"TARGET PHRASE:\n{phrase}\n"
            "TASK:\nClassify only the semantic quantifier binding TARGET in this "
            "event. Predicate negation is body negation unless the source assigns "
            "it to the quantifier.\n"
            "NONE: TARGET is an ordinary definite/specific referent.\n"
            "EXISTS: at least one TARGET satisfies the event.\n"
            "NOT_EXISTS: no TARGET satisfies the event.\n"
            "FORALL: every member of TARGET's stated class satisfies the event.\n"
            "NOT_FORALL: the source denies that every member satisfies the event.\n"
            "AMBIGUOUS: kind or negation scope is not determined.\n"
            "CHOICES:\nNONE\nEXISTS\nNOT_EXISTS\nFORALL\nNOT_FORALL\nAMBIGUOUS"
        )
        decision, _ = self._deep_semantic_choice_probe(
            "quantifier",
            prompt,
            (
                "NONE",
                "EXISTS",
                "NOT_EXISTS",
                "FORALL",
                "NOT_FORALL",
                "AMBIGUOUS",
            ),
        )
        assert decision is not None
        return QuantifierProbeDecision(decision)

    def _complete_contrastive_repeated_frames(
        self,
        assertions: list[AssertionCandidate],
        assertion_spans: dict[str, _Span | None],
    ) -> list[AssertionCandidate]:
        """Carry omitted slots across a strongly marked repeated predicate.

        This covers a peer clause that overtly repeats the same finite predicate
        but leaves part of its frame unspoken.  Completion is licensed only by a
        conjunction of source-visible constraints: adjacent clauses in one
        sentence, an adversative coordinator, a dash before the repeated finite
        predicate, and opposite proposition polarity.  Predicate identity comes
        from the already-normalized lexical form and every inherited filler comes
        from the unique preceding frame.  No predicate inventory or surface
        example participates in the decision.

        Proposition-valued edges are deliberately excluded.  Repeating a matrix
        predicate does not by itself authorize reusing or cloning an embedded
        situation; complete zero-predicate subgraphs are handled by the dedicated
        ellipsis recovery pass.
        """
        graph = self._candidate_graph
        if graph is None or len(assertions) < 2:
            return assertions

        clause_assertions: dict[str, list[str]] = {}
        for local_id, span in assertion_spans.items():
            if span is None:
                continue
            clause = graph.clause_for_token(span.start_index)
            if clause is not None:
                clause_assertions.setdefault(clause.clause_id, []).append(local_id)

        by_id = {item.local_id: item for item in assertions}

        def assertion_for_head(clause, head_index: int) -> tuple[str, AssertionCandidate] | None:
            matches: list[tuple[str, AssertionCandidate]] = []
            for local_id in clause_assertions.get(clause.clause_id, ()):
                span = assertion_spans.get(local_id)
                item = by_id.get(local_id)
                if span is None or item is None or span.start_index != head_index:
                    continue
                matches.append((local_id, item))
            return matches[0] if len(matches) == 1 else None

        clauses = list(graph.clauses)
        for index, target_clause in enumerate(clauses[1:], start=1):
            source_clause = clauses[index - 1]
            if source_clause.sentence_id != target_clause.sentence_id:
                continue

            target_heads = [
                head for head in target_clause.predicate_heads
                if head.finite and not head.nominal_predicative
            ]
            if len(target_heads) != 1:
                continue
            target_head = target_heads[0]

            clause_tokens = [
                token for token in graph.tokens
                if target_clause.span.start_index <= token.index <= target_clause.span.end_index
            ]
            first_word = next(
                (token.text.casefold() for token in clause_tokens if self._is_word_token(token)),
                "",
            )
            if first_word not in {"а", "но", "однако"}:
                continue
            if not any(
                token.text in {"-", "—", "–"} and token.index < target_head.token_index
                for token in clause_tokens
            ):
                continue

            target_pair = assertion_for_head(target_clause, target_head.token_index)
            if target_pair is None:
                continue
            target_id, target = target_pair

            source_pairs: list[tuple[str, AssertionCandidate]] = []
            for source_head in source_clause.predicate_heads:
                if not source_head.finite or source_head.nominal_predicative:
                    continue
                pair = assertion_for_head(source_clause, source_head.token_index)
                if pair is None:
                    continue
                if pair[1].predicate.lookup_form == target.predicate.lookup_form:
                    source_pairs.append(pair)
            if len(source_pairs) != 1:
                continue
            _source_id, source = source_pairs[0]
            if source.negated == target.negated:
                continue
            if not any(item.role is ActantRole.SUBJECT for item in source.actants):
                continue
            if not any(item.role is ActantRole.SUBJECT for item in target.actants):
                continue

            occupied = {item.role for item in target.actants}
            inherited = tuple(
                item
                for item in source.actants
                if item.role is not ActantRole.SUBJECT
                and item.role not in occupied
                and item.candidate_ref is None
                and item.proposition is None
            )
            if not inherited:
                continue

            by_id[target_id] = replace(
                target,
                actants=target.actants + inherited,
            )
            self._deterministic_trace(
                "contrastive_repeated_frame",
                (
                    f"SOURCE PREDICATE:\n{source.predicate.surface}\n"
                    f"TARGET PREDICATE:\n{target.predicate.surface}\n"
                    "INHERITED ROLES:\n"
                    + "\n".join(item.role.value for item in inherited)
                ),
                ",".join(item.role.value for item in inherited),
            )

        return [by_id[item.local_id] for item in assertions]

    def _realization_signature(self, evidence: EvidenceSpan | None, tokens):
        if evidence is None or evidence.start is None or evidence.end is None:
            return None
        covered = [
            token for token in tokens
            if token.start >= evidence.start and token.end <= evidence.end
            and self._is_word_token(token)
        ]
        if not covered:
            return None
        prepositions: list[str] = []
        nominal_cases: list[tuple[str, ...]] = []
        nominal_pos: list[tuple[str, ...]] = []
        nonfunctional_pos: list[tuple[str, ...]] = []
        for token in covered:
            infos = tuple(self._material_morph_analyses(token))
            prep_lemmas = sorted({
                info.normal_form.casefold() for info in infos
                if info.pos == "PREP" and info.normal_form
            })
            prepositions.extend(prep_lemmas)
            nom_infos = [info for info in infos if info.pos in {"NOUN", "NPRO"}]
            if nom_infos:
                nominal_cases.append(tuple(sorted({info.case for info in nom_infos if info.case})))
                nominal_pos.append(tuple(sorted({info.pos for info in nom_infos if info.pos})))
            content_pos = tuple(sorted({
                info.pos for info in infos
                if info.pos not in {None, "PREP", "CONJ", "PRCL", "INTJ"}
            }))
            if content_pos:
                nonfunctional_pos.append(content_pos)
        if nominal_cases and all(nominal_cases):
            return (
                "NOMINAL",
                tuple(prepositions),
                tuple(nominal_cases),
                tuple(nominal_pos),
            )
        # Pure adverbial/particle realizations have no grammatical case but still
        # provide a useful source-grounded parallel signature.  This is deliberately
        # POS-level only: it does not map an adverb to TIME/LOCATION/etc.
        if nonfunctional_pos and all(
            set(values) <= {"ADVB", "PRED"} for values in nonfunctional_pos
        ):
            return ("ADVERBIAL", tuple(nonfunctional_pos))
        return None


    @staticmethod
    def _compatible_realizations(left, right) -> bool:
        if left is None or right is None or left[0] != right[0]:
            return False
        if left[0] == "ADVERBIAL":
            left_pos = left[1]
            right_pos = right[1]
            return (
                len(left_pos) == len(right_pos)
                and all(set(a) & set(b) for a, b in zip(left_pos, right_pos))
            )
        _, left_preps, left_cases, left_pos = left
        _, right_preps, right_cases, right_pos = right
        return (
            left_preps == right_preps and left_pos == right_pos
            and len(left_cases) == len(right_cases)
            and all(set(a) & set(b) for a, b in zip(left_cases, right_cases))
        )

    def _unique_realization_roles(self, source_actants, target_evidence, tokens):
        # Compatibility is grammatical possibility, not analyser-score ranking.
        # Transfer only isolated edges of the bipartite correspondence: neither
        # the source slot nor the target phrase may have a competing counterpart.
        source = [(item.role, self._realization_signature(item.evidence, tokens))
                  for item in source_actants]
        target = [self._realization_signature(evidence, tokens) for evidence in target_evidence]
        aligned = {}
        used_source = set()
        # Preserve exact parallel feature bundles first. Context can then narrow
        # case-syncretic remaining phrases, but cannot displace an exact pair.
        for exact in (True, False):
            edges = [(i, j) for i, (_, signature) in enumerate(source)
                     for j, other in enumerate(target)
                     if i not in used_source and j not in aligned
                     and signature is not None and other is not None
                     and (signature == other if exact else self._compatible_realizations(signature, other))]
            isolated = [(i, j) for i, j in edges
                        if sum(a == i for a, _ in edges) == 1
                        and sum(b == j for _, b in edges) == 1]
            for i, j in isolated:
                aligned[j] = source[i][0]
                used_source.add(i)
        return aligned

    def _recover_ellipsis_assertions(
        self,
        text: str,
        tokens: tuple[_SourceToken, ...],
        assertions: list[AssertionCandidate],
        assertion_spans: dict[str, _Span | None],
    ) -> tuple[list[AssertionCandidate], dict[str, _Span | None]]:
        """Complete coordinated zero-predicate frames before canonicalization.

        ``LinguisticCandidateBuilder`` marks only a narrowly licensed structural
        shell: an overt finite peer clause followed by a comma+coordinator tail
        with no predicate of its own.  This method performs the semantic part of
        reconstruction *after* the source assertion exists, so the inherited
        predicate and admissible role inventory come from an already parsed frame
        rather than from a lexical marker or free-form model guess.

        The recovered assertion is still runtime perception data.  No UID is
        allocated and AH is not mutated here.
        """
        graph = self._candidate_graph
        if graph is None:
            return assertions, assertion_spans

        ellipsis_clauses = [
            clause for clause in graph.clauses
            if clause.ellipsis_kind is not None
        ]
        if not ellipsis_clauses:
            return assertions, assertion_spans

        source_by_clause: dict[str, list[AssertionCandidate]] = {}
        for assertion in assertions:
            span = assertion_spans.get(assertion.local_id)
            if span is None:
                continue
            clause = graph.clause_for_token(span.start_index)
            if clause is not None:
                source_by_clause.setdefault(clause.clause_id, []).append(assertion)

        out = list(assertions)
        spans_out = dict(assertion_spans)
        marker_words = {"нет", "тоже"}

        used_ids = {item.local_id for item in assertions} | set(assertion_spans)

        def unresolved(clause, reason: str) -> None:
            self._deterministic_trace(
                "ellipsis_recovery", f"TARGET_CLAUSE:{clause.span.text}",
                f"UNRESOLVED:{reason}",
            )
            # A licensed frame is meaningful source content. Returning the other
            # assertions as a successful parse would authorize a partial commit.
            raise AdaptiveParseError(f"unresolved ellipsis: {reason}", tuple(self._traces))

        def referenced_local_ids(item: AssertionCandidate) -> tuple[str, ...]:
            refs: list[str] = []
            for actant in item.actants:
                if actant.candidate_ref is not None:
                    refs.append(actant.candidate_ref)
                if actant.proposition is not None:
                    refs.extend(actant.proposition.leaf_refs())
            return tuple(dict.fromkeys(refs))

        def actant_identity(item: ActantCandidate) -> tuple[object, ...] | None:
            if item.entity_ref is not None:
                return ("entity", item.entity_ref)
            evidence = item.evidence
            if evidence is not None and evidence.start is not None and evidence.end is not None:
                return ("span", evidence.start, evidence.end)
            if item.lookup_text:
                return ("text", item.lookup_text.casefold())
            return None

        def alternative_identity_roles(
            component: tuple[AssertionCandidate, ...],
        ) -> set[ActantRole] | None:
            """Return roles whose *identity* varies across otherwise stable readings.

            Pronoun resolution may preserve several complete AssertionCandidate
            readings.  Frame completion only needs to stop when those alternatives
            alter predicate/topology, or when an ambiguous inherited filler would
            be copied into the target.  If the target explicitly replaces every
            varying role, the ambiguity is irrelevant to the recovered proposition
            and must not veto ellipsis.
            """
            varying: set[ActantRole] = set()
            for item in component:
                if not item.alternatives:
                    continue
                base_roles = {actant.role: actant for actant in item.actants}
                if len(base_roles) != len(item.actants):
                    return None
                base_structure = {
                    role: (
                        actant.candidate_ref is not None,
                        actant.proposition is not None,
                        actant.composition is not None,
                    )
                    for role, actant in base_roles.items()
                }
                for alternative in item.alternatives:
                    if (
                        alternative.predicate.lookup_form != item.predicate.lookup_form
                        or alternative.negated != item.negated
                        or alternative.status is not item.status
                    ):
                        return None
                    alt_roles = {actant.role: actant for actant in alternative.actants}
                    if len(alt_roles) != len(alternative.actants):
                        return None
                    if set(alt_roles) != set(base_roles):
                        return None
                    alt_structure = {
                        role: (
                            actant.candidate_ref is not None,
                            actant.proposition is not None,
                            actant.composition is not None,
                        )
                        for role, actant in alt_roles.items()
                    }
                    if alt_structure != base_structure:
                        return None
                    for role, base_actant in base_roles.items():
                        if actant_identity(base_actant) != actant_identity(alt_roles[role]):
                            varying.add(role)
            return varying

        def direct_slots(component: tuple[AssertionCandidate, ...]) -> dict[ActantRole, ActantCandidate]:
            """Choose one visible source slot per role, root before descendants.

            Proposition-valued actants are structural edges, not replaceable
            surface slots.  A matrix role wins when the same role also occurs in a
            child; controller identity propagation below still updates correlated
            child roles through their shared entity/span identity.
            """
            slots: dict[ActantRole, ActantCandidate] = {}
            for assertion in component:
                for actant in assertion.actants:
                    if actant.candidate_ref is not None or actant.proposition is not None:
                        continue
                    slots.setdefault(actant.role, actant)
            return slots

        def realization_representatives(
            slots: dict[ActantRole, ActantCandidate],
            pool: list[AssertionCandidate],
            target_evidence: list[EvidenceSpan] | tuple[EvidenceSpan, ...],
        ) -> tuple[ActantCandidate, ...]:
            """Use the clearest source mention of an already-identical filler.

            A coordinated source graph can mention one entity first as a noun and
            later as a pronoun.  Root selection must compare grammatical
            realization, yet the later frame may carry only the pronominal copy.
            Exact local identity lets us borrow the earlier *surface evidence* for
            this comparison without borrowing its role or adding an assertion.
            """
            target_signatures = [
                self._realization_signature(evidence, tokens)
                for evidence in target_evidence
            ]
            result: list[ActantCandidate] = []
            for role, slot in slots.items():
                identity = actant_identity(slot)
                aliases = [slot]
                if identity is not None:
                    aliases.extend(
                        actant
                        for assertion in pool
                        for actant in assertion.actants
                        if actant.candidate_ref is None
                        and actant.proposition is None
                        and actant_identity(actant) == identity
                        and actant not in aliases
                    )

                def clarity(candidate: ActantCandidate) -> tuple[int, int, int]:
                    signature = self._realization_signature(candidate.evidence, tokens)
                    exact = sum(
                        signature is not None and signature == target
                        for target in target_signatures
                    )
                    compatible = sum(
                        self._compatible_realizations(signature, target)
                        for target in target_signatures
                    )
                    return exact, compatible, int(candidate is slot)

                representative = max(aliases, key=clarity)
                result.append(replace(representative, role=role))
            return tuple(result)

        def target_spans_for_clause(clause, blocked_markers: set[int]) -> tuple[_Span, ...]:
            old_active = self._active_implicit_clause_id
            old_blocked = set(getattr(self, "_runtime_blocked_token_indices", set()))
            self._active_implicit_clause_id = clause.clause_id
            self._runtime_blocked_token_indices = old_blocked | blocked_markers
            try:
                return self._candidate_phrase_spans(
                    text, tokens, None, [], requested_spans=()
                )
            finally:
                self._active_implicit_clause_id = old_active
                self._runtime_blocked_token_indices = old_blocked

        for clause in ellipsis_clauses:
            source_clause = next(
                (item for item in graph.clauses
                 if item.clause_id == clause.ellipsis_source_clause_id), None,
            )
            candidates = source_by_clause.get(clause.ellipsis_source_clause_id or "", [])
            blocked_markers = {
                token.index
                for token in graph.tokens
                if clause.span.start_index <= token.index <= clause.span.end_index
                and token.text.casefold() in marker_words
            }
            if (
                source_clause is None
                or source_clause.span.end_index >= clause.span.start_index
                or not candidates
            ):
                unresolved(clause, "source_frame_not_unique_or_unavailable")

            candidate_by_id = {item.local_id: item for item in candidates}
            referenced = {
                ref
                for item in candidates
                for ref in referenced_local_ids(item)
                if ref in candidate_by_id
            }
            roots = [item for item in candidates if item.local_id not in referenced]

            def rooted_component(root: AssertionCandidate) -> tuple[AssertionCandidate, ...]:
                reachable = {root.local_id}
                changed = True
                while changed:
                    changed = False
                    for local_id in tuple(reachable):
                        for ref in referenced_local_ids(candidate_by_id[local_id]):
                            if ref in candidate_by_id and ref not in reachable:
                                reachable.add(ref)
                                changed = True
                return (
                    root,
                    *tuple(
                        item for item in candidates
                        if item.local_id in reachable and item.local_id != root.local_id
                    ),
                )

            component: tuple[AssertionCandidate, ...] = ()
            if len(roots) == 1:
                source = roots[0]
                component = rooted_component(source)
                # Independent assertions in the same surface clause are not part
                # of the rooted content subgraph.  Select among roots below rather
                # than silently absorbing them into one ellipsis.
                if len(component) != len(candidates):
                    roots = [item for item in candidates if item.local_id not in referenced]
                else:
                    roots = []

            if roots:
                target_spans = target_spans_for_clause(clause, blocked_markers)
                ranked: list[
                    tuple[
                        tuple[int, int, int],
                        AssertionCandidate,
                        tuple[AssertionCandidate, ...],
                    ]
                ] = []
                for candidate in roots:
                    candidate_component = rooted_component(candidate)
                    slots = direct_slots(candidate_component)
                    representatives = realization_representatives(
                        slots,
                        candidates,
                        tuple(span.evidence for span in target_spans),
                    )
                    alignment = self._unique_realization_roles(
                        representatives,
                        [span.evidence for span in target_spans],
                        tokens,
                    )
                    rank = (
                        int(bool(target_spans) and len(alignment) == len(target_spans)),
                        len(alignment),
                        len(slots),
                    )
                    ranked.append((rank, candidate, candidate_component))
                best_rank = max(
                    (rank for rank, _item, _component in ranked),
                    default=(0, 0, 0),
                )
                winners = [
                    (item, candidate_component)
                    for rank, item, candidate_component in ranked
                    if rank == best_rank
                ]
                if len(winners) != 1 or best_rank[1] == 0:
                    unresolved(clause, "source_frame_not_unique_or_unavailable")
                source, component = winners[0]

            if not component:
                unresolved(clause, "source_frame_not_unique_or_unavailable")

            ambiguous_source_roles = alternative_identity_roles(component)
            if ambiguous_source_roles is None:
                unresolved(clause, "source_alternatives_change_frame_topology")
            source_slots = direct_slots(component)
            source_roles = set(source_slots)
            if not source_roles:
                unresolved(clause, "source_roles_not_unique_or_empty")

            # A dash shell can independently support nominal predication.  The
            # linguistic graph deliberately preserves that reading alongside the
            # ellipsis candidate.  Replace it only when every visible target slot
            # participates in a bijective grammatical-realization alignment with
            # the source frame.  This makes strong punctuation safe without a
            # vocabulary list or plausibility guess.
            provisional = (
                source_by_clause.get(clause.clause_id, [])
                if clause.implicit_copula
                else []
            )
            reclaimed_predicates: set[int] = set()
            if clause.implicit_copula and provisional:
                if len(provisional) != 1:
                    unresolved(clause, "nominal_parallel_parse_not_unique")
                visible: dict[tuple[int, int], EvidenceSpan] = {}
                target_candidate = provisional[0]
                for actant in target_candidate.actants:
                    evidence = actant.evidence
                    if (
                        evidence is not None
                        and evidence.start is not None
                        and evidence.end is not None
                        and clause.span.evidence.start <= evidence.start < evidence.end
                        and evidence.end <= clause.span.evidence.end
                    ):
                        visible[(evidence.start, evidence.end)] = evidence
                predicate_evidence = target_candidate.predicate.evidence
                if (
                    predicate_evidence is not None
                    and predicate_evidence.start is not None
                    and predicate_evidence.end is not None
                    and clause.span.evidence.start <= predicate_evidence.start < predicate_evidence.end
                    and predicate_evidence.end <= clause.span.evidence.end
                ):
                    visible[(predicate_evidence.start, predicate_evidence.end)] = predicate_evidence
                    reclaimed_predicates.update(
                        token.index
                        for token in graph.tokens
                        if token.start >= predicate_evidence.start
                        and token.end <= predicate_evidence.end
                    )
                visible_evidence = tuple(
                    visible[key] for key in sorted(visible)
                )
                visible_source = realization_representatives(
                    source_slots, candidates, visible_evidence
                )
                provisional_alignment = self._unique_realization_roles(
                    visible_source, visible_evidence, tokens
                )
                if (
                    len(visible_evidence) < 2
                    or len(provisional_alignment) != len(visible_evidence)
                    or len(set(provisional_alignment.values())) != len(visible_evidence)
                ):
                    self._deterministic_trace(
                        "ellipsis_recovery",
                        f"TARGET_CLAUSE:{clause.span.text}",
                        "NOMINAL_PREDICATION:preserved",
                    )
                    continue
                provisional_ids = {item.local_id for item in provisional}
                out = [item for item in out if item.local_id not in provisional_ids]
                for local_id in provisional_ids:
                    spans_out.pop(local_id, None)
                source_by_clause.pop(clause.clause_id, None)

            old_hints = getattr(self, "_ellipsis_role_hints", {})
            old_active_clause = self._active_implicit_clause_id
            old_blocked = set(getattr(self, "_runtime_blocked_token_indices", set()))
            old_reclaimed = set(
                getattr(self, "_runtime_reclaimed_predicate_indices", set())
            )
            self._active_implicit_clause_id = clause.clause_id
            self._runtime_blocked_token_indices = old_blocked | blocked_markers
            self._runtime_reclaimed_predicate_indices = old_reclaimed | reclaimed_predicates
            try:
                target_spans = self._candidate_phrase_spans(text, tokens, None, [], requested_spans=())
                target_source = realization_representatives(
                    source_slots,
                    candidates,
                    tuple(span.evidence for span in target_spans),
                )
                aligned = self._unique_realization_roles(
                    target_source,
                    [span.evidence for span in target_spans],
                    tokens,
                )
                self._ellipsis_role_hints = {
                    (target_spans[index].start_index, target_spans[index].end_index): role
                    for index, role in aligned.items()
                }
                target_actants, _ = self._extract_actants(
                    text,
                    tokens,
                    None,
                    source.predicate,
                    act_type="ASSERTION",
                    requested_roles=(),
                    requested_spans=(),
                    role_whitelist=source_roles,
                )
            finally:
                self._ellipsis_role_hints = old_hints
                self._active_implicit_clause_id = old_active_clause
                self._runtime_blocked_token_indices = old_blocked
                self._runtime_reclaimed_predicate_indices = old_reclaimed

            for actant in target_actants:
                evidence = actant.evidence
                if (
                    evidence is None or evidence.start is None or evidence.end is None
                    or evidence.start < clause.span.evidence.start
                    or evidence.end > clause.span.evidence.end
                    or evidence.start >= evidence.end
                    or text[evidence.start:evidence.end] != evidence.text
                ):
                    unresolved(clause, "target_role_without_local_evidence")

            # Parallel ellipsis gives us stronger *structural* evidence than a
            # free-standing role probe: overt fillers in the target can be aligned
            # with the already-resolved source frame by their grammatical
            # realization signature.  This is deliberately not a generic
            # DAT->RECIPIENT / NOM->SUBJECT shortcut.  We only transfer a source
            # role when the target phrase has the same source-grounded realization
            # signature and that signature identifies exactly one source slot.
            # Exact source-grounded bundles are aligned before compatible
            # syncretic bundles, even if a bounded semantic probe initially swaps
            # two roles in the target frame.
            target_source = realization_representatives(
                source_slots,
                candidates,
                tuple(item.evidence for item in target_actants),
            )
            alignment = self._unique_realization_roles(
                target_source,
                [item.evidence for item in target_actants],
                tokens,
            )
            aligned: list[ActantCandidate] = []
            alignment_changed = False
            for index, target_actant in enumerate(target_actants):
                aligned_role = alignment.get(index)
                if aligned_role is not None and aligned_role is not target_actant.role:
                    target_actant = replace(target_actant, role=aligned_role)
                    alignment_changed = True
                aligned.append(target_actant)
            if alignment_changed:
                target_actants = tuple(aligned)
                self._deterministic_trace(
                    "ellipsis_slot_alignment",
                    f"SOURCE:{source.local_id}\nTARGET_CLAUSE:{clause.span.text}",
                    ",".join(f"{item.role.value}:{item.mention or item.normalized_hint or '?'}" for item in target_actants),
                )

            # One canonical slot cannot silently keep only the final filler.
            # Coordinated fillers must arrive as one explicit composition.
            if not target_actants:
                unresolved(clause, "no_explicit_target_roles")
            explicit_by_role = {actant.role: actant for actant in target_actants}
            if len(explicit_by_role) != len(target_actants):
                unresolved(clause, "duplicate_target_roles")
            if not set(explicit_by_role) <= source_roles:
                unresolved(clause, "target_role_outside_source_frame")
            unresolved_inherited = set(ambiguous_source_roles or ()) - set(explicit_by_role)
            if unresolved_inherited:
                unresolved(
                    clause,
                    "source_identity_ambiguity_would_be_inherited:"
                    + ",".join(sorted(role.value for role in unresolved_inherited)),
                )
            replacement_by_identity: dict[tuple[object, ...], ActantCandidate] = {}
            for role, replacement in explicit_by_role.items():
                source_slot = source_slots.get(role)
                identity = None if source_slot is None else actant_identity(source_slot)
                if identity is None:
                    unresolved(clause, "explicit_role_has_no_source_identity")
                previous = replacement_by_identity.get(identity)
                if previous is not None and previous != replacement:
                    unresolved(clause, "conflicting_correlated_role_replacements")
                replacement_by_identity[identity] = replacement

            inherited_roles = sorted(
                role.value for role in source_roles if role not in explicit_by_role
            )
            replaced_roles = sorted(role.value for role in explicit_by_role)

            kind = clause.ellipsis_kind
            if kind is EllipsisKind.PROPOSITION_NEGATION and source.negated:
                explicit_confirmation = any(
                    token.text.casefold() == "тоже"
                    for token in graph.tokens
                    if clause.span.start_index <= token.index <= clause.span.end_index
                )
                if not explicit_confirmation:
                    unresolved(clause, "negated_antecedent_requires_clarification")
                # In the licensed parallel frame, "тоже нет" confirms the
                # preceding negative proposition; it is not double negation.

            root_negated = (
                True
                if kind is EllipsisKind.PROPOSITION_NEGATION
                else source.negated
            )
            local_id_map: dict[str, str] = {}
            next_id = len(out) + 1
            for source_item in component:
                while f"A{next_id}" in used_ids:
                    next_id += 1
                local_id_map[source_item.local_id] = f"A{next_id}"
                used_ids.add(f"A{next_id}")
                next_id += 1

            def remap_expr(expr: PropositionExprCandidate) -> PropositionExprCandidate:
                if expr.operator is PropositionOperator.REF:
                    assert expr.ref is not None
                    return replace(expr, ref=local_id_map.get(expr.ref, expr.ref))
                return replace(
                    expr,
                    members=tuple(remap_expr(member) for member in expr.members),
                )

            evidence = EvidenceSpan(
                clause.span.text,
                clause.span.evidence.start,
                clause.span.evidence.end,
            )
            recovered_component: list[AssertionCandidate] = []
            target_span = self._resolve_span(
                text, tokens, clause.span.start_index, clause.span.end_index,
            )
            for source_item in component:
                cloned_actants: list[ActantCandidate] = []
                for source_actant in source_item.actants:
                    if source_actant.candidate_ref is not None:
                        cloned_actants.append(
                            replace(
                                source_actant,
                                candidate_ref=local_id_map.get(
                                    source_actant.candidate_ref,
                                    source_actant.candidate_ref,
                                ),
                            )
                        )
                        continue
                    if source_actant.proposition is not None:
                        cloned_actants.append(
                            replace(
                                source_actant,
                                proposition=remap_expr(source_actant.proposition),
                            )
                        )
                        continue
                    identity = actant_identity(source_actant)
                    replacement = (
                        replacement_by_identity.get(identity)
                        if identity is not None
                        else None
                    )
                    cloned_actants.append(
                        replace(replacement, role=source_actant.role)
                        if replacement is not None
                        else source_actant
                    )

                local_id = local_id_map[source_item.local_id]
                recovered = AssertionCandidate(
                    local_id=local_id,
                    predicate=source_item.predicate,
                    actants=tuple(cloned_actants),
                    evidence=evidence,
                    negated=(
                        root_negated
                        if source_item.local_id == source.local_id
                        else source_item.negated
                    ),
                    status=source_item.status,
                    temporal_mode=source_item.temporal_mode,
                    transition_operator=source_item.transition_operator,
                    quoted=source_item.quoted,
                )
                recovered_component.append(recovered)
                out.append(recovered)
                # Predicate evidence still points to the antecedent; structural
                # scope ownership belongs to the target clause.
                spans_out[local_id] = target_span
                if source_item.local_id in self._asserted_nonfinite_refs:
                    self._asserted_nonfinite_refs.add(local_id)

            source_by_clause[clause.clause_id] = recovered_component
            local_id = local_id_map[source.local_id]
            self._deterministic_trace(
                "frame_completion",
                (
                    f"SOURCE:{source.local_id}\n"
                    f"TARGET_CLAUSE:{clause.span.text}\n"
                    f"INHERITED:{','.join(inherited_roles) or '-'}"
                ),
                (
                    f"root={source.predicate.lookup_form if source.predicate else '?'}; "
                    f"frames={len(recovered_component)}"
                ),
            )
            self._deterministic_trace(
                "ellipsis_recovery",
                (
                    f"SOURCE:{source.local_id}\n"
                    f"TARGET_CLAUSE:{clause.span.text}\n"
                    f"MODE:{kind.value if kind is not None else 'FRAME'}"
                ),
                (
                    f"{local_id}; replaced={','.join(replaced_roles) or '-'}; "
                    f"inherited={','.join(inherited_roles) or '-'}; "
                    f"negated={str(root_negated).lower()}; "
                    f"frames={len(recovered_component)}"
                ),
            )

        return out, spans_out

    def _project_orphan_subordinate_participants(
        self,
        assertions: list[AssertionCandidate],
    ) -> tuple[list[AssertionCandidate], tuple[str, ...]]:
        """Recover semantic content behind an orphaned subordinate connector.

        Comma-heavy prose can place an empty subordinate connector segment between a
        matrix predicate and the finite predicate that completes it, e.g. ``увидел,
        что к судну, разрезая воду, приближалась лодка``.  The clause graph correctly
        recognizes ``что`` as subordinate to the matrix clause, but a detached
        parenthetical can leave the later finite clause without a dependency edge.

        The important distinction is semantic: in ``увидел, что лодка приближалась``
        the matrix OBJECT is the *proposition/event*, not the noun ``лодка``.  AH
        already supports an N as an actant of another N, so this pass first asks one
        tiny source-only question whether CHILD EVENT itself is matrix content.  Only
        when the text instead makes the child's SUBJECT a direct matrix participant
        do we project that participant.  NO_LINK/UNCLEAR changes nothing.

        Python fixes the exact orphaned-connector shape, one parent with a free
        OBJECT slot, and one nearest asserted finite child before the model is called.
        The model never sees or chooses canonical UIDs.
        """
        graph = self._candidate_graph
        if graph is None or not assertions:
            return assertions, ()

        by_id = {item.local_id: item for item in assertions}
        head_by_index = {head.token_index: head for head in graph.predicates}

        def predicate_token(item: AssertionCandidate):
            evidence = item.predicate.evidence
            if evidence is None or evidence.start is None or evidence.end is None:
                return None
            matches = [
                token for token in graph.tokens
                if token.start == evidence.start and token.end == evidence.end
            ]
            return matches[0] if len(matches) == 1 else None

        assertion_clause: dict[str, object] = {}
        assertion_head: dict[str, object] = {}
        for item in assertions:
            token = predicate_token(item)
            if token is None:
                continue
            clause = graph.clause_for_token(token.index)
            head = head_by_index.get(token.index)
            if clause is not None and head is not None:
                assertion_clause[item.local_id] = clause
                assertion_head[item.local_id] = head

        diagnostics: list[str] = []
        for bridge in graph.clauses:
            if (
                bridge.parent_clause_id is None
                or bridge.relative
                or bridge.quoted
                or bridge.predicate_heads
                or bridge.connector_span is None
                or not bridge.marker
            ):
                continue

            parents = [
                item for item in assertions
                if getattr(assertion_clause.get(item.local_id), "clause_id", None) == bridge.parent_clause_id
                and item.status is AssertionStatus.ASSERTED
                and not item.quoted
                and not item.negated
                and not any(actant.role is ActantRole.OBJECT for actant in item.actants)
            ]
            if len(parents) != 1:
                continue
            parent = parents[0]
            parent_head = assertion_head.get(parent.local_id)
            if parent_head is None or not getattr(parent_head, "finite", False):
                continue

            connector_end = bridge.connector_span.evidence.end
            if connector_end is None:
                continue
            child_pool: list[tuple[int, AssertionCandidate]] = []
            for child in assertions:
                if child.local_id == parent.local_id:
                    continue
                child_clause = assertion_clause.get(child.local_id)
                child_head = assertion_head.get(child.local_id)
                predicate_evidence = child.predicate.evidence
                if (
                    child_clause is None or child_head is None
                    or child.status is not AssertionStatus.ASSERTED
                    or child.quoted or child.negated
                    or getattr(child_clause, "sentence_id", None) != bridge.sentence_id
                    or getattr(child_clause, "relative", False)
                    or getattr(child_clause, "quoted", False)
                    or getattr(child_clause, "implicit_copula", False)
                    or not getattr(child_head, "finite", False)
                    or predicate_evidence is None or predicate_evidence.start is None
                    or predicate_evidence.start <= connector_end
                ):
                    continue
                subjects = [a for a in child.actants if a.role is ActantRole.SUBJECT]
                if len(subjects) != 1:
                    continue
                participant = subjects[0]
                if participant.candidate_ref is not None or participant.proposition is not None:
                    continue
                child_pool.append((predicate_evidence.start, child))
            if not child_pool:
                continue
            child_pool.sort(key=lambda pair: pair[0])
            child = child_pool[0][1]
            participant = next(a for a in child.actants if a.role is ActantRole.SUBJECT)

            source_text = graph.text
            prompt = (
                f"TEXT:\n{source_text}\n"
                f"PARENT EVENT:\n{parent.predicate.surface}\n"
                f"CHILD EVENT:\n{child.predicate.surface}\n"
                f"CHILD SUBJECT:\n{participant.mention or participant.normalized_hint or '?'}\n"
                "QUESTION:\nWhat, if anything, fills the direct semantic OBJECT/content slot "
                "of PARENT EVENT in this sentence?\n"
                "EVENT_CONTENT: the proposition CHILD EVENT itself is what is perceived, "
                "said, known, thought, etc.\n"
                "DIRECT_SUBJECT_OBJECT: CHILD SUBJECT itself is a direct OBJECT of PARENT "
                "EVENT, independently of CHILD EVENT.\n"
                "NO_LINK: neither relation is entailed by the text.\n"
                "UNCLEAR: the sentence does not determine one reading.\n"
                "CHOICES:\nEVENT_CONTENT\nDIRECT_SUBJECT_OBJECT\nNO_LINK\nUNCLEAR"
            )
            decision, _ = self._deep_semantic_choice_probe(
                "subordinate_content",
                prompt,
                ("EVENT_CONTENT", "DIRECT_SUBJECT_OBJECT", "NO_LINK", "UNCLEAR"),
                optional=True,
            )
            parent = by_id[parent.local_id]
            if decision == "EVENT_CONTENT":
                projected = ActantCandidate(
                    ActantRole.OBJECT,
                    candidate_ref=child.local_id,
                    semantic_hint="SUBORDINATE_PROPOSITION_CONTENT",
                    evidence=child.evidence or child.predicate.evidence,
                )
                by_id[parent.local_id] = replace(parent, actants=parent.actants + (projected,))
                diagnostics.append(
                    f"subordinate-content: {child.local_id} projected as {parent.local_id}.OBJECT event"
                )
                continue
            if decision == "DIRECT_SUBJECT_OBJECT":
                projected = replace(participant, role=ActantRole.OBJECT)
                by_id[parent.local_id] = replace(parent, actants=parent.actants + (projected,))
                diagnostics.append(
                    f"subordinate-content: {child.local_id}.SUBJECT projected as {parent.local_id}.OBJECT"
                )

        return [by_id.get(item.local_id, item) for item in assertions], tuple(diagnostics)

    def _narrative_causal_review_eligible(
        self,
        source: AssertionCandidate,
        target: AssertionCandidate,
        hint: SituationRelationHintCandidate,
    ) -> bool:
        """Return True only for a narrow source pattern worth one causal probe.

        ``EventNormalizer`` intentionally emits broad CAUSAL_CANDIDATE hints for
        diagnostic/runtime use.  Calling an LLM for every adjacent pair would turn
        ordinary coordination, relative clauses and nominal helper facts into an
        unbounded semantic second pass.  Promotion is therefore restricted to a
        high-information pair already established by EventNormalizer: two material
        events in the same non-relative, non-quoted sentence and an explicit
        CAUSAL_CANDIDATE for that exact adjacent pair.  A role-changing shared
        participant or a structural passive-result description is additionally
        required before the model is asked.

        The guard is structural, not lexical.  It never decides CAUSE itself; it only
        decides whether the already bounded CAUSAL_RESPONSE/NO_CAUSAL_RESPONSE/UNCLEAR question is
        worth asking.  Cross-sentence adjacency remains a weak runtime hint.
        """
        graph = self._candidate_graph
        if graph is None:
            return False

        def predicate_token_and_clause(item: AssertionCandidate):
            evidence = item.predicate.evidence
            if evidence is None or evidence.start is None or evidence.end is None:
                return None, None
            matches = [
                token for token in graph.tokens
                if token.start == evidence.start and token.end == evidence.end
            ]
            if len(matches) != 1:
                return None, None
            token = matches[0]
            return token, graph.clause_for_token(token.index)

        source_token, source_clause = predicate_token_and_clause(source)
        target_token, target_clause = predicate_token_and_clause(target)
        if source_token is None or target_token is None or source_clause is None or target_clause is None:
            return False
        if (
            source_clause.sentence_id != target_clause.sentence_id
            or source_clause.relative
            or target_clause.relative
            or source_clause.quoted
            or target_clause.quoted
            or source_clause.implicit_copula
            or target_clause.implicit_copula
        ):
            return False

        # Synthetic/helper predicates need not have a material finite/gerund head.
        def is_event_head(token) -> bool:
            material = material_analyses(token.analyses)
            return any(item.pos in {"VERB", "GRND"} for item in material)

        if not is_event_head(source_token) or not is_event_head(target_token):
            return False

        def identity(actant: ActantCandidate) -> tuple[str, str] | None:
            if actant.entity_ref:
                return ("entity", actant.entity_ref)
            value = (actant.normalized_hint or actant.mention or "").strip().casefold().replace("ё", "е")
            return ("text", value) if value else None

        # Reaching this point means EventNormalizer has already reduced the text
        # to one concrete adjacent event pair and emitted a CAUSAL_CANDIDATE.  Keep
        # the semantic second pass sparse: ordinary same-subject serial narration
        # must not trigger a model call.  A review is useful when source identity
        # already shows a participant changing between actor/patient roles (reaction
        # pattern), or when EventNormalizer marked the target as a passive-result
        # description whose referent may not yet have converged.
        source_by_role: dict[ActantRole, set[tuple[str, str]]] = {}
        target_by_role: dict[ActantRole, set[tuple[str, str]]] = {}
        for actant in source.actants:
            ident = identity(actant)
            if ident is not None:
                source_by_role.setdefault(actant.role, set()).add(ident)
        for actant in target.actants:
            ident = identity(actant)
            if ident is not None:
                target_by_role.setdefault(actant.role, set()).add(ident)

        source_patients = set().union(
            source_by_role.get(ActantRole.OBJECT, set()),
            source_by_role.get(ActantRole.RECIPIENT, set()),
        )
        target_patients = set().union(
            target_by_role.get(ActantRole.OBJECT, set()),
            target_by_role.get(ActantRole.RECIPIENT, set()),
        )
        source_subjects = source_by_role.get(ActantRole.SUBJECT, set())
        target_subjects = target_by_role.get(ActantRole.SUBJECT, set())
        role_transition = bool(
            (source_patients & target_subjects)
            or (source_subjects & target_patients)
        )
        result_description = "passive-result subject" in (hint.reason or "")
        return role_transition or result_description

    def _resolve_narrative_causal_candidates(
        self,
        assertions: list[AssertionCandidate],
        relations: tuple[SituationRelationCandidate, ...],
        hints: tuple[SituationRelationHintCandidate, ...],
    ) -> tuple[
        tuple[SituationRelationCandidate, ...],
        tuple[SituationRelationHintCandidate, ...],
        tuple[str, ...],
    ]:
        """Promote only source-grounded narrative response hints to canonical CAUSE.

        EventNormalizer deliberately emits broad runtime CAUSAL_CANDIDATE hints
        from local narrative structure.  They are not truth.  This pass asks one
        tiny UID-free question only after Python has fixed the two concrete source
        events.  CAUSAL_RESPONSE promotes the pair to an ordinary
        SituationRelationCandidate so Integration may materialize ``L(CAUSE)``;
        NO_CAUSAL_RESPONSE/UNCLEAR leave the
        hint non-canonical.  Invalid protocol output is optional/fail-closed and
        never destroys the already parsed facts.
        """
        by_id = {item.local_id: item for item in assertions}
        existing = {(item.canonical_relation_id, item.source_ref, item.target_ref) for item in relations}
        out = list(relations)
        kept_hints: list[SituationRelationHintCandidate] = []
        diagnostics: list[str] = []
        for hint in hints:
            if hint.kind is not SituationRelationHintKind.CAUSAL_CANDIDATE:
                kept_hints.append(hint)
                continue
            source = by_id.get(hint.source_ref)
            target = by_id.get(hint.target_ref)
            if (
                source is None or target is None
                or source.status is not AssertionStatus.ASSERTED
                or target.status is not AssertionStatus.ASSERTED
                or source.quoted or target.quoted
                or source.negated or target.negated
                or ("CAUSE", source.local_id, target.local_id) in existing
                or not self._narrative_causal_review_eligible(source, target, hint)
            ):
                kept_hints.append(hint)
                continue

            def event_text(item: AssertionCandidate) -> str:
                evidence = item.evidence or item.predicate.evidence
                if evidence is not None and evidence.text.strip():
                    return evidence.text.strip()
                parts = [item.predicate.surface]
                parts.extend(a.mention for a in item.actants if a.mention)
                return " ".join(parts).strip()

            prompt = (
                f"TEXT:\n{self._candidate_graph.text if self._candidate_graph is not None else ''}\n"
                f"EVENT A:\n{event_text(source)}\n"
                f"EVENT B:\n{event_text(target)}\n"
                "QUESTION:\nDoes this narrative present EVENT B as a direct reaction, "
                "response, consequence, or result triggered by EVENT A in this scene? "
                "A contrastive construction can still describe a reaction. Mere temporal "
                "order, topic continuity, shared participants, or plausibility are not enough.\n"
                "CHOICES:\nCAUSAL_RESPONSE\nNO_CAUSAL_RESPONSE\nUNCLEAR"
            )
            decision, _ = self._deep_semantic_choice_probe(
                "narrative_causality",
                prompt,
                ("CAUSAL_RESPONSE", "NO_CAUSAL_RESPONSE", "UNCLEAR"),
                optional=True,
            )
            if decision == "CAUSAL_RESPONSE":
                relation = SituationRelationCandidate(
                    "CAUSE", source.local_id, target.local_id, hint.evidence
                )
                out.append(relation)
                existing.add(("CAUSE", source.local_id, target.local_id))
                diagnostics.append(
                    f"narrative-causality: {source.local_id} CAUSE {target.local_id} confirmed from source"
                )
                continue
            kept_hints.append(hint)
        return tuple(out), tuple(kept_hints), tuple(diagnostics)

    def _materialize_nominal_subject_projections(
        self,
        text: str,
        tokens: tuple[_SourceToken, ...],
        assertions: list[AssertionCandidate],
        assertion_spans: dict[str, _Span | None],
    ) -> tuple[list[AssertionCandidate], dict[str, _Span | None]]:
        """Expose recoverable referent classes from nominal naming/label clauses.

        The explicit facts remain ordinary nominal assertions, for example
        ``название(Крипл, моего проекта)`` and ``имя(Крипл, моего ИИ)``.  Some
        nominal predicates additionally say that SUBJECT is *the name/title/label
        used for the thing described by a complement*.  In that case a shorthand
        class assertion such as ``проект(Крипл)`` is useful for ordinary queries.

        Crucially, the model no longer answers the abstract question "is this noun
        a shorthand class/identity of SUBJECT?".  The live Qwen run showed that this
        wording can correctly parse the frame yet reject ``проект`` for
        ``Крипл — название моего проекта``.  Instead the semantic work is split:

        1. deterministic syntax has already established a nominal-predicate frame;
        2. one isolated deep-semantic cue checks only one local paraphrase: whether
           the complement is *called/named/labeled by SUBJECT* (YES / NO / UNCLEAR);
        3. when that cue is YES and there is exactly one noun concept in the
           complements, Python projects it directly;
        4. only when several noun concepts remain does a second bounded probe choose
           the complement target.

        This stays generic and does not use a lexical marker table. The semantic model
        receives no AH UIDs, memory, proof state, or candidate truth value; it can only
        accept/reject the one local naming paraphrase.  Canonical projection, identity,
        and validation remain deterministic.  No NAME/DENOTES ontology or hidden proof
        rule is introduced.
        """
        if not assertions or not self._nominal_subject_spans:
            return assertions, assertion_spans

        token_by_index = {token.index: token for token in tokens}

        def token_indices_for_evidence(evidence: EvidenceSpan | None) -> tuple[int, ...]:
            if evidence is None or evidence.start is None or evidence.end is None:
                return ()
            return tuple(
                token.index
                for token in tokens
                if token.start >= evidence.start
                and token.end <= evidence.end
                and self._is_word_token(token)
            )

        def noun_choices(actant: ActantCandidate) -> tuple[tuple[int, str, str], ...]:
            values: list[tuple[int, str, str]] = []
            seen: set[tuple[int, str]] = set()
            for index in token_indices_for_evidence(actant.evidence):
                token = token_by_index[index]
                selected = self._contextual_nominal_lemmas.get(index)
                infos = tuple(
                    info for info in self._morph_all(token)
                    if info.pos == "NOUN" and info.normal_form.strip()
                )
                lemmas: list[str] = []
                if selected is not None:
                    matching = [
                        info.normal_form.strip() for info in infos
                        if info.normal_form.strip().casefold() == selected.casefold()
                    ]
                    if matching:
                        lemmas.append(matching[0])
                if not lemmas:
                    for info in infos:
                        lemma = info.normal_form.strip()
                        if lemma.casefold() not in {item.casefold() for item in lemmas}:
                            lemmas.append(lemma)
                for lemma in lemmas:
                    key = (index, lemma.casefold())
                    if key in seen:
                        continue
                    seen.add(key)
                    values.append((index, token.text, lemma))
            return tuple(values)

        projected: list[AssertionCandidate] = []
        new_spans = dict(assertion_spans)
        existing_signatures = {
            (
                item.predicate.lookup_form.casefold(),
                tuple(
                    (actant.role, (actant.normalized_hint or actant.mention or "").casefold())
                    for actant in item.actants
                ),
            )
            for item in assertions
        }

        for assertion in tuple(assertions):
            predicate_evidence = assertion.predicate.evidence
            if predicate_evidence is None or predicate_evidence.start is None:
                continue
            predicate_token_index = next(
                (
                    token.index
                    for token in tokens
                    if token.start == predicate_evidence.start
                    and token.end == predicate_evidence.end
                ),
                None,
            )
            if predicate_token_index not in self._nominal_subject_spans:
                continue

            subject = next(
                (actant for actant in assertion.actants if actant.role is ActantRole.SUBJECT),
                None,
            )
            if subject is None:
                continue

            candidate_rows: list[tuple[ActantCandidate, int, str, str]] = []
            for actant in assertion.actants:
                if actant.role is ActantRole.SUBJECT:
                    continue
                for index, surface, lemma in noun_choices(actant):
                    if index == predicate_token_index:
                        continue
                    candidate_rows.append((actant, index, surface, lemma))
            if not candidate_rows:
                continue

            complements = "\n".join(
                f"{actant.role.value} = {actant.mention or actant.normalized_hint or ''}"
                for actant in assertion.actants
                if actant.role is not ActantRole.SUBJECT
            ) or "none"
            semantic_prompt = (
                f"TEXT:\n{text}\n"
                f"CLAUSE:\n{assertion.evidence.text if assertion.evidence is not None else text}\n"
                f"SUBJECT:\n{subject.mention or subject.normalized_hint or ''}\n"
                f"NOMINAL PREDICATE:\n{assertion.predicate.lookup_form}\n"
                f"COMPLEMENT:\n{complements}\n"
                "QUESTION:\nDoes this clause state that SUBJECT is the name/title/label/designation "
                "used for the referent or kind described by COMPLEMENT?\n"
                "YES: SUBJECT functions as that referent's name/label (pattern: X is the name/title of Y).\n"
                "NO: the nominal predicate expresses another relation such as part, property, location, "
                "capital, material, role, or association; merely being related to COMPLEMENT is not enough.\n"
                "UNCLEAR: the clause itself does not decide reliably.\n"
                "Judge only the literal local clause. Do not use world knowledge and do not decide "
                "whether any projected assertion should be stored.\n"
                "CHOICES:\nYES\nNO\nUNCLEAR"
            )
            label_semantics, _ = self._deep_semantic_choice_probe(
                "nominal_label_semantics",
                semantic_prompt,
                ("YES", "NO", "UNCLEAR"),
                optional=True,
            )
            if label_semantics != "YES":
                continue

            selected_rows: list[tuple[ActantCandidate, int, str, str]]
            # One complement noun is already a fully deterministic target.  Do not
            # spend a second model call deciding among one item and NONE after the
            # predicate family itself has been established as LABEL_IDENTIFIER.
            if len(candidate_rows) == 1:
                selected_rows = [candidate_rows[0]]
            else:
                labels = tuple(f"C{i}" for i in range(1, len(candidate_rows) + 1))
                choices = ("NONE", *labels)
                options = "\n".join(
                    f"{label} = {row[3]} (source: {row[2]}; complement: "
                    f"{row[0].role.value}={row[0].mention or row[0].normalized_hint or ''})"
                    for label, row in zip(labels, candidate_rows)
                )
                target_prompt = (
                    f"TEXT:\n{text}\n"
                    f"SUBJECT:\n{subject.mention or subject.normalized_hint or ''}\n"
                    f"NOMINAL PREDICATE:\n{assertion.predicate.lookup_form}\n"
                    f"COMPLEMENTS:\n{complements}\n"
                    f"CANDIDATE TARGET CONCEPTS:\n{options}\n"
                    "KNOWN PREDICATE FAMILY:\nThe nominal predicate is a name/title/label/identifier sense.\n"
                    "QUESTION:\nWhich candidate names the kind of thing that SUBJECT labels? "
                    "Choose a noun only when it is the target of that naming/label relation, not "
                    "a nested owner, location, source, material, or associated noun.\n"
                    "CHOICES:\n" + "\n".join(choices)
                )
                decision, _ = self._exact_choice_probe(
                    "nominal_projection_target", target_prompt, choices
                )
                if decision == "NONE":
                    continue
                selected_rows = [candidate_rows[labels.index(decision)]]

            for _actant, token_index, surface, lemma in selected_rows:
                token = token_by_index[token_index]
                predicate = PredicateCandidate(
                    surface=surface,
                    normalized_hint=lemma,
                    evidence=EvidenceSpan(surface, token.start, token.end),
                )
                projected_subject = replace(subject, role=ActantRole.SUBJECT)
                signature = (
                    predicate.lookup_form.casefold(),
                    ((
                        ActantRole.SUBJECT,
                        (projected_subject.normalized_hint or projected_subject.mention or "").casefold(),
                    ),),
                )
                if signature in existing_signatures:
                    continue
                local_id = f"A{len(assertions) + len(projected) + 1}"
                projected_assertion = AssertionCandidate(
                    local_id=local_id,
                    predicate=predicate,
                    actants=(projected_subject,),
                    evidence=assertion.evidence,
                    negated=assertion.negated,
                    status=assertion.status,
                    quoted=assertion.quoted,
                )
                projected.append(projected_assertion)
                new_spans[local_id] = assertion_spans.get(assertion.local_id)
                existing_signatures.add(signature)

        if projected:
            assertions.extend(projected)
        return assertions, new_spans

    def _resolve_nominal_predication_modes(
        self,
        builder: LinguisticCandidateBuilder,
        graph: LinguisticCandidateGraph,
    ) -> LinguisticCandidateGraph:
        """Normalize noun-headed copular shells before predicate scheduling.

        Russian present-tense nominal predication may omit ``быть`` and may use a
        dash / copular ``это``.  Morphology alone can misread a proper/common name
        as ADJS and thereby turn the referent into a predicate (the real ``Крипл``
        failure).  Python therefore gives an already recognized explicit copular
        shell precedence over that ambiguous lexical POS reading: the left term is
        the predicated-about term and the right nominal head is the runtime
        predicate.  A finite overt verb is not silently nominalized by this rule.
        No model chooses the subject/predicate direction of an explicit shell.

        A noun immediately after the copular shell is promoted to a runtime
        predicate head.  Coordinated repetitions (``... и ... это имя ...``)
        become peer predicate frames and reuse the same left referent through the
        existing coordinated-actant machinery.  This is runtime syntax only; no
        NAME/DENOTES ontology is introduced.
        """
        tokens = graph.tokens
        if not tokens:
            return graph

        def is_word(index: int) -> bool:
            return 1 <= index <= len(tokens) and bool(re.search(r"\w", tokens[index - 1].text))

        def low(index: int) -> str:
            return tokens[index - 1].text.casefold() if 1 <= index <= len(tokens) else ""

        def material(index: int) -> tuple[MorphInfo, ...]:
            token = tokens[index - 1]
            return builder._material_analyses(token)

        def noun_lemmas(index: int) -> tuple[str, ...]:
            values: list[str] = []
            for info in material(index):
                if info.pos != "NOUN":
                    continue
                value = info.normal_form.strip()
                if value and value not in values:
                    values.append(value)
            return tuple(values)

        def is_nominal_left(index: int) -> bool:
            return any(
                info.pos in {"NOUN", "NPRO"} and (info.case in {None, "nomn"})
                for info in material(index)
            )

        def is_strong_verbal(index: int) -> bool:
            return any(info.pos in {"VERB", "PRED", "INFN", "GRND"} for info in material(index))

        def sentence_bounds(index: int) -> tuple[int, int]:
            left, right = 1, len(tokens)
            for token in tokens:
                if token.index < index and token.text in {".", "!", "?", ";"}:
                    left = token.index + 1
                elif token.index > index and token.text in {".", "!", "?", ";"}:
                    right = token.index - 1
                    break
            return left, right

        def dash_is_copular(index: int) -> bool:
            token = tokens[index - 1]
            if token.text in {"—", "–"}:
                return True
            if token.text != "-":
                return False
            # Hyphens inside lexical compounds are not copular punctuation.
            left_space = token.start > 0 and graph.text[token.start - 1].isspace()
            right_space = token.end < len(graph.text) and graph.text[token.end].isspace()
            return left_space or right_space

        def nearest_word_left(index: int, lower: int) -> int | None:
            for cursor in range(index - 1, lower - 1, -1):
                if not is_word(cursor):
                    continue
                if low(cursor) in {"что", "чтобы", "если", "когда", "где", "куда", "откуда"}:
                    return None
                return cursor
            return None

        def next_noun(index: int, upper: int) -> int | None:
            for cursor in range(index, upper + 1):
                if tokens[cursor - 1].text in {",", ";", ".", "!", "?"}:
                    break
                if low(cursor) in {"и", "или", "либо", "а", "но", "однако"}:
                    break
                if noun_lemmas(cursor):
                    return cursor
            return None

        original_by_index = {head.token_index: head for head in graph.predicates}
        predicates = dict(original_by_index)
        promoted: dict[int, PredicateHeadCandidate] = {}
        suppressed: set[int] = set()
        handled_markers: set[int] = set()

        # Structural primary shells: X — [это] Y and X это Y.  For the latter we
        # reject a verbal left neighbour so ordinary object pronoun ``это`` is not
        # reinterpreted as a copula.
        marker_indices = [
            token.index for token in tokens
            if dash_is_copular(token.index) or token.text.casefold() == "это"
        ]
        # At most one primary nominal shell is selected per punctuation-bounded
        # sentence.  Additional repeated copulas in that sentence are handled as
        # coordinated predicates below; independent sentences remain independent.
        primary_frames: list[tuple[_Span, int, int]] = []
        primary_sentences: set[tuple[int, int]] = set()
        for marker_index in marker_indices:
            owner = graph.clause_for_token(marker_index)
            if (
                owner is not None
                and owner.ellipsis_kind is not None
                and not owner.implicit_copula
            ):
                # The structural graph already assigned this shell to recovery.
                # A later nominal pass must not reinterpret its role fillers as
                # new predicates and thereby erase the antecedent relation.
                self._deterministic_trace(
                    "predicate_ownership", f"CLAUSE:{owner.clause_id}\nTEXT:{owner.span.text}",
                    "ELLIPSIS:preserved",
                )
                continue
            left_bound, right_bound = sentence_bounds(marker_index)
            sentence_key = (left_bound, right_bound)
            if sentence_key in primary_sentences:
                continue
            marker_is_dash = dash_is_copular(marker_index)
            left_index = nearest_word_left(marker_index, left_bound)
            if left_index is None:
                continue
            if not marker_is_dash and is_strong_verbal(left_index):
                continue

            right_cursor = marker_index + 1
            shell_tokens = {marker_index}
            if marker_is_dash and right_cursor <= right_bound and low(right_cursor) == "это":
                shell_tokens.add(right_cursor)
                right_cursor += 1
            head_index = next_noun(right_cursor, right_bound)
            if head_index is None:
                continue

            # Do not steal a noun that is already inside an overt verbal frame.
            if any(
                head.strength >= 2
                and head.token_index not in {left_index, head_index}
                and left_index < head.token_index < head_index
                for head in graph.predicates
            ):
                continue

            left_head = original_by_index.get(left_index)
            if left_head is not None and not is_nominal_left(left_index):
                # Once the explicit copular shell ``X — [это] Y`` / ``X это Y``
                # has been recognized and Y is a nominal head, the shell itself
                # supplies the local syntactic direction: X is the term being
                # predicated about and Y is the nominal predicate.  Do not ask an
                # LLM to vote against that structure merely because morphology
                # offered an adjective-like reading for X (the live ``Крипл ->
                # криплый`` failure).  A finite overt verb on the left is not
                # silently nominalized here; those clauses stay with the ordinary
                # predicate machinery.  Infinitives remain eligible nominal
                # subjects (e.g. ``Работать — это труд``).
                left_infos = material(left_index)
                if any(info.pos == "VERB" for info in left_infos):
                    continue
                suppressed.add(left_index)

            lemmas = noun_lemmas(head_index)
            if not lemmas:
                continue
            promoted[head_index] = PredicateHeadCandidate(
                head_index, 2, True, lemmas, nominal_predicative=True
            )
            subject_token = tokens[left_index - 1]
            subject_span = _Span(
                left_index,
                left_index,
                subject_token.text,
                EvidenceSpan(subject_token.text, subject_token.start, subject_token.end),
            )
            self._nominal_subject_spans[head_index] = subject_span
            self._nominal_linker_tokens.update(shell_tokens)
            handled_markers.add(marker_index)
            primary_sentences.add(sentence_key)
            primary_frames.append((subject_span, head_index, right_bound))

        # Coordinated nominal predicates may repeat the copular shell while
        # omitting the original subject: X — это Y и одновременно с этим это Z.
        for subject_span, primary_head, right_bound in primary_frames:
            cursor = primary_head + 1
            while cursor <= right_bound:
                if low(cursor) not in {"и", "да", "а", "но", "однако"}:
                    cursor += 1
                    continue
                coordinator = cursor
                scan = cursor + 1
                copula_index: int | None = None
                while scan <= right_bound:
                    if tokens[scan - 1].text in {",", ";", ".", "!", "?"}:
                        break
                    if low(scan) in {"или", "либо"}:
                        break
                    if low(scan) == "это":
                        copula_index = scan
                        break
                    # Stop before a new overt verbal event; this is not nominal
                    # predicate coordination anymore.
                    if is_strong_verbal(scan):
                        break
                    scan += 1
                if copula_index is None:
                    cursor += 1
                    continue
                head_index = next_noun(copula_index + 1, right_bound)
                if head_index is None:
                    cursor += 1
                    continue
                lemmas = noun_lemmas(head_index)
                if not lemmas:
                    cursor += 1
                    continue
                promoted[head_index] = PredicateHeadCandidate(
                    head_index, 2, True, lemmas, nominal_predicative=True
                )
                self._nominal_subject_spans[head_index] = subject_span
                self._nominal_linker_tokens.update(range(coordinator, copula_index + 1))
                handled_markers.add(copula_index)
                cursor = head_index + 1

        if not promoted and not suppressed:
            return graph

        for index in suppressed:
            predicates.pop(index, None)
        predicates.update(promoted)
        predicate_tuple = tuple(predicates[index] for index in sorted(predicates))
        clauses = builder._clauses(graph.text, graph.tokens, predicate_tuple)
        # Rebuilding after promoting a provisional nominal predicate must not
        # erase an independently licensed ellipsis reading.  The new predicate
        # head makes the rebuilt clause look overtly complete, although the
        # original candidate graph had already established both readings.  Keep
        # that runtime ambiguity until frame recovery can compare the complete
        # source/target slot structures.  Match by source extent rather than by
        # clause id so this remains stable if clause numbering changes.
        provisional_ellipsis = {
            (
                item.sentence_id,
                item.span.evidence.start,
                item.span.evidence.end,
            ): item
            for item in graph.clauses
            if item.ellipsis_kind is not None and item.implicit_copula
        }
        if provisional_ellipsis:
            clauses = tuple(
                replace(
                    item,
                    implicit_copula=True,
                    ellipsis_kind=original.ellipsis_kind,
                    ellipsis_source_clause_id=original.ellipsis_source_clause_id,
                )
                if (
                    original := provisional_ellipsis.get(
                        (
                            item.sentence_id,
                            item.span.evidence.start,
                            item.span.evidence.end,
                        )
                    )
                ) is not None
                else item
                for item in clauses
            )
        coordinations = builder._coordinations(graph.text, graph.tokens, predicate_tuple)
        predicate_coordinations = builder._predicate_coordinations(graph.tokens, clauses)
        frame_graph = builder._frame_graph(
            graph.tokens, clauses, predicate_tuple, predicate_coordinations
        )
        return replace(
            graph,
            predicates=predicate_tuple,
            clauses=clauses,
            coordinations=coordinations,
            frame_graph=frame_graph,
        )

    def _resolve_relative_adverb_clause_modes(
        self,
        builder: LinguisticCandidateBuilder,
        graph: LinguisticCandidateGraph,
    ) -> LinguisticCandidateGraph:
        """Resolve the surface ambiguity of relative adverbs before frame parsing.

        ``где/куда/откуда/когда`` after a nominal anchor are not sufficient proof
        of a relative clause: ``Лиза написала текст, когда получила советы`` is
        temporal subordination, while ``день, когда она пришла`` is relative.
        Python narrows the issue to one binary semantic distinction and rebuilds
        only the runtime ClauseFrameGraph; no AH role is assigned here.
        """
        ambiguous = [
            clause for clause in graph.clauses
            if clause.relative and (clause.marker or "").casefold() in {"где", "куда", "откуда", "когда"}
        ]
        if not ambiguous:
            return graph
        clauses = list(graph.clauses)
        changed = False
        for clause in ambiguous:
            prompt = (
                f"TEXT:\n{graph.text}\n"
                f"CONNECTOR:\n{clause.marker}\n"
                "QUESTION:\nDoes this connector introduce a relative clause that modifies a nominal "
                "anchor, or an independent subordinate situation relation?\n"
                "CHOICES:\nRELATIVE\nSUBORDINATE"
            )
            decision, _ = self._exact_choice_probe(
                "relative_clause_mode", prompt, ("RELATIVE", "SUBORDINATE")
            )
            if decision == "RELATIVE":
                continue
            index = next(i for i, item in enumerate(clauses) if item.clause_id == clause.clause_id)
            clauses[index] = replace(clause, relative=False)
            changed = True
        if not changed:
            return graph
        clause_tuple = tuple(clauses)
        frame_graph = builder._frame_graph(
            graph.tokens, clause_tuple, graph.predicates, graph.frame_graph.coordinations
        )
        return replace(graph, clauses=clause_tuple, frame_graph=frame_graph)

    def _deterministic_act_type(
        self,
        tokens: tuple[_SourceToken, ...],
        predicate_candidates: tuple[int, ...],
        clause_id: str | None,
    ) -> str | None:
        """Classify force for one clause/frame root, never for a whole sentence.

        Orthographic ``?`` belongs to the clause that carries the independent
        illocution.  An embedded complement in ``Скажи, когда он придёт?`` must
        therefore not become a second QUERY merely because the outer sentence ends
        in a question mark.  Quoted clauses are an explicit exception: their own
        punctuation establishes an independent quoted force.
        """
        graph = self._candidate_graph
        clause = None
        if graph is not None and clause_id is not None:
            clause = next((item for item in graph.clauses if item.clause_id == clause_id), None)

        if clause is not None:
            start, end = clause.span.start_index, clause.span.end_index
            focus_index = (
                predicate_candidates[0] if predicate_candidates else start
            )
        elif predicate_candidates:
            focus_index = predicate_candidates[0]
            start, end = self._clause_bounds(
                self._resolve_span_from_source(tokens, focus_index, focus_index), tokens
            )
        else:
            start, end = 1, len(tokens)
            focus_index = start

        moods: set[str] = set()
        for index in predicate_candidates:
            if index < start or index > end:
                continue
            for info in self._material_morph_analyses(tokens[index - 1]):
                if info.pos == "VERB" and info.mood:
                    moods.add(info.mood)

        # Imperative morphology is local clause force and wins over sentence-level
        # punctuation (``Скажи?`` is still a request/command frame).
        if moods == {"impr"}:
            return "COMMAND"

        embedded = False
        quoted = bool(clause.quoted) if clause is not None else False
        if graph is not None and predicate_candidates:
            embedded = graph.frame_graph.is_embedded(focus_index)
        elif clause is not None and clause.parent_clause_id is not None:
            embedded = True

        # Clause spans omit terminal strong punctuation. Inspect only punctuation
        # immediately belonging to this clause, not the rest of the sentence.
        terminal_question = any(
            tokens[i - 1].text == "?"
            for i in range(start, end + 1)
        )
        cursor = end + 1
        while not terminal_question and cursor <= len(tokens):
            token = tokens[cursor - 1]
            if token.text in {"?", "!", ".", ";"}:
                terminal_question = token.text == "?"
                break
            if token.text in {"»", "”", "\"", ",", ":"}:
                cursor += 1
                continue
            if self._is_word_token(token):
                break
            cursor += 1

        if terminal_question and (not embedded or quoted):
            return "QUERY"

        # Non-quoted embedded clauses are proposition content/modifiers, not
        # independent speech acts. Their frames are parsed assertion-shaped so
        # proposition composition can attach/scope them later.
        if embedded and not quoted:
            return "ASSERTION"

        explicit_subject = any(
            self._has_structural_morph(tokens[i - 1], poses={"NOUN", "NPRO"}, case="nomn")
            for i in range(start, end + 1)
            if self._is_word_token(tokens[i - 1])
        )
        if explicit_subject:
            return "ASSERTION"

        if predicate_candidates:
            if "indc" in moods or not moods:
                return "ASSERTION"
            return None
        if clause is not None and clause.implicit_copula:
            return "ASSERTION"
        return None

    def _assertion_evidence(
        self,
        text: str,
        tokens: tuple[_SourceToken, ...],
        predicate_span: _Span | None,
    ) -> EvidenceSpan:
        """Return the smallest deterministic clause evidence for one frame."""
        if self._candidate_graph is None:
            return EvidenceSpan(text, 0, len(text))
        if predicate_span is None:
            clause = next(
                (item for item in self._candidate_graph.clauses
                 if item.clause_id == self._active_implicit_clause_id),
                None,
            )
            return clause.span.evidence if clause is not None else EvidenceSpan(text, 0, len(text))
        clause = self._candidate_graph.clause_for_token(predicate_span.start_index)
        if clause is None:
            return EvidenceSpan(text, 0, len(text))
        start, end = self._predicate_argument_bounds(predicate_span, tokens)
        return self._resolve_span(text, tokens, start, end).evidence

    def _derive_act_dependencies(
        self,
        assertion_spans: dict[str, _Span | None],
        query_spans: dict[str, _Span | None],
        command_spans: dict[str, _Span | None],
    ) -> tuple[ActDependencyCandidate, ...]:
        """Project ClauseFrameGraph orientation into the public runtime contract.

        This is intentionally structural only. A SUBORDINATE/NONFINITE/QUOTED
        edge says which act/frame is embedded under which root; it does not assign
        OBJECT/PURPOSE/etc. and does not materialize an AH relation.
        """
        graph = self._candidate_graph
        if graph is None or not graph.frame_graph.dependencies:
            return ()
        all_spans = {**assertion_spans, **query_spans, **command_spans}
        head_refs: dict[int, list[str]] = {}
        for ref, span in all_spans.items():
            if span is None:
                continue
            for head in graph.predicates:
                if span.start_index <= head.token_index <= span.end_index:
                    head_refs.setdefault(head.token_index, []).append(ref)

        kind_map = {
            FrameDependencyKind.SUBORDINATE: ActDependencyKind.SUBORDINATE,
            FrameDependencyKind.NONFINITE: ActDependencyKind.NONFINITE,
            FrameDependencyKind.QUOTED: ActDependencyKind.QUOTED,
        }
        result: list[ActDependencyCandidate] = []
        seen: set[tuple[str, str, ActDependencyKind]] = set()
        for edge in graph.frame_graph.dependencies:
            parents = head_refs.get(edge.parent_token_index, [])
            children = head_refs.get(edge.child_token_index, [])
            if len(parents) != 1 or len(children) != 1:
                continue
            kind = kind_map[edge.kind]
            key = (parents[0], children[0], kind)
            if key in seen:
                continue
            seen.add(key)
            result.append(ActDependencyCandidate(parents[0], children[0], kind))
        return tuple(result)

    def _mark_quoted_acts(
        self,
        assertions: list[AssertionCandidate],
        queries: list[QueryCandidate],
        commands: list[CommandCandidate],
        dependencies: tuple[ActDependencyCandidate, ...],
        assertion_spans: dict[str, _Span | None],
        query_spans: dict[str, _Span | None],
        command_spans: dict[str, _Span | None],
    ) -> tuple[list[AssertionCandidate], list[QueryCandidate], list[CommandCandidate]]:
        """Mark the complete runtime subtree rooted in direct quotation.

        QUOTED is a scope boundary, not merely an edge label. Descendant clauses
        inside the quote inherit quotation even when their immediate dependency is
        SUBORDINATE/NONFINITE. This prevents embedded quoted assertions/questions/
        commands from leaking back into the current speaker's top-level acts.
        """
        adjacency: dict[str, list[str]] = {}
        quoted: set[str] = set()

        # Clause-level quote recognition is the primary source boundary. It also
        # covers cases where several local assertions share one predicate span and
        # therefore cannot be projected to a unique ActDependencyCandidate edge.
        graph = self._candidate_graph
        if graph is not None:
            for ref, span in {**assertion_spans, **query_spans, **command_spans}.items():
                if span is None:
                    continue
                clause = graph.clause_for_token(span.start_index)
                if clause is not None and clause.quoted:
                    quoted.add(ref)

        for dependency in dependencies:
            adjacency.setdefault(dependency.parent_ref, []).append(dependency.child_ref)
            if dependency.kind is ActDependencyKind.QUOTED:
                quoted.add(dependency.child_ref)
        queue = list(quoted)
        while queue:
            parent = queue.pop()
            for child in adjacency.get(parent, ()):
                if child not in quoted:
                    quoted.add(child)
                    queue.append(child)
        if not quoted:
            return assertions, queries, commands

        def mark_assertion(item: AssertionCandidate) -> AssertionCandidate:
            if item.local_id not in quoted:
                return item
            alternatives = tuple(replace(alt, quoted=True) for alt in item.alternatives)
            return replace(item, quoted=True, alternatives=alternatives)

        return (
            [mark_assertion(item) for item in assertions],
            [replace(item, quoted=True) if item.local_id in quoted else item for item in queries],
            [replace(item, quoted=True) if item.local_id in quoted else item for item in commands],
        )

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

        def branch_expr(refs: tuple[str, ...]) -> PropositionExprCandidate:
            if len(refs) == 1:
                return PropositionExprCandidate.ref_expr(refs[0])
            ordered_refs = sorted(
                refs,
                key=lambda ref: assertion_spans[ref].start_index
                if assertion_spans.get(ref) is not None else 10**9,
            )
            # Preserve explicit OR at proposition level. AND is the default only
            # when no disjunctive coordinator occurs between consecutive frames.
            saw_or = False
            saw_and = False
            for left, right in zip(ordered_refs, ordered_refs[1:]):
                ls, rs = assertion_spans.get(left), assertion_spans.get(right)
                if ls is None or rs is None:
                    continue
                between = [
                    token.text.casefold() for token in graph.tokens
                    if ls.end_index < token.index < rs.start_index
                ]
                saw_or = saw_or or any(item in {"или", "либо"} for item in between)
                saw_and = saw_and or any(item in {"и", "да"} for item in between)
            operator = PropositionOperator.OR if saw_or and not saw_and else PropositionOperator.AND
            return PropositionExprCandidate(
                operator,
                members=tuple(PropositionExprCandidate.ref_expr(ref) for ref in ordered_refs),
            )

        out: list[ConditionalCandidate] = []
        seen: set[tuple[tuple[str, ...], tuple[str, ...]]] = set()
        clauses = list(graph.clauses)
        clause_index = {item.clause_id: i for i, item in enumerate(clauses)}
        for clause in clauses:
            if clause.marker != "если" or clause.parent_clause_id is None:
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
            consequent_ids: list[str] = list(
                clause_to_locals.get(clause.parent_clause_id, ())
            )
            # A fronted condition can govern an additive coordinated continuation
            # that the clause builder represents as the next top-level sibling:
            # ``Если A, B и C``.  Once B is the parent consequent, contiguous
            # same-sentence siblings explicitly led by additive coordinators remain
            # inside that consequent region.  Do not absorb OR/adversative siblings
            # here: they require a different logical composition than AND.
            if 0 <= parent_i:
                for sibling in clauses[parent_i + 1:]:
                    if sibling.sentence_id != clause.sentence_id:
                        break
                    if sibling.parent_clause_id is not None:
                        break
                    if sibling.marker.casefold() not in {"и", "да"}:
                        break
                    sibling_locals = clause_to_locals.get(sibling.clause_id, ())
                    if not sibling_locals:
                        break
                    consequent_ids.extend(sibling_locals)
            consequent = tuple(dict.fromkeys(consequent_ids))
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
                    antecedent_expr=branch_expr(antecedent),
                    consequent_expr=branch_expr(consequent),
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
        def mark(item: AssertionCandidate) -> AssertionCandidate:
            if item.local_id not in conditional_ids:
                return item
            alternatives = tuple(
                replace(alt, status=AssertionStatus.CONDITIONAL)
                for alt in item.alternatives
            )
            return replace(
                item,
                status=AssertionStatus.CONDITIONAL,
                alternatives=alternatives,
            )

        return [mark(item) for item in assertions]

    def _mark_embedded_statuses(
        self,
        assertions: list[AssertionCandidate],
    ) -> list[AssertionCandidate]:
        """Mark proposition-valued content that is not independently asserted.

        OBJECT-content, PURPOSE and HOW-TO are semantic operands of a matrix
        proposition. Their child N nodes must exist canonically so the parent can
        reference them, but ordinary world lookup must not treat them as true by
        mention alone. Factivity, when supported, is a separate semantic mechanism.
        """
        embedded_refs: set[str] = set()
        for parent in assertions:
            for actant in parent.actants:
                if actant.role not in {ActantRole.OBJECT, ActantRole.PURPOSE, ActantRole.HOW_TO}:
                    continue
                if (
                    actant.candidate_ref is not None
                    and actant.candidate_ref not in self._asserted_nonfinite_refs
                ):
                    embedded_refs.add(actant.candidate_ref)
                if actant.proposition is not None:
                    embedded_refs.update(
                        ref for ref in actant.proposition.leaf_refs()
                        if ref not in self._asserted_nonfinite_refs
                    )
        if not embedded_refs:
            return assertions
        def mark(item: AssertionCandidate) -> AssertionCandidate:
            if item.local_id not in embedded_refs or item.status is not AssertionStatus.ASSERTED:
                return item
            alternatives = tuple(
                replace(alt, status=AssertionStatus.EMBEDDED)
                if alt.status is AssertionStatus.ASSERTED else alt
                for alt in item.alternatives
            )
            return replace(
                item,
                status=AssertionStatus.EMBEDDED,
                alternatives=alternatives,
            )

        return [mark(item) for item in assertions]

    def _promote_factive_embedded_content(
        self,
        assertions: list[AssertionCandidate],
    ) -> tuple[list[AssertionCandidate], tuple[str, ...]]:
        """Promote proposition content only when the matrix event entails its truth.

        ``_mark_embedded_statuses`` is intentionally conservative: proposition-valued
        OBJECT content is scoped EMBEDDED so verbs of saying, thinking, hoping, etc.
        cannot leak their complements into ordinary world truth.  Some matrix events
        are factive in the concrete source use, however (for example perception or
        discovery of an event that actually occurred).  This pass handles exactly
        that missing semantic boundary.

        Python first fixes one asserted matrix proposition and one already-linked
        EMBEDDED child through the explicit ``SUBORDINATE_PROPOSITION_CONTENT`` cue.
        The model receives only the source text and the two local event descriptions
        and answers one bounded FACTIVE/NONFACTIVE/UNCLEAR question.  Canonical UIDs
        never cross the perception boundary.  NONFACTIVE/UNCLEAR leaves the child
        scoped; only FACTIVE restores ordinary ASSERTED status.
        """
        graph = self._candidate_graph
        if graph is None or not assertions:
            return assertions, ()

        by_id = {item.local_id: item for item in assertions}
        diagnostics: list[str] = []

        def event_text(item: AssertionCandidate) -> str:
            evidence = item.evidence or item.predicate.evidence
            if evidence is not None and evidence.text.strip():
                return evidence.text.strip()
            parts = [item.predicate.surface]
            parts.extend(a.mention for a in item.actants if a.mention)
            return " ".join(parts).strip()

        for parent in assertions:
            if (
                parent.status is not AssertionStatus.ASSERTED
                or parent.quoted
                or parent.negated
            ):
                continue
            for actant in parent.actants:
                if (
                    actant.role is not ActantRole.OBJECT
                    or actant.candidate_ref is None
                    or (actant.semantic_hint or "").strip().upper()
                    != "SUBORDINATE_PROPOSITION_CONTENT"
                ):
                    continue
                child = by_id.get(actant.candidate_ref)
                if (
                    child is None
                    or child.status is not AssertionStatus.EMBEDDED
                    or child.quoted
                    or child.negated
                ):
                    continue

                prompt = (
                    f"TEXT:\n{graph.text}\n"
                    f"MATRIX EVENT:\n{event_text(parent)}\n"
                    f"CONTENT EVENT:\n{event_text(child)}\n"
                    "QUESTION:\nDoes this use of MATRIX EVENT present CONTENT EVENT "
                    "as an actual fact in the narrated world, rather than merely as "
                    "something said, thought, imagined, hoped, intended, or otherwise "
                    "represented without asserting its truth?\n"
                    "FACTIVE: the text commits to CONTENT EVENT as actually occurring/holding.\n"
                    "NONFACTIVE: the text only represents CONTENT EVENT as content and does not "
                    "commit to its truth.\n"
                    "UNCLEAR: the text does not determine this safely.\n"
                    "CHOICES:\nFACTIVE\nNONFACTIVE\nUNCLEAR"
                )
                decision, _ = self._deep_semantic_choice_probe(
                    "factivity",
                    prompt,
                    ("FACTIVE", "NONFACTIVE", "UNCLEAR"),
                    optional=True,
                )
                if decision != "FACTIVE":
                    continue

                alternatives = tuple(
                    replace(alt, status=AssertionStatus.ASSERTED)
                    if alt.status is AssertionStatus.EMBEDDED else alt
                    for alt in child.alternatives
                )
                promoted = replace(
                    child,
                    status=AssertionStatus.ASSERTED,
                    alternatives=alternatives,
                )
                by_id[child.local_id] = promoted
                diagnostics.append(
                    f"factivity: {child.local_id} promoted to ASSERTED content of {parent.local_id}"
                )

        return [by_id.get(item.local_id, item) for item in assertions], tuple(diagnostics)

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

        clause_by_id = {clause.clause_id: clause for clause in graph.clauses}

        def primary_locals(clause_id: str) -> list[str]:
            """Return assertions headed by the clause's source predicate heads.

            Clause-local helper assertions (for example a structural locative
            predicate materialized from ``в``) are useful canonical facts, but
            they are not the situation denoted by an inter-clause connective.
            FOLLOW/CAUSE therefore anchor to the source predicate head(s) first
            and fall back to all clause-local assertions only for legacy/implicit
            clauses without an explicit head.
            """
            values = clause_to_locals.get(clause_id, [])
            clause = clause_by_id.get(clause_id)
            if clause is None or not clause.predicate_heads:
                return values
            heads = {head.token_index for head in clause.predicate_heads}
            # ``assertion_spans`` describe the source region consumed while parsing
            # an assertion, not necessarily the token that *heads* that assertion.
            # A structural helper materialized inside the same region can therefore
            # share the host span even though its own predicate is a preposition.
            # Anchor connective relations to the assertion's predicate evidence
            # itself and compare that evidence with the clause's explicit source
            # predicate heads.
            head_tokens = {
                token.index: token for token in graph.tokens if token.index in heads
            }
            assertion_by_id = {item.local_id: item for item in assertions}
            direct: list[str] = []
            for local_id in values:
                candidate = assertion_by_id.get(local_id)
                evidence = candidate.predicate.evidence if candidate is not None else None
                if evidence is None or evidence.start is None or evidence.end is None:
                    continue
                if any(
                    token.start == evidence.start and token.end == evidence.end
                    for token in head_tokens.values()
                ):
                    direct.append(local_id)
            return direct or values

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
            if clause.parent_clause_id is None:
                continue
            if clause.marker in {"потому_что", "так_как", "поскольку"}:
                child_ids = primary_locals(clause.clause_id)
                parent_ids = primary_locals(clause.parent_clause_id)
                if child_ids and parent_ids:
                    source_id = child_ids[0]
                    target_id = parent_ids[-1]
                    key = ("CAUSE", source_id, target_id)
                    if key not in seen and source_id != target_id:
                        seen.add(key)
                        result.append(
                            SituationRelationCandidate(
                                relation_id="CAUSE",
                                source_ref=source_id,
                                target_ref=target_id,
                                evidence=(
                                    clause.connector_span.evidence
                                    if clause.connector_span is not None else None
                                ),
                            )
                        )
                continue
            direction = directions.get(clause.marker or "")
            if direction is None:
                continue
            child_ids = primary_locals(clause.clause_id)
            parent_ids = primary_locals(clause.parent_clause_id)
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
        # operators, not persistent TIME entities.  Their lexical discourse
        # semantics is enough to establish FOLLOW; do not require the model to
        # first invent a temporary TIME actant merely so it can be stripped again.
        referenced_assertion_ids = {
            ref
            for item in assertions
            for actant in item.actants
            for ref in (
                (actant.candidate_ref,)
                if actant.candidate_ref is not None
                else (
                    actant.proposition.leaf_refs()
                    if actant.proposition is not None
                    else ()
                )
            )
        }
        independent_ids = {
            item.local_id for item in assertions
            if item.local_id not in referenced_assertion_ids
        }
        ordered_assertions = sorted(
            (
                item for item in assertions
                if item.local_id in independent_ids
                and assertion_spans.get(item.local_id) is not None
            ),
            key=lambda item: assertion_spans[item.local_id].start_index,
        )

        def local_clause_id(local_id: str) -> str | None:
            span = assertion_spans.get(local_id)
            if span is None:
                return None
            clause = graph.clause_for_token(span.start_index)
            return None if clause is None else clause.clause_id

        def ellipsis_family_root(clause_id: str) -> str:
            current = clause_id
            visited: set[str] = set()
            while current not in visited:
                visited.add(current)
                clause = clause_by_id.get(current)
                source = None if clause is None else clause.ellipsis_source_clause_id
                if source is None or source not in clause_by_id:
                    break
                current = source
            return current

        independent_by_family: dict[str, set[str]] = {}
        for local_id in independent_ids:
            clause_id = local_clause_id(local_id)
            if clause_id is None:
                continue
            root = ellipsis_family_root(clause_id)
            independent_by_family.setdefault(root, set()).add(local_id)

        for previous, current in zip(ordered_assertions, ordered_assertions[1:]):
            current_span = assertion_spans.get(current.local_id)
            direct_marker: str | None = None
            direct_evidence: EvidenceSpan | None = None
            if current_span is not None:
                clause = graph.clause_for_token(current_span.start_index)
                if clause is not None:
                    for index in range(clause.span.start_index, clause.span.end_index + 1):
                        token = graph.token(index)
                        if not re.search(r"\w", token.text):
                            continue
                        low = token.text.casefold()
                        if low in _DISCOURSE_FOLLOW_MARKERS:
                            direct_marker = low
                            direct_evidence = EvidenceSpan(
                                token.text, token.start, token.end
                            )
                        break
            marker = next(
                (
                    actant for actant in current.actants
                    if actant.role == ActantRole.TIME
                    and (actant.lookup_text or "").casefold() in _DISCOURSE_FOLLOW_MARKERS
                ),
                None,
            )
            if direct_marker is None and marker is None:
                continue

            previous_clause_id = local_clause_id(previous.local_id)
            current_clause_id = local_clause_id(current.local_id)
            if previous_clause_id is None or current_clause_id is None:
                continue
            previous_family = ellipsis_family_root(previous_clause_id)
            current_family = ellipsis_family_root(current_clause_id)
            # A sequencing marker may scope two parallel discourse blocks.  The
            # pairwise L schema cannot encode that group relation, so it must not
            # choose one event on either side arbitrarily.  Embedded descendants
            # do not make a block ambiguous; only independent proposition roots do.
            if (
                previous_family == current_family
                or independent_by_family.get(previous_family) != {previous.local_id}
                or independent_by_family.get(current_family) != {current.local_id}
            ):
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
                    evidence=(direct_evidence if direct_evidence is not None else marker.evidence),
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
                    # These source expressions are discourse operators, not
                    # persistent temporal entities when they precede a later
                    # event relative to source-visible prior content.  Remove the
                    # staging actant even when a group-scoped ordering cannot be
                    # represented by one unambiguous pairwise FOLLOW edge.  A
                    # standalone or post-predicate temporal use remains intact.
                    actant_evidence = actant.evidence
                    predicate_evidence = assertion.predicate.evidence
                    leading = (
                        actant_evidence is not None
                        and actant_evidence.end is not None
                        and predicate_evidence is not None
                        and predicate_evidence.start is not None
                        and actant_evidence.end <= predicate_evidence.start
                    )
                    has_prior_source_assertion = (
                        actant_evidence is not None
                        and actant_evidence.start is not None
                        and any(
                            other.local_id != assertion.local_id
                            and other.evidence is not None
                            and other.evidence.end is not None
                            and other.evidence.end <= actant_evidence.start
                            for other in assertions
                        )
                    )
                    relation_targeted = any(
                        relation_id == "FOLLOW" and target_id == assertion.local_id
                        for relation_id, _source_id, target_id in relation_pairs
                    )
                    redundant = relation_targeted or (
                        leading and has_prior_source_assertion
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
        if actant.candidate_ref is not None or actant.composition is not None or actant.proposition is not None:
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

    def _materialize_nominal_modifier_assertions(
        self,
        assertions: list[AssertionCandidate],
        assertion_spans: dict[str, _Span | None],
    ) -> tuple[list[AssertionCandidate], dict[str, _Span | None]]:
        """Compile explicitly selected nominal-attached source modifiers.

        Attachment is resolved before semantic role assignment and is not tied to
        OBJECT or to any particular preposition.  A nominal reading becomes an
        ordinary lexical predicate realization whose SUBJECT is the entity being
        modified; the modifier filler keeps the semantic role already resolved for
        that relation.  Exact source evidence lets the turn-local identity binder
        reuse the same entity as the owner mention in the matrix frame.
        """
        if not self._pending_nominal_modifiers:
            return assertions, assertion_spans

        out = list(assertions)
        spans = dict(assertion_spans)
        for pending in self._pending_nominal_modifiers:
            local_id = f"A{len(out) + 1}"
            owner = pending.owner_span
            modifier = pending.modifier_span
            evidence = None
            start = owner.evidence.start
            end = modifier.evidence.end
            if start is not None and end is not None and self._candidate_graph is not None:
                evidence = EvidenceSpan(self._candidate_graph.text[start:end], start, end)

            owner_mention, owner_hint = self._semantic_actant_text(owner)
            subject = ActantCandidate(
                role=ActantRole.SUBJECT,
                mention=owner_mention,
                normalized_hint=owner_hint,
                evidence=owner.evidence,
            )
            filler = self._make_actant(pending.modifier_role, modifier)
            out.append(
                AssertionCandidate(
                    local_id=local_id,
                    predicate=pending.predicate,
                    actants=(subject, filler),
                    evidence=evidence,
                )
            )

            # The nominal relation belongs to the same proposition scope as the
            # matrix mention that supplied its owner.  Reuse that frame's source
            # predicate span when possible so conditional/embedded compilation
            # cannot accidentally promote the modifier relation to top-level truth.
            owner_span = None
            if owner.evidence.start is not None:
                owner_span = next(
                    (
                        span
                        for item in assertions
                        if (span := assertion_spans.get(item.local_id)) is not None
                        and any(
                            actant.evidence is not None
                            and actant.evidence.start is not None
                            and actant.evidence.end is not None
                            and actant.evidence.start <= owner.evidence.start
                            and actant.evidence.end >= owner.evidence.end
                            for actant in item.actants
                        )
                    ),
                    None,
                )
            spans[local_id] = owner_span

        self._pending_nominal_modifiers = []
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

        def proposition_expr(refs: list[str] | tuple[str, ...]) -> PropositionExprCandidate:
            ordered_refs = tuple(dict.fromkeys(refs))
            if not ordered_refs:
                raise AdaptiveParseError("empty proposition expression", tuple(self._traces))

            # Recovered ellipsis may clone a complete matrix/content subgraph into
            # a clause with no overt predicate heads.  Its local candidate_ref /
            # proposition edges are stronger root evidence than source-token
            # ownership, so filter referenced children before consulting the graph.
            ordered_set = set(ordered_refs)
            structurally_dependent = {
                ref
                for parent_ref in ordered_refs
                for actant in by_id[parent_ref].actants
                for ref in (
                    ((actant.candidate_ref,) if actant.candidate_ref is not None else ())
                    + (
                        actant.proposition.leaf_refs()
                        if actant.proposition is not None
                        else ()
                    )
                )
                if ref in ordered_set
            }
            structural_roots = tuple(
                ref for ref in ordered_refs if ref not in structurally_dependent
            )
            if structural_roots:
                ordered_refs = structural_roots

            # A clause proposition is composed from its frame roots, not from every
            # assertion whose predicate happens to occupy that clause.  A nonfinite
            # child is already semantically contained by its matrix frame once the
            # dependency is attached (REQUEST(content=ENTER), WANT(content=BUY), ...).
            # Including it again here would create false AND(matrix, child) content
            # and breaks inter-clause relations such as CAUSE(matrix_clause, ...).
            ref_head_for_roots: dict[str, int] = {}
            for ref in ordered_refs:
                span = assertion_spans.get(ref)
                if span is None:
                    continue
                heads = [
                    h.token_index for h in graph.predicates
                    if span.start_index <= h.token_index <= span.end_index
                ]
                if len(heads) == 1:
                    ref_head_for_roots[ref] = heads[0]
            represented_heads = set(ref_head_for_roots.values())
            dependent_heads = {
                dep.child_token_index
                for dep in graph.frame_graph.dependencies
                if dep.kind is FrameDependencyKind.NONFINITE
                and dep.parent_token_index in represented_heads
                and dep.child_token_index in represented_heads
            }
            root_refs = tuple(
                ref for ref in ordered_refs
                if ref_head_for_roots.get(ref) not in dependent_heads
            )
            if root_refs:
                ordered_refs = root_refs
            if len(ordered_refs) == 1:
                return PropositionExprCandidate.ref_expr(ordered_refs[0])

            # Preserve explicit predicate coordination.  Source order is used only
            # to find the written coordinator; the resulting AND/OR is semantic
            # proposition composition, not a parent/child guess.
            ref_head: dict[str, int] = {}
            for ref in ordered_refs:
                span = assertion_spans.get(ref)
                if span is None:
                    continue
                heads = [h.token_index for h in graph.predicates if span.start_index <= h.token_index <= span.end_index]
                if len(heads) == 1:
                    ref_head[ref] = heads[0]
            head_ref = {head: ref for ref, head in ref_head.items()}
            for group in graph.frame_graph.coordinations:
                members = tuple(head_ref[h] for h in group.member_token_indices if h in head_ref)
                if len(members) >= 2 and set(members) == set(ordered_refs):
                    op = PropositionOperator.OR if group.operator is CoordinationKind.OR else PropositionOperator.AND
                    return PropositionExprCandidate(op, members=tuple(PropositionExprCandidate.ref_expr(r) for r in members))

            # Cross-clause coordination may not live in a single predicate group.
            # Inspect only explicit coordinators between consecutive proposition
            # spans; absent OR evidence defaults to conjunction of simultaneously
            # present situation members.
            sorted_refs = sorted(ordered_refs, key=lambda r: assertion_spans[r].start_index if assertion_spans.get(r) else 10**9)
            saw_or = False
            saw_and = False
            for left, right in zip(sorted_refs, sorted_refs[1:]):
                ls, rs = assertion_spans.get(left), assertion_spans.get(right)
                if ls is None or rs is None:
                    continue
                between = [t.text.casefold() for t in graph.tokens if ls.end_index < t.index < rs.start_index]
                saw_or = saw_or or any(x in {"или", "либо"} for x in between)
                saw_and = saw_and or any(x in {"и", "да"} for x in between)
            op = PropositionOperator.OR if saw_or and not saw_and else PropositionOperator.AND
            return PropositionExprCandidate(op, members=tuple(PropositionExprCandidate.ref_expr(r) for r in sorted_refs))

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
        # A source-linked gerund is grammatically controlled by its matrix
        # subject. Perform this after local pronoun resolution so an already
        # established entity_ref is copied when available, then let exact-span
        # binding below stabilize any still-deictic source copy.
        self._inherit_nonfinite_subjects(by_id)
        # A fronted gerund can itself receive the matrix subject only in the pass
        # above and then license a following finite conjunct (``снял, подняв..., и
        # поставил``). Re-run the same source-structural inheritance to a fixed
        # point; already filled SUBJECT slots make this idempotent.
        self._inherit_omitted_clause_subjects(by_id, clause_to_locals)
        # Predicate coordination owns shared arguments as a group-level property.
        # SUBJECT, postposed OBJECT and other roles therefore use one mechanism
        # instead of accumulating role-specific ellipsis functions.
        self._share_coordinated_predicate_actants(
            by_id, clause_to_locals, assertion_spans
        )
        # Structural inheritance/coordination may have introduced the first usable
        # copy of a source pronoun only after the initial coreference pass. Resolve
        # once more before exact-span coalescing; already resolved pronouns are
        # skipped, so this is idempotent.
        self._resolve_pronoun_coreferences(by_id)
        # Repeated copies of the same source span must retain the identity that was
        # established above. Exact evidence-span identity is deterministic.
        self._bind_reused_source_mentions(by_id)
        # Possessive pronouns that live *inside* an NP are not ordinary actants,
        # so bind their unique turn-local antecedent after ordinary coreference has
        # stabilized source entity ids.
        self._resolve_nominal_relation_coreferences(by_id)

        def attach_expr(parent_id: str, expr: PropositionExprCandidate, role: ActantRole) -> bool:
            parent = by_id[parent_id]
            leaves = set(expr.leaf_refs())
            if parent_id in leaves:
                return False
            if any(
                (a.candidate_ref is not None and a.candidate_ref in leaves)
                or (a.proposition is not None and leaves & set(a.proposition.leaf_refs()))
                for a in parent.actants
            ):
                return False
            if any(a.role == role for a in parent.actants):
                return False
            actant = (
                ActantCandidate(role=role, candidate_ref=next(iter(leaves)))
                if expr.operator is PropositionOperator.REF
                else ActantCandidate(role=role, proposition=expr)
            )
            by_id[parent_id] = replace(parent, actants=parent.actants + (actant,))
            return True

        def attach(parent_id: str, child_id: str, role: ActantRole) -> bool:
            return attach_expr(parent_id, PropositionExprCandidate.ref_expr(child_id), role)

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
            decision, _margin = self._exact_choice_probe(
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

        # Cross-clause markers establish structural subordination only.  Semantic
        # relation is chosen after both frames exist; no ``чтобы→PURPOSE`` /
        # ``где→LOCATION`` shortcut survives here.  ``если`` is handled by the
        # proposition-level conditional compiler below.
        for clause in graph.clauses:
            if clause.parent_clause_id is None or clause.relative or clause.marker == "если":
                continue
            # Compound ordering connectives already have a complete canonical
            # inter-situation meaning represented later as FOLLOW.  They are not
            # proposition-valued actants of the matrix predicate, so do not ask a
            # general frame-role probe that can incorrectly turn them into
            # PURPOSE/OBJECT and thereby mark the child EMBEDDED.
            if clause.marker in {
                "после_того_как", "перед_тем_как", "до_того_как",
                "потому_что", "так_как", "поскольку",
            }:
                continue
            children = clause_to_locals.get(clause.clause_id, [])
            parents = clause_to_locals.get(clause.parent_clause_id, [])
            if not children or not parents:
                continue
            parent_id = parents[-1]
            child_expr = proposition_expr(children)
            child_leaves = set(child_expr.leaf_refs())
            if child_leaves and all(
                any(
                    actant.candidate_ref == leaf
                    or (
                        actant.proposition is not None
                        and leaf in actant.proposition.leaf_refs()
                    )
                    for actant in by_id[parent_id].actants
                )
                for leaf in child_leaves
            ):
                # The early ellipsis-only graph-settling pass has already attached
                # this complete proposition.  Attachment is idempotent and must
                # not request a second semantic decision.
                continue
            representative = by_id[children[0]]
            allowed = (
                ActantRole.OBJECT, ActantRole.PURPOSE, ActantRole.CAUSE, ActantRole.TIME,
                ActantRole.LOCATION, ActantRole.SOURCE, ActantRole.HOW_TO,
            )
            role = self._choose_frame_relation(by_id[parent_id], representative, allowed, allow_none=True)
            if role is None:
                continue
            if role == ActantRole.OBJECT and any(a.role == ActantRole.OBJECT for a in by_id[parent_id].actants):
                if len(children) != 1 or not free_nested_object_slot(parent_id, children[0]):
                    raise AdaptiveParseError(
                        "unresolved OBJECT-content participant role conflict for embedded proposition",
                        tuple(self._traces),
                    )
            attach_expr(parent_id, child_expr, role)

        def attach_oriented_frame(parent_id: str, child_id: str) -> None:
            """Resolve only the semantic relation after structural orientation."""
            parent = by_id[parent_id]
            child = by_id[child_id]
            if any(a.candidate_ref == child_id for a in parent.actants):
                return
            if child.predicate.sense_hint == "STRUCTURAL_NOMINAL_ATTACHMENT":
                return
            if (
                parent.predicate.lookup_form == child.predicate.lookup_form
                and parent.predicate.evidence is not None
                and child.predicate.evidence is not None
                and parent.predicate.evidence.start == child.predicate.evidence.start
                and parent.predicate.evidence.end == child.predicate.evidence.end
            ):
                return

            available_list: list[ActantRole] = []
            for role in (
                ActantRole.OBJECT, ActantRole.PURPOSE, ActantRole.CAUSE, ActantRole.HOW_TO
            ):
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
                return
            role = self._choose_frame_relation(parent, child, available, allow_none=True)
            if (
                role == ActantRole.OBJECT
                and any(a.role == ActantRole.OBJECT for a in by_id[parent_id].actants)
            ):
                if not free_nested_object_slot(parent_id, child_id):
                    raise AdaptiveParseError(
                        "unresolved OBJECT-content participant role conflict between "
                        f"{by_id[parent_id].predicate.lookup_form!r} and "
                        f"{child.predicate.lookup_form!r}",
                        tuple(self._traces),
                    )
            if role is not None:
                attach(parent_id, child_id, role)

        # ClauseFrameGraph, not source order, owns predicate hierarchy.  In
        # particular a fronted gerund has an edge FINITE_MATRIX -> GERUND even
        # though its token/local-id occurs first.  Cross-clause subordinate edges
        # were handled above because their marker relation has separate semantics;
        # quoted edges deliberately remain structural only until quotation scope is
        # materialized by its dedicated layer.
        head_to_locals: dict[int, list[str]] = {}
        for local_id, span in assertion_spans.items():
            if span is None:
                continue
            for head in graph.predicates:
                if span.start_index <= head.token_index <= span.end_index:
                    head_to_locals.setdefault(head.token_index, []).append(local_id)

        for dependency in graph.frame_graph.dependencies:
            if dependency.kind is not FrameDependencyKind.NONFINITE:
                continue
            parents = head_to_locals.get(dependency.parent_token_index, [])
            children = head_to_locals.get(dependency.child_token_index, [])
            # Multiple local candidates over exactly one source predicate are
            # alternatives/siblings. Do not fabricate hierarchy between variants.
            if len(parents) != 1 or len(children) != 1:
                continue
            attach_oriented_frame(parents[0], children[0])

        self._resolve_control_subjects(by_id, assertion_spans)
        # Control resolution can be the first point where an infinitival member of
        # an explicit predicate coordination acquires its source actor
        # (``Зурита успел подняться и уселся``). Re-run the generic coordination
        # sharing after control; filled role slots make the operation idempotent.
        self._share_coordinated_predicate_actants(
            by_id, clause_to_locals, assertion_spans
        )
        self._bind_reused_source_mentions(by_id)
        self._classify_nonfinite_assertion_status(by_id, assertion_spans)
        return [by_id[item.local_id] for item in assertions]

    def _classify_nonfinite_assertion_status(
        self,
        by_id: dict[str, AssertionCandidate],
        assertion_spans: dict[str, _Span | None],
    ) -> None:
        """Distinguish a bare asserted infinitive from scoped proposition content.

        A structural NONFINITE edge does not decide truth status.  In particular,
        an asserted phase/aspect/change operation over a proposition does not make
        the bare proposition an independently asserted ordinary-world fact.  The
        child remains addressable as the matrix operation's scoped operand.

        Python first narrows the question to one already-oriented matrix/infinitive
        pair.  A tiny fixed-choice semantic probe sees only source text and the two
        source predicates; it never receives AH UIDs or canonical candidates.
        UNCLEAR and protocol failure conservatively keep the ordinary EMBEDDED
        treatment.
        """
        graph = self._candidate_graph
        if graph is None:
            return

        head_to_locals: dict[int, list[str]] = {}
        for local_id, span in assertion_spans.items():
            if span is None:
                continue
            for head in graph.predicates:
                if span.start_index <= head.token_index <= span.end_index:
                    head_to_locals.setdefault(head.token_index, []).append(local_id)

        def child_is_attached(parent: AssertionCandidate, child_id: str) -> bool:
            for actant in parent.actants:
                if actant.candidate_ref == child_id:
                    return True
                if (
                    actant.proposition is not None
                    and child_id in actant.proposition.leaf_refs()
                ):
                    return True
            return False

        for dependency in graph.frame_graph.dependencies:
            if dependency.kind is not FrameDependencyKind.NONFINITE:
                continue
            child_token = next(
                (item for item in graph.tokens if item.index == dependency.child_token_index),
                None,
            )
            if child_token is None or not any(
                info.pos == "INFN" for info in self._material_morph_analyses(child_token)
            ):
                # Gerunds describe a source-visible event/state directly and are
                # handled by gerund control/EventNormalizer, not this ambiguity.
                continue
            parents = head_to_locals.get(dependency.parent_token_index, [])
            children = head_to_locals.get(dependency.child_token_index, [])
            if len(parents) != 1 or len(children) != 1:
                continue
            parent_id, child_id = parents[0], children[0]
            parent, child = by_id.get(parent_id), by_id.get(child_id)
            if parent is None or child is None or not child_is_attached(parent, child_id):
                continue
            pair = (parent_id, child_id)
            if pair in self._classified_nonfinite_pairs:
                continue

            prompt = (
                f"TEXT:\n{graph.text}\n"
                f"MATRIX PREDICATE:\n{parent.predicate.surface}\n"
                f"INFINITIVE EVENT:\n{child.predicate.surface}\n"
                "QUESTION:\nIs the bare INFINITIVE EVENT an independent ordinary-world "
                "fact, an operand of an asserted phase/aspect/change operation, or only "
                "non-asserted content?\nCHOICES:\nASSERTED_EVENT\nSCOPED_EVENT\n"
                "NONASSERTED_CONTENT\nUNCLEAR"
            )
            decision, _margin = self._deep_semantic_choice_probe(
                "nonfinite_assertion_status",
                prompt,
                (
                    "ASSERTED_EVENT",
                    "SCOPED_EVENT",
                    "NONASSERTED_CONTENT",
                    "UNCLEAR",
                ),
                optional=True,
            )
            self._classified_nonfinite_pairs.add(pair)
            if decision == "ASSERTED_EVENT":
                self._asserted_nonfinite_refs.add(child_id)
            elif decision == "SCOPED_EVENT":
                self._scoped_nonfinite_pairs.add(pair)

    def _normalize_transition_occurrences(
        self,
        assertions: list[AssertionCandidate],
        assertion_spans: dict[str, _Span | None],
    ) -> tuple[list[AssertionCandidate], dict[str, _Span | None]]:
        """Map source phase/aspect meaning to occurrence-level transition g.

        Structural frame orientation and ordinary actant extraction are already
        complete.  The model sees only a bounded source-local choice and cannot
        invent a predicate, role or AH identifier.  The matrix lexical shell is
        removed only after the earlier probe has classified its infinitive as a
        SCOPED_EVENT and this probe identifies one exact TransitionOperator.
        """
        graph = self._candidate_graph
        if graph is None or not assertions:
            return assertions, assertion_spans
        by_id = {item.local_id: item for item in assertions}
        spans = dict(assertion_spans)

        def leaves(item: AssertionCandidate) -> set[str]:
            refs: set[str] = set()
            for actant in item.actants:
                if actant.candidate_ref is not None:
                    refs.add(actant.candidate_ref)
                if actant.proposition is not None:
                    refs.update(actant.proposition.leaf_refs())
            return refs

        def choose(
            occurrence: AssertionCandidate,
            *,
            matrix: AssertionCandidate | None = None,
            cue_text: str | None = None,
        ) -> TransitionOperator | None:
            context = (
                f"TEXT:\n{graph.text}\n"
                + (
                    f"MATRIX PREDICATE:\n{matrix.predicate.surface}\n"
                    if matrix is not None else ""
                )
                + (
                    f"OPERATOR CUE:\n{cue_text}\n"
                    if cue_text is not None else ""
                )
                + f"OPERAND PREDICATE:\n{occurrence.predicate.surface}\n"
                + (
                    "QUESTION:\nWhich transition over the OPERAND is explicitly "
                    "contributed by OPERATOR CUE in this occurrence? Return NONE "
                    "when that cue is only an ordinary time, manner, degree, or "
                    "discourse modifier.\n"
                    if cue_text is not None else
                    "QUESTION:\nWhich transition over the OPERAND is explicitly "
                    "asserted in this occurrence?\n"
                )
                + "CHOICES:\nSTART\nSTOP\nCONTINUE\nAGAIN\nNO_LONGER\nNONE\nUNCLEAR"
            )
            label, _margin = self._deep_semantic_choice_probe(
                "transition_operator",
                context,
                (
                    "START", "STOP", "CONTINUE", "AGAIN", "NO_LONGER",
                    "NONE", "UNCLEAR",
                ),
                optional=True,
            )
            if label in {None, "NONE", "UNCLEAR"}:
                return None
            return TransitionOperator(label)

        def without_consumed_cues(
            actants: tuple[ActantCandidate, ...],
            consumed_indices: set[int],
        ) -> tuple[ActantCandidate, ...]:
            if not consumed_indices:
                return actants

            def consumed(actant: ActantCandidate) -> bool:
                evidence = actant.evidence
                if (
                    evidence is None
                    or evidence.start is None
                    or evidence.end is None
                ):
                    return False
                covered = {
                    token.index
                    for token in graph.tokens
                    if evidence.start <= token.start
                    and token.end <= evidence.end
                    and re.search(r"\w", token.text)
                }
                return bool(covered) and covered <= consumed_indices

            return tuple(item for item in actants if not consumed(item))

        # A scoped phase shell nested under another non-asserted content frame is
        # not ordinary-world truth.  Do not promote it merely because its own
        # matrix/infinitive edge is locally phase-like.
        externally_referenced = {
            ref
            for owner in by_id.values()
            for ref in leaves(owner)
        }
        removed: set[str] = set()
        for parent_id, child_id in tuple(self._scoped_nonfinite_pairs):
            parent = by_id.get(parent_id)
            child = by_id.get(child_id)
            if parent is None or child is None:
                continue
            if parent_id in externally_referenced and parent_id not in self._asserted_nonfinite_refs:
                continue
            operator = choose(child, matrix=parent)
            self._transition_classified_refs.add(child_id)
            if operator is None:
                continue
            if parent.negated and operator is not TransitionOperator.NO_LONGER:
                continue

            parent_span = spans.get(parent_id)
            child_span = spans.get(child_id)
            clause = (
                None
                if parent_span is None
                else graph.clause_for_token(parent_span.start_index)
            )
            matrix_cues = (
                ()
                if clause is None
                else tuple(
                    token
                    for token in graph.tokens[
                        clause.span.start_index - 1 : clause.span.end_index
                    ]
                    if (
                        parent_span is None
                        or token.index < parent_span.start_index
                        or token.index > parent_span.end_index
                    )
                    and (
                        child_span is None
                        or token.index < child_span.start_index
                        or token.index > child_span.end_index
                    )
                    and any(
                        info.pos in {"ADVB", "PRCL"}
                        for info in token.analyses
                    )
                    and token.index in self._transition_cue_token_indices
                )
            )
            consumed_matrix_cues = {
                token.index
                for token in matrix_cues
                if choose(child, matrix=parent, cue_text=token.text) is operator
            }

            occupied = {item.role for item in child.actants}
            inherited = tuple(
                item
                for item in without_consumed_cues(
                    parent.actants, consumed_matrix_cues
                )
                if item.role not in occupied
                and item.candidate_ref is None
                and item.proposition is None
            )
            by_id[child_id] = replace(
                child,
                actants=child.actants + inherited,
                evidence=parent.evidence or child.evidence,
                negated=False,
                status=parent.status,
                temporal_mode=TemporalMode.TRANSITION,
                transition_operator=operator,
            )
            removed.add(parent_id)
            spans.pop(parent_id, None)
            self._deterministic_trace(
                "transition_normalization",
                (
                    f"MATRIX:{parent.predicate.surface}\n"
                    f"OPERAND:{child.predicate.surface}\nLOCAL:{child_id}"
                ),
                operator.value,
            )

        for local_id in removed:
            by_id.pop(local_id, None)

        # Non-matrix markers are considered only when morphology exposes overt
        # ADVB/PRCL candidates in the same clause.  Each candidate is classified
        # separately by the bounded source-only probe, so an ordinary temporal or
        # manner adverb can return NONE while a neighbouring aspectual cue supplies
        # one operator.  This is a general candidate lattice, not a marker list.
        embedded_refs = {
            ref
            for owner in by_id.values()
            for ref in leaves(owner)
        }
        for local_id, occurrence in tuple(by_id.items()):
            if local_id in self._transition_classified_refs or local_id in embedded_refs:
                continue
            span = spans.get(local_id)
            if span is None:
                continue
            clause = graph.clause_for_token(span.start_index)
            if clause is None:
                continue

            cue_tokens = tuple(
                item
                for item in graph.tokens[clause.span.start_index - 1 : clause.span.end_index]
                if (item.index < span.start_index or item.index > span.end_index)
                and any(info.pos in {"ADVB", "PRCL"} for info in item.analyses)
                and item.index in self._transition_cue_token_indices
            )
            if not cue_tokens:
                continue

            classified = tuple(
                (token, choose(occurrence, cue_text=token.text))
                for token in cue_tokens
            )
            operators = {
                operator for _token, operator in classified
                if operator is not None
            }
            if not operators:
                raise AdaptiveParseError(
                    "transition operator unresolved for an explicit source cue",
                    tuple(self._traces),
                )
            if len(operators) != 1:
                self._deterministic_trace(
                    "transition_normalization",
                    f"OPERAND:{occurrence.predicate.surface}\nLOCAL:{local_id}",
                    "UNRESOLVED:conflicting cue operators",
                )
                raise AdaptiveParseError(
                    "conflicting transition operators for one occurrence",
                    tuple(self._traces),
                )
            operator = next(iter(operators))
            consumed_indices = {
                token.index
                for token, token_operator in classified
                if token_operator is operator
            }

            self._transition_classified_refs.add(local_id)
            if occurrence.negated and operator is not TransitionOperator.NO_LONGER:
                continue
            by_id[local_id] = replace(
                occurrence,
                actants=without_consumed_cues(
                    occurrence.actants, consumed_indices
                ),
                negated=False,
                temporal_mode=TemporalMode.TRANSITION,
                transition_operator=operator,
            )
            self._deterministic_trace(
                "transition_normalization",
                f"OPERAND:{occurrence.predicate.surface}\nLOCAL:{local_id}",
                operator.value,
            )

        return (
            [by_id[item.local_id] for item in assertions if item.local_id in by_id],
            spans,
        )

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
        parent. Controller identity is a separate local decision. Parent SUBJECT is
        eligible regardless of surface order (required for fronted non-finites such
        as ``Улыбаясь, Иван вошёл``); other participant roles remain eligible only
        when they occur before a postposed child. One candidate is deterministic,
        several are presented to the weak model as one finite choice. No lexical
        verb table or sentence-specific rule is used.
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
                        or (
                            actant.role is not ActantRole.SUBJECT
                            and actant.evidence.start >= child_span.evidence.start
                        )
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
                    choices = "\n".join((*labels, "UNCLEAR"))
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
                    decision, _margin = self._exact_choice_probe(
                        "control_subject", prompt, (*tuple(labels), "UNCLEAR")
                    )
                    chosen = (
                        None if decision == "UNCLEAR" else controllers[labels.index(decision)]
                    )
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
                            grammatical_number=controller.grammatical_number,
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
                    grammatical_number=chosen.grammatical_number,
                )
                by_id[child_id] = replace(
                    current_child, actants=current_child.actants + (copied,)
                )

    def _span_from_evidence(
        self,
        text: str,
        tokens: tuple[_SourceToken, ...],
        evidence: EvidenceSpan,
    ) -> _Span | None:
        if evidence.start is None or evidence.end is None:
            return None
        covered = [
            token.index
            for token in tokens
            if token.start >= evidence.start and token.end <= evidence.end
        ]
        if not covered:
            return None
        return self._resolve_span(text, tokens, min(covered), max(covered))

    def _raw_nominal_spans(
        self,
        text: str,
        tokens: tuple[_SourceToken, ...],
        start: int,
        end: int,
    ) -> tuple[_Span, ...]:
        """Conservatively chunk source NPs for structural antecedent fallback."""
        blocked: set[int] = set()
        result: list[_Span] = []
        index = start
        while index <= end:
            token = tokens[index - 1]
            if not self._structural_nominal_infos(token):
                index += 1
                continue
            left = index
            cursor = index - 1
            while cursor >= start and self._has_morph(
                tokens[cursor - 1], poses={"ADJF", "PRTF", "NUMR"}
            ):
                left = cursor
                cursor -= 1
            phrase_end = self._nominal_phrase_end(tokens, left, end, blocked) or index
            result.append(self._resolve_span(text, tokens, left, phrase_end))
            index = max(index + 1, phrase_end + 1)

        graph = self._candidate_graph
        if graph is not None:
            for coordination in graph.coordinations:
                if (
                    start <= coordination.span.start_index
                    and coordination.span.end_index <= end
                    and all(
                        any(
                            self._structural_nominal_infos(tokens[i - 1])
                            for i in range(member.start_index, member.end_index + 1)
                        )
                        for member in coordination.member_spans
                    )
                ):
                    result.append(
                        self._resolve_span(
                            text,
                            tokens,
                            coordination.span.start_index,
                            coordination.span.end_index,
                        )
                    )

        # Keep both a coordination and its members until agreement filtering.
        # ``Иван и Мария, которые...`` selects the plural group, whereas
        # ``Иван и Мария, которая...`` may legitimately select the feminine member.
        unique: dict[tuple[int, int], _Span] = {
            (item.start_index, item.end_index): item for item in result
        }
        return tuple(
            sorted(unique.values(), key=lambda item: (item.start_index, item.end_index))
        )

    def _relative_agreement_compatible(
        self,
        relative_index: int,
        antecedent: _RelativeAntecedentCandidate,
        tokens: tuple[_SourceToken, ...],
    ) -> bool:
        relative_token = tokens[relative_index - 1]
        relative_infos = [
            info
            for info in self._material_morph_analyses(relative_token)
            if info.pos in {"NPRO", "ADJF", "PRTF"}
        ]
        # Relative adverbs (где/куда/когда/откуда) do not agree morphologically.
        if not relative_infos:
            return True
        if (
            (antecedent.actant is not None and antecedent.actant.composition is not None)
            or self._composition_for_span(antecedent.span) is not None
        ):
            relative_numbers = {info.number for info in relative_infos if info.number}
            return not relative_numbers or "plur" in relative_numbers

        head_token = next(
            (
                tokens[index - 1]
                for index in range(antecedent.span.end_index, antecedent.span.start_index - 1, -1)
                if self._structural_nominal_infos(tokens[index - 1])
            ),
            None,
        )
        if head_token is None:
            return True
        antecedent_infos = [
            info
            for info in self._material_morph_analyses(head_token)
            if info.pos in {"NOUN", "NPRO"}
        ]
        if not antecedent_infos:
            return True
        for rel in relative_infos:
            for ant in antecedent_infos:
                if rel.number and ant.number and rel.number != ant.number:
                    continue
                if (
                    rel.number != "plur"
                    and ant.number != "plur"
                    and rel.gender
                    and ant.gender
                    and rel.gender != ant.gender
                ):
                    continue
                return True
        return False

    def _relative_entity_anchor_span(self, span: _Span) -> _Span:
        """Return the source span that denotes the entity carried by an actant.

        PP evidence may be wider than the entity identity stored by the actant.
        For example ``рядом с журналом`` and ``в комнате`` denote the entities
        ``журналом`` and ``комнате`` respectively.  Relative clauses bind that
        nominal anchor, not the whole modifier phrase.  Keep compositions intact:
        their group span is itself the addressable antecedent candidate.
        """
        graph = self._candidate_graph
        if graph is None or self._composition_for_span(span) is not None:
            return span
        start = span.start_index
        end = span.end_index
        if start > end:
            return span
        first = graph.token(start)
        if (
            start + 2 <= end
            and first.text.casefold() in _SPATIAL_RELATION_ADVERBS
            and graph.token(start + 1).text.casefold() == "с"
            and self._has_morph(graph.token(start + 1), poses={"PREP"})
        ):
            start += 2
        elif first.has_pos("PREP"):
            start += 1
        if start > end:
            return span
        return self._resolve_span(graph.text, self._source_tokens(graph.text), start, end)

    def _relative_antecedent_candidates(
        self,
        by_id: dict[str, AssertionCandidate],
        parent_ids: list[str],
        parent_clause,
        relative_clause,
        tokens: tuple[_SourceToken, ...],
    ) -> tuple[_RelativeAntecedentCandidate, ...]:
        graph = self._candidate_graph
        if graph is None or relative_clause.connector_span is None:
            return ()
        connector_start = relative_clause.connector_span.evidence.start
        found: dict[tuple[int | None, int | None], _RelativeAntecedentCandidate] = {}
        for parent_id in parent_ids:
            parent = by_id[parent_id]
            for actant in parent.actants:
                if actant.candidate_ref is not None or actant.evidence is None:
                    continue
                evidence = actant.evidence
                if (
                    connector_start is not None
                    and evidence.end is not None
                    and evidence.end > connector_start
                ):
                    continue
                span = self._span_from_evidence(graph.text, tokens, evidence)
                if span is None:
                    continue
                anchor_span = self._relative_entity_anchor_span(span)
                key = (anchor_span.evidence.start, anchor_span.evidence.end)
                found.setdefault(
                    key,
                    _RelativeAntecedentCandidate(anchor_span, parent_id, actant),
                )

        # Headless antecedent fragments (``Дом, где...``) have no parsed parent
        # frame yet. Fall back to source NPs only when semantic parent actants do
        # not already provide candidates, so internal genitives do not create
        # artificial ambiguity beside a resolved actant.
        if not found:
            for span in self._raw_nominal_spans(
                graph.text,
                tokens,
                parent_clause.span.start_index,
                parent_clause.span.end_index,
            ):
                found[(span.evidence.start, span.evidence.end)] = _RelativeAntecedentCandidate(span)

        relative_index = relative_clause.connector_span.start_index
        compatible = [
            item
            for item in found.values()
            if self._relative_agreement_compatible(relative_index, item, tokens)
        ]
        return tuple(
            sorted(compatible, key=lambda item: (item.span.start_index, item.span.end_index))
        )

    def _choose_relative_antecedent(
        self,
        clause,
        candidates: tuple[_RelativeAntecedentCandidate, ...],
    ) -> tuple[_RelativeAntecedentCandidate, ...]:
        if len(candidates) <= 1:
            return candidates
        graph = self._candidate_graph
        if graph is None or clause.connector_span is None:
            return candidates
        labels = [f"C{i}" for i in range(1, len(candidates) + 1)]
        allowed = tuple([*labels, "UNCLEAR"])
        prompt = (
            f"TEXT:\n{graph.text}\nRELATIVE CONNECTOR:\n{clause.connector_span.text}\n"
            "POSSIBLE ANTECEDENT MENTIONS:\n"
            + "\n".join(
                f"{label}: {candidate.span.text}"
                for label, candidate in zip(labels, candidates)
            )
            + "\nQUESTION:\nWhich source mention is modified by this relative clause? "
            "Choose UNCLEAR if the sentence itself does not determine exactly one.\n"
            "CHOICES:\n" + "\n".join(allowed)
        )

        def parse_label(raw: str) -> str:
            value = raw.strip().upper()
            if value not in allowed:
                raise AdaptiveParseError(
                    "relative_antecedent expected exactly one of: " + ", ".join(allowed)
                )
            return value

        selected = self._probe(
            "antecedent_choice",
            prompt,
            parse_label,
            max_new_tokens=4,
        )
        if selected == "UNCLEAR":
            return candidates
        return (candidates[labels.index(selected)],)

    def _relative_binding_actant(
        self,
        by_id: dict[str, AssertionCandidate],
        role: ActantRole,
        candidate: _RelativeAntecedentCandidate,
    ) -> ActantCandidate:
        mention, hint = self._semantic_actant_text(candidate.span)
        if candidate.actant is not None and candidate.actant.composition is not None:
            return ActantCandidate(
                role=role,
                mention=mention,
                normalized_hint=hint,
                evidence=candidate.span.evidence,
                composition=candidate.actant.composition,
            )
        entity_ref: str | None = None
        if candidate.actant is not None and candidate.assertion_id is not None:
            entity_ref = candidate.actant.entity_ref or self._ensure_actant_entity_ref(
                by_id, candidate.assertion_id, candidate.actant
            )
        if entity_ref is None:
            composition = self._composition_for_span(candidate.span)
            if composition is not None:
                return ActantCandidate(
                    role=role,
                    mention=mention,
                    normalized_hint=hint,
                    evidence=candidate.span.evidence,
                    composition=composition,
                )
            entity_ref = self._next_entity_ref()
        return ActantCandidate(
            role=role,
            mention=mention,
            normalized_hint=hint,
            entity_ref=entity_ref,
            evidence=candidate.span.evidence,
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
            candidates = self._relative_antecedent_candidates(
                by_id, parent_ids, parent_clause, clause, tokens
            )
            if not candidates:
                continue
            selected = self._choose_relative_antecedent(clause, candidates)

            relative_index = clause.connector_span.start_index
            relative_start = relative_index
            if (
                relative_index > 1
                and self._has_structural_morph(tokens[relative_index - 2], poses={"PREP"})
            ):
                relative_start = relative_index - 1
            relative_span = self._resolve_span(
                graph.text, tokens, relative_start, relative_index
            )

            for child_id in child_ids:
                child = by_id[child_id]
                candidate_evidence = {
                    (item.span.evidence.start, item.span.evidence.end)
                    for item in selected
                }
                if child.alternatives or any(
                    actant.evidence is not None
                    and (actant.evidence.start, actant.evidence.end) in candidate_evidence
                    for actant in child.actants
                ):
                    # A prior graph-settling pass already installed this exact
                    # antecedent binding (or preserved its complete alternatives).
                    # Re-running role selection would consume another semantic
                    # vote and could assign the same entity a second role.
                    continue
                occupied = {item.role for item in child.actants}
                role = self._choose_relative_role(
                    graph.text, child, relative_span, selected[0].span, occupied
                )
                if role is None or role in occupied:
                    continue

                if len(selected) == 1:
                    binding = self._relative_binding_actant(by_id, role, selected[0])
                    by_id[child_id] = replace(
                        child, actants=child.actants + (binding,)
                    )
                    self._deterministic_trace(
                        "relative_coreference",
                        f"RELATIVE:\n{relative_span.text}\nANTECEDENT:\n{selected[0].span.text}\n"
                        f"PREDICATE:\n{child.predicate.surface}",
                        f"{role.value}:{selected[0].span.text}",
                    )
                    continue

                # Source ambiguity remains semantic ambiguity, not nearest-NP
                # guessing. Preserve one complete local frame per antecedent; the
                # deterministic Integration ambiguity layer may canonicalize later.
                variants: list[AssertionCandidate] = []
                bases = child.alternatives or (replace(child, alternatives=()),)
                for candidate in selected:
                    binding = self._relative_binding_actant(by_id, role, candidate)
                    for base in bases:
                        variants.append(
                            replace(base, actants=base.actants + (binding,), alternatives=())
                        )
                by_id[child_id] = replace(child, alternatives=tuple(variants))
                self._deterministic_trace(
                    "relative_coreference_alternatives",
                    f"RELATIVE:\n{relative_span.text}\nPREDICATE:\n{child.predicate.surface}",
                    str(len(variants)),
                )

    def _bind_relative_matrix_subjects(
        self,
        by_id: dict[str, AssertionCandidate],
        clause_to_locals: dict[str, list[str]],
    ) -> None:
        """Reuse the already-resolved relative antecedent in a following matrix frame.

        The old implementation re-ran a nearest-nominal heuristic here, which could
        disagree with relative resolution itself.  Matrix binding now consumes only
        the antecedent identity/composition already established for the relative
        clause. Unresolved relative alternatives are left unresolved.
        """
        graph = self._candidate_graph
        if graph is None:
            return
        clauses = list(graph.clauses)
        for idx, clause in enumerate(clauses):
            if not clause.relative or clause.parent_clause_id is None or clause.connector_span is None:
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
            tokens = self._source_tokens(graph.text)
            candidates = self._relative_antecedent_candidates(
                by_id,
                clause_to_locals.get(parent_clause.clause_id, []),
                parent_clause,
                clause,
                tokens,
            )
            if not candidates:
                continue
            evidence_keys = {
                (candidate.span.evidence.start, candidate.span.evidence.end)
                for candidate in candidates
            }
            bindings: list[ActantCandidate] = []
            for child_id in child_ids:
                child = by_id[child_id]
                if child.alternatives:
                    continue
                for actant in child.actants:
                    if actant.evidence is None:
                        continue
                    if (actant.evidence.start, actant.evidence.end) in evidence_keys:
                        bindings.append(actant)
            unique: dict[tuple[object, ...], ActantCandidate] = {}
            for actant in bindings:
                if actant.composition is not None:
                    key = ("composition", actant.evidence.start, actant.evidence.end)
                elif actant.entity_ref is not None:
                    key = ("entity", actant.entity_ref)
                else:
                    key = ("span", actant.evidence.start, actant.evidence.end)
                unique[key] = actant
            if len(unique) != 1:
                continue
            antecedent_binding = next(iter(unique.values()))

            matrix_clause = next(
                (
                    item
                    for item in clauses[idx + 1:]
                    if item.sentence_id == clause.sentence_id
                    and not item.relative
                    and item.parent_clause_id is None
                    and clause_to_locals.get(item.clause_id)
                ),
                None,
            )
            if matrix_clause is None:
                continue
            matrix_id = clause_to_locals[matrix_clause.clause_id][0]
            matrix = by_id[matrix_id]
            if any(item.role is ActantRole.SUBJECT for item in matrix.actants):
                continue
            copied = replace(antecedent_binding, role=ActantRole.SUBJECT)
            by_id[matrix_id] = replace(matrix, actants=matrix.actants + (copied,))
            self._deterministic_trace(
                "relative_matrix_subject",
                f"ANTECEDENT:\n{copied.mention or copied.normalized_hint}\n"
                f"MATRIX PREDICATE:\n{matrix.predicate.surface}",
                copied.lookup_text or "",
            )

    def _choose_relative_role(
        self,
        text: str,
        child: AssertionCandidate,
        relative_span: _Span,
        antecedent: _Span,
        occupied: set[ActantRole],
    ) -> ActantRole | None:
        allowed = {
            ActantRole.SUBJECT,
            ActantRole.OBJECT,
            ActantRole.RECIPIENT,
            ActantRole.SOURCE,
            ActantRole.LOCATION,
            ActantRole.TIME,
            ActantRole.TOOL,
        } - occupied
        if not allowed:
            return None
        # Relative binding is the same semantic relation problem as an ordinary
        # actant. Bare case and relative-adverb surface form remain evidence only.
        # The semantic target, however, is the antecedent entity rather than the
        # surface pronoun itself. Showing only ``которого`` made a weak model treat
        # grammatical case as the participant meaning. Preserve the original
        # evidence/span for canonicalization, but present the bounded role decision
        # as ``ANTECEDENT (relative form: pronoun)``.
        semantic_target = _Span(
            relative_span.start_index,
            relative_span.end_index,
            f"{antecedent.text} (relative form: {relative_span.text})",
            relative_span.evidence,
        )
        return self._classify_role(
            text,
            child.predicate,
            semantic_target,
            occupied,
            None,
            requested=False,
            allowed_roles=allowed,
        )

    def _share_coordinated_predicate_actants(
        self,
        by_id: dict[str, AssertionCandidate],
        clause_to_locals: dict[str, list[str]],
        assertion_spans: dict[str, _Span | None],
    ) -> None:
        """Resolve shared actants for an explicit predicate coordination group.

        A coordination group is structural evidence only.  It never means that
        every actant is shared.  Python first narrows sharing to one source-denoting
        actant with no competing filler for the same semantic role.  Strong cases
        are handled deterministically (common SUBJECT, a postposed OBJECT with only
        transitive member predicates, and resolved pronominal object ellipsis).
        Other peripheral candidates receive one binary SHARED/LOCAL semantic probe.

        The same transfer code works for every ActantRole.  Adding RECIPIENT, TOOL,
        LOCATION or another role therefore does not require another ellipsis path.
        """
        graph = self._candidate_graph
        if graph is None or not graph.frame_graph.coordinations:
            return

        clause_members = {
            clause_id: set(local_ids)
            for clause_id, local_ids in clause_to_locals.items()
        }

        def actant_key(actant: ActantCandidate) -> tuple[object, ...]:
            if actant.entity_ref is not None:
                return ("entity", actant.entity_ref)
            if actant.candidate_ref is not None:
                return ("candidate", actant.candidate_ref)
            if actant.composition is not None:
                return ("composition", repr(actant.composition))
            if actant.evidence is not None:
                return ("span", actant.evidence.start, actant.evidence.end)
            return ("text", (actant.normalized_hint or actant.mention or "").casefold())

        def source_is_pronoun(actant: ActantCandidate) -> bool:
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

        def predicate_transitivity(local_id: str) -> str | None:
            span = assertion_spans.get(local_id)
            if span is None:
                return None
            token = next(
                (item for item in graph.tokens if item.index == span.start_index),
                None,
            )
            if token is None:
                return None
            return stable_transitivity(token.analyses)

        def has_competing_surface_subject(
            target_id: str,
            coordinator_indices: tuple[int, ...],
        ) -> bool:
            """Block subject inheritance when the target has an explicit NOM shell.

            NOM is not itself semantic SUBJECT; here it is used only as negative
            structural evidence that a new grammatical subject domain may begin.
            """
            target_span = assertion_spans.get(target_id)
            if target_span is None:
                return False
            previous_coord = max(
                (index for index in coordinator_indices if index < target_span.start_index),
                default=None,
            )
            if previous_coord is None:
                return False
            return any(
                token.has_case("nomn", poses={"NOUN", "NPRO"})
                for token in graph.tokens
                if previous_coord < token.index < target_span.start_index
            )

        def add_to_targets(
            source: ActantCandidate,
            role: ActantRole,
            targets: list[str],
            *,
            stage: str,
            clear_inherited_evidence: bool = False,
        ) -> None:
            if not targets:
                return
            for target_id in targets:
                current = by_id[target_id]
                if any(item.role == role for item in current.actants):
                    continue
                inherited = replace(source, evidence=None) if clear_inherited_evidence else source
                by_id[target_id] = replace(
                    current,
                    actants=current.actants + (inherited,),
                )
            self._deterministic_trace(
                stage,
                "ROLE:\n"
                f"{role.value}\nSHARED ACTANT:\n{source.lookup_text or actant_key(source)}\n"
                "TARGET PREDICATES:\n"
                + "\n".join(by_id[target].predicate.surface for target in targets),
                source.lookup_text or role.value,
            )

        for group in graph.frame_graph.coordinations:
            allowed_locals = clause_members.get(group.clause_id, set())
            token_to_local: dict[int, str] = {}
            for local_id in allowed_locals:
                span = assertion_spans.get(local_id)
                if span is None or span.start_index not in group.member_token_indices:
                    continue
                # Structural helper assertions can share a clause span; only the
                # assertion whose predicate begins on the member head owns it.
                evidence = by_id[local_id].predicate.evidence
                if evidence is None:
                    continue
                token = next(
                    (item for item in graph.tokens if item.index == span.start_index),
                    None,
                )
                if token is None or token.start != evidence.start:
                    continue
                token_to_local.setdefault(span.start_index, local_id)

            member_ids = [
                token_to_local[index]
                for index in group.member_token_indices
                if index in token_to_local
            ]
            if len(member_ids) < 2:
                continue

            member_spans = [assertion_spans[item] for item in member_ids]
            if any(span is None for span in member_spans):
                continue
            concrete_spans = [span for span in member_spans if span is not None]
            first_predicate_start = min(span.evidence.start for span in concrete_spans)
            last_predicate_end = max(span.evidence.end for span in concrete_spans)

            # SUBJECT is resolved first because a common semantic subject is useful
            # negative evidence against cross-subject sharing for the other roles.
            roles = [ActantRole.SUBJECT] + [
                role for role in ActantRole if role is not ActantRole.SUBJECT
            ]
            for role in roles:
                occurrences: list[tuple[str, ActantCandidate]] = []
                for local_id in member_ids:
                    occurrences.extend(
                        (local_id, actant)
                        for actant in by_id[local_id].actants
                        if actant.role == role
                    )
                if not occurrences:
                    continue

                by_key: dict[tuple[object, ...], list[tuple[str, ActantCandidate]]] = {}
                for local_id, actant in occurrences:
                    by_key.setdefault(actant_key(actant), []).append((local_id, actant))
                # Two genuinely different fillers mean the role is member-local.
                if len(by_key) != 1:
                    continue
                source_members = next(iter(by_key.values()))
                source_id, source = source_members[0]
                missing = [
                    local_id for local_id in member_ids
                    if not any(a.role == role for a in by_id[local_id].actants)
                ]
                if not missing:
                    continue

                source_evidence = source.evidence
                peripheral_before = (
                    source_evidence is not None
                    and source_evidence.end is not None
                    and source_evidence.end <= first_predicate_start
                )
                peripheral_after = (
                    source_evidence is not None
                    and source_evidence.start is not None
                    and source_evidence.start >= last_predicate_end
                )

                if role is ActantRole.SUBJECT:
                    targets = [
                        target for target in missing
                        if not has_competing_surface_subject(
                            target, group.coordinator_token_indices
                        )
                    ]
                    if (peripheral_before or peripheral_after) and targets:
                        add_to_targets(
                            source,
                            role,
                            targets,
                            stage="coordinated_shared_actant",
                        )
                        continue

                    # Russian permits the explicit subject after the first finite
                    # predicate but before the coordinator: ``выпустили матросы X
                    # и упали``. In an explicit predicate-coordination group, that
                    # grammatical subject controls rightward members unless a new
                    # nominative shell starts there. This is stronger than generic
                    # ellipsis and needs no semantic guess.
                    source_span = assertion_spans.get(source_id)
                    rightward_subjects: list[str] = []
                    if source_evidence is not None and source_span is not None:
                        for target in targets:
                            target_span = assertion_spans.get(target)
                            if target_span is None or target_span.start_index <= source_span.start_index:
                                continue
                            if any(
                                source_evidence.end is not None
                                and target_span.evidence.start is not None
                                and source_evidence.end <= token.start < target_span.evidence.start
                                and token.index in group.coordinator_token_indices
                                for token in graph.tokens
                            ):
                                rightward_subjects.append(target)
                    if rightward_subjects:
                        add_to_targets(
                            source,
                            role,
                            rightward_subjects,
                            stage="coordinated_rightward_subject",
                        )
                    continue

                # Never propagate a non-subject actant across independently resolved
                # semantic subjects.  This prevents constructions such as
                # ``Иван открыл дверь, а Мария закрыла`` from borrowing Иван's door.
                subject_keys = {
                    actant_key(actant)
                    for local_id in member_ids
                    for actant in by_id[local_id].actants
                    if actant.role is ActantRole.SUBJECT
                }
                if len(subject_keys) > 1:
                    continue

                if role is ActantRole.OBJECT and peripheral_after:
                    target_transitivity = {
                        target: predicate_transitivity(target) for target in missing
                    }
                    if any(value == "intr" for value in target_transitivity.values()):
                        continue
                    if all(value == "tran" for value in target_transitivity.values()):
                        add_to_targets(
                            source,
                            role,
                            missing,
                            stage="coordinated_shared_actant",
                        )
                        continue

                # An actant immediately before a coordinator may license rightward
                # ellipsis even when it is not group-peripheral.  This is discovered
                # generically for every role; a resolved pronominal OBJECT is the
                # strongest deterministic instance, while ordinary noun/PP fillers
                # use the same SHARED/LOCAL decision below.
                rightward: list[str] = []
                source_span = assertion_spans.get(source_id)
                if (
                    source_evidence is not None
                    and source_evidence.end is not None
                    and source_span is not None
                ):
                    for target in missing:
                        target_span = assertion_spans.get(target)
                        if target_span is None or target_span.start_index <= source_span.start_index:
                            continue
                        if any(
                            source_evidence.end <= token.start < target_span.evidence.start
                            and token.index in group.coordinator_token_indices
                            for token in graph.tokens
                        ):
                            rightward.append(target)

                if (
                    role is ActantRole.OBJECT
                    and source.entity_ref is not None
                    and source_is_pronoun(source)
                    and rightward
                ):
                    compatible = [
                        target for target in rightward
                        if predicate_transitivity(target) != "intr"
                    ]
                    if compatible:
                        add_to_targets(
                            source,
                            role,
                            compatible,
                            stage="coordinated_shared_actant",
                            clear_inherited_evidence=True,
                        )
                        continue

                # For any remaining role, a group-peripheral filler or a filler
                # directly adjacent to a following coordinator is a structurally
                # plausible shared argument.  One tiny semantic decision asks only
                # shared-vs-local; it does not reclassify the role.
                probe_targets = missing if (peripheral_before or peripheral_after) else rightward
                if not probe_targets:
                    continue
                probe_members = [source_id] + [
                    target for target in probe_targets if target != source_id
                ]
                if self._coordination_shared_actant_probe(
                    graph.text,
                    [by_id[item].predicate for item in probe_members],
                    role,
                    source,
                ):
                    add_to_targets(
                        source,
                        role,
                        probe_targets,
                        stage="coordinated_shared_actant",
                    )

    def _coordination_shared_actant_probe(
        self,
        text: str,
        predicates: list[PredicateCandidate],
        role: ActantRole,
        source: ActantCandidate,
    ) -> bool:
        """Tiny group-level decision: one known filler is SHARED or LOCAL."""
        target = source.lookup_text
        if target is None and source.composition is not None:
            target = " / ".join(member.lookup_text for member in source.composition.members)
        if not target:
            return False
        prompt = (
            f"TEXT:\n{text}\n"
            "COORDINATED PREDICATES:\n"
            + "\n".join(f"- {predicate.surface}" for predicate in predicates)
            + f"\nKNOWN SEMANTIC ROLE:\n{role.value}\n"
            + f"ACTANT:\n{target}\n"
            + "QUESTION:\nDoes this one actant fill the same semantic role for all listed "
              "coordinated predicates, or only for the predicate it is attached to?\n"
            + "CHOICES:\nSHARED\nLOCAL"
        )
        decision, _margin = self._exact_choice_probe(
            "coordination_shared_actant",
            prompt,
            ("SHARED", "LOCAL"),
        )
        return decision == "SHARED"

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
            confirm_omitted_subject: bool = False,
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
                if confirm_omitted_subject:
                    source_text = graph.text
                    prompt = (
                        f"TEXT:\n{source_text}\n"
                        f"PARENT SUBJECT:\n{inherited.lookup_text or inherited.mention or '?'}\n"
                        f"CHILD PREDICATE:\n{child.predicate.surface}\n"
                        "QUESTION:\nDoes the omitted semantic subject of the CHILD predicate "
                        "refer to the same participant as PARENT SUBJECT, or is the CHILD "
                        "independent/impersonal?\n"
                        "CHOICES:\nSAME_SUBJECT\nINDEPENDENT"
                    )
                    decision, _margin = self._exact_choice_probe(
                        "clause_subject_control",
                        prompt,
                        ("SAME_SUBJECT", "INDEPENDENT"),
                    )
                    if decision != "SAME_SUBJECT":
                        continue
                copied = ActantCandidate(
                    role=ActantRole.SUBJECT,
                    mention=inherited.mention,
                    normalized_hint=inherited.normalized_hint,
                    semantic_hint=inherited.semantic_hint,
                    entity_ref=entity_ref,
                    evidence=inherited.evidence,
                    grammatical_number=inherited.grammatical_number,
                )
                by_id[child_id] = replace(child, actants=child.actants + (copied,))
                self._deterministic_trace(
                    stage,
                    f"PARENT SUBJECT:\n{copied.lookup_text}\nCHILD PREDICATE:\n{child.predicate.surface}",
                    copied.lookup_text or "",
                )

        # Subordination is structural; the marker does not prove semantic-role
        # identity.  When a finite subordinate frame omits its subject and the
        # matrix supplies exactly one candidate, ask only the tiny controller
        # question SAME_SUBJECT/INDEPENDENT.  This covers ordinary ellipsis such
        # as ``Лиза напишет, если получит советы`` without turning impersonal
        # ``если стемнеет`` into an assertion about Лиза.
        for clause in graph.clauses:
            if (
                clause.relative
                or clause.parent_clause_id is None
                or clause.connector_span is None
            ):
                continue
            child_ids = clause_to_locals.get(clause.clause_id, [])
            # If the subordinate clause already states a semantic subject in any
            # coordinated member, that local subject domain wins.  Group-level
            # coordination will propagate it to omitted peer frames; importing the
            # matrix subject first would poison constructions such as
            # ``Если Лиза получит X и прочитает Y, она ...``.
            if any(
                any(actant.role is ActantRole.SUBJECT for actant in by_id[child_id].actants)
                for child_id in child_ids
            ):
                continue
            inherit(
                clause_to_locals.get(clause.parent_clause_id, []),
                child_ids,
                all_children=True,
                stage="subject_inheritance",
                confirm_omitted_subject=True,
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
            if any(mark in _STRONG_BOUNDARY for mark in between):
                continue
            # Besides comma-separated serial predicates, an explicit coordinator
            # can start a new same-sentence clause: ``Вера узнала знак и на
            # мгновение закрыла глаза``. The coordinator licenses omitted-subject
            # inheritance only when the right clause has no competing subject;
            # ``inherit`` enforces that condition. This is source syntax, not a
            # lexical valency rule.
            right_first = next(
                (
                    token.text.casefold()
                    for token in graph.tokens
                    if right.span.start_index <= token.index <= right.span.end_index
                    and re.search(r"\w", token.text)
                ),
                "",
            )
            explicit_coordinator = right_first in {"и", "а", "но", "да", "однако"}
            if "," not in between and not explicit_coordinator:
                continue
            inherit(
                clause_to_locals.get(left.clause_id, []),
                clause_to_locals.get(right.clause_id, []),
                all_children=False,
                stage=(
                    "coordinated_clause_subject_inheritance"
                    if explicit_coordinator else "paratactic_subject_inheritance"
                ),
            )


    def _inherit_nonfinite_subjects(
        self,
        by_id: dict[str, AssertionCandidate],
    ) -> None:
        """Propagate the matrix subject into source-linked gerund frames.

        Russian adverbial participles (GRND) are subject-controlled by the matrix
        clause: in ``Отперев калитку, Алексей вошёл`` the understood actor of
        ``отперев`` is the same grammatical participant as ``Алексей``.  The
        linguistic candidate graph already records a NONFINITE dependency, so this
        pass only copies a source-grounded SUBJECT across that dependency.  It does
        not apply to infinitives, whose controller can legitimately differ
        (``попросил его уйти``), and it never invents a subject when the matrix
        frame itself has none.
        """
        graph = self._candidate_graph
        if graph is None:
            return

        token_by_start = {token.start: token for token in graph.tokens}
        local_ids_by_token: dict[int, list[str]] = {}
        for local_id, assertion in by_id.items():
            evidence = assertion.predicate.evidence
            if evidence is None:
                continue
            token = token_by_start.get(evidence.start)
            if token is not None:
                local_ids_by_token.setdefault(token.index, []).append(local_id)

        def identity_key(actant: ActantCandidate) -> tuple[object, ...]:
            if actant.entity_ref is not None:
                return ("entity", actant.entity_ref)
            if actant.evidence is not None:
                return ("span", actant.evidence.start, actant.evidence.end)
            return ("text", (actant.lookup_text or "").casefold())

        for dependency in graph.frame_graph.dependencies:
            if dependency.kind is not FrameDependencyKind.NONFINITE:
                continue
            child_token = graph.token(dependency.child_token_index)
            # NONFINITE also includes infinitives. Only GRND has deterministic
            # same-subject control in the construction handled here.
            if not self._has_morph(child_token, poses={"GRND"}):
                continue

            parent_ids = local_ids_by_token.get(dependency.parent_token_index, [])
            child_ids = local_ids_by_token.get(dependency.child_token_index, [])
            if not parent_ids or not child_ids:
                continue

            subjects: list[ActantCandidate] = []
            for parent_id in parent_ids:
                subjects.extend(
                    actant
                    for actant in by_id[parent_id].actants
                    if actant.role is ActantRole.SUBJECT
                )
            unique_subjects: dict[tuple[object, ...], ActantCandidate] = {}
            for subject in subjects:
                unique_subjects.setdefault(identity_key(subject), subject)
            if len(unique_subjects) != 1:
                continue
            inherited = next(iter(unique_subjects.values()))

            for child_id in child_ids:
                child = by_id[child_id]
                if any(actant.role is ActantRole.SUBJECT for actant in child.actants):
                    continue
                copied = replace(inherited, role=ActantRole.SUBJECT)
                by_id[child_id] = replace(child, actants=child.actants + (copied,))
                self._deterministic_trace(
                    "nonfinite_subject_control",
                    f"MATRIX SUBJECT:\n{copied.lookup_text or copied.mention or '?'}\n"
                    f"GERUND PREDICATE:\n{child.predicate.surface}",
                    copied.entity_ref or copied.lookup_text or "",
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
            # Reused copies of an unresolved third-person personal pronoun are not
            # an identity commitment yet.  Allocating a fresh E here would make the
            # later anaphora resolver believe the pronoun was already resolved and
            # block ordinary cross-sentence binding (e.g. ``Алексей пришёл. Он...``).
            # Keep the exact source-span copies unbound until `_resolve_pronoun_coreferences`
            # can attach them to an earlier nominal.  This is a grammatical-class
            # rule derived from morphology, not a lexical name list.
            if not existing:
                def unresolved_personal_pronoun(actant: ActantCandidate) -> bool:
                    words = re.findall(r"[\w-]+", actant.mention or actant.normalized_hint or "", flags=re.UNICODE)
                    if not words:
                        return False
                    try:
                        analyses = tuple(self.morphology.analyze_all(words[-1]))
                    except AttributeError:
                        item = self.morphology.analyze(words[-1])
                        analyses = () if item is None else (item,)
                    return any(
                        info.pos == "NPRO" and info.normal_form.casefold() in {"он", "она", "оно", "они"}
                        for info in analyses
                    )
                if all(unresolved_personal_pronoun(actant) for _aid, actant in members):
                    continue
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

    def _resolve_nominal_relation_coreferences(
        self,
        by_id: dict[str, AssertionCandidate],
    ) -> None:
        """Bind explicit third-person possessors inside already parsed NPs.

        Ordinary pronoun resolution operates on actant positions. A possessive in
        ``торжество его`` is intentionally *inside* the SUBJECT NP and therefore
        never becomes a standalone actant. This pass applies the same conservative
        source-order principle to that internal relation: bind only when one
        structurally compatible earlier discourse entity remains; otherwise keep
        the relation unresolved for InteractionContext/clarification rather than
        guessing.
        """
        third_person = {"он", "она", "оно", "они"}

        def morphs(text: str | None) -> tuple[MorphInfo, ...]:
            if not text:
                return ()
            words = re.findall(r"[\w-]+", text, flags=re.UNICODE)
            if not words:
                return ()
            
            try:
                return tuple(self.morphology.analyze_all(words[-1]))
            except AttributeError:
                item = self.morphology.analyze(words[-1])
                return () if item is None else (item,)

        def pronoun_signature(text: str) -> tuple[set[str], set[str], set[str]] | None:
            infos = tuple(
                item for item in morphs(text)
                if item.pos == "NPRO" and item.normal_form.casefold() in third_person
            )
            if not infos:
                return None
            numbers = {item.number for item in infos if item.number}
            genders = {item.gender for item in infos if item.gender}
            # Russian его/ему etc. are masculine/neuter syncretic even when one
            # dictionary reading carries only masc. Preserve that grammatical fact.
            folded = text.casefold().replace("ё", "е")
            if folded in {"его", "него", "ему", "нему", "нем"} and genders == {"masc"}:
                genders.add("neut")
            lemmas = {item.normal_form.casefold() for item in infos}
            return numbers, genders, lemmas

        def candidate_surface_infos(candidate: ActantCandidate) -> tuple[MorphInfo, ...]:
            # Compatibility is about the grammatical form that occurred in the
            # source, not the canonical lemma used for entity lookup.  In
            # particular ``письма`` may be plural in the sentence even though its
            # normalized_hint is singular ``письмо``.  For structured NPs inspect
            # the explicit head token rather than the last genitive dependent.
            surface = (
                candidate.nominal_relations[0].head_mention
                if candidate.nominal_relations
                else candidate.mention
            )
            infos = material_analyses(morphs(surface))
            role_cases = {
                ActantRole.SUBJECT: {"nomn"},
                ActantRole.OBJECT: {"accs", "gent", "gen2"},
                ActantRole.RECIPIENT: {"datv"},
                ActantRole.LOCATION: {"loct"},
                ActantRole.TOOL: {"ablt"},
            }.get(candidate.role)
            if role_cases and infos:
                narrowed = tuple(item for item in infos if item.case in role_cases)
                if narrowed:
                    infos = narrowed
            if infos:
                return infos
            return material_analyses(morphs(candidate.normalized_hint))

        def compatible(sig: tuple[set[str], set[str], set[str]], candidate: ActantCandidate) -> bool:
            infos = candidate_surface_infos(candidate)
            if not infos:
                return True
            if not any(
                item.pos in {"NOUN", "NPRO"}
                or (item.pos in {"ADJF", "ADJS", "PRTF", "PRTS"} and "Subx" in item.grammemes)
                for item in infos
            ):
                return False
            p_numbers, p_genders, _ = sig
            c_numbers = {item.number for item in infos if item.number}
            c_genders = {item.gender for item in infos if item.gender}
            if p_numbers and c_numbers and p_numbers.isdisjoint(c_numbers):
                return False
            if p_genders and c_genders and p_genders.isdisjoint(c_genders):
                return False
            return True

        # Snapshot source candidates by position. entity_ref allocation may mutate
        # by_id, so we keep stable assertion ids + actant indexes rather than object
        # identities.
        antecedents: list[tuple[int, str, int]] = []
        for assertion_id, assertion in by_id.items():
            for actant_index, actant in enumerate(assertion.actants):
                if (
                    actant.candidate_ref is not None
                    or actant.composition is not None
                    or actant.proposition is not None
                    or actant.evidence is None
                ):
                    continue
                antecedents.append((actant.evidence.start or 0, assertion_id, actant_index))
        antecedents.sort(key=lambda row: row[0])

        relation_sites: list[tuple[int, str, int, int]] = []
        for assertion_id, assertion in by_id.items():
            for actant_index, actant in enumerate(assertion.actants):
                for relation_index, relation in enumerate(actant.nominal_relations):
                    if (
                        relation.kind is not NominalRelationKind.POSSESSOR
                        or relation.dependent_entity_ref is not None
                        or relation.evidence is None
                        or pronoun_signature(relation.dependent_mention) is None
                    ):
                        continue
                    relation_sites.append((relation.evidence.start or 0, assertion_id, actant_index, relation_index))
        relation_sites.sort(key=lambda row: row[0])

        for relation_pos, assertion_id, actant_index, relation_index in relation_sites:
            current_assertion = by_id[assertion_id]
            if actant_index >= len(current_assertion.actants):
                continue
            current_actant = current_assertion.actants[actant_index]
            if relation_index >= len(current_actant.nominal_relations):
                continue
            relation = current_actant.nominal_relations[relation_index]
            sig = pronoun_signature(relation.dependent_mention)
            if sig is None:
                continue

            pool: list[tuple[int, str, int, ActantCandidate]] = []
            for pos, antecedent_id, antecedent_index in antecedents:
                if pos >= relation_pos:
                    break
                assertion = by_id[antecedent_id]
                if antecedent_index >= len(assertion.actants):
                    continue
                candidate = assertion.actants[antecedent_index]
                if compatible(sig, candidate):
                    pool.append((pos, antecedent_id, antecedent_index, candidate))
            if not pool:
                continue
            # Subjects are the strongest discourse anchors. If exactly one entity
            # survives among prior SUBJECT mentions, do not let incidental OBJECTs
            # of the same gender create a false ambiguity. Otherwise keep all.
            subject_pool = [row for row in pool if row[3].role is ActantRole.SUBJECT]
            if subject_pool:
                pool = subject_pool

            unique: dict[tuple[object, ...], tuple[int, str, int, ActantCandidate]] = {}
            for row in pool:
                candidate = row[3]
                if candidate.entity_ref is not None:
                    key = ("entity", candidate.entity_ref)
                elif candidate.evidence is not None:
                    key = ("span", candidate.evidence.start, candidate.evidence.end)
                else:
                    key = ("site", row[1], row[2])
                unique[key] = row
            if len(unique) != 1:
                continue
            _pos, antecedent_id, antecedent_index, antecedent = next(iter(unique.values()))
            entity_ref = antecedent.entity_ref or self._ensure_actant_entity_ref(
                by_id, antecedent_id, antecedent
            )
            if entity_ref is None:
                continue

            # _ensure_actant_entity_ref may have replaced assertions; fetch the
            # current relation site again and update only its internal possessor.
            assertion = by_id[assertion_id]
            actants = list(assertion.actants)
            if actant_index >= len(actants):
                continue
            target_actant = actants[actant_index]
            rels = list(target_actant.nominal_relations)
            if relation_index >= len(rels):
                continue
            rels[relation_index] = replace(rels[relation_index], dependent_entity_ref=entity_ref)
            actants[actant_index] = replace(target_actant, nominal_relations=tuple(rels))
            by_id[assertion_id] = replace(assertion, actants=tuple(actants))
            self._deterministic_trace(
                "nominal_possessor_binding",
                f"POSSESSOR:\n{relation.dependent_mention}\nANTECEDENT:\n{antecedent.lookup_text}",
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

        def pronoun_infos(
            value: str | None,
            role: ActantRole | None = None,
        ) -> tuple[MorphInfo, ...]:
            # Personal/anaphoric pronouns form a small closed grammatical class.
            # Preserve *all* dictionary analyses here rather than applying the
            # generic probability floor used for open-class lexical ambiguity.
            # Oblique personal forms are morphologically syncretic (one surface
            # form can represent more than one gender/lemma); dropping a lower
            # scored reading can incorrectly eliminate the true antecedent before
            # deterministic same-role/discourse constraints are applied.
            infos = tuple(
                info for info in morphs(value)
                if (
                    info.pos == "NPRO"
                    and info.normal_form.casefold() in third_person_lemmas
                )
                or (
                    info.pos == "ADJF"
                    and "Anph" in info.grammemes
                    and "Subx" in info.grammemes
                )
            )
            if not infos or role is None:
                return infos
            role_cases = {
                ActantRole.SUBJECT: {"nomn"},
                ActantRole.OBJECT: {"accs", "gent", "gen2"},
                ActantRole.RECIPIENT: {"datv"},
                ActantRole.LOCATION: {"loct"},
                ActantRole.TOOL: {"ablt"},
            }.get(role)
            if role_cases is None:
                return infos
            narrowed = tuple(info for info in infos if info.case in role_cases)
            return narrowed or infos

        def is_oblique_third_person(
            infos: tuple[MorphInfo, ...], role: ActantRole
        ) -> bool:
            return (
                role is not ActantRole.SUBJECT
                and any(
                    info.pos == "NPRO"
                    and info.normal_form.casefold() in third_person_lemmas
                    for info in infos
                )
            )

        def needs_local_antecedent_probe(infos: tuple[MorphInfo, ...]) -> bool:
            # Morphology-marked substantivized anaphors (e.g. demonstratives)
            # carry an explicit backward-reference function but are not ordinary
            # third-person personal pronouns.  If deterministic compatibility
            # leaves several source mentions, one bounded source-label decision is
            # the minimal remaining semantic task.  Personal pronouns keep the
            # existing ambiguity-preserving path.
            return any(
                info.pos == "ADJF"
                and "Anph" in info.grammemes
                and "Subx" in info.grammemes
                for info in infos
            )

        def candidate_surface_infos(candidate: ActantCandidate) -> tuple[MorphInfo, ...]:
            # Keep source inflection for agreement/coreference.  Canonical entity
            # lookup deliberately lemmatizes nouns, but using that lemma here loses
            # number/gender evidence (e.g. plural ``письма`` -> singular
            # ``письмо``) and can make a local pronoun fall through to a stale
            # cross-turn anchor.  Structured NPs expose their source head directly.
            surface = (
                candidate.nominal_relations[0].head_mention
                if candidate.nominal_relations
                else candidate.mention
            )
            infos = material_analyses(morphs(surface))
            role_cases = {
                ActantRole.SUBJECT: {"nomn"},
                ActantRole.OBJECT: {"accs", "gent", "gen2"},
                ActantRole.RECIPIENT: {"datv"},
                ActantRole.LOCATION: {"loct"},
                ActantRole.TOOL: {"ablt"},
            }.get(candidate.role)
            if role_cases and infos:
                narrowed = tuple(item for item in infos if item.case in role_cases)
                if narrowed:
                    infos = narrowed
            if infos:
                return infos
            return material_analyses(morphs(candidate.normalized_hint))

        def compatible(
            pronoun: tuple[MorphInfo, ...],
            candidate: ActantCandidate,
            pronoun_role: ActantRole,
        ) -> bool:
            candidate_infos = candidate_surface_infos(candidate)
            if not candidate_infos:
                return True
            # Personal pronouns refer to discourse entities, not ordinary
            # predicative properties.  Dictionary morphology marks adjective and
            # participle states as nominal-like forms too, but allowing every
            # ADJF/PRTF here made a state such as ``сердитая`` compete with the
            # actual woman as antecedent of ``она``.  Keep only genuine nominal
            # readings plus explicitly substantivized adjective/participle forms.
            referential = any(
                info.pos in {"NOUN", "NPRO"}
                or (
                    info.pos in {"ADJF", "ADJS", "PRTF", "PRTS"}
                    and "Subx" in info.grammemes
                )
                for info in candidate_infos
            )
            if not referential:
                return False
            p_numbers = {x.number for x in pronoun if x.number}
            c_numbers = {x.number for x in candidate_infos if x.number}
            if p_numbers and c_numbers and p_numbers.isdisjoint(c_numbers):
                return False
            p_genders = {x.gender for x in pronoun if x.gender}
            c_genders = {x.gender for x in candidate_infos if x.gender}
            oblique_personal = (
                pronoun_role is not ActantRole.SUBJECT
                and any(
                    x.pos == "NPRO"
                    and x.normal_form.casefold() in third_person_lemmas
                    for x in pronoun
                )
            )
            # Russian third-person oblique masculine forms are syncretic with
            # neuter. Dictionary morphology can expose only the masculine tag for
            # that surface paradigm, so treating it as a hard identity constraint
            # incorrectly excludes neuter antecedents. This is a grammatical
            # paradigm rule, not lexical/semantic guessing. Feminine and nominative
            # gender distinctions remain strict.
            effective_p_genders = set(p_genders)
            if oblique_personal and effective_p_genders == {"masc"}:
                effective_p_genders.add("neut")
            if (
                effective_p_genders
                and c_genders
                and effective_p_genders.isdisjoint(c_genders)
            ):
                return False
            # Animacy on an oblique personal pronoun is inflectional/syncretic and
            # is not a reliable referent constraint (the same pronoun can point to
            # animate or inanimate entities). Keep animacy filtering for other
            # anaphoric forms where morphology genuinely distinguishes it.
            if not oblique_personal:
                p_animacy = {x.animacy for x in pronoun if x.animacy}
                c_animacy = {x.animacy for x in candidate_infos if x.animacy}
                if p_animacy and c_animacy and p_animacy.isdisjoint(c_animacy):
                    return False

            # Person is a grammatical compatibility constraint, not a semantic
            # guess.  A third-person anaphor cannot corefer with a locally
            # explicit first/second-person deictic mention merely because both
            # are singular and morphology lacks gender on the deictic pronoun.
            # This prevents spurious correlated alternatives such as treating
            # ``её`` as potentially identical to the current speaker ``Я``.
            persons = {"1per", "2per", "3per"}
            p_persons = {g for x in pronoun for g in x.grammemes if g in persons}
            c_persons = {g for x in candidate_infos for g in x.grammemes if g in persons}
            if p_persons and c_persons and p_persons.isdisjoint(c_persons):
                return False
            return True

        # Structural subject-control / coordination can copy the same unresolved
        # third-person pronoun into several frames before this resolver runs.  Those
        # copies may carry a temporary local ``entity_ref`` merely to keep the
        # copies together (``Отперев калитку, он толкнул её``).  Such a ref is not
        # evidence that ``он`` has already been linked to an antecedent.  If an
        # entity_ref is used *only* by third-person personal-pronoun mentions, reset
        # it to unresolved before antecedent search.  A real local binding is safe:
        # its ref is also present on at least one non-pronominal source mention and
        # therefore survives this pass.  This keeps structural propagation from
        # hiding a stronger same-unit antecedent without consulting AH state.
        ref_sites: dict[str, list[tuple[str, int, ActantCandidate]]] = {}
        for current_id, current_assertion in by_id.items():
            for current_index, current_actant in enumerate(current_assertion.actants):
                if current_actant.entity_ref is not None:
                    ref_sites.setdefault(current_actant.entity_ref, []).append(
                        (current_id, current_index, current_actant)
                    )

        provisional_refs: set[str] = set()
        for ref_id, sites in ref_sites.items():
            if not sites:
                continue
            only_personal_third = True
            for _site_id, _site_index, site_actant in sites:
                infos = pronoun_infos(
                    site_actant.mention or site_actant.normalized_hint,
                    site_actant.role,
                )
                if not any(
                    info.pos == "NPRO"
                    and info.normal_form.casefold() in third_person_lemmas
                    for info in infos
                ):
                    only_personal_third = False
                    break
            if only_personal_third:
                provisional_refs.add(ref_id)

        if provisional_refs:
            for current_id, current_assertion in tuple(by_id.items()):
                changed = False
                updated_actants: list[ActantCandidate] = []
                for current_actant in current_assertion.actants:
                    if current_actant.entity_ref in provisional_refs:
                        updated_actants.append(replace(current_actant, entity_ref=None))
                        changed = True
                    else:
                        updated_actants.append(current_actant)
                if changed:
                    by_id[current_id] = replace(
                        current_assertion, actants=tuple(updated_actants)
                    )
            self._deterministic_trace(
                "pronoun_provisional_ref_reset",
                "LOCAL_PRONOUN_REFS:\n" + ", ".join(sorted(provisional_refs)),
                "UNRESOLVED",
            )

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
            p_infos = pronoun_infos(
                original_pronoun.mention or original_pronoun.normalized_hint,
                original_pronoun.role,
            )
            if not p_infos or original_pronoun.entity_ref is not None:
                continue
            anaphoric_substantive = needs_local_antecedent_probe(p_infos)
            prior: list[tuple[int, str, ActantCandidate]] = []
            for candidate_position, candidate_id, candidate in ordered:
                if candidate_position >= position:
                    break
                if candidate_id == assertion_id and candidate == original_pronoun:
                    continue
                if not compatible(p_infos, candidate, original_pronoun.role):
                    continue
                # Russian non-reflexive third-person oblique pronouns cannot bind
                # the grammatical SUBJECT of their own local clause. ``Матрос
                # ухватил его`` therefore cannot mean the matros grabbed himself;
                # that reading requires reflexive ``себя``. This is a binding
                # constraint, not a semantic preference, and it prevents a local
                # subject from stealing an antecedent that should remain available
                # from the preceding discourse.
                if (
                    candidate_id == assertion_id
                    and candidate.role is ActantRole.SUBJECT
                    and is_oblique_third_person(p_infos, original_pronoun.role)
                ):
                    continue
                # Do not use an unresolved third-person pronoun as a fresh anchor.
                # A previously bound pronoun is safe because its entity_ref already
                # identifies the antecedent exactly.
                c_pronoun = pronoun_infos(
                    candidate.mention or candidate.normalized_hint,
                    candidate.role,
                )
                if c_pronoun and candidate.entity_ref is None:
                    continue
                prior.append((candidate_position, candidate_id, candidate))

            # A matrix pronoun may resume the same semantic participant from an
            # immediately dependent non-finite frame: ``Сняв плащ, она повесила
            # его``.  This is stronger than generic recency because the linguistic
            # frame graph explicitly links the gerund/infinitive child to this
            # matrix predicate.  Prefer the child only when one compatible
            # antecedent with the *same semantic role* survives; otherwise keep
            # the ordinary ambiguity-preserving resolver below.  No canonical UID
            # or lexical predicate is consulted here.
            graph = self._candidate_graph
            structural_pool: list[tuple[int, str, ActantCandidate]] = []
            if graph is not None:
                current_predicate = by_id[assertion_id].predicate.evidence
                current_token = (
                    next((t for t in graph.tokens if current_predicate is not None and t.start == current_predicate.start), None)
                    if current_predicate is not None
                    else None
                )
                if current_token is not None:
                    nonfinite_children = {
                        dep.child_token_index
                        for dep in graph.frame_graph.dependencies
                        if dep.parent_token_index == current_token.index
                        and dep.kind is FrameDependencyKind.NONFINITE
                    }
                    if nonfinite_children:
                        for item in prior:
                            candidate_predicate = by_id[item[1]].predicate.evidence
                            if candidate_predicate is None or item[2].role is not original_pronoun.role:
                                continue
                            candidate_token = next(
                                (t for t in graph.tokens if t.start == candidate_predicate.start),
                                None,
                            )
                            if candidate_token is not None and candidate_token.index in nonfinite_children:
                                structural_pool.append(item)
                        structural_keys = {
                            (
                                ("entity", item[2].entity_ref)
                                if item[2].entity_ref is not None
                                else (
                                    "span",
                                    item[2].evidence.start if item[2].evidence is not None else item[0],
                                    item[2].evidence.end if item[2].evidence is not None else item[0],
                                )
                            )
                            for item in structural_pool
                        }
                        if len(structural_keys) != 1:
                            structural_pool = []

            # Same-role preference is safe only inside one non-subordinate
            # sentence region (for example a conditional antecedent followed by
            # its main clause).  Across sentence boundaries or inside an embedded
            # complement, other matrix participants remain legitimate antecedents.
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
            if structural_pool:
                pool = structural_pool
            elif (
                current_clause is not None
                and current_clause.parent_clause_id is None
                and not cross_sentence
                and not anaphoric_substantive
            ):
                same_role = [item for item in prior if item[2].role == original_pronoun.role]
                pool = same_role if same_role else prior
            elif graph is not None and current_clause is not None and cross_sentence:
                # Ordinary personal-pronoun continuity does not require a lexical
                # discourse marker.  Keep only compatible mentions from the most
                # recent preceding sentence; older sentences remain outside the
                # local ambiguity set.  Crucially, do *not* prefer the same semantic
                # role across a sentence boundary: ``Шум разбудил Павла. Он пришёл``
                # must keep Павел eligible even though he was OBJECT, not SUBJECT.
                # If several recent personal-pronoun antecedents survive grammar,
                # preserve all readings.  Source text alone does not make entity
                # identity a safe model decision; Integration owns clarification.
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
                    first_word = next(
                        (
                            graph.token(i).text.casefold()
                            for i in range(
                                current_clause.span.start_index,
                                current_clause.span.end_index + 1,
                            )
                            if re.search(r"\w", graph.token(i).text)
                        ),
                        "",
                    )
                    if first_word in {"потом", "затем", "тогда", "далее"}:
                        same_role = [
                            item for item in recent
                            if item[2].role == original_pronoun.role
                        ]
                        pool = same_role if len(same_role) == 1 else recent
                    else:
                        pool = recent
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
                if anaphoric_substantive:
                    candidates = list(unique_pool.values())
                    labels = [f"C{i}" for i in range(1, len(candidates) + 1)]
                    allowed = tuple([*labels, "UNCLEAR"])
                    source_text = (
                        self._candidate_graph.text
                        if self._candidate_graph is not None
                        else ""
                    )
                    prompt = (
                        f"TEXT:\n{source_text}\nANAPHOR:\n"
                        f"{original_pronoun.mention or original_pronoun.normalized_hint}\n"
                        "CANDIDATE EARLIER MENTIONS:\n"
                        + "\n".join(
                            f"{label}: {item[2].mention or item[2].normalized_hint}"
                            for label, item in zip(labels, candidates)
                        )
                        + "\nQUESTION:\nWhich earlier mention does ANAPHOR refer to in TEXT? "
                        "Choose UNCLEAR if the sentence itself does not determine one.\n"
                        "CHOICES:\n" + "\n".join(allowed)
                    )

                    def parse_antecedent_label(raw: str) -> str:
                        label = raw.strip().upper()
                        if label not in allowed:
                            raise AdaptiveParseError(
                                "antecedent_choice expected exactly one of: "
                                + ", ".join(allowed)
                            )
                        return label

                    selected_label = self._probe(
                        "antecedent_choice",
                        prompt,
                        parse_antecedent_label,
                        max_new_tokens=4,
                                )
                    if selected_label != "UNCLEAR":
                        selected_index = labels.index(selected_label)
                        _, antecedent_id, antecedent = candidates[selected_index]
                        unique_pool = {
                            ("selected", selected_index): candidates[selected_index]
                        }

                if len(unique_pool) == 1:
                    _, antecedent_id, antecedent = next(iter(unique_pool.values()))
                else:
                # Perception is allowed to expose several local semantic readings,
                # but canonical entity choice belongs to deterministic Integration.
                # Preserve one complete AssertionCandidate per compatible antecedent
                # instead of asking the LLM to choose a canonical referent or failing
                # before the architecture's Ambiguity Handling stage.
                    # Stabilize every candidate antecedent *before* branching.
                    # `_ensure_actant_entity_ref` may mutate the assertion that owns
                    # the source mention.  If we allocate those refs lazily while
                    # constructing alternatives, later alternatives inherit a
                    # different base assertion than earlier ones.  When an
                    # antecedent is another role of the same assertion this creates
                    # artificial correlated alternatives (two roles appear to vary)
                    # even though only the pronoun binding is ambiguous.
                    #
                    # Pre-binding all source mentions first makes the common
                    # assertion skeleton identical in every reading; only the
                    # anaphoric role changes.  This is a general runtime identity
                    # invariant and does not choose any antecedent.
                    stabilized: list[tuple[int, str, ActantCandidate, str]] = []
                    for _pos, antecedent_id, antecedent in unique_pool.values():
                        entity_ref = antecedent.entity_ref or self._ensure_actant_entity_ref(
                            by_id, antecedent_id, antecedent
                        )
                        if entity_ref is not None:
                            stabilized.append((_pos, antecedent_id, antecedent, entity_ref))
                    if not stabilized:
                        continue

                    latest = by_id[assertion_id]
                    base_variants = latest.alternatives or (replace(latest, alternatives=()),)
                    variants: list[AssertionCandidate] = []
                    for _pos, antecedent_id, antecedent, entity_ref in stabilized:
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
        """Choose one parent↔child semantic relation in one bounded decision.

        ClauseFrameGraph proves only that CHILD is structurally dependent on PARENT.
        Surface markers and infinitive morphology may narrow the admissible relation
        set, but they never assign an AH role.  The model therefore compares all
        remaining meanings at once instead of answering an ordered sequence of
        binary questions where an early false positive (typically CONTENT_LINK)
        could prevent CAUSE/TIME/PURPOSE from ever being considered.
        """
        if not allowed:
            return None

        labels: dict[ActantRole, tuple[str, str]] = {
            ActantRole.OBJECT: (
                "CONTENT_LINK",
                "CHILD is semantic content or selected complement of PARENT: what is said, known, wanted, decided, requested, begun, etc. If CHILD is what PARENT wants/decides/requests/begins, use CONTENT_LINK even though CHILD is intended.",
            ),
            ActantRole.PURPOSE: (
                "GOAL_LINK",
                "CHILD is an adjunct goal for which PARENT itself is performed: 'PARENT in order to CHILD'. Do not use GOAL_LINK for wanted/decided/requested/begun content.",
            ),
            ActantRole.CAUSE: (
                "CAUSE_LINK",
                "CHILD is the reason/cause that explains why PARENT happens.",
            ),
            ActantRole.TIME: (
                "TIME_LINK",
                "CHILD locates PARENT in time or supplies the temporal situation relative to which PARENT occurs.",
            ),
            ActantRole.LOCATION: (
                "PLACE_LINK",
                "CHILD supplies the place/location in relation to which PARENT occurs.",
            ),
            ActantRole.SOURCE: (
                "SOURCE_LINK",
                "CHILD is the source/origin situation from which PARENT or its content arises.",
            ),
            ActantRole.HOW_TO: (
                "MANNER_LINK",
                "CHILD describes the manner/procedure by which PARENT is carried out.",
            ),
        }
        offered = [(role, *labels[role]) for role in allowed if role in labels]
        if not offered:
            if allow_none:
                return None
            raise AdaptiveParseError(
                "no supported semantic frame relation remains between "
                f"{parent.predicate.lookup_form!r} and {child.predicate.lookup_form!r}"
            )

        source_text = self._candidate_graph.text if self._candidate_graph is not None else ""
        lines = [
            f"TEXT:\n{source_text}",
            f"PARENT PREDICATE:\n{parent.predicate.surface}",
            f"CHILD PREDICATE:\n{child.predicate.surface}",
            "RELATION MEANINGS:",
        ]
        for _role, label, description in offered:
            lines.append(f"{label}: {description}")
        choices = tuple(label for _role, label, _description in offered)
        if allow_none:
            lines.append("SEPARATE: CHILD is structurally nearby/dependent but fills none of the listed semantic relations of PARENT.")
            choices = (*choices, "SEPARATE")
        lines.append(
            "QUESTION:\nWhich one relation best describes CHILD relative to PARENT? "
            "First distinguish selected CONTENT from adjunct PURPOSE: if CHILD is what "
            "PARENT means/wants/decides/requests/begins, choose CONTENT_LINK; choose "
            "GOAL_LINK only when PARENT itself is done in order to achieve CHILD. "
            "Then compare the remaining listed meanings."
        )
        lines.append("CHOICES:\n" + "\n".join(choices))
        decision, _compat = self._exact_choice_probe(
            "frame_relation", "\n".join(lines), choices
        )
        if decision == "SEPARATE":
            return None
        for role, label, _description in offered:
            if decision == label:
                return role
        raise AdaptiveParseError("frame relation escaped bounded choice set")

    @staticmethod
    def _frame_relation_choice_labels(role: ActantRole) -> tuple[str, str]:
        """Compatibility helper for diagnostics/older focused tests."""
        return {
            ActantRole.OBJECT: ("CONTENT_LINK", "SEPARATE"),
            ActantRole.PURPOSE: ("GOAL_LINK", "SEPARATE"),
            ActantRole.CAUSE: ("CAUSE_LINK", "SEPARATE"),
            ActantRole.TIME: ("TIME_LINK", "SEPARATE"),
            ActantRole.LOCATION: ("PLACE_LINK", "SEPARATE"),
            ActantRole.SOURCE: ("SOURCE_LINK", "SEPARATE"),
            ActantRole.HOW_TO: ("MANNER_LINK", "SEPARATE"),
        }.get(role, ("LINKED", "SEPARATE"))

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
        # A grammatical subject-like span may be used only to isolate the two
        # contrasted phrases.  Its AH role is still resolved semantically below;
        # nominative/agreement does not assign SUBJECT.
        subject_span = self._deterministic_subject_span(tokens, predicate_span, None)
        selected = [subject_span] if subject_span is not None else []
        candidates = self._candidate_phrase_spans(
            text, tokens, predicate_span, selected, requested_spans=()
        )
        left = [c for c in candidates if ne < c.start_index and c.end_index < contrast]
        right = [c for c in candidates if contrast < c.start_index <= end]
        if len(left) != 1 or len(right) != 1:
            return None
        left_allowed = set(
            self._deterministic_role_candidates(
                tokens, predicate_span, predicate, left[0]
            )
        ) or None
        role = self._classify_role(
            text, predicate, left[0], set(), None, requested=False,
            allowed_roles=left_allowed,
        )
        if role is None:
            return None
        right_allowed = set(
            self._deterministic_role_candidates(
                tokens, predicate_span, predicate, right[0]
            )
        )
        if right_allowed and role not in right_allowed:
            return None

        prefix: list[ActantCandidate] = []
        if subject_span is not None:
            subject_allowed = set(
                self._deterministic_role_candidates(
                    tokens, predicate_span, predicate, subject_span
                )
            ) or None
            subject_role = self._classify_role(
                text, predicate, subject_span, set(), None, requested=False,
                allowed_roles=subject_allowed,
            )
            if subject_role is None or subject_role == role:
                # The special rewrite cannot preserve the one-role-per-frame
                # invariant in this reading. Fall back to ordinary parsing rather
                # than inventing a semantic role from word order/case.
                return None
            prefix.append(self._make_actant(subject_role, subject_span))

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
        requested_roles: tuple[ActantRole, ...],
        requested_spans: tuple[_Span, ...],
        role_whitelist: set[ActantRole] | None = None,
    ) -> tuple[tuple[ActantCandidate, ...], tuple[_Span, ...]]:
        spans: list[_Span] = []
        roles: set[ActantRole] = set()
        actants: list[ActantCandidate] = []

        # Do not turn grammatical nominative/agreement into AH SUBJECT here.
        # SUBJECT is semantic (actor/holder/experiencer), not a syntactic label.
        # Nominative phrases remain ordinary phrase candidates and are classified
        # by one bounded semantic relation decision below.  The only narrower
        # exception is a subject explicitly licensed by a nominal-predication
        # shell resolved before frame parsing (X — [это] Y). In that structure X
        # is the referential term by construction, not a NOM->SUBJECT shortcut.
        if predicate_span is not None:
            nominal_subject = self._nominal_subject_spans.get(predicate_span.start_index)
            if nominal_subject is not None and ActantRole.SUBJECT not in requested_roles:
                self._trace_deterministic_actant(
                    text, tokens, predicate_span, nominal_subject, ActantRole.SUBJECT
                )
                spans.append(nominal_subject)
                roles.add(ActantRole.SUBJECT)
                actants.append(self._make_actant(ActantRole.SUBJECT, nominal_subject))

        state_span = None
        if ActantRole.STATE not in requested_roles and ActantRole.STATE not in roles:
            state_span = self._deterministic_copular_state_span(
                text, tokens, predicate_span, predicate, spans, requested_spans
            )
        if state_span is not None:
            self._contextualize_nominal_span(text, predicate, state_span, tokens)
            self._trace_deterministic_actant(text, tokens, predicate_span, state_span, ActantRole.STATE)
            spans.append(state_span)
            roles.add(ActantRole.STATE)
            actants.append(self._make_actant(ActantRole.STATE, state_span))

            # Once a genuine adjectival/predicative copular STATE has been
            # structurally identified, one unambiguous agreeing nominal is by
            # definition the semantic holder of that state.  This is deliberately
            # narrower than NOM->SUBJECT: without the proven copular STATE the same
            # grammatical nominative still goes through semantic role resolution.
            if ActantRole.SUBJECT not in requested_roles:
                holder_span = self._deterministic_copular_holder_span(
                    tokens, predicate_span, state_span
                )
                if holder_span is not None and not any(holder_span.overlaps(item) for item in spans):
                    self._contextualize_nominal_span(text, predicate, holder_span, tokens)
                    self._trace_deterministic_actant(
                        text, tokens, predicate_span, holder_span, ActantRole.SUBJECT
                    )
                    spans.append(holder_span)
                    roles.add(ActantRole.SUBJECT)
                    actants.append(self._make_actant(ActantRole.SUBJECT, holder_span))

        actant_iterations = 0
        for _ in range(self.settings.max_actants_per_act):
            actant_iterations += 1
            candidates = self._candidate_phrase_spans(
                text, tokens, predicate_span, spans, requested_spans=requested_spans
            )
            if not candidates:
                self._deterministic_trace(
                    "actant_start",
                    self._actant_phrase_prompt(text, predicate_span, spans, (), requested_spans),
                    0,
                )
                break

            # Only a singleton returned by _deterministic_role_candidates is a
            # structurally entailed semantic relation (currently explicit passive
            # voice or a copular state complement). Case, agreement, prepositions
            # and lexical markers never enter this fast path.
            deterministic_items: list[tuple[_Span, tuple[ActantRole, ...]]] = []
            role_frequency: dict[ActantRole, int] = {}
            for candidate_span in candidates:
                self._contextualize_nominal_span(text, predicate, candidate_span, tokens)
                role_candidates = self._deterministic_role_candidates(
                    tokens, predicate_span, predicate, candidate_span
                )
                if role_whitelist is not None:
                    role_candidates = tuple(
                        role for role in role_candidates if role in role_whitelist
                    )
                if len(role_candidates) != 1:
                    continue
                role_candidate = role_candidates[0]
                if role_candidate in roles or role_candidate in requested_roles:
                    continue
                deterministic_items.append((candidate_span, role_candidates))
                role_frequency[role_candidate] = role_frequency.get(role_candidate, 0) + 1

            deterministic = next(
                (item for item in deterministic_items if role_frequency[item[1][0]] == 1),
                None,
            )

            if deterministic is not None:
                span, allowed_roles = deterministic
            else:
                # Candidate-phrase discovery is now structural and exhaustive:
                # clause/predicate boundaries, other predicate heads, connectives,
                # requested WH spans and already consumed phrases have already been
                # removed before this point.  Asking the model a second question
                # "is any phrase relevant?" allowed a single spurious STOP to erase
                # the entire frame (the dominant broad200 failure).  Enumerate the
                # finite source candidates deterministically and reserve the model
                # only for the genuinely semantic role decision.
                span = candidates[0]
                allowed_roles = self._deterministic_role_candidates(
                    tokens, predicate_span, predicate, span
                )
                if role_whitelist is not None:
                    allowed_roles = tuple(
                        role for role in allowed_roles if role in role_whitelist
                    )
            self._deterministic_trace(
                "actant_start",
                self._actant_phrase_prompt(text, predicate_span, spans, candidates, requested_spans),
                span.spec,
            )

            attachment_target = self._resolve_modifier_attachment(
                text, tokens, predicate_span, predicate, span
            )
            if (
                attachment_target is not None
                and attachment_target.kind is _AttachmentTargetKind.NOMINAL
            ):
                owner = attachment_target.nominal_span
                if owner is None:
                    raise AdaptiveParseError("nominal attachment selected without owner span")
                self._queue_nominal_modifier(text, tokens, owner, span)
                spans.append(span)
                self._deterministic_trace(
                    "structural_attachment",
                    f"ATTACHMENT: {span.text}",
                    attachment_target.key,
                )
                continue
            if attachment_target is not None:
                self._deterministic_trace(
                    "structural_attachment",
                    f"ATTACHMENT: {span.text}",
                    attachment_target.key,
                )

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
                if role_whitelist is not None:
                    remaining_whitelist = {
                        item for item in role_whitelist
                        if item not in roles and item not in requested_roles
                    }
                    filtered_allowed = (
                        remaining_whitelist
                        if filtered_allowed is None
                        else filtered_allowed & remaining_whitelist
                    )
                role = self._classify_role(
                    text,
                    predicate,
                    span,
                    used_roles=roles,
                    forbidden_role=requested_roles if act_type == "QUERY" else None,
                    requested=False,
                    allowed_roles=filtered_allowed,
                )
                if role is None:
                    if self._is_registered_transition_cue(span):
                        spans.append(span)
                        continue
                    # The phrase was already selected as a semantically relevant
                    # actant candidate.  Failing to classify its role is therefore
                    # not evidence that the phrase is irrelevant.  Silently
                    # dropping it would permit a partial frame to reach canonical
                    # Integration (for example ``увидеть(Иван)`` after failing to
                    # classify ``Петра``).  Preserve the trust boundary: unresolved
                    # selected semantics fail closed instead of being omitted.
                    raise AdaptiveParseError(
                        f"selected actant role unresolved: {span.text}"
                    )
            spans.append(span)
            roles.add(role)
            actants.append(self._make_actant(role, span))

        # A weak model is allowed to stop actant enumeration, but it is not
        # allowed to make a structurally ambiguous attachment disappear.  Recheck
        # unconsumed phrase candidates through the ambiguity gate before accepting
        # the frame.
        remaining_candidates = self._candidate_phrase_spans(
            text, tokens, predicate_span, spans, requested_spans=requested_spans
        )
        for remaining in remaining_candidates:
            self._contextualize_nominal_span(text, predicate, remaining, tokens)
            attachment_target = self._resolve_modifier_attachment(
                text, tokens, predicate_span, predicate, remaining
            )
            if (
                attachment_target is not None
                and attachment_target.kind is _AttachmentTargetKind.NOMINAL
            ):
                owner = attachment_target.nominal_span
                if owner is None:
                    raise AdaptiveParseError("nominal attachment selected without owner span")
                self._queue_nominal_modifier(text, tokens, owner, remaining)
                spans.append(remaining)
                self._deterministic_trace(
                    "structural_attachment",
                    f"ATTACHMENT: {remaining.text}",
                    attachment_target.key,
                )
                continue
            if attachment_target is not None:
                allowed = self._deterministic_role_candidates(
                    tokens, predicate_span, predicate, remaining
                )
                if role_whitelist is not None:
                    allowed = tuple(role for role in allowed if role in role_whitelist)
                filtered = {item for item in allowed if item not in roles} if allowed else None
                if role_whitelist is not None:
                    remaining_whitelist = {
                        item for item in role_whitelist
                        if item not in roles and item not in requested_roles
                    }
                    filtered = (
                        remaining_whitelist
                        if filtered is None
                        else filtered & remaining_whitelist
                    )
                role = self._classify_role(
                    text,
                    predicate,
                    remaining,
                    used_roles=roles,
                    forbidden_role=requested_roles if act_type == "QUERY" else None,
                    requested=False,
                    allowed_roles=filtered,
                )
                if role is None and self._is_registered_transition_cue(remaining):
                    spans.append(remaining)
                    self._deterministic_trace(
                        "structural_attachment",
                        f"TRANSITION CUE: {remaining.text}",
                        RuntimeRoleCue.TRANSITION_OPERATOR.value,
                    )
                    continue
                if role is not None and role not in roles:
                    spans.append(remaining)
                    roles.add(role)
                    actants.append(self._make_actant(role, remaining))
                    self._deterministic_trace(
                        "structural_attachment",
                        f"ATTACHMENT: {remaining.text}",
                        attachment_target.key,
                    )

        if actant_iterations >= self.settings.max_actants_per_act:
            unconsumed = self._candidate_phrase_spans(
                text, tokens, predicate_span, spans, requested_spans=requested_spans
            )
            if unconsumed:
                raise AdaptiveParseError(
                    "incomplete parse: meaningful actant candidates remain after "
                    f"max_actants_per_act={self.settings.max_actants_per_act}: "
                    + " | ".join(item.text for item in unconsumed[:4])
                )

        actants = self._split_quantified_nominal_actants(text, actants)
        actants = self._fuse_quantified_duration_actants(text, actants)

        return tuple(actants), tuple(spans)

    def _split_quantified_nominal_actants(
        self,
        text: str,
        actants: list[ActantCandidate],
    ) -> list[ActantCandidate]:
        """Separate a leading quantity from a counted nominal participant.

        Candidate chunking intentionally keeps ``NUMR + nominal`` together so the
        noun phrase cannot be consumed as two competing participants.  Once the
        semantic role of that phrase is known, however, AH has a dedicated AMOUNT
        slot.  A counted participant such as ``three books`` therefore becomes
        OBJECT=books + AMOUNT=three, while a phrase already resolved as DURATION
        remains one duration value (``two hours``).

        The rule is morphological and role-generic: it contains no numeral, noun,
        predicate or acceptance-case vocabulary.  It only splits an initial run of
        NUMR/numeric tokens when the remaining source span still has a nominal head.
        """
        graph = self._candidate_graph
        if graph is None or any(item.role is ActantRole.AMOUNT for item in actants):
            return list(actants)

        non_split_roles = {
            ActantRole.AMOUNT, ActantRole.DURATION, ActantRole.TIME,
            ActantRole.CAUSE, ActantRole.PURPOSE, ActantRole.HOW_TO,
        }
        result = list(actants)
        for index, actant in enumerate(tuple(result)):
            if actant.role in non_split_roles or actant.evidence is None:
                continue
            if actant.evidence.start is None or actant.evidence.end is None:
                continue
            if (
                actant.candidate_ref is not None
                or actant.entity_ref is not None
                or actant.composition is not None
                or actant.proposition is not None
            ):
                continue

            phrase_tokens = [
                token for token in graph.tokens
                if token.start >= actant.evidence.start
                and token.end <= actant.evidence.end
                and re.search(r"\w", token.text)
            ]
            if len(phrase_tokens) < 2:
                continue

            quantity: list[object] = []
            for token in phrase_tokens:
                numeric_literal = bool(re.fullmatch(r"[+-]?(?:\d+(?:[.,]\d+)?)", token.text))
                is_numr = any(
                    info.pos == "NUMR"
                    for info in self._material_morph_analyses(
                        _SourceToken(token.index, token.text, token.start, token.end)
                    )
                )
                if numeric_literal or is_numr:
                    quantity.append(token)
                    continue
                break
            if not quantity or len(quantity) >= len(phrase_tokens):
                continue

            remainder = phrase_tokens[len(quantity):]
            remainder_span = self._resolve_span(
                text,
                tuple(_SourceToken(t.index, t.text, t.start, t.end) for t in graph.tokens),
                remainder[0].index,
                remainder[-1].index,
            )
            source_tokens = tuple(
                _SourceToken(t.index, t.text, t.start, t.end) for t in graph.tokens
            )
            if not self._span_has_nominal_head(remainder_span, source_tokens):
                continue
            amount_span = self._resolve_span(
                text, source_tokens, quantity[0].index, quantity[-1].index
            )
            participant = self._make_actant(actant.role, remainder_span)
            amount = self._make_actant(ActantRole.AMOUNT, amount_span)
            result[index] = participant
            result.append(amount)
            # One concrete N has one AMOUNT role.  If a sentence contains several
            # independently quantified participants, preserving them requires a
            # richer multi-frame representation rather than silently duplicating
            # the canonical role.  Stop after the first valid split.
            break
        return result

    @staticmethod
    def _fuse_quantified_duration_actants(
        text: str,
        actants: list[ActantCandidate],
    ) -> list[ActantCandidate]:
        """Fold an adjacent numeric AMOUNT into an already-resolved DURATION.

        The semantic distinction is made *before* this normalization: a counted
        entity remains OBJECT + AMOUNT, while an expression whose nominal head was
        independently classified as DURATION denotes one duration phrase.  Thus
        no duration-unit lexicon or ``NUMR+NOUN -> DURATION`` shortcut is needed.
        """
        result = list(actants)
        durations = [item for item in result if item.role is ActantRole.DURATION and item.evidence]
        # A numeric literal can arrive here as a generic/OBJECT actant when the
        # bounded role probe recognized the following nominal head as DURATION
        # but did not independently label the quantity as AMOUNT. Adjacency to
        # an already-resolved DURATION is sufficient to fold that literal into
        # the same phrase; no duration-unit vocabulary is involved.
        quantities = [
            item
            for item in result
            if item.evidence is not None
            and (
                item.role is ActantRole.AMOUNT
                or bool(
                    re.fullmatch(
                        r"[+-]?(?:\d+(?:[.,]\d+)?)",
                        item.evidence.text.strip(),
                    )
                )
            )
        ]
        for duration in durations:
            preceding = [
                quantity for quantity in quantities
                if quantity in result
                and quantity is not duration
                and quantity.evidence is not None
                and duration.evidence is not None
                and quantity.evidence.end <= duration.evidence.start
                and text[quantity.evidence.end:duration.evidence.start].strip() == ""
            ]
            if len(preceding) != 1:
                continue
            quantity = preceding[0]
            assert quantity.evidence is not None and duration.evidence is not None
            evidence = EvidenceSpan(
                text[quantity.evidence.start:duration.evidence.end],
                quantity.evidence.start,
                duration.evidence.end,
            )
            fused = replace(
                duration,
                mention=evidence.text,
                normalized_hint=None,
                evidence=evidence,
            )
            result[result.index(duration)] = fused
            result.remove(quantity)
        return result

    @staticmethod
    def _lexeme_analysis_profile(
        analyses: tuple[MorphInfo, ...] | list[MorphInfo],
        normal_form: str,
    ) -> str:
        """Render morphology evidence for one lexical candidate.

        A lexical A/B probe decides dictionary identity, not semantic role.  A bare
        lemma string can be underspecified for genuine homographs (for example an
        indeclinable proper-name reading versus an inflected proper name, or a
        short adjective versus a passive participle).  Expose only analyser facts
        already available for the observed surface form so the model can make the
        tiny contextual lexical decision without inventing a second morphology
        system.
        """
        selected = [
            item for item in analyses
            if item.normal_form.strip().casefold() == normal_form.strip().casefold()
        ]
        if not selected:
            return "no additional morphology evidence"

        def values(attr: str) -> str:
            found = sorted({
                str(getattr(item, attr))
                for item in selected
                if getattr(item, attr) is not None
            })
            return "/".join(found) if found else "-"

        marker_labels = {
            "Name": "personal-name",
            "Surn": "surname",
            "Patr": "patronymic",
            "Geox": "geographic-name",
            "Orgn": "organization-name",
            "Abbr": "abbreviation",
            "Fixd": "indeclinable",
            "pssv": "passive",
            "Qual": "qualitative",
            "Apro": "pronominal",
            "Anph": "anaphoric",
            "past": "past",
            "pres": "present",
            "futr": "future",
        }
        markers = sorted({
            marker_labels[tag]
            for item in selected
            for tag in item.grammemes
            if tag in marker_labels
        })
        parts = [
            f"POS={values('pos')}",
            f"CASE={values('case')}",
            f"NUMBER={values('number')}",
            f"GENDER={values('gender')}",
        ]
        if markers:
            parts.append("FEATURES=" + ",".join(markers))
        return "; ".join(parts)

    def _contextualize_nominal_span(
        self,
        text: str,
        predicate: PredicateCandidate,
        span: _Span,
        tokens: tuple[_SourceToken, ...],
    ) -> None:
        """Narrow genuine lexical homonymy before role/identity consumption.

        This is not a morphology-score repair and contains no word-specific rules.
        If one selected surface token has exactly two materially plausible nominal
        lexemes, the model performs only the bounded lexical decision A/B.  Python
        then keeps analyses of the selected lexeme; case/number/etc. remain
        deterministic morphology evidence.  More-than-binary lexical ambiguity
        fails closed rather than being collapsed by analyser order.
        """
        for index in range(span.start_index, span.end_index + 1):
            token = tokens[index - 1]
            if token.index in self._contextual_nominal_lemmas:
                continue
            recovery = self._lexical_recovery_for_token(token)
            if (
                recovery is not None
                and recovery.status is LexicalRecoveryStatus.UNKNOWN_TOKEN
            ):
                # Lexical Recovery intentionally protected this surface as an
                # unknown name/term/code. Productive morphology may still provide
                # useful case/POS hypotheses, but it must not reopen lexical identity
                # and force the bounded lexeme probe to choose a dictionary lemma.
                continue
            analyses = self._material_morph_analyses(token, apply_context=False)
            forms: dict[str, str] = {}
            for info in analyses:
                if info.pos not in {"NOUN", "NPRO"} or not info.normal_form.strip():
                    continue
                key = info.normal_form.strip().casefold()
                forms.setdefault(key, info.normal_form.strip())
            if len(forms) <= 1:
                continue
            ordered = [forms[key] for key in sorted(forms)]
            if len(ordered) != 2:
                raise AdaptiveParseError(
                    f"nominal lexical ambiguity is not binary: {token.text} -> "
                    + ", ".join(ordered)
                )
            chosen = self._resolve_binary_lexeme_hypotheses(
                text=text,
                target=token.text,
                candidates=(ordered[0], ordered[1]),
                analyses=analyses,
                predicate_surface=predicate.surface,
            )
            self._contextual_nominal_lemmas[token.index] = chosen.casefold()

    def _resolve_binary_lexeme_hypotheses(
        self,
        *,
        text: str,
        target: str,
        candidates: tuple[str, str],
        analyses: tuple[MorphInfo, ...] | list[MorphInfo],
        predicate_surface: str | None = None,
    ) -> str:
        """Resolve binary lexical identity by mirrored comparative A/B probes.

        Each orientation asks the same comparative question with candidates swapped.
        A lexical winner is accepted only when both probes select the same lemma.
        This avoids two independent YES/NO hypotheses and prevents option position
        from becoming the hidden deciding signal.
        """
        a, b = candidates

        def choose(first: str, second: str) -> str:
            lines = [f"TEXT:\n{text}"]
            if predicate_surface:
                lines.append(f"PREDICATE:\n{predicate_surface}")
            lines.extend(
                [
                    f"TARGET:\n{target}",
                    f"A LEMMA:\n{first}",
                    f"A MORPHOLOGY:\n{self._lexeme_analysis_profile(analyses, first)}",
                    f"B LEMMA:\n{second}",
                    f"B MORPHOLOGY:\n{self._lexeme_analysis_profile(analyses, second)}",
                    "QUESTION:\nWhich dictionary lemma is TARGET using in TEXT? "
                    "Use the meaning of the whole sentence and TARGET's surrounding complements/modifiers "
                    "to identify the lexeme. Decide lexical identity only; do not assign semantic roles.",
                    "CHOICES:\nA\nB",
                ]
            )
            decision, _ = self._exact_choice_probe(
                "lexeme_comparison", "\n".join(lines), ("A", "B")
            )
            return first if decision == "A" else second

        winner_ab = choose(a, b)
        winner_ba = choose(b, a)
        if winner_ab == winner_ba:
            return winner_ab

        # Some local generators exhibit a pure option-position bias on A/B even
        # when the lexical decision itself is easy (e.g. ``Петру`` -> ``Пётр`` or
        # ``стоит`` -> ``стоять``).  Mirroring detects that failure correctly, but
        # aborting the whole sentence throws away otherwise valid structure.  Use
        # one position-free, bounded fallback: ask for the source-language lemma
        # directly and accept it only when deterministic validation maps it to
        # exactly one of the two morphology candidates.  No canonical UID or AH
        # identity is exposed to the model, and an out-of-set answer still fails
        # closed.
        candidate_by_key: dict[str, str] = {}
        for candidate in candidates:
            key = candidate.strip().casefold().replace("ё", "е")
            if key in candidate_by_key:
                raise AdaptiveParseError(
                    "lexeme candidates collapse under orthographic normalization: "
                    + ", ".join(candidates)
                )
            candidate_by_key[key] = candidate

        lines = [f"TEXT:\n{text}"]
        if predicate_surface:
            lines.append(f"PREDICATE:\n{predicate_surface}")
        lines.extend(
            [
                f"TARGET:\n{target}",
                "ALLOWED LEMMAS:\n" + "\n".join(candidates),
                "QUESTION:\nWrite exactly the one allowed dictionary lemma that TARGET uses in TEXT.",
            ]
        )

        def validate_literal(raw: str) -> str:
            value = self._scalar(raw)
            key = value.casefold().replace("ё", "е")
            if key not in candidate_by_key:
                raise AdaptiveParseError(
                    "expected one of the known lexical lemmas: " + ", ".join(candidates)
                )
            return candidate_by_key[key]

        try:
            return self._probe(
                "lexeme_identity",
                "\n".join(lines),
                validate_literal,
                max_new_tokens=8,
            )
        except AdaptiveParseError as exc:
            raise AdaptiveParseError(
                "mirrored lexical comparison is order-sensitive and literal lexical "
                "fallback did not resolve it: " + ", ".join(candidates)
            ) from exc

    def _grammatical_number_for_span(
        self, span: _Span, *, role: ActantRole | None = None
    ) -> str | None:
        """Return stable source-head singular/plural morphology when available.

        Canonical lookup may lemmatize ``письма`` to ``письмо`` or ``матросы`` to
        ``матрос``. Number must therefore be captured from the source head before
        lemmatization. Case supplied by an already known semantic core role can
        narrow syncretic readings; otherwise the value is accepted only when all
        material readings of the head agree.
        """
        graph = self._candidate_graph
        if graph is None:
            return None
        tokens = [
            graph.token(i)
            for i in range(span.start_index, span.end_index + 1)
            if re.search(r"\w", graph.token(i).text)
        ]
        if not tokens:
            return None
        if (
            len(tokens) >= 3
            and tokens[0].text.casefold() in _SPATIAL_RELATION_ADVERBS
            and tokens[1].text.casefold() == "с"
        ):
            tokens = tokens[2:]
        elif tokens and tokens[0].has_pos("PREP"):
            tokens = tokens[1:]
        if not tokens:
            return None

        head: _SourceToken | None = None
        for token in tokens:
            infos = self._morph_all(token)
            if any(info.pos in {"NOUN", "NPRO"} for info in infos):
                head = token
                break
        if head is None:
            return None
        all_head_infos = self._morph_all(head)
        infos = tuple(
            info for info in all_head_infos
            if info.pos in {"NOUN", "NPRO"} and info.number in {"sing", "plur"}
        )
        selected_lemma = self._contextual_nominal_lemmas.get(head.index)
        if selected_lemma is None:
            stable = stable_normal_form(all_head_infos, poses={"NOUN", "NPRO"})
            selected_lemma = stable.casefold() if stable else None
        if selected_lemma is not None:
            lexical = tuple(
                info for info in infos
                if info.normal_form.strip().casefold() == selected_lemma
            )
            if lexical:
                infos = lexical
        case_hint = {
            ActantRole.SUBJECT: "nomn",
            ActantRole.OBJECT: "accs",
        }.get(role)
        if case_hint is not None:
            narrowed = tuple(info for info in infos if info.case == case_hint)
            if narrowed:
                infos = narrowed
        numbers = {
            str(info.number)
            for info in infos
            if info.number is not None and str(info.number) in {"sing", "plur"}
        }
        return next(iter(numbers)) if len(numbers) == 1 else None

    def _make_actant(self, role: ActantRole, span: _Span) -> ActantCandidate:
        composition = self._composition_for_span(span)
        # TIME/DURATION have already been selected semantically. Their full source
        # expressions are values, not entities identified by a nominal head:
        # head reduction would collapse distinct instants or measures.  Keep the
        # whole-phrase lookup and source evidence; do not infer roles from words.
        nominal_relations = (
            () if role in {ActantRole.TIME, ActantRole.DURATION}
            else self._nominal_relations_for_span(span, role=role)
        )
        mention, normalized_hint = self._semantic_actant_text(span, role=role)
        if role in {ActantRole.TIME, ActantRole.DURATION}:
            # TemporalNormalizer consumes the exact semantic phrase after the
            # governing preposition has been removed.  If the phrase is not one of
            # its deterministic forms, canonical identity must still preserve that
            # phrase instead of replacing it with a generic noun lemma.
            normalized_hint = None
        # A structurally decomposed NP must resolve the actant identity from its
        # nominal head, not from the whole source phrase.  The full source mention
        # remains evidence, while internal possessive/genitive structure is carried
        # separately and canonicalized by Integration.
        if nominal_relations:
            head_hint = nominal_relations[0].head_normalized_hint
            if head_hint:
                normalized_hint = head_hint
        return ActantCandidate(
            role=role,
            mention=mention,
            normalized_hint=normalized_hint,
            evidence=span.evidence,
            composition=composition,
            nominal_relations=nominal_relations,
            grammatical_number=self._grammatical_number_for_span(span, role=role),
        )

    _FIRST_POSSESSIVE_FORMS = frozenset({
        "мой", "моя", "моё", "мое", "мои", "моего", "моей",
        "моему", "моим", "моими", "моих", "мою",
    })
    _SECOND_POSSESSIVE_FORMS = frozenset({
        "твой", "твоя", "твоё", "твое", "твои", "твоего", "твоей",
        "твоему", "твоим", "твоими", "твоих", "твою",
    })

    def _nominal_relations_for_span(
        self, span: _Span, *, role: ActantRole | None = None
    ) -> tuple[NominalRelationCandidate, ...]:
        """Extract source-grounded structure internal to one NP.

        Canonical entity identity follows the substantive nominal head rather than
        the whole surface description.  Internal source structure is preserved as
        typed relations:

        - explicit possessive morphology -> ``POSSESSOR``;
        - post-head genitive nominal dependency -> ``GENITIVE_DEP``;
        - attributive adjective/participle/number -> ``NOMINAL_MODIFIER``.

        ``NOMINAL_MODIFIER`` is deliberately weak.  It records that a modifier was
        asserted inside this NP but does not reinterpret ``керосиновая`` as
        MATERIAL, ``разбухшая`` as a historical event, or ``старая`` as any other
        stronger predicate.  Such semantic specialization, if needed, belongs to a
        separate bounded decision.
        """
        graph = self._candidate_graph
        if graph is None:
            return ()
        tokens = [
            graph.token(i) for i in range(span.start_index, span.end_index + 1)
            if re.search(r"\w", graph.token(i).text)
        ]
        if not tokens:
            return ()

        # Strip only external event governors.  They describe the event-to-NP
        # relation and therefore are not part of the NP's internal structure.
        if (
            len(tokens) >= 3
            and tokens[0].text.casefold() in _SPATIAL_RELATION_ADVERBS
            and tokens[1].text.casefold() == "с"
        ):
            tokens = tokens[2:]
        elif tokens and tokens[0].has_pos("PREP"):
            tokens = tokens[1:]
        if not tokens:
            return ()

        def preserve_case(token: _SourceToken, value: str | None) -> str | None:
            if value is not None and token.text[:1].isupper():
                return value[:1].upper() + value[1:]
            return value

        def nominal_form(
            token: _SourceToken, *, role_hint: ActantRole | None = None
        ) -> str | None:
            analyses = self._morph_all(token)
            case_hint = {
                ActantRole.SUBJECT: "nomn",
                ActantRole.OBJECT: "accs",
            }.get(role_hint)
            # Quantified NPs can govern a non-nominative head even when the whole
            # phrase is SUBJECT (``несколько матросов``). Do not let the semantic
            # role force a surname-like NOM.SG homograph over the lexical noun.
            try:
                token_position = tokens.index(token)
            except ValueError:
                token_position = 0
            quantified = any(
                any(info.pos == "NUMR" for info in self._morph_all(previous))
                for previous in tokens[:token_position]
            )
            if case_hint is not None and not quantified:
                forms = {
                    item.normal_form.strip().casefold(): item.normal_form.strip()
                    for item in analyses
                    if item.pos in {"NOUN", "NPRO"}
                    and item.case == case_hint
                    and item.normal_form.strip()
                }
                if len(forms) == 1:
                    return preserve_case(token, next(iter(forms.values())))
            return preserve_case(
                token, stable_normal_form(analyses, poses={"NOUN", "NPRO"})
            )

        def modifier_form(token: _SourceToken) -> str | None:
            # Attributive modifiers are lexical descriptors, not proper-name
            # identities. Sentence-initial capitalization must therefore not turn
            # ``Сухая`` into a distinct canonical descriptor from ``сухая``.
            return stable_normal_form(
                self._morph_all(token), poses={"ADJF", "PRTF", "NUMR"}
            )

        def relation_evidence(left: _SourceToken, right: _SourceToken) -> EvidenceSpan:
            start = min(left.start, right.start)
            end = max(left.end, right.end)
            return EvidenceSpan(graph.text[start:end], start, end)

        possessive_forms = {
            item.replace("ё", "е")
            for item in self._FIRST_POSSESSIVE_FORMS | self._SECOND_POSSESSIVE_FORMS
        }

        # Find the first substantive head.  A token with a possessive-adjective
        # reading is a modifier when a real noun follows inside this established NP.
        head_pos: int | None = None
        for pos, token in enumerate(tokens):
            if self._has_structural_morph(token, poses={"NOUN"}):
                head_pos = pos
                break
            if self._has_structural_morph(token, poses={"NPRO"}):
                if self._is_postnominal_possessive_anaphor(token) and any(
                    self._has_structural_morph(other, poses={"NOUN"})
                    for other in tokens[pos + 1:]
                ):
                    continue
                head_pos = pos
                break
        if head_pos is None:
            return ()

        head_token = tokens[head_pos]
        main_head_form = nominal_form(head_token, role_hint=role)
        main_head_mention = head_token.text
        relations: list[NominalRelationCandidate] = []

        # Pre-head attributes are part of the description of the nominal head.
        # First/second-person possessive adjectives are semantically explicit;
        # ordinary attributes stay at the weak NOMINAL_MODIFIER level.  A token
        # that also has a material NPRO reading is deliberately not swallowed as a
        # normal pre-head modifier, preserving the conservative boundary used by
        # _nominal_phrase_end for third-person forms.
        for modifier in tokens[:head_pos]:
            folded = modifier.text.casefold().replace("ё", "е")
            if folded in possessive_forms:
                relations.append(
                    NominalRelationCandidate(
                        NominalRelationKind.POSSESSOR,
                        head_mention=main_head_mention,
                        head_normalized_hint=main_head_form,
                        dependent_mention=modifier.text,
                        dependent_normalized_hint=None,
                        evidence=relation_evidence(modifier, head_token),
                    )
                )
                continue
            if self._has_structural_morph(modifier, poses={"NPRO"}):
                continue
            if self._has_morph(modifier, poses={"ADJF", "PRTF", "NUMR"}):
                relations.append(
                    NominalRelationCandidate(
                        NominalRelationKind.NOMINAL_MODIFIER,
                        head_mention=main_head_mention,
                        head_normalized_hint=main_head_form,
                        dependent_mention=modifier.text,
                        dependent_normalized_hint=modifier_form(modifier),
                        evidence=relation_evidence(modifier, head_token),
                    )
                )

        current_head_token = head_token
        current_head_form = main_head_form
        current_head_mention = main_head_mention
        cursor = head_pos + 1
        genitive_family = {"gent", "gen1", "gen2"}
        while cursor < len(tokens):
            token = tokens[cursor]
            folded = token.text.casefold().replace("ё", "е")
            if (
                self._is_postnominal_possessive_anaphor(token)
                or folded in possessive_forms
            ):
                relations.append(
                    NominalRelationCandidate(
                        NominalRelationKind.POSSESSOR,
                        head_mention=current_head_mention,
                        head_normalized_hint=current_head_form,
                        dependent_mention=token.text,
                        dependent_normalized_hint=None,
                        evidence=relation_evidence(current_head_token, token),
                    )
                )
                cursor += 1
                continue

            # A genitive dependent may itself have attributive modifiers:
            # ``нижний ящик письменного стола`` -> modifier(ящик, нижний),
            # genitive(ящик, стол), modifier(стол, письменный).
            dep_start = cursor
            while cursor < len(tokens) and self._has_morph(
                tokens[cursor], poses={"ADJF", "PRTF", "NUMR"}
            ):
                if self._has_structural_morph(tokens[cursor], poses={"NPRO"}):
                    break
                cursor += 1
            if cursor >= len(tokens):
                break
            dep_head = tokens[cursor]
            cases = self._structural_nominal_cases(dep_head)
            if (
                not cases
                or not (cases & genitive_family)
                or not self._has_morph(dep_head, poses={"NOUN", "NPRO"})
            ):
                break
            quantified_prefix = any(
                self._has_morph(item, poses={"NUMR"})
                or bool(re.fullmatch(r"[+-]?(?:\d+(?:[.,]\d+)?)", item.text))
                for item in tokens[dep_start:cursor]
            )
            if (
                (not cases.issubset(genitive_family) or quantified_prefix)
                and not self._ambiguous_genitive_dependency(
                    tuple(graph.tokens),
                    current_head_token.index,
                    tokens[dep_start].index,
                    dep_head.index,
                )
            ):
                break
            dep_form = nominal_form(dep_head)
            dep_mention = self._semantic_token_range_text(
                self._source_tokens_from_graph(graph),
                tokens[dep_start].index,
                dep_head.index,
            )
            relations.append(
                NominalRelationCandidate(
                    NominalRelationKind.GENITIVE_DEP,
                    head_mention=current_head_mention,
                    head_normalized_hint=current_head_form,
                    dependent_mention=dep_mention,
                    dependent_normalized_hint=dep_form,
                    evidence=relation_evidence(current_head_token, dep_head),
                )
            )
            for modifier in tokens[dep_start:cursor]:
                if self._has_structural_morph(modifier, poses={"NPRO"}):
                    continue
                relations.append(
                    NominalRelationCandidate(
                        NominalRelationKind.NOMINAL_MODIFIER,
                        head_mention=dep_head.text,
                        head_normalized_hint=dep_form,
                        dependent_mention=modifier.text,
                        dependent_normalized_hint=modifier_form(modifier),
                        evidence=relation_evidence(modifier, dep_head),
                    )
                )

            # Preserve nested genitive chains, e.g. ``дверь дома брата``.
            current_head_token = dep_head
            current_head_form = dep_form
            current_head_mention = dep_head.text
            cursor += 1

        return tuple(relations)

    def _semantic_actant_text(
        self, span: _Span, *, role: ActantRole | None = None
    ) -> tuple[str, str | None]:
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
        governed_by_preposition = bool(tokens and tokens[0].has_pos("PREP"))
        if (
            len(tokens) >= 3
            and tokens[0].text.casefold() in _SPATIAL_RELATION_ADVERBS
            and tokens[1].text.casefold() == "с"
        ):
            governed_by_preposition = True
            tokens = tokens[2:]
        elif tokens[0].has_pos("PREP"):
            tokens = tokens[1:]
        if not tokens:
            return span.text, None
        mention = self._semantic_token_range_text(
            self._source_tokens_from_graph(graph),
            tokens[0].index,
            tokens[-1].index,
        )
        normalized_hint: str | None = None
        if len(tokens) == 1:
            # Lexical identity, once contextually selected, is monotonic.  Do not
            # reopen the same homonymy through an independent stable-normal-form
            # utility after role classification; that can silently replace the
            # accepted lemma before entity lookup/Integration.
            chosen = self._contextual_nominal_lemmas.get(tokens[0].index)
            if chosen is not None:
                selected_forms = [
                    info.normal_form.strip()
                    for info in self._morph_all(tokens[0])
                    if info.pos in {"NOUN", "NPRO"}
                    and info.normal_form.strip().casefold() == chosen
                ]
                normalized_hint = selected_forms[0] if selected_forms else chosen
            else:
                normalized_hint = None
                # Role assignment and lexical identity are separate decisions, but
                # once a semantic core role is known it can disambiguate a *bare*
                # Russian case-syncretic nominal.  Use all dictionary readings here
                # (not only high-score material ones): analyser probability must not
                # override a grammatically required accusative/nominative reading.
                # Prepositional arguments are excluded because their surface case
                # is governed by the preposition rather than by SUBJECT/OBJECT.
                case_hint = {
                    ActantRole.SUBJECT: "nomn",
                    ActantRole.OBJECT: "accs",
                }.get(role)
                if case_hint is not None and not governed_by_preposition:
                    case_forms = {
                        info.normal_form.strip().casefold(): info.normal_form.strip()
                        for info in self._morph_all(tokens[0])
                        if info.pos in {"NOUN", "NPRO"}
                        and info.case == case_hint
                        and info.normal_form.strip()
                    }
                    if len(case_forms) == 1:
                        normalized_hint = next(iter(case_forms.values()))
                if normalized_hint is None:
                    normalized_hint = stable_normal_form(
                        self._morph_all(tokens[0]), poses={"NOUN", "NPRO"}
                    )
            if normalized_hint is not None and tokens[0].text[:1].isupper():
                normalized_hint = normalized_hint[:1].upper() + normalized_hint[1:]
        return mention, normalized_hint

    def _composition_for_span(self, span: _Span) -> ActantCompositionCandidate | None:
        runtime = self._runtime_compositions.get((span.start_index, span.end_index))
        if runtime is not None:
            operator, member_spans = runtime
            composition_operator = (
                CompositionOperator.AND
                if operator is CoordinationKind.AND
                else CompositionOperator.OR
            )
            members = tuple(
                CompositionMemberCandidate(
                    mention=self._semantic_actant_text(member)[0],
                    normalized_hint=self._semantic_actant_text(member)[1],
                    evidence=member.evidence,
                )
                for member in member_spans
            )
            return ActantCompositionCandidate(operator=composition_operator, members=members)

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

    def _is_postnominal_possessive_anaphor(self, token: _SourceToken) -> bool:
        """Whether a token can be a postnominal possessive pronoun modifier.

        Russian ``его/её/их`` receive both personal-pronoun and indeclinable
        possessive-adjective analyses. Before a noun they must remain available as
        independent participants (``увидел его друга`` is genuinely ambiguous at
        the lexical level), but immediately *after an already established nominal
        head* an anaphoric possessive-adjective reading is structural evidence for
        a possessive NP such as ``решение его``.

        Current pymorphy exposes the indeclinable possessive reading as the
        combined ``Apro+Anph+Fixd`` adjective signature.  ``Subx`` alone is *not*
        sufficient: demonstrative/correlative forms can also be substantivized and
        anaphoric (for example the first ``то`` in ``то дрожала, то замирала``).
        Requiring the indeclinable marker keeps those discourse particles outside
        the preceding NP without consulting a surface-word list.
        """
        return any(
            info.pos == "ADJF"
            and {"Anph", "Apro", "Fixd"} <= set(info.grammemes)
            for info in self._morph_all(token)
        )

    def _ambiguous_genitive_dependency(
        self,
        tokens: tuple[_SourceToken, ...],
        head_index: int,
        dependent_start_index: int,
        dependent_index: int,
    ) -> bool:
        """Resolve one structurally ambiguous post-head nominal attachment.

        Dictionary case alone cannot decide a case-syncretic N+N boundary.  A
        post-head quantified phrase is ambiguous for a second, independent reason:
        it may be a dependent constituent of the noun or a separate event measure.
        Python exposes exactly those two local structures and a bounded probe
        returns GENITIVE_DEP or SEPARATE.  The decision is cached for the source
        span and never sees AH state or canonical UIDs.
        """
        key = (head_index, dependent_start_index, dependent_index)
        cached = self._genitive_attachment_cache.get(key)
        if cached is not None:
            return cached
        graph = self._candidate_graph
        if graph is None:
            return False
        head = graph.token(head_index)
        dependent_start = graph.token(dependent_start_index)
        dependent = graph.token(dependent_index)
        dependent_phrase = self._semantic_token_range_text(
            self._source_tokens_from_graph(graph),
            dependent_start.index,
            dependent.index,
        )
        prompt = (
            f"TEXT:\n{graph.text}\n"
            f"HEAD NOMINAL:\n{head.text}\n"
            f"FOLLOWING PHRASE:\n{dependent_phrase}\n"
            "QUESTION:\nIn this exact text, is FOLLOWING PHRASE a genitive "
            "dependent inside the same noun phrase headed by HEAD NOMINAL, or is "
            "it a separate event participant, measure, or adjunct?\n"
            "CHOICES:\nGENITIVE_DEP\nSEPARATE\nUNCLEAR"
        )
        decision, _margin = self._exact_choice_probe(
            "nominal_genitive_attachment",
            prompt,
            ("GENITIVE_DEP", "SEPARATE", "UNCLEAR"),
        )
        value = decision == "GENITIVE_DEP"
        self._genitive_attachment_cache[key] = value
        return value

    def _postnominal_possessive_belongs_to_np(
        self,
        tokens: tuple[_SourceToken, ...],
        start: int,
        end: int,
        pronoun_index: int,
        limit: int,
    ) -> bool:
        """Disambiguate possessive-modifier vs participant only when both fit.

        ``торжество его было...`` has no plausible transitive argument slot for
        the postnominal anaphor and remains deterministic possession. In a source
        like ``решение его удивило`` / ``падение ... его испугало`` both readings
        are structurally possible, so one tiny source-only probe decides whether
        the token stays inside the NP. UNCLEAR conservatively leaves it separate.
        """
        # If no following finite transitive predicate exists before a strong
        # boundary, the personal-pronoun reading has no local predicate argument
        # host and the explicit possessive morphology is sufficient.
        transitive_head: _SourceToken | None = None
        for index in range(pronoun_index + 1, limit + 1):
            token = tokens[index - 1]
            if token.text in _STRONG_BOUNDARY:
                break
            analyses = self._morph_all(token)
            finite = any(info.pos == "VERB" for info in analyses)
            if finite and stable_transitivity(analyses) == "tran":
                transitive_head = token
                break
        if transitive_head is None:
            return True

        key = (start, end, pronoun_index)
        cached = self._postnominal_possessive_cache.get(key)
        if cached is not None:
            return cached
        graph = self._candidate_graph
        if graph is None:
            return False
        phrase = self._semantic_token_range_text(tokens, start, end)
        pronoun = tokens[pronoun_index - 1]
        prompt = (
            f"TEXT:\n{graph.text}\n"
            f"CURRENT NOUN PHRASE:\n{phrase}\n"
            f"ANAPHORIC FORM:\n{pronoun.text}\n"
            f"FOLLOWING PREDICATE:\n{transitive_head.text}\n"
            "QUESTION:\nIn this exact text, does ANAPHORIC FORM possessively modify "
            "CURRENT NOUN PHRASE, or is it a separate participant of the following "
            "predicate?\n"
            "CHOICES:\nPOSSESSOR\nSEPARATE_PARTICIPANT\nUNCLEAR"
        )
        decision, _margin = self._exact_choice_probe(
            "postnominal_possessive_attachment",
            prompt,
            ("POSSESSOR", "SEPARATE_PARTICIPANT", "UNCLEAR"),
        )
        value = decision == "POSSESSOR"
        self._postnominal_possessive_cache[key] = value
        return value

    def _nominal_phrase_end(
        self,
        tokens: tuple[_SourceToken, ...],
        start: int,
        limit: int,
        blocked: set[int],
    ) -> int | None:
        """Return the end of one conservative NP beginning at ``start``.

        The chunker keeps adjective/participle/number modifiers with their nominal
        head and admits recursively extended genitive dependents only when their
        material case evidence is confined to the genitive family.  This preserves
        the old fail-safe against DAT/ACC syncretism while handling phrases such as
        ``центр большого города`` instead of splitting ``города`` into a fake
        independent actant.
        """
        if start > limit or start in blocked:
            return None
        cursor = start
        while cursor <= limit and cursor not in blocked and self._has_morph(
            tokens[cursor - 1], poses={"ADJF", "PRTF", "NUMR"}
        ):
            # A personal pronoun may also receive a possessive-adjective reading
            # from morphology (notably Russian ``его/её/их``).  When a material
            # NPRO reading exists, do not swallow it as an NP modifier of the
            # following noun: ``отправил его Марии`` contains two participants.
            if self._has_structural_morph(tokens[cursor - 1], poses={"NPRO"}):
                break
            cursor += 1
        if cursor > limit or cursor in blocked or not self._has_morph(
            tokens[cursor - 1], poses={"NOUN", "NPRO"}
        ):
            return None
        end = cursor
        # Pronoun heads do not absorb following nominals; this preserves distinct
        # participants in case-syncretic sequences such as ``его Марии``.
        if not self._has_structural_morph(tokens[cursor - 1], poses={"NOUN"}):
            return end

        genitive_family = {"gent", "gen1", "gen2"}
        cursor += 1
        while cursor <= limit and cursor not in blocked:
            # A postnominal possessive anaphor belongs to the NP even though the
            # same surface also has an NPRO reading. This special handling is
            # intentionally position-sensitive; pre-head NPRO forms keep the
            # conservative participant boundary above.
            if self._is_postnominal_possessive_anaphor(tokens[cursor - 1]):
                if not self._postnominal_possessive_belongs_to_np(
                    tokens, start, end, cursor, limit
                ):
                    break
                end = cursor
                cursor += 1
                continue
            modifier_start = cursor
            while cursor <= limit and cursor not in blocked and self._has_morph(
                tokens[cursor - 1], poses={"ADJF", "PRTF", "NUMR"}
            ):
                if self._has_structural_morph(tokens[cursor - 1], poses={"NPRO"}):
                    break
                cursor += 1
            if cursor > limit or cursor in blocked:
                break
            nominal_cases = self._structural_nominal_cases(tokens[cursor - 1])
            if not nominal_cases or not (nominal_cases & genitive_family):
                break
            if not self._has_morph(tokens[cursor - 1], poses={"NOUN", "NPRO"}):
                break
            quantified_prefix = any(
                self._has_morph(tokens[index - 1], poses={"NUMR"})
                or bool(
                    re.fullmatch(
                        r"[+-]?(?:\d+(?:[.,]\d+)?)",
                        tokens[index - 1].text,
                    )
                )
                for index in range(modifier_start, cursor)
            )
            if not nominal_cases.issubset(genitive_family) or quantified_prefix:
                # Case syncretism and post-head quantified phrases both leave two
                # valid local boundaries.  Ask only for that boundary instead of
                # swallowing an arbitrary neighbouring argument.
                head_index = end
                if not self._ambiguous_genitive_dependency(
                    tokens, head_index, modifier_start, cursor
                ):
                    break
            end = cursor
            cursor += 1
            if modifier_start == cursor:
                break
        return end

    def _prepositional_member_end(
        self,
        tokens: tuple[_SourceToken, ...],
        start: int,
        limit: int,
        blocked: set[int],
        *,
        inherited_preposition: bool = False,
    ) -> int | None:
        cursor = start
        if not inherited_preposition:
            if cursor > limit or not self._has_morph(tokens[cursor - 1], poses={"PREP"}):
                return None
            cursor += 1
        end = self._nominal_phrase_end(tokens, cursor, limit, blocked)
        if end is not None:
            return end
        # Source-denoting adverbial complements remain legal PP fillers even when
        # morphology does not expose a nominal head. Keep the old conservative
        # fallback to one content token rather than swallowing a whole clause.
        if cursor <= limit and cursor not in blocked and self._is_word_token(tokens[cursor - 1]):
            return cursor
        return None

    def _candidate_phrase_spans(
        self,
        text: str,
        tokens: tuple[_SourceToken, ...],
        predicate: _Span | None,
        selected: list[_Span],
        *,
        requested_spans: tuple[_Span, ...] = (),
    ) -> tuple[_Span, ...]:
        clause_start, clause_end = self._predicate_argument_bounds(predicate, tokens)
        blocked: set[int] = set(getattr(self, "_nominal_linker_tokens", set()))
        blocked.update(getattr(self, "_runtime_blocked_token_indices", set()))
        if predicate is not None:
            blocked.update(range(predicate.start_index, predicate.end_index + 1))
        for requested_span in requested_spans:
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
            reclaimed_predicate_positions = set(
                getattr(self, "_runtime_reclaimed_predicate_indices", set())
            )
            for head in self._candidate_graph.predicates:
                if (
                    head.token_index not in current_predicate_positions
                    and head.token_index not in reclaimed_predicate_positions
                ):
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

            # Relational spatial adverb + its PP complement is one modifier
            # phrase.  Its semantic role is still decided later; chunking only
            # prevents ``рядом`` and ``с журналом`` from becoming unrelated actants.
            if (
                low in _SPATIAL_RELATION_ADVERBS
                and index + 2 <= clause_end
                and tokens[index].text.casefold() == "с"
                and self._has_morph(tokens[index], poses={"PREP"})
            ):
                end = self._prepositional_member_end(
                    tokens, index + 1, clause_end, blocked
                )
                if end is not None and end >= index + 2:
                    span = self._resolve_span(text, tokens, index, end)
                    result.append(span)
                    consumed.update(range(index, end + 1))
                    index = end + 1
                    continue

            if self._has_morph(token, poses={"PREP"}):
                first_end = self._prepositional_member_end(
                    tokens, index, clause_end, blocked
                )
                if first_end is not None and first_end > index:
                    members = [self._resolve_span(text, tokens, index, first_end)]
                    operator: CoordinationKind | None = None
                    end = first_end
                    cursor = end + 1
                    while cursor <= clause_end:
                        if cursor in blocked:
                            break
                        low_coord = tokens[cursor - 1].text.casefold()
                        if low_coord not in {"и", "или", "либо"}:
                            break
                        current_operator = (
                            CoordinationKind.OR
                            if low_coord in {"или", "либо"}
                            else CoordinationKind.AND
                        )
                        if operator is not None and current_operator is not operator:
                            break
                        member_start = cursor + 1
                        if member_start > clause_end or member_start in blocked:
                            break
                        has_prep = self._has_morph(tokens[member_start - 1], poses={"PREP"})
                        member_end = self._prepositional_member_end(
                            tokens, member_start, clause_end, blocked,
                            inherited_preposition=not has_prep,
                        )
                        if member_end is None:
                            break
                        operator = current_operator
                        members.append(self._resolve_span(text, tokens, member_start, member_end))
                        end = member_end
                        cursor = end + 1
                    span = self._resolve_span(text, tokens, index, end)
                    if len(members) >= 2 and operator is not None:
                        self._runtime_compositions[(span.start_index, span.end_index)] = (
                            operator, tuple(members)
                        )
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
                end = self._nominal_phrase_end(tokens, start, clause_end, blocked)
                if end is None:
                    end = index
                span = self._resolve_span(text, tokens, start, end)
                if not any(span.overlaps(old) for old in result):
                    result.append(span)
                    consumed.update(range(start, end + 1))
                index = max(index + 1, end + 1)
                continue

            # A nominal modifier/quantifier that precedes its head belongs to the
            # same NP.  Starting it as a singleton first would permanently consume
            # the token and split ``два часа`` / ``красную книгу`` into competing
            # actants on the next iteration.
            if self._has_morph(token, poses={"ADJF", "PRTF", "NUMR"}):
                nominal_end = self._nominal_phrase_end(tokens, index, clause_end, blocked)
                if nominal_end is not None and nominal_end > index:
                    span = self._resolve_span(text, tokens, index, nominal_end)
                    result.append(span)
                    consumed.update(range(index, nominal_end + 1))
                    index = nominal_end + 1
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

    def _is_modifier_phrase(
        self, span: _Span, tokens: tuple[_SourceToken, ...]
    ) -> bool:
        words = [
            tokens[i - 1]
            for i in range(span.start_index, span.end_index + 1)
            if self._is_word_token(tokens[i - 1])
        ]
        if not words:
            return False
        if self._has_morph(words[0], poses={"PREP"}):
            return True
        return (
            words[0].text.casefold() in _SPATIAL_RELATION_ADVERBS
            and any(self._has_morph(item, poses={"PREP"}) for item in words[1:])
        )

    def _span_has_nominal_head(
        self, span: _Span, tokens: tuple[_SourceToken, ...]
    ) -> bool:
        if self._is_modifier_phrase(span, tokens):
            return False
        return any(
            self._structural_nominal_infos(tokens[index - 1])
            for index in range(span.start_index, span.end_index + 1)
        )

    @staticmethod
    def _only_nonlexical_between(
        left: _Span, right: _Span, tokens: tuple[_SourceToken, ...]
    ) -> bool:
        if left.end_index >= right.start_index:
            return False
        for index in range(left.end_index + 1, right.start_index):
            token = tokens[index - 1]
            if re.search(r"\w", token.text):
                return False
            if token.text in _STRONG_BOUNDARY:
                return False
        return True

    def _attachment_targets(
        self,
        text: str,
        tokens: tuple[_SourceToken, ...],
        predicate_span: _Span | None,
        predicate: PredicateCandidate,
        modifier: _Span,
    ) -> tuple[_AttachmentTarget, ...]:
        """Enumerate finite structural owners for one source modifier.

        The target set is role-agnostic.  The event/frame is always a possible
        owner for an adpositional modifier; a nominal owner is added only when a
        source NP is locally adjacent to the modifier inside the same frame window.
        No OBJECT/CASE/preposition semantics are consulted here.
        """
        if not self._is_modifier_phrase(modifier, tokens):
            return ()
        targets: list[_AttachmentTarget] = [
            _AttachmentTarget(
                _AttachmentTargetKind.PREDICATE,
                f"ATTACH:PRED:{modifier.spec}",
                f"«{modifier.text}» относится к действию «{predicate.surface}»",
            )
        ]
        all_spans = self._candidate_phrase_spans(
            text, tokens, predicate_span, [], requested_spans=()
        )
        nominal_candidates = [
            candidate
            for candidate in all_spans
            if candidate.end_index < modifier.start_index
            and self._span_has_nominal_head(candidate, tokens)
            and self._only_nonlexical_between(candidate, modifier, tokens)
        ]
        # Prefer the widest coordination/NP that ends at the same nearest source
        # position; nested genitive members may still appear as separate targets
        # only when they are independently chunked rather than swallowed by the NP.
        if nominal_candidates:
            nearest_end = max(item.end_index for item in nominal_candidates)
            nominal_candidates = [item for item in nominal_candidates if item.end_index == nearest_end]
        unique: dict[tuple[int, int], _Span] = {}
        for candidate in nominal_candidates:
            unique[(candidate.start_index, candidate.end_index)] = candidate
        for candidate in sorted(unique.values(), key=lambda item: (item.start_index, item.end_index)):
            targets.append(
                _AttachmentTarget(
                    _AttachmentTargetKind.NOMINAL,
                    f"ATTACH:NOM:{modifier.spec}:{candidate.spec}",
                    f"«{modifier.text}» описывает «{candidate.text}»",
                    candidate,
                )
            )
        return tuple(targets)

    def _resolve_modifier_attachment(
        self,
        text: str,
        tokens: tuple[_SourceToken, ...],
        predicate_span: _Span | None,
        predicate: PredicateCandidate,
        span: _Span,
    ) -> _AttachmentTarget | None:
        targets = self._attachment_targets(text, tokens, predicate_span, predicate, span)
        if len(targets) <= 1:
            return None

        resolution = (self._structural_resolution or "").strip()
        selected = next((target for target in targets if target.key == resolution), None)
        # Backward compatibility for the old single WITH-attachment protocol.
        if selected is None and resolution == "PREDICATE_ATTACHMENT":
            selected = next(
                (target for target in targets if target.kind is _AttachmentTargetKind.PREDICATE),
                None,
            )
        if selected is None and resolution == "OBJECT_ATTACHMENT":
            nominal = [target for target in targets if target.kind is _AttachmentTargetKind.NOMINAL]
            if len(nominal) == 1:
                selected = nominal[0]
        if selected is not None:
            return selected

        def require_clarification() -> None:
            spec = StructuralClarificationSpec(
                ambiguity_type="MODIFIER_ATTACHMENT",
                mention=span.text,
                source_text=text,
                options=tuple(
                    StructuralClarificationOption(target.key, target.label)
                    for target in targets
                ),
            )
            raise AdaptiveStructuralClarificationRequired(spec)

        # Instrumental PP attachment after a nominal has two grammatically valid
        # ownership structures: it can modify the event/frame or the adjacent NP.
        # World plausibility of the modifier content is not syntactic evidence
        # and must not let an LLM collapse that structural
        # ambiguity.  Detect the construction from morphology only.  Other PPs
        # still use the bounded semantic attachment probe below; e.g. an accusative
        # directional complement is not made ambiguous merely by adjacency.
        prep_positions = [
            i for i in range(span.start_index, span.end_index + 1)
            if self._has_morph(tokens[i - 1], poses={"PREP"})
        ]
        if prep_positions:
            first_prep = min(prep_positions)

            def stable_pp_head_case() -> str | None:
                """Return one coherent case for the PP nominal head, or ``None``.

                Case is a phrase-level constraint.  Looking for *any* case reading
                on *any* token lets an ambiguous adjective override the much stronger
                noun head analysis (live example: ``в дальней комнате`` where
                ``дальней`` has a weak instrumental reading but ``комнате`` is
                strongly locative).  Select the rightmost material NOUN/NPRO as the
                nominal head and accept its case only when readings agree or one
                scored case clearly dominates.  Adjective/participle case is a
                fallback only when the PP has no nominal head at all.
                """

                def case_for_infos(infos: tuple[MorphInfo, ...]) -> str | None:
                    material = tuple(item for item in infos if item.case)
                    if not material:
                        return None
                    cases = {item.case for item in material if item.case}
                    if len(cases) == 1:
                        return next(iter(cases))
                    scores: dict[str, float] = {}
                    for item in material:
                        assert item.case is not None
                        scores[item.case] = scores.get(item.case, 0.0) + max(0.0, item.score)
                    ranked = sorted(scores.items(), key=lambda pair: pair[1], reverse=True)
                    if len(ranked) < 2:
                        return ranked[0][0] if ranked else None
                    best_case, best_score = ranked[0]
                    second_score = ranked[1][1]
                    if best_score >= 0.60 and best_score >= second_score * 1.8:
                        return best_case
                    return None

                nominal_fallback: tuple[MorphInfo, ...] | None = None
                for i in range(span.end_index, first_prep, -1):
                    analyses = self._material_morph_analyses(tokens[i - 1])
                    nominal = tuple(item for item in analyses if item.pos in {"NOUN", "NPRO"})
                    if nominal:
                        return case_for_infos(nominal)
                    if nominal_fallback is None:
                        adjectival = tuple(
                            item for item in analyses if item.pos in {"ADJF", "PRTF"}
                        )
                        if adjectival:
                            nominal_fallback = adjectival
                return case_for_infos(nominal_fallback or ())

            # The hard ambiguity rule applies only to a *bare postnominal PP*
            # (``NP + PREP + instrumental``).  If the selected modifier has a
            # lexical governor before the preposition, the instrumental noun is
            # embedded inside that larger modifier rather than being evidence
            # that the whole phrase can attach to the adjacent NP.  Example
            # classes include adverbially headed relational phrases; they must
            # go through the ordinary bounded attachment decision below instead
            # of being promoted to ambiguity from instrumental case alone.
            #
            # This is deliberately structural: no predicate, noun or fixed
            # phrase vocabulary is consulted.  A genuinely ambiguous bare PP
            # such as ``увидел человека с прибором`` still starts at PREP and
            # therefore retains the clarification path.
            bare_postnominal_pp = first_prep == span.start_index
            pp_head_case = stable_pp_head_case()
            instrumental_complement = pp_head_case == "ablt"
            if bare_postnominal_pp and instrumental_complement:
                require_clarification()

        # The clause graph has already licensed predicate ellipsis, and the
        # bijective realization match identifies an existing source event slot.
        # Apply that constraint before a nominal-attachment vote could consume it.
        # Explicit clarification choices and genuine instrumental ambiguity above
        # retain priority. No locative/preverbal semantic shortcut is used.
        aligned_role = getattr(self, "_ellipsis_role_hints", {}).get(
            (span.start_index, span.end_index)
        )
        if aligned_role is not None:
            event = next((target for target in targets
                          if target.kind is _AttachmentTargetKind.PREDICATE), None)
            if event is not None:
                self._deterministic_trace("ellipsis_attachment", span.text, aligned_role.value)
                return event

        # Structural adjacency only enumerates possible owners; it is not itself
        # evidence that every PP is genuinely ambiguous.  For constructions not
        # deterministically ambiguous above, resolve one tiny local attachment
        # question before escalating to the user.  The model sees only source
        # readings, never canonical refs.
        local_labels: list[str] = []
        label_to_target: dict[str, _AttachmentTarget] = {}
        nominal_index = 0
        for target in targets:
            if target.kind is _AttachmentTargetKind.PREDICATE:
                label = "EVENT"
            else:
                nominal_index += 1
                label = f"NOMINAL_{nominal_index}"
            local_labels.append(label)
            label_to_target[label] = target
        choices = tuple([*local_labels, "UNCLEAR"])
        prompt = (
            f"TEXT:\n{text}\nPREDICATE:\n{predicate.surface}\nMODIFIER:\n{span.text}\n"
            "POSSIBLE READINGS:\n"
            + "\n".join(
                f"{label}: " + (
                    "MODIFIER fills a semantic relation of this PREDICATE occurrence, "
                    "even if its surface position is next to a nominal"
                    if label_to_target[label].kind is _AttachmentTargetKind.PREDICATE
                    else (
                        f"MODIFIER describes only the source nominal "
                        f"'{label_to_target[label].nominal_span.text}' and does not fill "
                        "a semantic relation of this PREDICATE occurrence"
                    )
                )
                for label in local_labels
            )
            + "\nQUESTION:\nWhich semantic contribution is determined by the whole "
              "sentence? Syntactic adjacency alone does not decide this choice. Choose "
              "UNCLEAR only when two or more listed readings remain genuinely possible "
              "from the text."
            + "\nCHOICES:\n" + "\n".join(choices)
        )

        def parse_attachment(raw: str) -> str:
            label = raw.strip().upper()
            if label not in choices:
                raise AdaptiveParseError(
                    "modifier_attachment expected exactly one of: " + ", ".join(choices)
                )
            return label

        decision = self._probe(
            "modifier_attachment",
            prompt,
            parse_attachment,
            max_new_tokens=10,
        )
        if decision != "UNCLEAR":
            return label_to_target[decision]

        require_clarification()

    def _nominal_modifier_predicate(
        self, span: _Span, tokens: tuple[_SourceToken, ...]
    ) -> PredicateCandidate:
        content = [
            tokens[index - 1]
            for index in range(span.start_index, span.end_index + 1)
            if self._is_word_token(tokens[index - 1])
        ]
        if not content:
            raise AdaptiveParseError("nominal modifier has no lexical relation marker")
        relation_tokens: list[_SourceToken] = []
        if content[0].text.casefold() in _SPATIAL_RELATION_ADVERBS:
            relation_tokens.append(content[0])
            if len(content) > 1 and self._has_morph(content[1], poses={"PREP"}):
                relation_tokens.append(content[1])
        else:
            prep = next((item for item in content if self._has_morph(item, poses={"PREP"})), None)
            if prep is not None:
                relation_tokens.append(prep)
        if not relation_tokens:
            relation_tokens.append(content[0])
        start = relation_tokens[0].start
        end = relation_tokens[-1].end
        surface = " ".join(item.text for item in relation_tokens)
        evidence_text = (
            self._candidate_graph.text[start:end]
            if self._candidate_graph is not None
            else surface
        )
        return PredicateCandidate(
            surface=surface,
            normalized_hint=surface.casefold(),
            sense_hint="STRUCTURAL_NOMINAL_ATTACHMENT",
            evidence=EvidenceSpan(evidence_text, start, end),
        )

    def _queue_nominal_modifier(
        self,
        text: str,
        tokens: tuple[_SourceToken, ...],
        owner: _Span,
        modifier: _Span,
    ) -> None:
        relation = self._nominal_modifier_predicate(modifier, tokens)
        role = self._classify_role(
            text,
            relation,
            modifier,
            used_roles={ActantRole.SUBJECT},
            forbidden_role=None,
            requested=False,
            allowed_roles={role for role in ActantRole if role is not ActantRole.SUBJECT},
        )
        if role is None:
            raise AdaptiveParseError(
                f"nominal modifier role unresolved: {modifier.text}"
            )
        self._pending_nominal_modifiers.append(
            _PendingNominalModifier(owner, modifier, relation, role)
        )

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
        """Return only structurally licensed semantic-role constraints.

        This helper used to contain positive ``surface -> AH role`` shortcuts
        (preposition -> LOCATION/PURPOSE/CAUSE, dative -> RECIPIENT, accusative
        -> OBJECT, nominative agreement -> SUBJECT, temporal lexeme -> TIME).
        Those shortcuts are unsound because AH roles are semantic relations to
        the predicate.  Morphology may rule readings out or expose a genuinely
        encoded voice relation, but it may not choose a role merely from case or
        a marker.

        Empty tuple means "no safe narrowing" and causes the bounded semantic
        role probe to see the complete remaining role set.
        """
        aligned_role = getattr(self, "_ellipsis_role_hints", {}).get(
            (span.start_index, span.end_index)
        )
        if aligned_role is not None:
            return (aligned_role,)
        words = [
            tokens[i - 1].text.casefold()
            for i in range(span.start_index, span.end_index + 1)
        ]
        passive = self._is_passive_predicate(predicate_span, tokens)

        # Passive voice is not a case shortcut: the voice construction itself
        # reverses the grammatical subject/object realization.  The architecture
        # defines SUBJECT semantically, so an overt instrumental agent is SUBJECT
        # and the nominative patient is OBJECT.  Keep this only where passive
        # morphology is explicitly present.
        if passive and any(
            self._has_structural_morph(
                tokens[i - 1], poses={"NOUN", "NPRO"}, case="ablt"
            )
            for i in range(span.start_index, span.end_index + 1)
        ):
            return (ActantRole.SUBJECT,)
        if passive and any(
            self._has_structural_morph(
                tokens[i - 1], poses={"NOUN", "NPRO"}, case="nomn"
            )
            for i in range(span.start_index, span.end_index + 1)
        ):
            return (ActantRole.OBJECT,)

        # Active finite intransitive clause + one agreeing nominative nominal is a
        # stronger constraint than bare NOM morphology.  The lexical valency rules
        # out a direct patient, while finite agreement identifies the sole holder /
        # experiencer of the event.  This lets deterministic structure remove a
        # pointless 16-way semantic probe for clauses such as ``X moved/failed/
        # leaked`` without reinstating the old unsound NOM->SUBJECT shortcut for
        # transitive, copular, passive or syntactically ambiguous clauses.
        if predicate_span is not None and not passive:
            predicate_transitivity_values = {
                stable_transitivity(self._morph_all(tokens[i - 1]))
                for i in range(predicate_span.start_index, predicate_span.end_index + 1)
            } - {None}
            if predicate_transitivity_values == {"intr"}:
                structural_subject = self._deterministic_subject_span(
                    tokens, predicate_span, None
                )
                if (
                    structural_subject is not None
                    and structural_subject.start_index == span.start_index
                    and structural_subject.end_index == span.end_index
                ):
                    return (ActantRole.SUBJECT,)

        # A lexical copula plus an adjectival/predicative complement directly
        # encodes predication of state/property.  This is predicate-structure
        # evidence, not an arbitrary case/preposition mapping.
        if self._is_copular_lookup(predicate.lookup_form) and any(
            self._has_morph(
                tokens[i - 1], poses={"ADJF", "ADJS", "PRTF", "PRTS", "PRED"}
            )
            for i in range(span.start_index, span.end_index + 1)
        ):
            return (ActantRole.STATE,)

        # A lexically opaque bare token (code/new term) can still occupy a
        # structurally forced direct-filler slot.  This is not UNKNOWN->OBJECT:
        # require an active, stably transitive predicate plus an independently
        # recovered SUBJECT elsewhere in the same clause, no governing preposition,
        # and an opaque target whose lexical identity was deliberately left unknown.
        # The rule only removes a pointless semantic probe for the remaining direct
        # participant; it does not canonicalize the token itself.
        if predicate_span is not None and not passive and span.start_index == span.end_index:
            target_token = tokens[span.start_index - 1]
            recovery = self._lexical_recovery_for_token(target_token)
            if (
                recovery is not None
                and recovery.status is LexicalRecoveryStatus.UNKNOWN_TOKEN
                and not self._has_morph(target_token, poses={"PREP"})
                and not (
                    span.start_index > 1
                    and self._has_morph(tokens[span.start_index - 2], poses={"PREP"})
                )
            ):
                transitivity_values = {
                    stable_transitivity(self._morph_all(tokens[i - 1]))
                    for i in range(predicate_span.start_index, predicate_span.end_index + 1)
                } - {None}
                structural_subject = self._deterministic_subject_span(
                    tokens, predicate_span, None
                )
                if (
                    transitivity_values == {"tran"}
                    and structural_subject is not None
                    and not structural_subject.overlaps(span)
                ):
                    return (ActantRole.OBJECT,)

        # Pure adverbs cannot be nominal participants or physical substances.
        # Keep only a negative POS-derived restriction; the actual adverbial
        # relation (place/time/duration/cause/purpose/manner/etc.) remains semantic.
        span_infos = [
            info
            for i in range(span.start_index, span.end_index + 1)
            for info in self._material_morph_analyses(tokens[i - 1])
            if info.pos is not None
        ]
        if span_infos and all(info.pos == "ADVB" for info in span_infos):
            return (
                ActantRole.LOCATION,
                ActantRole.STATE,
                ActantRole.TIME,
                ActantRole.DURATION,
                ActantRole.CAUSE,
                ActantRole.PURPOSE,
                ActantRole.AMOUNT,
                ActantRole.HOW_TO,
            )

        # A PP is a structural phrase, but its preposition does not identify an AH
        # relation.  Examples deliberately covered by leaving it open: ``в 2020
        # году`` (TIME), ``на два часа`` (DURATION), ``верить в него`` (OBJECT),
        # ``с другом`` (AUXILLIARY), ``с ножом`` (TOOL), ``с утра`` (TIME),
        # ``для Марии`` (RECIPIENT/beneficiary), ``для отдыха`` (PURPOSE).
        if words and self._has_morph(tokens[span.start_index - 1], poses={"PREP"}):
            return ()

        # Bare case is also only surface realization.  DAT/ACC/NOM/ABL/etc. stay
        # in morphology evidence shown through the sentence/target text, but case
        # alone does not remove semantic alternatives.  This is required for
        # experiencers (``мне холодно``, ``меня тошнит``), elapsed-time accusatives
        # (``ждал час``), governed objects, recipients and other predicate-specific
        # realizations.  If a future deterministic rule narrows this set, it must
        # be justified by a formal contradiction, not by a frequent case->role map.

        # Nominative agreement, word order, temporal vocabulary and all other
        # surface cues are intentionally not positive semantic-role evidence on
        # their own. The sole active-intransitive construction above is accepted
        # only because lexical valency + agreement jointly entail the holder.
        return ()

    def _actant_phrase_prompt(
        self,
        text: str,
        predicate: _Span | None,
        selected: list[_Span],
        candidates: tuple[_Span, ...],
        requested_spans: tuple[_Span, ...],
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
        if requested_spans:
            lines.append(
                "QUESTION_PLACEHOLDERS:\n"
                + " | ".join(span.text for span in requested_spans)
            )
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
            if self._active_implicit_clause_id is not None:
                clause = next(
                    (item for item in self._candidate_graph.clauses
                     if item.clause_id == self._active_implicit_clause_id),
                    None,
                )
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

    def _subject_agrees_with_predicate(
        self,
        token: _SourceToken,
        predicate_span: _Span | None,
        tokens: tuple[_SourceToken, ...],
    ) -> bool:
        """Return False only when finite agreement formally excludes SUBJECT.

        This is deliberately one-way. Missing/ambiguous morphology is not evidence
        against a subject reading. Number disagreement, and gender disagreement for
        Russian past singular finite verbs, are grammatical contradictions and may
        therefore narrow the role space before semantic probing.
        """
        if predicate_span is None:
            return True
        predicate_infos = [
            info
            for i in range(predicate_span.start_index, predicate_span.end_index + 1)
            for info in self._material_morph_analyses(tokens[i - 1])
            if info.pos == "VERB"
        ]
        subject_infos = [
            info
            for info in self._material_morph_analyses(token)
            if info.pos in {"NOUN", "NPRO"} and info.case == "nomn"
        ]
        if not predicate_infos or not subject_infos:
            return True

        predicate_numbers = {item.number for item in predicate_infos if item.number}
        subject_numbers = {item.number for item in subject_infos if item.number}
        if predicate_numbers and subject_numbers and predicate_numbers.isdisjoint(subject_numbers):
            return False

        past_singular = [
            item
            for item in predicate_infos
            if item.number == "sing" and "past" in item.grammemes and item.gender
        ]
        if past_singular:
            predicate_genders = {item.gender for item in past_singular if item.gender}
            subject_genders = {item.gender for item in subject_infos if item.gender}
            if predicate_genders and subject_genders and predicate_genders.isdisjoint(subject_genders):
                return False
        return True

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
            predicate_transitivity = None
            if predicate_span is not None:
                transitivity_values = {
                    stable_transitivity(self._morph_all(tokens[i - 1]))
                    for i in range(predicate_span.start_index, predicate_span.end_index + 1)
                } - {None}
                if len(transitivity_values) == 1:
                    predicate_transitivity = next(iter(transitivity_values))
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
                if self._has_structural_nominal_case(token, "nomn"):
                    # A post-verbal NOM/ACC-syncretic NP under a stably transitive
                    # predicate is not an *unambiguous* subject.  The same formal
                    # surface can be the direct object, so deterministic subject
                    # recovery must leave it to later role resolution/inheritance.
                    # Pre-verbal nominatives remain licensed by ordinary agreement.
                    if (
                        predicate_span is not None
                        and token.index > predicate_span.end_index
                        and predicate_transitivity == "tran"
                        and self._has_structural_nominal_case(token, "accs")
                    ):
                        continue
                    if not self._subject_agrees_with_predicate(token, predicate_span, tokens):
                        continue
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
        end = head
        # Russian postnominal possessives (``решение его``, ``торжество её``)
        # are part of the referential NP.  The generic NP chunker already knows
        # this, but deterministic copular-holder recovery used to return only the
        # nominal head and left the possessive behind as a fake third actant.
        # Extend only across the immediately following morphology-marked
        # possessive anaphor; no lexical list or semantic guess is involved.
        if head < clause_end and self._is_postnominal_possessive_anaphor(tokens[head]):
            end = head + 1
        return self._resolve_span_from_source(tokens, start, end)

    def _deterministic_copular_holder_span(
        self,
        tokens: tuple[_SourceToken, ...],
        predicate_span: _Span | None,
        state_span: _Span,
    ) -> _Span | None:
        """Return a structurally entailed holder for a proven copular STATE.

        Participial complements are excluded because ``дверь была открыта Иваном``
        may be a passive event rather than a simple predicated state; those frames
        keep using the dedicated passive-role path.
        """
        state_tokens = [
            tokens[index - 1]
            for index in range(state_span.start_index, state_span.end_index + 1)
            if 1 <= index <= len(tokens)
        ]
        if any(self._has_morph(token, poses={"PRTS", "PRTF"}) for token in state_tokens):
            return None
        return self._deterministic_subject_span(tokens, predicate_span, None)

    def _deterministic_copular_state_span(
        self,
        text: str,
        tokens: tuple[_SourceToken, ...],
        predicate_span: _Span | None,
        predicate: PredicateCandidate,
        selected: list[_Span],
        requested_spans: tuple[_Span, ...],
    ) -> _Span | None:
        if not self._is_copular_lookup(predicate.lookup_form):
            return None
        clause_start, clause_end = self._clause_bounds(predicate_span, tokens)
        lower_bound = predicate_span.end_index + 1 if predicate_span is not None else clause_start
        starts: list[int] = []
        for token in tokens:
            if token.index < lower_bound or token.index > clause_end:
                continue
            if any(self._span_contains(span, token.index) for span in requested_spans):
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

    def _explicit_question_words(
        self,
        tokens: tuple[_SourceToken, ...],
        predicate_span: _Span | None = None,
    ) -> tuple[_SourceToken, ...]:
        """Return every WH placeholder belonging to the current query frame.

        Connector-looking forms inside subordinate clauses are excluded exactly as
        in the old scalar helper.  The important difference is that no WH token is
        discarded merely because another one was found first.
        """
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
        clause_start, clause_end = self._clause_bounds(predicate_span, tokens)
        result: list[_SourceToken] = []
        for token in tokens:
            if token.index < clause_start or token.index > clause_end:
                continue
            if token.text.casefold() not in _QUESTION_WORDS:
                continue
            # Sentence-initial interrogatives may also be lexically tagged as
            # subordinators. Before the first predicate they are query syntax.
            if token.index in connector_indices and not (
                first_predicate is not None and token.index < first_predicate
            ):
                continue
            result.append(token)
        return tuple(result)

    def _explicit_question_word(
        self, tokens: tuple[_SourceToken, ...], predicate_span: _Span | None = None
    ) -> _SourceToken | None:
        """Backward-compatible scalar view for old diagnostic helpers."""
        words = self._explicit_question_words(tokens, predicate_span)
        return words[0] if words else None

    def _requested_query_spans(
        self,
        text: str,
        tokens: tuple[_SourceToken, ...],
        predicate_span: _Span | None = None,
    ) -> tuple[_Span, ...]:
        """Return clause-local WH placeholders without assigning semantic roles."""
        spans: list[_Span] = []
        for token in self._explicit_question_words(tokens, predicate_span):
            span = self._resolve_span(text, tokens, token.index, token.index)
            if token.index > 1:
                previous = tokens[token.index - 2]
                if self._has_morph(previous, poses={"PREP"}):
                    span = self._resolve_span(text, tokens, previous.index, token.index)
            spans.append(span)
        return tuple(spans)

    def _requested_query_roles(
        self,
        text: str,
        tokens: tuple[_SourceToken, ...],
        predicate: PredicateCandidate,
        predicate_span: _Span | None = None,
        *,
        used_roles: set[ActantRole] | None = None,
        requested_spans: tuple[_Span, ...] | None = None,
    ) -> tuple[tuple[ActantRole, ...], tuple[_Span, ...]]:
        spans = (
            requested_spans
            if requested_spans is not None
            else self._requested_query_spans(text, tokens, predicate_span)
        )
        occupied = set(used_roles or ())
        if not spans:
            pseudo = _Span(1, len(tokens), text, EvidenceSpan(text, 0, len(text)))
            role = self._classify_role(
                text, predicate, pseudo, occupied, None, requested=True
            )
            if role is None:
                raise AdaptiveParseError("requested role unresolved")
            return (role,), ()

        roles: list[ActantRole] = []
        for span in spans:
            role = self._classify_role(
                text,
                predicate,
                span,
                used_roles=occupied | set(roles),
                forbidden_role=None,
                requested=True,
            )
            if role is None:
                raise AdaptiveParseError(f"requested role unresolved: {span.text}")
            roles.append(role)
        return tuple(roles), tuple(spans)

    def _requested_query_role(
        self,
        text: str,
        tokens: tuple[_SourceToken, ...],
        predicate: PredicateCandidate,
    ) -> tuple[ActantRole, _Span | None]:
        """Backward-compatible single-gap adapter."""
        roles, spans = self._requested_query_roles(text, tokens, predicate)
        if len(roles) != 1:
            raise AdaptiveParseError("query contains multiple requested roles")
        return roles[0], spans[0] if spans else None

    def resolve_actant_role(
        self,
        source_text: str,
        predicate: PredicateCandidate,
        target_text: str,
        candidate_roles: tuple[ActantRole, ...],
    ) -> ActantRole:
        """Reconcile one parsed filler against a deterministically narrowed T.

        This is used only after canonical schema resolution has shown that the
        original role label cannot belong to the selected existing template. The
        model receives the source text, target phrase and a small UID-free set of
        existing semantic role meanings. It cannot choose a T or canonical UID.
        """
        candidates = set(candidate_roles)
        if not candidates:
            raise AdaptiveParseError("actant role reconciliation has no candidates")
        if len(candidates) == 1:
            return next(iter(candidates))
        synthetic = _Span(1, 1, target_text, EvidenceSpan(target_text))
        role = self._role_cue_probe(
            text=source_text,
            predicate=predicate,
            span=synthetic,
            requested=False,
            candidates=candidates,
            allow_none=False,
        )
        if role is None:
            raise AdaptiveParseError("actant role reconciliation returned no role")
        return role

    @staticmethod
    def _role_cue_lines(candidates: set[ActantRole]) -> str:
        lines: list[str] = []
        for cue, role, description in _ROLE_CUE_SPECS:
            if role in candidates:
                lines.append(f"{cue.value}: {description}")
        return "\n".join(lines)

    def _role_cue_probe(
        self,
        *,
        text: str,
        predicate: PredicateCandidate,
        span: _Span,
        requested: bool,
        candidates: set[ActantRole],
        allow_none: bool = False,
        allow_transition_operator: bool = False,
    ) -> ActantRole | None:
        """Resolve one target relation with one exact runtime semantic cue.

        Earlier binary trees made several individually plausible decisions for
        the same span.  A single wrong upper decision irreversibly removed the
        correct role and later probes could not recover it.  Here deterministic
        syntax first removes roles that are structurally impossible; the model
        then performs exactly one bounded semantic task over the remaining
        meanings.  It returns a protocol cue only.  Python maps that cue to the
        canonical role and rejects any cue outside the admissible set.
        """
        allowed_cues = tuple(
            cue for cue, role, _description in _ROLE_CUE_SPECS
            if role in candidates
        )
        allowed_labels = tuple(cue.value for cue in allowed_cues) + (
            ("NO_RELATION",) if allow_none else ()
        ) + (
            (RuntimeRoleCue.TRANSITION_OPERATOR.value,)
            if allow_transition_operator else ()
        )
        if not allowed_cues:
            raise AdaptiveParseError("role cue probe has no admissible cues")
        mode = "MISSING INFORMATION" if requested else "TARGET"
        prompt = (
            f"TEXT:\n{text}\nPREDICATE:\n{predicate.surface}\n{mode}:\n{span.text}\n"
            "CANDIDATE RELATIONS:\n"
            f"{self._role_cue_lines(candidates)}"
            + ("\nNO_RELATION: TARGET is not a semantic participant/circumstance of this PREDICATE"
               if allow_none else "")
            + (
                "\nTRANSITION_OPERATOR: TARGET is not an actant; it explicitly "
                "marks that the predicate occurrence begins, ends, continues, "
                "repeats, or no longer holds"
                if allow_transition_operator else ""
            )
            + "\nQUESTION:\nWhich single relation does TARGET have in this event? "
            "Use the whole sentence. Grammatical negation (НЕ) negates the proposition "
            "or contrasts a filler; by itself it never changes that filler's semantic role "
            "and never means ABSENT_ENTITY. Choose ABSENT_ENTITY only when TARGET itself "
            "is explicitly represented as absent/excluded/non-participating. "
            "Distinguish AFFECTED_OR_CONTENT from CONSTITUENT_MATERIAL strictly: "
            "MATERIAL means TARGET is a substance/component incorporated into a different "
            "affected or resulting entity; if TARGET is itself the affected/content/result "
            "entity, it is not MATERIAL. "
            "Choose only among the listed candidate relations.\n"
            "CHOICES:\n" + "\n".join(allowed_labels)
        )

        def parse_label(raw: str) -> str:
            label = raw.strip().upper()
            if label not in allowed_labels:
                raise AdaptiveParseError(
                    "role_cue expected exactly one of: " + ", ".join(allowed_labels)
                )
            return label

        label = self._probe(
            "role_cue",
            prompt,
            parse_label,
            max_new_tokens=10,
        )
        if label == "NO_RELATION":
            if not allow_none:
                raise AdaptiveParseError("NO_RELATION is not admissible for this target")
            return None
        if label == RuntimeRoleCue.TRANSITION_OPERATOR.value:
            if not allow_transition_operator:
                raise AdaptiveParseError("TRANSITION_OPERATOR is not admissible")
            graph = self._candidate_graph
            if graph is None:
                raise AdaptiveParseError("transition cue requires candidate graph")
            indices = {
                token.index
                for token in graph.tokens
                if span.start_index <= token.index <= span.end_index
                and any(
                    info.pos in {"ADVB", "PRCL"}
                    for info in token.analyses
                )
            }
            if not indices:
                raise AdaptiveParseError("transition cue has no ADVB/PRCL source token")
            self._transition_cue_token_indices.update(indices)
            return None
        cue = RuntimeRoleCue(label)
        role = _ROLE_CUE_TO_ROLE[cue]
        if role not in candidates:
            raise AdaptiveParseError("role cue escaped admissible role set")
        return role

    def _classify_role(
        self,
        text: str,
        predicate: PredicateCandidate,
        span: _Span,
        used_roles: set[ActantRole],
        forbidden_role: ActantRole | tuple[ActantRole, ...] | set[ActantRole] | None,
        *,
        requested: bool,
        allowed_roles: set[ActantRole] | None = None,
        allow_none: bool = False,
    ) -> ActantRole | None:
        semantic_span = self._semantic_span(span)
        graph = self._candidate_graph
        span_tokens = (
            ()
            if graph is None
            else tuple(
                graph.token(index)
                for index in range(span.start_index, span.end_index + 1)
                if re.search(r"\w", graph.token(index).text)
            )
        )
        allow_transition_operator = bool(span_tokens) and all(
            any(
                info.pos in {"ADVB", "PRCL"}
                for info in token.analyses
            )
            for token in span_tokens
        )
        if forbidden_role is None:
            forbidden_roles: set[ActantRole] = set()
        elif isinstance(forbidden_role, ActantRole):
            forbidden_roles = {forbidden_role}
        else:
            forbidden_roles = set(forbidden_role)
        candidates = {
            role
            for role in _TEMPLATE_ROLE_DESCRIPTIONS
            if role not in used_roles
            and role not in forbidden_roles
            and (allowed_roles is None or role in allowed_roles)
        }
        if not candidates:
            raise AdaptiveParseError("no canonical roles remain available")
        if (
            len(candidates) == 1
            and not allow_none
            and not allow_transition_operator
        ):
            role = next(iter(candidates))
            self._deterministic_trace(
                "role_cue",
                self._requested_role_prompt(text, predicate, semantic_span),
                _ROLE_TO_CUE[role].value,
            )
            return role
        return self._role_cue_probe(
            text=text,
            predicate=predicate,
            span=semantic_span,
            requested=requested,
            candidates=candidates,
            allow_none=allow_none,
            allow_transition_operator=allow_transition_operator,
        )

    def _is_registered_transition_cue(self, span: _Span) -> bool:
        graph = self._candidate_graph
        if graph is None:
            return False
        indices = {
            token.index
            for token in graph.tokens
            if span.start_index <= token.index <= span.end_index
            and re.search(r"\w", token.text)
        }
        return bool(indices) and indices <= self._transition_cue_token_indices

    def _exact_choice_probe(
        self,
        stage: str,
        prompt: str,
        choices: tuple[str, ...],
    ) -> tuple[str, float]:
        """Resolve a bounded semantic choice by exact generation only.

        There is no likelihood scorer, calibrated margin, tournament, or second
        semantic voter. Python first narrows the option set; the model must emit
        exactly one supplied protocol label. Callers that permit ambiguity include
        an explicit ``UNCLEAR`` option and preserve alternatives when it is chosen.
        The float return is retained as ``inf`` only for compatibility with older
        call sites that ignored the former scorer margin.
        """
        if not choices or len(set(choices)) != len(choices):
            raise AdaptiveParseError(f"{stage} requires unique fixed choices")
        instruction = self._instruction(stage)
        user_prompt = self._compose_probe_prompt(prompt, instruction)
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

    def _deep_semantic_choice_probe(
        self,
        stage: str,
        prompt: str,
        choices: tuple[str, ...],
        *,
        optional: bool = False,
    ) -> tuple[str | None, float]:
        """Resolve one rare local semantic cue without enabling model thinking.

        Machine-protocol probes must remain non-thinking.  Thinking-capable chat
        templates can spend the whole generation budget on an internal reasoning
        channel (or return that channel instead of the requested label), which
        breaks an exact ``YES / NO / UNCLEAR`` contract.  This semantic role is
        therefore isolated by role but uses ordinary non-thinking generation.

        The model receives no AH UIDs, Workspace, proof state, or canonical
        candidates.  Python retains all validation and materialization authority.

        ``optional=True`` is used only for post-parse semantic enrichment.  If the
        model violates the bounded output protocol, the invalid trace is preserved
        and the enrichment is omitted fail-closed; already parsed primary facts are
        not discarded.  Backend/infrastructure failures still propagate.
        """
        if not choices or len(set(choices)) != len(choices):
            raise AdaptiveParseError(f"{stage} requires unique fixed choices")
        instruction = self._instruction(stage)
        user_prompt = self._compose_probe_prompt(prompt, instruction)
        override = self._generation_override(8)
        # Never opt a machine-protocol semantic probe into a reasoning channel.
        # Explicit False also overrides a globally enabled thinking setting.
        override["enable_thinking"] = False
        response = self.backend.generate(
            user_prompt,
            system=self._probe_system(),
            override=override,
            role=f"semantic_{stage}",
        )
        raw = response.text.strip()
        label = raw.upper()
        if label not in choices:
            error = f"expected exactly one of: {', '.join(choices)}"
            self._traces.append(
                ProbeTrace(stage, user_prompt, raw, None, 0, error)
            )
            if optional:
                return None, float("inf")
            raise AdaptiveParseError(f"{stage} {error}")
        self._traces.append(ProbeTrace(stage, user_prompt, raw, label, 0, None))
        return label, float("inf")

    def _probe(
        self,
        stage: str,
        prompt: str,
        validator: Callable[[str], T],
        *,
        max_new_tokens: int,
    ) -> T:
        instruction = self._instruction(stage)
        user_prompt = self._compose_probe_prompt(prompt, instruction)
        last_error = "invalid answer"
        for retry_index in range(self.settings.retry_attempts + 1):
            # Exact protocol validation happens after ordinary deterministic
            # generation. Do not pass ``choice_outputs``: the process backend
            # implements that option by continuation likelihood scoring, which
            # would become a second semantic voter.
            override = self._generation_override(max_new_tokens)
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
            _SourceToken(i, m.group(0), m.start(), m.end(), m.group(0))
            for i, m in enumerate(re.finditer(r"\w+|[^\w\s]", text, flags=re.UNICODE), start=1)
        )

    @staticmethod
    def _source_tokens_from_graph(
        graph: LinguisticCandidateGraph,
    ) -> tuple[_SourceToken, ...]:
        return tuple(
            _SourceToken(
                item.index,
                item.text,
                item.start,
                item.end,
                item.provenance_text,
            )
            for item in graph.tokens
        )

    def _semantic_token_range_text(
        self,
        tokens: tuple[_SourceToken, ...],
        start_index: int,
        end_index: int,
    ) -> str:
        """Reconstruct normalized text while retaining raw inter-token spacing.

        Character offsets continue to address the original source.  Corrected
        surfaces are substituted only into the runtime semantic string, so an OOV
        typo can never become canonical S/entity identity through a raw slice.
        """
        selected = tokens[start_index - 1 : end_index]
        if not selected:
            return ""
        source = self._candidate_graph.text if self._candidate_graph is not None else ""
        parts: list[str] = [selected[0].text]
        for left, right in zip(selected, selected[1:]):
            separator = source[left.end:right.start] if source else " "
            parts.extend((separator, right.text))
        return "".join(parts)

    def _semantic_span(self, span: _Span) -> _Span:
        graph = self._candidate_graph
        if graph is None:
            return span
        text = self._semantic_token_range_text(
            self._source_tokens_from_graph(graph),
            span.start_index,
            span.end_index,
        )
        return replace(span, text=text)

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

    def _lexical_recovery_for_token(
        self, token: _SourceToken
    ) -> TokenCandidate | None:
        """Return the monotonic Lexical Recovery decision for a parser token.

        ``_SourceToken`` intentionally contains only normalized source offsets,
        while recovery/provenance lives on ``LinguisticCandidateGraph.tokens``.
        Reading ``token.recovery`` therefore never worked on the real parser path
        and allowed productive morphology to reopen a protected UNKNOWN.  Keep the
        ownership boundary explicit and index the runtime graph instead.
        """
        direct = getattr(token, "recovery", None)
        if direct is not None:
            return direct
        graph = self._candidate_graph
        if graph is None:
            return None
        try:
            return graph.token(token.index).recovery
        except (IndexError, KeyError, TypeError, ValueError):
            return None

    def _material_morph_analyses(
        self, token: _SourceToken, *, apply_context: bool = True
    ) -> tuple[MorphInfo, ...]:
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
        material = [item for item in analyses if item.score >= floor]

        # Context-free morphology probabilities must not erase a genuine
        # case-syncretic reading before syntax gets a chance to narrow it.
        # Russian animate names are a common example: ``Петра`` is often scored
        # mostly as genitive by pymorphy, while the same lexical form is also
        # accusative and is the ordinary direct object in ``увидел Петра``.
        # Keep lower-scored CASE alternatives when they are the same nominal
        # lexeme and agree on all non-case structural features with a material
        # reading.  Unrelated low-probability homonyms remain filtered out.
        nominal_anchors = {
            (
                item.normal_form.casefold(), item.pos, item.number, item.gender,
                item.animacy, item.mood, item.transitivity,
            )
            for item in material
            if item.pos in {"NOUN", "NPRO"} and item.case is not None
        }
        if nominal_anchors:
            for item in analyses:
                if item in material or item.pos not in {"NOUN", "NPRO"} or item.case is None:
                    continue
                key = (
                    item.normal_form.casefold(), item.pos, item.number, item.gender,
                    item.animacy, item.mood, item.transitivity,
                )
                if key in nominal_anchors:
                    material.append(item)
        if apply_context:
            chosen = self._contextual_nominal_lemmas.get(token.index)
            if chosen is not None:
                material = [
                    item for item in material
                    if item.pos not in {"NOUN", "NPRO"}
                    or item.normal_form.strip().casefold() == chosen
                ]
        return tuple(material)

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

    @staticmethod
    def _nominal_like_info(info: MorphInfo) -> bool:
        """Return whether one morphology reading can syntactically head an NP.

        Besides ordinary NOUN/NPRO readings, Russian morphology exposes
        substantivized anaphoric adjectives (``тот``, relative ``который``) as
        ADJF+Subx/Apro.  Treating those forms as adjectives only loses formal
        case/agreement evidence and later forces semantic role guesses.  This is
        a morphology-class decision, not lexical special-casing.
        """
        if info.pos in {"NOUN", "NPRO"}:
            return True
        return info.pos == "ADJF" and "Subx" in info.grammemes

    def _structural_nominal_infos(self, token: _SourceToken) -> tuple[MorphInfo, ...]:
        return tuple(
            info for info in self._material_morph_analyses(token)
            if self._nominal_like_info(info)
        )

    def _structural_nominal_cases(self, token: _SourceToken) -> set[str]:
        return {
            info.case for info in self._structural_nominal_infos(token)
            if info.case is not None
        }

    def _has_structural_nominal_case(self, token: _SourceToken, case: str) -> bool:
        return any(info.case == case for info in self._structural_nominal_infos(token))

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

            # Dependency scheduling: a child frame is not parsed before its still
            # unparsed structural parent.  This is what makes a fronted gerund or
            # fronted subordinate clause dependent on the later finite matrix
            # predicate without pretending source order is semantic hierarchy.
            available_indices = {item.token_index for item in available}
            ready = [
                item for item in available
                if (parent := self._candidate_graph.frame_graph.parent_of(item.token_index)) is None
                or parent not in available_indices
            ]
            if not ready:
                raise AdaptiveParseError("cyclic or unresolved ClauseFrameGraph dependency")

            # Among independent ready roots, source order is merely a deterministic
            # work-queue order.  Within one clause prefer the structurally stronger
            # finite head over secondary non-finite morphology.
            first_clause_start = min(
                (
                    clause.span.start_index
                    for item in ready
                    if (clause := self._candidate_graph.clause_for_token(item.token_index)) is not None
                ),
                default=1,
            )
            same_clause = [
                item for item in ready
                if (clause := self._candidate_graph.clause_for_token(item.token_index)) is not None
                and clause.span.start_index == first_clause_start
            ]
            pool = same_clause or ready
            strongest = max(item.strength for item in pool)
            return tuple(
                item.token_index for item in pool if item.strength == strongest
            )

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

    def _next_implicit_copula_clause(
        self, used_clause_ids: set[str]
    ):
        graph = self._candidate_graph
        if graph is None:
            return None
        candidates = [
            clause for clause in graph.clauses
            if (
                clause.implicit_copula
                and not clause.predicate_heads
                and clause.clause_id not in used_clause_ids
            )
        ]
        if not candidates:
            return None
        return min(candidates, key=lambda clause: clause.span.start_index)

    def _has_remaining_frame_candidates(
        self,
        tokens: tuple[_SourceToken, ...],
        excluded: list[_Span],
        used_implicit_clause_ids: set[str],
    ) -> bool:
        return bool(
            self._predicate_morph_candidates(tokens, excluded)
            or self._next_implicit_copula_clause(used_implicit_clause_ids) is not None
        )

    def _atomic_morph_predicate(
        self,
        index: int,
        tokens: tuple[_SourceToken, ...],
    ) -> bool:
        if index < 1 or index > len(tokens):
            return False
        if self._candidate_graph is not None:
            head = next(
                (item for item in self._candidate_graph.predicates if item.token_index == index),
                None,
            )
            if head is not None and head.nominal_predicative:
                return True
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
        if self._candidate_graph is not None:
            head = next(
                (item for item in self._candidate_graph.predicates if item.token_index == start),
                None,
            )
            if head is not None and head.nominal_predicative:
                lemmas = tuple(dict.fromkeys(
                    item.normal_form.strip()
                    for item in analyses
                    if item.pos == "NOUN" and item.normal_form.strip()
                ))
                if len(lemmas) == 1:
                    return lemmas[0]
                if len(lemmas) > 1:
                    # Nominal predicate homonymy is still lexical ambiguity. Keep
                    # it bounded and UID-free rather than trusting analyser order.
                    choices = tuple(f"L{i + 1}" for i in range(len(lemmas)))
                    prompt = (
                        f"TEXT:\n{self._candidate_graph.text}\nTARGET:\n{token.text}\n"
                        + "CHOICES:\n"
                        + "\n".join(f"{label}: {lemma}" for label, lemma in zip(choices, lemmas))
                    )
                    decision, _ = self._exact_choice_probe(
                        "nominal_predicate_lexeme", prompt, choices
                    )
                    return lemmas[choices.index(decision)]
                return None
        for positions in ({"VERB", "PRED"}, {"INFN", "GRND", "ADJS", "PRTS"}):
            candidates = [item for item in analyses if item.pos in positions]
            if not candidates:
                continue

            expected_number = self._explicit_subject_number(tokens, start)

            def compatibility(info: MorphInfo) -> tuple[int, int]:
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
                # Analyzer probability is evidence about lexical frequency, not
                # sentence-context identity.  It must not silently choose between
                # different predicate lexemes once structural compatibility is equal.
                return mood_score, number_score

            best_key = max(compatibility(item) for item in candidates)
            best = [item for item in candidates if compatibility(item) == best_key]
            forms = {item.normal_form.casefold(): item.normal_form for item in best}
            if len(forms) == 1:
                return next(iter(forms.values()))
            ordered = [forms[key] for key in sorted(forms)]
            if len(ordered) != 2:
                raise AdaptiveParseError(
                    f"predicate lexical ambiguity is not binary: {token.text} -> "
                    + ", ".join(ordered)
                )
            full_text = self._candidate_graph.text if self._candidate_graph is not None else token.text
            return self._resolve_binary_lexeme_hypotheses(
                text=full_text,
                target=token.text,
                candidates=(ordered[0], ordered[1]),
                analyses=best,
                predicate_surface=token.text,
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
        # label.  The context-resolved source-language normal form gives Integration
        # a lexical key without making the sensory layer choose among homographs.
        # The observed surface may later be added to that resolved S even when the
        # same surface legitimately belongs to another paradigm as well.
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

    def _act_type_prompt(
        self,
        text: str,
        tokens: tuple[_SourceToken, ...],
        excluded: list[_Span],
        *,
        focus_clause_id: str | None = None,
    ) -> str:
        options = {
            "NONE": "none or unclear",
            "ASSERTION": "states information as a claim/fact",
            "QUERY": "asks for information",
            "COMMAND": "requests or orders an action",
        }
        focus = text
        graph = self._candidate_graph
        if graph is not None:
            clause = (
                next((item for item in graph.clauses if item.clause_id == focus_clause_id), None)
                if focus_clause_id is not None else None
            )
            if clause is None:
                excluded_positions = {
                    i for span in excluded for i in range(span.start_index, span.end_index + 1)
                }
                remaining = [
                    p for p in graph.predicates if p.token_index not in excluded_positions
                ]
                if remaining:
                    clause = graph.clause_for_token(remaining[0].token_index)
            if clause is not None:
                focus = clause.span.text
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
        if self._candidate_graph is None:
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
            "FILL_ROLE: asks for one or more missing participants, properties, circumstances, places, times, causes, purposes, manners, or amounts"
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
