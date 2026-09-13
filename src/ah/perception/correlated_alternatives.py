from __future__ import annotations

from dataclasses import replace
from typing import Protocol

from ah.llm.process_backend import LLMResponse

from .adaptive_parser import (
    AdaptiveParseError,
    AdaptiveSettings,
    AdaptiveStructuralClarificationRequired,
)
from .association_semantics import AssociationLLMPerceptionService
from .contracts import ActantCandidate, AssertionCandidate, PerceptionResult
from .lexical_recovery import EmbeddingSemanticReranker
from .llm_parser import (
    PerceptionAttemptDiagnostic,
    PerceptionClarificationRequired,
    PerceptionParseError,
)
from .probe_protocol import (
    CHOICE_MAX_NEW_TOKENS,
    ProbeProtocolError,
    compose_choice_prompt,
    decode_choice,
)
from .structural_speech_act import StructuralSpeechActAdaptiveParser


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


def _source_referent_labels(
    result: PerceptionResult,
) -> dict[str, tuple[str, str | None]]:
    """Assign UID-free labels to local refs and ground them in source mentions."""

    mentions: dict[str, list[tuple[int, str]]] = {}
    order: list[str] = []
    for assertion in result.assertions:
        variants = (replace(assertion, alternatives=()), *assertion.alternatives)
        for variant in variants:
            for actant in variant.actants:
                ref = actant.entity_ref
                if ref is None:
                    continue
                if ref not in mentions:
                    mentions[ref] = []
                    order.append(ref)
                value = (actant.lookup_text or "").strip()
                evidence = actant.evidence
                if value and evidence is not None and evidence.start is not None:
                    mentions[ref].append((evidence.start, value))

    ranked = sorted(
        order,
        key=lambda ref: (
            min((start for start, _value in mentions[ref]), default=10**12),
            order.index(ref),
        ),
    )
    labels: dict[str, tuple[str, str | None]] = {}
    for index, ref in enumerate(ranked, start=1):
        grounded = min(mentions[ref], default=None)
        labels[ref] = (
            f"R{index}",
            None if grounded is None else grounded[1],
        )
    return labels


