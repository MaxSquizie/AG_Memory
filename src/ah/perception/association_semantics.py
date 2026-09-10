from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from ah.llm.process_backend import LLMResponse
from ah.model import ActantRole

from .contracts import ActantCandidate, CommandCandidate, QueryCandidate
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
class AssociationQueryDecision:
    """UID-free endpoint choice for one associative-search speech act."""

    left_role: ActantRole
    right_role: ActantRole

    def __post_init__(self) -> None:
        if self.left_role is self.right_role:
            raise ValueError("association endpoints must use different actant roles")


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

    Deterministic code supplies only already parsed explicit actants and local E1/E2
    labels. The model never sees AH UIDs and never constructs AssociationGoal. The
    output vocabulary is finite for the current act: ORDINARY, UNKNOWN, or one of
    the enumerated ASSOCIATION:Ea:Eb endpoint pairs.
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
    def _candidate_actants(
        actants: tuple[ActantCandidate, ...],
    ) -> tuple[ActantCandidate, ...]:
        # Association endpoints here are explicit entity/concept mentions. Compound
        # proposition/composition endpoints need a separate typed contract; do not
        # flatten them into entities merely to make the goal compile.
        result: list[ActantCandidate] = []
        seen_roles: set[ActantRole] = set()
        for actant in actants:
            if actant.role in seen_roles:
                continue
            if (
                actant.proposition is not None
                or actant.composition is not None
                or actant.candidate_ref is not None
                or not actant.lookup_text
            ):
                continue
            seen_roles.add(actant.role)
            result.append(actant)
        return tuple(result)

    def classify(
        self,
        source_text: str,
        act: QueryCandidate | CommandCandidate,
    ) -> tuple[AssociationQueryDecision | None, tuple[AssociationProbeAttempt, ...]]:
        candidates = self._candidate_actants(act.actants)
        if len(candidates) < 2:
            return None, ()

        labels = tuple(f"E{index + 1}" for index in range(len(candidates)))
        role_by_label = {
            label: candidate.role for label, candidate in zip(labels, candidates)
        }
        pair_choices = tuple(
            f"ASSOCIATION:{labels[left]}:{labels[right]}"
            for left in range(len(labels))
            for right in range(left + 1, len(labels))
        )
        choices = ("ORDINARY", *pair_choices, "UNKNOWN")
        endpoint_lines = "\n".join(
            f"{label}: role={candidate.role.value}; text={candidate.lookup_text}"
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
                        "top_p": 1.0,
                        "top_k": 0,
                        "repetition_penalty": 1.0,
                        "no_repeat_ngram_size": 0,
                    },
                    role="perception",
                )
            except Exception as exc:
                # Model/backend failure is a perception-boundary failure. Do not let
                # a transport/runtime exception escape around orchestrator's normal
                # raw-H preservation path, and do not reinterpret it as ORDINARY.
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
                        role_by_label[left_label], role_by_label[right_label]
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
