from __future__ import annotations

from dataclasses import replace
from typing import Protocol

from ah.llm.process_backend import LLMResponse

from .association_semantics import AssociationLLMPerceptionService
from .contracts import ActantCandidate, AssertionCandidate, PerceptionResult
from .llm_parser import PerceptionAttemptDiagnostic, PerceptionParseError


class _TextGenerator(Protocol):
    def generate(
        self,
        prompt: str,
        *,
        system: str = "",
        override: dict | None = None,
        role: str = "generic",
    ) -> LLMResponse: ...


def _actant_key(item: ActantCandidate) -> tuple[object, ...]:
    if item.entity_ref is not None:
        return ("entity_ref", item.entity_ref)
    if item.candidate_ref is not None:
        return ("candidate_ref", item.candidate_ref)
    if item.composition is not None:
        return ("composition", repr(item.composition))
    if item.proposition is not None:
        return ("proposition", repr(item.proposition))
    return ("mention", (item.lookup_text or "").strip().casefold())


def _varying_roles(
    variants: tuple[AssertionCandidate, ...],
) -> tuple[str, ...]:
    if len(variants) < 2:
        return ()
    role_maps = [{item.role.value: item for item in variant.actants} for variant in variants]
    role_sets = {tuple(sorted(mapping)) for mapping in role_maps}
    if len(role_sets) != 1:
        return ()
    roles: list[str] = []
    for role in sorted(role_maps[0]):
        if len({_actant_key(mapping[role]) for mapping in role_maps}) > 1:
            roles.append(role)
    return tuple(roles)


def _variant_text(variant: AssertionCandidate) -> str:
    rows = []
    for actant in variant.actants:
        value = (actant.lookup_text or "").strip()
        if not value:
            value = "[referent chosen by this reading]"
        rows.append(f"{actant.role.value}={value}")
    return "; ".join(rows)


class CorrelatedAlternativeLLMPerceptionService(AssociationLLMPerceptionService):
    """Resolve only whole-frame correlated runtime alternatives.

    The deterministic parser owns candidate generation.  This layer is invoked only
    when two or more semantic roles vary *together* across complete frame readings.
    Choosing those roles independently would create a Cartesian product that the
    source never proposed, while Integration intentionally supports only independent
    one-role ambiguity.  The model therefore sees opaque A1/A2/... labels for the
    complete readings and can return only one label or UNKNOWN.

    UNKNOWN and malformed protocol output remain fail-closed.  No AH UID, canonical
    entity identity, template UID, or mutation is exposed to the probe.
    """

    PROMPT_NAME = "correlated_frame_choice.txt"

    def parse(self, text, interaction_context):
        result = super().parse(text, interaction_context)
        return self._resolve_correlated_alternatives(text, result)

    def parse_with_structural_resolution(
        self, text, interaction_context, resolution_key
    ):
        result = super().parse_with_structural_resolution(
            text, interaction_context, resolution_key
        )
        return self._resolve_correlated_alternatives(text, result)

    def _resolve_correlated_alternatives(
        self,
        source_text: str,
        result: PerceptionResult,
    ) -> PerceptionResult:
        if self.settings.protocol not in {"adaptive_v1", "adaptive_v2", "adaptive_v3"}:
            return result
        assertions: list[AssertionCandidate] = []
        changed = False
        for assertion in result.assertions:
            variants = assertion.alternatives
            varying = _varying_roles(variants)
            # A single varying role is already canonicalizable by Integration as
            # k_AMBIGUOUS.  Zero varying roles need no semantic decision either.
            if len(varying) <= 1:
                assertions.append(assertion)
                continue
            chosen = self._choose_correlated_frame(source_text, assertion, varying)
            assertions.append(replace(chosen, local_id=assertion.local_id, alternatives=()))
            changed = True
        return replace(result, assertions=tuple(assertions)) if changed else result

    def _choose_correlated_frame(
        self,
        source_text: str,
        assertion: AssertionCandidate,
        varying_roles: tuple[str, ...],
    ) -> AssertionCandidate:
        variants = assertion.alternatives
        if len(variants) < 2:
            return assertion
        if self.settings.probe_prompt_dir is None:
            raise PerceptionParseError(
                "correlated frame resolution requires perception probe_prompt_dir"
            )
        prompt_path = self.settings.probe_prompt_dir / self.PROMPT_NAME
        try:
            system = prompt_path.read_text(encoding="utf-8").strip()
        except FileNotFoundError as exc:
            raise PerceptionParseError(
                f"missing correlated-frame prompt: {prompt_path}"
            ) from exc
        if not system:
            raise PerceptionParseError(
                f"empty correlated-frame prompt: {prompt_path}"
            )

        labels = tuple(f"A{index}" for index in range(1, len(variants) + 1))
        choices = (*labels, "UNKNOWN")
        frames = "\n".join(
            f"{label}: {_variant_text(variant)}"
            for label, variant in zip(labels, variants)
        )
        prompt = (
            f"TEXT:\n{source_text}\n"
            f"PREDICATE:\n{assertion.predicate.surface}\n"
            f"CORRELATED ROLES:\n{', '.join(varying_roles)}\n"
            f"COMPLETE READINGS:\n{frames}\n"
            "CHOICES:\n" + "\n".join(choices)
        )
        attempts: list[PerceptionAttemptDiagnostic] = []
        for retry_index in range(self.settings.probe_retry_attempts + 1):
            try:
                response = self.backend.generate(
                    prompt,
                    system=system,
                    override={
                        "max_new_tokens": 8,
                        "temperature": 0.0,
                        "repetition_penalty": 1.0,
                        "no_repeat_ngram_size": 0,
                        "enable_thinking": False,
                    },
                    role="semantic_correlated_frame",
                )
            except Exception as exc:
                attempts.append(
                    PerceptionAttemptDiagnostic(
                        role="correlated_frame",
                        raw_text="",
                        error=f"backend:{type(exc).__name__}:{exc}",
                        prompt=prompt,
                        retry_index=retry_index,
                    )
                )
                self._record_diagnostic(source_text, attempts, None, str(exc))
                raise PerceptionParseError(
                    "correlated frame semantic probe backend failed"
                ) from exc

            label = response.text.strip().upper()
            if label in labels:
                return variants[labels.index(label)]
            if label == "UNKNOWN":
                attempts.append(
                    PerceptionAttemptDiagnostic(
                        role="correlated_frame",
                        raw_text=response.text,
                        normalized_answer=label,
                        prompt=prompt,
                        retry_index=retry_index,
                    )
                )
                message = "correlated frame readings remain semantically unresolved"
                self._record_diagnostic(source_text, attempts, None, message)
                raise PerceptionParseError(message)

            attempts.append(
                PerceptionAttemptDiagnostic(
                    role="correlated_frame",
                    raw_text=response.text,
                    error="expected exactly one correlated-frame choice",
                    prompt=prompt,
                    retry_index=retry_index,
                )
            )
            if retry_index < self.settings.probe_retry_attempts:
                prompt = (
                    prompt
                    + "\nRETRY CONSTRAINT:\nReturn exactly one line copied from CHOICES."
                )

        message = "correlated frame semantic probe returned no valid bounded choice"
        self._record_diagnostic(source_text, attempts, None, message)
        raise PerceptionParseError(message)