def _variant_text(
    variant: AssertionCandidate,
    referent_labels: dict[str, tuple[str, str | None]],
) -> str:
    rows = []
    for actant in variant.actants:
        label = referent_labels.get(actant.entity_ref or "")
        if label is not None:
            local_label, grounded = label
            value = local_label if grounded is None else f"{local_label}[{grounded}]"
        else:
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
        if self.settings.protocol in {"adaptive_v1", "adaptive_v2", "adaptive_v3"}:
            result = self._parse_structural_adaptive(text)
        else:
            result = super().parse(text, interaction_context)
        return self._resolve_correlated_alternatives(text, result)

    def parse_with_structural_resolution(
        self, text, interaction_context, resolution_key
    ):
        if self.settings.protocol in {"adaptive_v1", "adaptive_v2", "adaptive_v3"}:
            result = self._parse_structural_adaptive(
                text, structural_resolution=resolution_key
            )
        else:
            result = super().parse_with_structural_resolution(
                text, interaction_context, resolution_key
            )
        return self._resolve_correlated_alternatives(text, result)

    def _parse_structural_adaptive(
        self,
        text: str,
        *,
        structural_resolution: str | None = None,
    ) -> PerceptionResult:
        """Run the normal adaptive pipeline with structural speech-act force.

        This is not a repair pass: the specialized parser is the only adaptive
        parser invoked for the turn.  It differs from the base class solely in
        punctuation-independent top-level interrogative recognition.
        """
        semantic_reranker = (
            EmbeddingSemanticReranker(self.backend)  # type: ignore[arg-type]
            if self.settings.embedding_model.strip()
            and callable(getattr(self.backend, "embed_texts", None))
            else None
        )
        parser = StructuralSpeechActAdaptiveParser(
            self.backend,
            AdaptiveSettings(
                prompt_dir=self.settings.probe_prompt_dir,
                generation=self.settings.generation,
                retry_attempts=self.settings.probe_retry_attempts,
                max_actants_per_act=self.settings.max_actants_per_act,
                predicate_symbol_language=self.settings.predicate_symbol_language,
                morphology_backend=self.settings.morphology_backend,
                verify_predicate_symbol=(self.settings.protocol == "adaptive_v3"),
            ),
            semantic_reranker=semantic_reranker,
        )
        try:
            parsed = parser.parse(text, structural_resolution=structural_resolution)
        except AdaptiveStructuralClarificationRequired as exc:
            attempts = [
                PerceptionAttemptDiagnostic(
                    role=trace.stage,
                    raw_text=trace.raw_text,
                    error=trace.error,
                    prompt=trace.prompt,
                    normalized_answer=trace.normalized_answer,
                    retry_index=trace.retry_index,
                )
                for trace in exc.traces
            ]
            self._record_diagnostic(text, attempts, None, str(exc))
            raise PerceptionClarificationRequired(exc.spec) from exc
        except AdaptiveParseError as exc:
            attempts = [
                PerceptionAttemptDiagnostic(
                    role=trace.stage,
                    raw_text=trace.raw_text,
                    error=trace.error,
                    prompt=trace.prompt,
                    normalized_answer=trace.normalized_answer,
                    retry_index=trace.retry_index,
                )
                for trace in exc.traces
            ]
            final_error = str(exc)
            self._record_diagnostic(text, attempts, None, final_error)
            raise PerceptionParseError(final_error) from exc

        attempts = [
            PerceptionAttemptDiagnostic(
                role=trace.stage,
                raw_text=trace.raw_text,
                error=trace.error,
                prompt=trace.prompt,
                normalized_answer=trace.normalized_answer,
                retry_index=trace.retry_index,
            )
            for trace in parsed.traces
        ]
        self._record_diagnostic(text, attempts, parsed.perception)
        return parsed.perception

    def _resolve_correlated_alternatives(
        self,
        source_text: str,
        result: PerceptionResult,
    ) -> PerceptionResult:
        if self.settings.protocol not in {"adaptive_v1", "adaptive_v2", "adaptive_v3"}:
            return result
        assertions: list[AssertionCandidate] = []
        changed = False
        referent_labels = _source_referent_labels(result)
        for assertion in result.assertions:
            variants = assertion.alternatives
            varying = _varying_roles(variants)
            # A single varying role is already canonicalizable by Integration as
            # k_AMBIGUOUS.  Zero varying roles need no semantic decision either.
            if len(varying) <= 1:
                assertions.append(assertion)
                continue
            chosen = self._choose_correlated_frame(
                source_text,
                assertion,
                varying,
                referent_labels,
            )
            assertions.append(replace(chosen, local_id=assertion.local_id, alternatives=()))
            changed = True
        return replace(result, assertions=tuple(assertions)) if changed else result

    def _choose_correlated_frame(
        self,
        source_text: str,
        assertion: AssertionCandidate,
        varying_roles: tuple[str, ...],
        referent_labels: dict[str, tuple[str, str | None]],
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
            instruction = prompt_path.read_text(encoding="utf-8").strip()
        except FileNotFoundError as exc:
            raise PerceptionParseError(
                f"missing correlated-frame prompt: {prompt_path}"
            ) from exc
        if not instruction:
            raise PerceptionParseError(
                f"empty correlated-frame prompt: {prompt_path}"
            )
        system_path = self.settings.probe_prompt_dir / "probe_system.txt"
        try:
            system = system_path.read_text(encoding="utf-8").strip()
        except FileNotFoundError as exc:
            raise PerceptionParseError(
                f"missing shared probe system prompt: {system_path}"
            ) from exc
        if not system:
            raise PerceptionParseError(
                f"empty shared probe system prompt: {system_path}"
            )

        labels = tuple(f"A{index}" for index in range(1, len(variants) + 1))
        choices = (*labels, "UNKNOWN")
        frames = "\n".join(
            f"{label}: {_variant_text(variant, referent_labels)}"
            for label, variant in zip(labels, variants)
        )
        context = (
            f"TEXT:\n{source_text}\n"
            f"PREDICATE:\n{assertion.predicate.surface}\n"
            f"CORRELATED ROLES:\n{', '.join(varying_roles)}\n"
            f"COMPLETE READINGS:\n{frames}"
        )
        attempts: list[PerceptionAttemptDiagnostic] = []
        for retry_index in range(self.settings.probe_retry_attempts + 1):
            try:
                prompt = compose_choice_prompt(
                    context,
                    instruction,
                    choices,
                    retry=retry_index > 0,
                )
            except ProbeProtocolError as exc:
                raise PerceptionParseError(
                    f"invalid correlated-frame choice protocol: {exc}"
                ) from exc
            try:
                response = self.backend.generate(
                    prompt,
                    system=system,
                    override={
                        "max_new_tokens": CHOICE_MAX_NEW_TOKENS,
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

            try:
                label = decode_choice(response.text, choices)
            except ProbeProtocolError:
                label = None
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

        message = "correlated frame semantic probe returned no valid bounded choice"
        self._record_diagnostic(source_text, attempts, None, message)
        raise PerceptionParseError(message)
