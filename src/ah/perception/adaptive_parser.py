from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Protocol, TypeVar
import re

from ah.config import LLMRoleSettings
from ah.llm.process_backend import LLMResponse
from ah.model import ActantRole

from .contracts import (
    ActantCandidate,
    AssertionCandidate,
    CommandCandidate,
    EvidenceSpan,
    PerceptionResult,
    PredicateCandidate,
    QueryCandidate,
    QueryMode,
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

    def __post_init__(self) -> None:
        if self.retry_attempts < 0 or self.retry_attempts > 2:
            raise ValueError("retry_attempts must be in [0, 2]")
        if self.max_acts <= 0:
            raise ValueError("max_acts must be > 0")
        if self.max_actants_per_act <= 0:
            raise ValueError("max_actants_per_act must be > 0")
        if self.predicate_symbol_language != "en":
            raise ValueError("predicate_symbol_language currently must be 'en'")


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


class AdaptiveParseError(ValueError):
    def __init__(self, message: str, traces: tuple[ProbeTrace, ...] = ()) -> None:
        super().__init__(message)
        self.traces = traces


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


# adaptive_v2 deliberately keeps model outputs tiny and numeric wherever possible.
# The model is never expected to know AH terminology. Canonical role names are shown
# only as human-readable labels next to plain-language definitions; Python maps the
# selected option to ActantRole.
_FALLBACK_PROMPTS: dict[str, str] = {
    "act_type": (
        "Choose what TEXT does. Reply with one OPTIONS number only."
    ),
    "predicate_start": (
        "Choose the first token of the main action, state, or relation. "
        "Reply with one OPTIONS number only."
    ),
    "predicate_end": (
        "PREDICATE_START is the first predicate token. Choose the last token that "
        "belongs to the same predicate phrase. For a one-token predicate choose the "
        "same number. Reply with one OPTIONS number only."
    ),
    "predicate_symbol": (
        "Translate TARGET predicate meaning into one short English base-form semantic label. "
        "Reply with lowercase ASCII letters and underscores only. No explanation."
    ),
    "negation": (
        "Is PREDICATE explicitly negated in TEXT? Reply 1 for yes or 0 for no."
    ),
    "actant_start": (
        "Choose the first token of one not-yet-selected phrase connected to PREDICATE: "
        "a participant, object, property/state, place, time, reason, goal, means, material, "
        "amount, or manner. Reply with one OPTIONS number only. Choose 0 if none remain."
    ),
    "actant_end": (
        "ACTANT_START is the first token of the selected phrase. Choose its last token. "
        "Keep coordinated values joined by words such as 'и' or 'или' in one phrase when "
        "they fill the same role. Reply with one OPTIONS number only."
    ),
    "role_family": (
        "Choose what kind of information TARGET expresses relative to PREDICATE. "
        "Reply with one OPTIONS number only."
    ),
    "role_participant": (
        "Choose TARGET's exact participant relation to PREDICATE. Reply with one OPTIONS number only."
    ),
    "role_description": (
        "Choose TARGET's exact description/context relation to PREDICATE. Reply with one OPTIONS number only."
    ),
    "role_circumstance": (
        "Choose TARGET's exact reason/means relation to PREDICATE. Reply with one OPTIONS number only."
    ),
    "query_mode": (
        "Choose the question type. Reply with one OPTIONS number only."
    ),
    "requested_role": (
        "TEXT asks for missing information represented by TARGET. Choose what information is missing. "
        "Reply with one OPTIONS number only."
    ),
}


_PROBE_SYSTEM = (
    "Do only the final TASK. Return only the requested number or short word. "
    "Do not copy TEXT, TOKENS, OPTIONS, or explain your answer."
)

_ACT_TYPE_CHOICES: dict[int, str] = {
    0: "NONE",
    1: "ASSERTION",
    2: "QUERY",
    3: "COMMAND",
}
_QUERY_MODE_CHOICES: dict[int, QueryMode] = {
    1: QueryMode.EXISTS,
    2: QueryMode.FILL_ROLE,
}

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

# High-confidence question words that have a stable role independent of most syntax.
_DETERMINISTIC_WH_ROLES: dict[str, ActantRole] = {
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


class AdaptivePerceptionParser:
    """Weak-model-oriented adaptive semantic recognizer.

    The LLM receives no AH objects, UIDs, templates, graph structure, or parser state.
    Each call solves one small natural-language decision. Python owns tokenization,
    candidate enumeration, exclusions, span assembly, role mapping, validation and
    PerceptionResult construction. Most model outputs are integers selected from an
    explicit OPTIONS list; only English predicate naming remains open text.
    """

    _EN_SYMBOL_RE = re.compile(r"[a-z][a-z0-9]*(?:_[a-z0-9]+)*")
    _IRREGULAR_EN = {
        "am": "be", "is": "be", "are": "be", "was": "be", "were": "be",
        "been": "be", "being": "be", "has": "have", "had": "have",
        "does": "do", "did": "do",
    }

    def __init__(self, backend: TextGenerator, settings: AdaptiveSettings) -> None:
        self.backend = backend
        self.settings = settings
        self._traces: list[ProbeTrace] = []

    def parse(self, text: str) -> AdaptiveParseResult:
        self._traces = []
        tokens = self._source_tokens(text)
        if not tokens:
            return AdaptiveParseResult(PerceptionResult(source_text=text), ())

        assertions: list[AssertionCandidate] = []
        queries: list[QueryCandidate] = []
        commands: list[CommandCandidate] = []
        used_predicates: list[_Span] = []
        parser_diagnostics: list[str] = []

        try:
            for act_index in range(1, self.settings.max_acts + 1):
                try:
                    act_choice = self._probe(
                        "act_type",
                        self._act_type_prompt(text, tokens, used_predicates),
                        lambda raw: self._number_choice(raw, _ACT_TYPE_CHOICES),
                        max_new_tokens=2,
                    )
                except AdaptiveParseError as exc:
                    if assertions or queries or commands:
                        parser_diagnostics.append("PARTIAL_PARSE: next act classification failed: " + str(exc))
                        break
                    raise
                act_type = act_choice
                if act_type == "NONE":
                    break

                predicate_start = self._probe(
                    "predicate_start",
                    self._predicate_start_prompt(text, tokens, used_predicates),
                    lambda raw: self._predicate_start_choice(raw, tokens, used_predicates),
                    max_new_tokens=3,
                )
                if predicate_start == -1:
                    if act_index == 1:
                        raise AdaptiveParseError("LLM classified an act but selected no meaningful predicate")
                    break

                predicate_span: _Span | None
                if predicate_start == 0:
                    predicate_span = None
                    target_text = text
                else:
                    end_choices = self._predicate_end_choices(text, tokens, predicate_start, used_predicates)
                    if len(end_choices) == 1:
                        predicate_end = next(iter(end_choices))
                        self._deterministic_trace(
                            "predicate_end", self._predicate_end_prompt(text, tokens, predicate_start, end_choices), predicate_end
                        )
                    else:
                        predicate_end = self._probe(
                            "predicate_end",
                            self._predicate_end_prompt(text, tokens, predicate_start, end_choices),
                            lambda raw: self._number_choice(raw, end_choices),
                            max_new_tokens=3,
                        )
                    predicate_span = self._resolve_span(text, tokens, predicate_start, predicate_end)
                    if any(predicate_span.overlaps(old) for old in used_predicates):
                        raise AdaptiveParseError("predicate overlaps an already parsed predicate")
                    used_predicates.append(predicate_span)
                    target_text = predicate_span.text

                canonical = self._probe(
                    "predicate_symbol",
                    self._predicate_symbol_prompt(text, target_text, implicit=predicate_span is None),
                    self._english_symbol,
                    max_new_tokens=10,
                )
                predicate = PredicateCandidate(
                    surface=(target_text if predicate_span is not None else canonical),
                    normalized_hint=canonical,
                    sense_hint=("IMPLICIT" if predicate_span is None else None),
                    evidence=(predicate_span.evidence if predicate_span is not None else None),
                )

                negated = False
                query_mode = QueryMode.EXISTS
                requested_role: ActantRole | None = None
                requested_span: _Span | None = None

                if act_type == "ASSERTION":
                    deterministic_negation = self._deterministic_negation(tokens, predicate_span)
                    if deterministic_negation is not None:
                        negated = deterministic_negation
                        self._deterministic_trace(
                            "negation", self._negation_prompt(text, predicate), 1 if negated else 0
                        )
                    else:
                        negated = self._probe(
                            "negation",
                            self._negation_prompt(text, predicate),
                            lambda raw: self._bit(raw) == 1,
                            max_new_tokens=2,
                        )
                elif act_type == "QUERY":
                    query_mode = self._probe(
                        "query_mode",
                        self._query_mode_prompt(text, predicate),
                        lambda raw: self._number_choice(raw, _QUERY_MODE_CHOICES),
                        max_new_tokens=2,
                    )
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
                    assertions.append(
                        AssertionCandidate(
                            local_id=f"A{len(assertions) + 1}",
                            predicate=predicate,
                            actants=actants,
                            evidence=EvidenceSpan(text, 0, len(text)),
                            negated=negated,
                        )
                    )
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

        except AdaptiveParseError as exc:
            traces = tuple(self._traces)
            if exc.traces:
                traces = exc.traces
            raise AdaptiveParseError(str(exc), traces) from exc

        result = PerceptionResult(
            source_text=text,
            assertions=tuple(assertions),
            queries=tuple(queries),
            commands=tuple(commands),
            diagnostics=tuple(parser_diagnostics),
        )
        return AdaptiveParseResult(result, tuple(self._traces))

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

        for _ in range(self.settings.max_actants_per_act):
            start_choices = self._actant_start_choices(
                tokens, predicate_span, spans, requested_span=requested_span
            )
            if not start_choices:
                self._deterministic_trace(
                    "actant_start",
                    self._actant_start_prompt(text, tokens, predicate_span, spans, {}, requested_span),
                    0,
                )
                break

            choice_map: dict[int, int] = {0: 0}
            choice_map.update({index: index for index in start_choices})
            start = self._probe(
                "actant_start",
                self._actant_start_prompt(
                    text, tokens, predicate_span, spans, choice_map, requested_span
                ),
                lambda raw: self._number_choice(raw, choice_map),
                max_new_tokens=3,
            )
            if start == 0:
                break

            end_choices = self._actant_end_choices(
                text, tokens, start, predicate_span, spans, requested_span=requested_span
            )
            if len(end_choices) == 1:
                end = next(iter(end_choices))
                self._deterministic_trace(
                    "actant_end", self._actant_end_prompt(text, tokens, start, end_choices), end
                )
            else:
                end = self._probe(
                    "actant_end",
                    self._actant_end_prompt(text, tokens, start, end_choices),
                    lambda raw: self._number_choice(raw, end_choices),
                    max_new_tokens=3,
                )
            span = self._resolve_span(text, tokens, start, end)
            self._validate_actant_span(span, predicate_span, spans, requested_span)

            role = self._classify_role(
                text,
                predicate,
                span,
                used_roles=roles,
                forbidden_role=requested_role if act_type == "QUERY" else None,
                requested=False,
            )
            spans.append(span)
            roles.add(role)
            actants.append(
                ActantCandidate(
                    role=role,
                    mention=span.text,
                    evidence=span.evidence,
                )
            )
        return tuple(actants), tuple(spans)

    def _requested_query_role(
        self,
        text: str,
        tokens: tuple[_SourceToken, ...],
        predicate: PredicateCandidate,
    ) -> tuple[ActantRole, _Span | None]:
        wh_tokens = [token for token in tokens if token.text.casefold() in _QUESTION_WORDS]
        if not wh_tokens:
            # No explicit question word. Ask for the missing role using the whole question
            # as target; this remains a discrete role-choice tree.
            pseudo = _Span(1, len(tokens), text, EvidenceSpan(text, 0, len(text)))
            role = self._classify_role(text, predicate, pseudo, set(), None, requested=True)
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
    ) -> ActantRole:
        available_groups: list[tuple[str, tuple[tuple[ActantRole, str], ...]]] = []
        for group_name, entries in _ROLE_GROUPS.items():
            filtered = tuple(
                (role, desc)
                for role, desc in entries
                if role not in used_roles and role != forbidden_role
            )
            if filtered:
                available_groups.append((group_name, filtered))
        if not available_groups:
            raise AdaptiveParseError("no canonical roles remain available")

        if len(available_groups) == 1:
            group_name, entries = available_groups[0]
            self._deterministic_trace(
                "role_family",
                self._role_family_prompt(text, predicate, span, available_groups, requested=requested),
                group_name,
            )
        else:
            family_choices = {i: name for i, (name, _entries) in enumerate(available_groups, start=1)}
            group_name = self._probe(
                "role_family",
                self._role_family_prompt(text, predicate, span, available_groups, requested=requested),
                lambda raw: self._number_choice(raw, family_choices),
                max_new_tokens=2,
            )
            entries = dict(available_groups)[group_name]

        role_choices = {i: role for i, (role, _desc) in enumerate(entries, start=1)}
        stage = f"role_{group_name}"
        if len(role_choices) == 1:
            role = next(iter(role_choices.values()))
            self._deterministic_trace(
                stage,
                self._role_exact_prompt(text, predicate, span, group_name, entries, requested=requested),
                role.value,
            )
            return role
        return self._probe(
            stage,
            self._role_exact_prompt(text, predicate, span, group_name, entries, requested=requested),
            lambda raw: self._number_choice(raw, role_choices),
            max_new_tokens=2,
        )

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
            response = self.backend.generate(
                user_prompt,
                system=self._probe_system(),
                override=self._generation_override(max_new_tokens),
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
                prompt=self._compose_probe_prompt(prompt, self._instruction(stage)),
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
        }

    def _probe_system(self) -> str:
        path = self.settings.prompt_dir / "probe_system.txt" if self.settings.prompt_dir else None
        if path is not None:
            try:
                text = path.read_text(encoding="utf-8").strip()
                if text:
                    return text
            except FileNotFoundError:
                pass
        return _PROBE_SYSTEM

    def _instruction(self, stage: str) -> str:
        path = self.settings.prompt_dir / f"{stage}.txt" if self.settings.prompt_dir else None
        if path is not None:
            try:
                text = path.read_text(encoding="utf-8").strip()
                if text:
                    return text
            except FileNotFoundError:
                pass
        return _FALLBACK_PROMPTS[stage]

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
        return "\n".join(f"{t.index}={t.text}" for t in tokens)

    @staticmethod
    def _is_word_token(token: _SourceToken) -> bool:
        return bool(re.search(r"\w", token.text, flags=re.UNICODE))

    @classmethod
    def _scalar(cls, raw: str) -> str:
        lines = [line.strip() for line in raw.strip().splitlines() if line.strip()]
        if len(lines) != 1:
            raise AdaptiveParseError("expected exactly one short answer")
        value = lines[0]
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"', "`"}:
            value = value[1:-1].strip()
        value = re.sub(r"[\s\.\,\:;!\?…]+$", "", value).strip()
        if not value:
            raise AdaptiveParseError("expected exactly one short answer")
        return value

    @classmethod
    def _integer(cls, raw: str) -> int:
        value = cls._scalar(raw).replace("−", "-")
        if re.fullmatch(r"-?\d+", value) is None:
            raise AdaptiveParseError("expected one integer option number")
        return int(value)

    @classmethod
    def _number_choice(cls, raw: str, choices: dict[int, T]) -> T:
        number = cls._integer(raw)
        if number not in choices:
            allowed = ", ".join(str(n) for n in sorted(choices))
            raise AdaptiveParseError(f"expected one option number: {allowed}")
        return choices[number]

    @classmethod
    def _bit(cls, raw: str) -> int:
        number = cls._integer(raw)
        if number not in {0, 1}:
            raise AdaptiveParseError("expected 0 or 1")
        return number

    @classmethod
    def _english_symbol(cls, raw: str) -> str:
        value = cls._scalar(raw).strip().lower().replace("-", "_").replace(" ", "_")
        value = cls._IRREGULAR_EN.get(value, value)
        if cls._EN_SYMBOL_RE.fullmatch(value) is None:
            raise AdaptiveParseError("expected one lowercase English ASCII predicate label")
        return value

    @staticmethod
    def _display_answer(value: Any) -> str:
        if isinstance(value, ActantRole):
            return value.value
        if isinstance(value, QueryMode):
            return value.value
        return str(value)

    def _predicate_start_choice(
        self,
        raw: str,
        tokens: tuple[_SourceToken, ...],
        excluded: list[_Span],
    ) -> int:
        choices = {-1: -1, 0: 0}
        for token in tokens:
            if not self._is_word_token(token):
                continue
            if any(span.start_index <= token.index <= span.end_index for span in excluded):
                continue
            choices[token.index] = token.index
        return self._number_choice(raw, choices)

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

    @classmethod
    def _deterministic_negation(
        cls,
        tokens: tuple[_SourceToken, ...],
        predicate: _Span | None,
    ) -> bool | None:
        markers = [token for token in tokens if token.text.casefold() in _NEGATION_MARKERS]
        if not markers:
            return False
        if predicate is not None:
            previous = predicate.start_index - 1
            if previous >= 1 and tokens[previous - 1].text.casefold() == "не":
                return True
            if any(token.text.casefold() == "не" and predicate.start_index <= token.index <= predicate.end_index for token in markers):
                return True
        if any(token.text.casefold() == "нет" for token in markers):
            return True
        # Other negative pronouns/adverbs can interact with scope; ask one binary probe.
        return None

    @staticmethod
    def _options_lines(options: dict[int, str]) -> str:
        return "\n".join(f"{number} = {description}" for number, description in options.items())

    def _act_type_prompt(self, text: str, tokens: tuple[_SourceToken, ...], excluded: list[_Span]) -> str:
        options = {
            0: "none or unclear",
            1: "states information as a claim/fact",
            2: "asks for information",
            3: "requests or orders an action",
        }
        lines = [f"TEXT:\n{text}"]
        if excluded:
            lines.append("ALREADY_PARSED: " + ", ".join(span.text for span in excluded))
        lines.append("OPTIONS:\n" + self._options_lines(options))
        return "\n".join(lines)

    def _predicate_start_prompt(self, text: str, tokens: tuple[_SourceToken, ...], excluded: list[_Span]) -> str:
        options: dict[int, str] = {
            -1: "no meaningful predicate exists",
            0: "predicate is understood but not written as a token",
        }
        for token in tokens:
            if not self._is_word_token(token):
                continue
            if any(span.start_index <= token.index <= span.end_index for span in excluded):
                continue
            options[token.index] = f"token {token.index}: {token.text}"
        lines = [f"TEXT:\n{text}", f"TOKENS:\n{self._tokens_text(tokens)}", "OPTIONS:\n" + self._options_lines(options)]
        return "\n".join(lines)

    def _predicate_end_prompt(
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
            f"PREDICATE_START: {start} = {tokens[start - 1].text}\nOPTIONS:\n{self._options_lines(options)}"
        )

    @staticmethod
    def _predicate_symbol_prompt(text: str, target: str, *, implicit: bool) -> str:
        marker = "implicit predicate of the sentence" if implicit else target
        return f"TEXT:\n{text}\nTARGET:\n{marker}"

    @staticmethod
    def _negation_prompt(text: str, predicate: PredicateCandidate) -> str:
        return f"TEXT:\n{text}\nPREDICATE:\n{predicate.surface}\nOPTIONS:\n0 = not negated\n1 = explicitly negated"

    @staticmethod
    def _query_mode_prompt(text: str, predicate: PredicateCandidate) -> str:
        return (
            f"TEXT:\n{text}\nPREDICATE:\n{predicate.surface}\nOPTIONS:\n"
            "1 = asks whether the proposition is true / exists (yes-no)\n"
            "2 = asks for a missing value such as who, what, where, when, why, how, or how much"
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
    def _role_family_prompt(
        text: str,
        predicate: PredicateCandidate,
        span: _Span,
        groups: list[tuple[str, tuple[tuple[ActantRole, str], ...]]],
        *,
        requested: bool,
    ) -> str:
        options = {
            i: f"{_ROLE_FAMILY_DESCRIPTIONS[name]}"
            for i, (name, _entries) in enumerate(groups, start=1)
        }
        mode = "MISSING INFORMATION" if requested else "TARGET"
        return (
            f"TEXT:\n{text}\nPREDICATE:\n{predicate.surface}\n{mode}:\n{span.text}\n"
            "OPTIONS:\n" + "\n".join(f"{n} = {d}" for n, d in options.items())
        )

    @staticmethod
    def _role_exact_prompt(
        text: str,
        predicate: PredicateCandidate,
        span: _Span,
        group_name: str,
        entries: tuple[tuple[ActantRole, str], ...],
        *,
        requested: bool,
    ) -> str:
        options = {
            i: f"{description}"
            for i, (role, description) in enumerate(entries, start=1)
        }
        mode = "MISSING INFORMATION" if requested else "TARGET"
        return (
            f"TEXT:\n{text}\nPREDICATE:\n{predicate.surface}\n{mode}:\n{span.text}\n"
            "OPTIONS:\n"
            + "\n".join(f"{n} = {d}" for n, d in options.items())
        )

    @staticmethod
    def _requested_role_prompt(text: str, predicate: PredicateCandidate, span: _Span) -> str:
        return f"TEXT:\n{text}\nPREDICATE:\n{predicate.surface}\nQUESTION_WORD:\n{span.text}"
