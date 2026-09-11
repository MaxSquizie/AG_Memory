from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from ah.llm.process_backend import LLMResponse
from ah.model import ActantRole

from .contracts import (
    ActRelationCandidate,
    ActantCandidate,
    CommandCandidate,
    QueryCandidate,
)
from .llm_parser import (
    LLMPerceptionService as _BaseLLMPerceptionService,
    PerceptionAttemptDiagnostic,
    PerceptionParseError,
)


class _TextGenerator(Protocol):
    def generate(
        self,
        prompt: str,
        *,
        system: str = "",
        override: dict | None = None,
        role: str = "generic",
    ) -> LLMResponse: ...


@dataclass(frozen=True, slots=True)
class AssociationEndpointSelector:
    """UID-free address of one endpoint inside an already parsed act.

    ``member_index`` is zero-based and is present only when the endpoint is one
    member of an ActantCompositionCandidate. This lets ``A и B`` remain one
    syntactic actant while association can still target A and B independently.
    """

    role: ActantRole
    member_index: int | None = None

    def __post_init__(self) -> None:
        if self.member_index is not None and self.member_index < 0:
            raise ValueError("association member_index must be >= 0")


@dataclass(frozen=True, slots=True)
class AssociationQueryDecision:
    """UID-free endpoint choice for one associative-search speech act."""

    left: AssociationEndpointSelector
    right: AssociationEndpointSelector

    def __post_init__(self) -> None:
        if self.left == self.right:
            raise ValueError("association endpoints must be distinct")

    @property
    def left_role(self) -> ActantRole:
        return self.left.role

    @property
    def right_role(self) -> ActantRole:
        return self.right.role


@dataclass(frozen=True, slots=True)
class AssociationActRelationCandidate(ActRelationCandidate):
    """Typed runtime ASSOCIATION marker with optional composition-member selectors.

    It deliberately subclasses ActRelationCandidate so PerceptionResult keeps its
    existing contract. Unlike an ordinary intra-act relation, two endpoints may use
    the same semantic role when they address different members of one composition.
    """

    source_member_index: int | None = None
    target_member_index: int | None = None

    def __post_init__(self) -> None:
        if self.canonical_relation_id != "ASSOCIATION":
            raise ValueError("AssociationActRelationCandidate requires ASSOCIATION")
        if not self.act_ref.strip():
            raise ValueError("AssociationActRelationCandidate.act_ref must be non-empty")
        for value in (self.source_member_index, self.target_member_index):
            if value is not None and value < 0:
                raise ValueError("association member indexes must be >= 0")
        if (
            self.source_role is self.target_role
            and self.source_member_index == self.target_member_index
        ):
            raise ValueError("association endpoint selectors must be distinct")

    @property
    def source_selector(self) -> AssociationEndpointSelector:
        return AssociationEndpointSelector(self.source_role, self.source_member_index)

    @property
    def target_selector(self) -> AssociationEndpointSelector:
        return AssociationEndpointSelector(self.target_role, self.target_member_index)


@dataclass(frozen=True, slots=True)
class _EndpointCandidate:
    selector: AssociationEndpointSelector
    text: str


@dataclass(frozen=True, slots=True)
class AssociationProbeAttempt:
    raw_text: str
    normalized_answer: str | None
    error: str | None
    retry_index: int


class AssociationProbeError(ValueError):
    def __init__(
        self,
        message: str,
        attempts: tuple[AssociationProbeAttempt, ...] = (),
    ) -> None:
        super().__init__(message)
        self.attempts = attempts


