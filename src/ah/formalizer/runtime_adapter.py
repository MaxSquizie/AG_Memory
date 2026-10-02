# -*- coding: utf-8 -*-
"""FormalizerAdapter — path B replacement seam (V7 §14 / integration).

Replaces :class:`ah.perception.adaptive_parser.AdaptivePerceptionParser` as the perception→formalization
entry point while leaving ``IntegrationService`` and the canonical store UNTOUCHED: it runs the new
formalizer vertical (T0..T6b) and translates its :class:`~ah.formalizer.state.FormalizationState` into the
product's :class:`ah.perception.contracts.PerceptionResult`, so ``integrate_external()`` consumes it exactly
as before. Role assignment is STRUCTURAL (derived from the frame construction declared in T2), never a
per-word rule — consistent with the two-tier invariant.

Slice 1 (this file): resolved predicate_value decisions -> assertions. Queries / quantifiers / temporal are
subsequent slices; until wired they surface as honest diagnostics, not fabricated candidates (V7 §0.8).
"""

from __future__ import annotations

# Declared relation labels for the demo-boundary closed set (already declared in decision_schema_v1.json).
_PREDICATE_LABELS = {"V1": "HAVE", "V2": "HAS_PART", "V3": "LOCATIVE", "V4": "LIKE"}


class FormalizerAdapter:
    """Drop-in replacement for AdaptivePerceptionParser.parse(): text -> PerceptionResult.

    ``selector`` is any object with ``select(prompt) -> raw JSON string`` (RealBackendSelector in production,
    FakeSelector.demo() in the deterministic dry run). ``morph``/``schema`` are optional overrides."""

    def __init__(self, selector, morph=None, schema=None):
        self._selector = selector
        self._morph = morph
        self._schema = schema  # lazily loaded if None

    # -- public entry (mirrors AdaptivePerceptionParser.parse) -------------- #
    def parse(self, text: str, context_facts: tuple[str, ...] = ()) -> "PerceptionResult":
        from ah.formalizer.pipeline import run as _run
        from ah.formalizer.selection_protocol import load_decision_schema

        schema = self._schema or load_decision_schema()
        state = _run(text, schema, self._selector, morph=self._morph, context_facts=context_facts)
        return self._to_perception_result(state)

    # -- translation: FormalizationState -> PerceptionResult --------------- #
    def _to_perception_result(self, state):
        from ah.perception.contracts import (
            ActantCandidate,
            AssertionCandidate,
            EvidenceSpan,
            PerceptionResult,
            PredicateCandidate,
        )

        assertions = []
        notes: list[str] = []
        for frame in state.frames:
            dec = state.decisions.get(f"{frame.frame_id}|predicate_value")
            if dec is None or not dec.selected:
                continue  # no candidate selected -> honest miss, never fabricated
            # A single assertion is emitted ONLY for a RESOLVED unique pick. An AMBIGUOUS/UNRESOLVED
            # decision is NOT collapsed to its first value (that would fabricate a fact); it is surfaced
            # as an explicit unresolved note so downstream sees honest incompleteness, not silence.
            if dec.outcome == "RESOLVED" and len(dec.selected) == 1:
                value = dec.selected[0]
                actant_pairs = self._assign_roles(frame, state)
                roles = tuple(role for role, _ in actant_pairs)
                predicate = self._build_predicate(frame, state, value, roles)
                actants = tuple(ActantCandidate(role=role, mention=mention) for role, mention in actant_pairs)
                assertions.append(AssertionCandidate(local_id=f"{frame.frame_id}:A0", predicate=predicate, actants=actants))
            else:
                notes.append(f"UNRESOLVED_PREDICATE {frame.frame_id}: outcome={dec.outcome} selected={list(dec.selected)}")

        diagnostics = tuple(f"{d.code}: {d.detail}" for d in state.diagnostics) + tuple(notes)
        return PerceptionResult(source_text=state.text, assertions=tuple(assertions), diagnostics=diagnostics)

    # -- predicate: real verb when present, else a declared STRUCTURAL predicate ---- #
    def _build_predicate(self, frame, state, value, roles=()):
        from ah.perception.contracts import EvidenceSpan, PredicateCandidate, TemplateCandidate

        # The frame's role structure IS the valency declaration: integration needs a TemplateCandidate
        # to materialize an unknown predicate (structural rule, no LLM probe).
        template = TemplateCandidate(tuple(roles)) if roles else None
        for ev in state.evidence:
            for var in ev.variants:
                if var.pos == "VERB":  # verbal frame: carry the real surface + lemma
                    return PredicateCandidate(
                        surface=ev.span,
                        normalized_hint=var.lemma,
                        evidence=EvidenceSpan(text=ev.span),
                        template_candidate=template,
                    )
        # relation-only frame (copula/ellipsis): a declared STRUCTURAL predicate, never a fake lexeme.
        label = _PREDICATE_LABELS.get(value, value)
        return PredicateCandidate(
            surface=label, normalized_hint=value, sense_hint=f"STRUCTURAL_{label}", template_candidate=template
        )

    # -- declared structural role assignment (from T2 frame construction) -- #
    def _assign_roles(self, frame, state):
        from ah.model.types import ActantRole as R

        # The verbal predicate is NOT an actant: drop any participant that is a VERB in the evidence.
        verb_spans = {ev.span for ev in state.evidence if any(v.pos == "VERB" for v in ev.variants)}
        parts = [p for p in frame.participants if p not in verb_spans]
        if not parts:
            return []
        con = (frame.construction or "").upper()
        possessive = "GEN" in con and ("U+" in con or frame.copula_ellipsis)  # у+GEN+NOM / copula ellipsis
        locative = "LOC" in con or "PREP" in con
        if possessive:
            # whole-part / possession: possessor(whole)=SUBJECT, part(theme)=OBJECT (surface order)
            roles = [R.SUBJECT] + [R.OBJECT] * max(0, len(parts) - 1)
        elif locative:
            # locative: first nominal=SUBJECT (if any), the locative participant=LOCATION
            roles = [R.LOCATION] * len(parts)
            if len(parts) >= 2:
                roles[0] = R.SUBJECT
        else:
            # verbal frame (NOM+V+ACC ...): first nominal before the verb=SUBJECT, remainder=OBJECT
            roles = [R.SUBJECT] + [R.OBJECT] * max(0, len(parts) - 1)
        return list(zip(roles, parts))