class AssociationSemanticClassifier:
    """One bounded semantic decision: ordinary query vs associative connection.

    Deterministic parsing enumerates source-grounded endpoint candidates first. The
    model sees only local E1/E2 labels plus human-readable source text; it never sees
    canonical UIDs and never constructs AssociationGoal. Output is one finite cue:
    ORDINARY, UNKNOWN, or ASSOCIATION:Ea:Eb.
    """

    PROMPT_NAME = "association_query.txt"

    def __init__(
        self,
        backend: _TextGenerator,
        prompt_dir: Path | None,
        *,
        retry_attempts: int = 1,
    ) -> None:
        if retry_attempts < 0 or retry_attempts > 2:
            raise ValueError("association retry_attempts must be in [0, 2]")
        self.backend = backend
        self.prompt_dir = prompt_dir
        self.retry_attempts = retry_attempts

    def _system_prompt(self) -> str:
        if self.prompt_dir is None:
            raise AssociationProbeError(
                "association semantic probe requires perception probe_prompt_dir"
            )
        path = self.prompt_dir / self.PROMPT_NAME
        try:
            text = path.read_text(encoding="utf-8").strip()
        except FileNotFoundError as exc:
            raise AssociationProbeError(
                f"missing association semantic prompt: {path}"
            ) from exc
        if not text:
            raise AssociationProbeError(
                f"empty association semantic prompt: {path}"
            )
        return text

    @staticmethod
    def _direct_endpoint_text(actant: ActantCandidate) -> str:
        if actant.evidence is not None and actant.evidence.text.strip():
            return actant.evidence.text.strip()
        if actant.lookup_text:
            return actant.lookup_text
        if actant.proposition is not None:
            return "proposition expressed by this actant in TEXT"
        if actant.candidate_ref is not None:
            return "proposition referenced by this actant in TEXT"
        if actant.entity_ref is not None:
            return "entity referenced by this actant in TEXT"
        return "endpoint expressed by this actant in TEXT"

    @classmethod
    def endpoint_candidates(
        cls,
        actants: tuple[ActantCandidate, ...],
    ) -> tuple[_EndpointCandidate, ...]:
        """Enumerate endpoints from parser structure, never from lexical markers."""
        result: list[_EndpointCandidate] = []
        seen: set[AssociationEndpointSelector] = set()
        for actant in actants:
            if actant.composition is not None:
                for index, member in enumerate(actant.composition.members):
                    selector = AssociationEndpointSelector(actant.role, index)
                    if selector in seen:
                        continue
                    seen.add(selector)
                    result.append(_EndpointCandidate(selector, member.lookup_text))
                continue
            selector = AssociationEndpointSelector(actant.role)
            if selector in seen:
                continue
            seen.add(selector)
            result.append(
                _EndpointCandidate(selector, cls._direct_endpoint_text(actant))
            )
        return tuple(result)

    def classify(
        self,
        source_text: str,
        act: QueryCandidate | CommandCandidate,
    ) -> tuple[AssociationQueryDecision | None, tuple[AssociationProbeAttempt, ...]]:
        candidates = self.endpoint_candidates(act.actants)
        if len(candidates) < 2:
            return None, ()

        labels = tuple(f"E{index + 1}" for index in range(len(candidates)))
        endpoint_by_label = {
            label: candidate for label, candidate in zip(labels, candidates)
        }
        pair_choices = tuple(
            f"ASSOCIATION:{labels[left]}:{labels[right]}"
            for left in range(len(labels))
            for right in range(left + 1, len(labels))
        )
        choices = ("ORDINARY", *pair_choices, "UNKNOWN")
        endpoint_lines = "\n".join(
            f"{label}: role={candidate.selector.role.value}; text={candidate.text}"
            for label, candidate in zip(labels, candidates)
        )
        act_kind = "QUERY" if isinstance(act, QueryCandidate) else "COMMAND"
        prompt = (
            f"TEXT:\n{source_text}\nACT TYPE:\n{act_kind}\n"
            f"PREDICATE:\n{act.predicate.surface}\n"
            f"EXPLICIT ENDPOINT CANDIDATES:\n{endpoint_lines}\n"
            "CHOICES:\n" + "\n".join(choices)
        )
        system = self._system_prompt()
        attempts: list[AssociationProbeAttempt] = []

        for retry_index in range(self.retry_attempts + 1):
            try:
                response = self.backend.generate(
                    prompt,
                    system=system,
                    override={
                        "max_new_tokens": 12,
                        "temperature": 0.0,
                        "repetition_penalty": 1.0,
                        "no_repeat_ngram_size": 0,
                        "enable_thinking": False,
                    },
                    role="semantic_association_query",
                )
            except Exception as exc:
                attempts.append(
                    AssociationProbeAttempt(
                        "",
                        None,
                        f"backend:{type(exc).__name__}:{exc}",
                        retry_index,
                    )
                )
                raise AssociationProbeError(
                    "association semantic probe backend failed",
                    tuple(attempts),
                ) from exc

            label = response.text.strip().upper()
            if label in choices:
                attempts.append(
                    AssociationProbeAttempt(response.text, label, None, retry_index)
                )
                if label == "ORDINARY":
                    return None, tuple(attempts)
                if label == "UNKNOWN":
                    raise AssociationProbeError(
                        "association query intent/endpoints are semantically unresolved",
                        tuple(attempts),
                    )
                _, left_label, right_label = label.split(":", 2)
                return (
                    AssociationQueryDecision(
                        endpoint_by_label[left_label].selector,
                        endpoint_by_label[right_label].selector,
                    ),
                    tuple(attempts),
                )

            error = "expected exactly one enumerated association-query choice"
            attempts.append(
                AssociationProbeAttempt(response.text, None, error, retry_index)
            )
            if retry_index < self.retry_attempts:
                prompt = (
                    prompt
                    + "\nRETRY CONSTRAINT:\nYour previous answer was invalid. "
                    "Return exactly one line copied from CHOICES and nothing else."
                )

        raise AssociationProbeError(
            "association semantic probe returned no valid bounded choice",
            tuple(attempts),
        )


class AssociationLLMPerceptionService(_BaseLLMPerceptionService):
    """Public perception service extension for the point-6 association micro-probe."""

    def classify_association_query(
        self,
        source_text: str,
        act: QueryCandidate | CommandCandidate,
    ) -> AssociationQueryDecision | None:
        if self.settings.protocol not in {"adaptive_v1", "adaptive_v2", "adaptive_v3"}:
            return None
        classifier = AssociationSemanticClassifier(
            self.backend,
            self.settings.probe_prompt_dir,
            retry_attempts=self.settings.probe_retry_attempts,
        )
        try:
            decision, _attempts = classifier.classify(source_text, act)
            return decision
        except AssociationProbeError as exc:
            attempts = [
                PerceptionAttemptDiagnostic(
                    role="association_query",
                    raw_text=item.raw_text,
                    error=item.error,
                    prompt="",
                    normalized_answer=item.normalized_answer,
                    retry_index=item.retry_index,
                )
                for item in exc.attempts
            ]
            self._record_diagnostic(source_text, attempts, None, str(exc))
            raise PerceptionParseError(str(exc)) from exc
