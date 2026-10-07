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

from dataclasses import dataclass, field

# Declared relation labels for the demo-boundary closed set (already declared in decision_schema_v1.json).
_PREDICATE_LABELS = {"V1": "HAVE", "V2": "HAS_PART", "V3": "LOCATIVE", "V4": "LIKE"}


@dataclass(frozen=True)
class NativePerceptionResult:
    """Outcome of the V7-native perception path (I01/I02): real input committed durably on the store.

    ``perception`` is the FULL candidate set (assertions/queries/commands/diagnostics via speech-act
    detection) — capability-complete vs the legacy parse(), so flipping the agent loop to it regresses
    nothing. The durable receipt fields below record which resolved assertion facts were committed; downstream
    reads those canonical facts from the store by ``observation_id`` (the "b" value-add: restart-safe).
    Legacy mode returns a bare PerceptionResult instead."""

    perception: object                  # full ah.perception.contracts.PerceptionResult
    observation_id: str
    version: int
    terminal: str                       # APPLIED | STALE_SUPERSEDED | REJECTED_ADMISSION
    committed_fragments: tuple[str, ...] = ()   # fragments whose FACT was asserted (T5)
    applied: bool = False               # fresh durable write (not an idempotent no-op)
    batch_hash: str = ""
    diagnostics: tuple[str, ...] = field(default_factory=tuple)


class FormalizerAdapter:
    """Drop-in replacement for AdaptivePerceptionParser.parse(): text -> PerceptionResult.

    ``selector`` is any object with ``select(prompt) -> raw JSON string`` (RealBackendSelector in production,
    FakeSelector.demo() in the deterministic dry run). ``morph``/``schema`` are optional overrides.

    Two modes:
      * legacy  — :meth:`parse` translates FormalizationState to a PerceptionResult for integrate_external();
      * native  — :meth:`interpret` runs the full V7 chain (T0..T4 -> C -> T5 gate + binding CAS -> T6 durable
        commit) on ``store`` and returns a NativePerceptionResult; downstream reads committed facts from the store.
    The native path is only available when a durable ``store`` + ``binding`` are wired (see bootstrap)."""

    def __init__(self, selector, morph=None, schema=None, store=None, binding=None):
        self._selector = selector
        self._morph = morph
        self._schema = schema  # lazily loaded if None
        self._store = store      # AHStoreAdapter (durable) — native path prerequisite
        self._binding = binding  # InterpretationRunBinding — native path prerequisite

    @property
    def native_available(self) -> bool:
        return self._store is not None and self._binding is not None

    # -- V7-native entry (I01): real input committed durably on the store ---- #
    def interpret(self, text: str, context_facts: tuple[str, ...] = ()) -> NativePerceptionResult:
        """Run one observation through T0..T4 -> C -> T5 gate (+binding CAS) -> T6 durable commit.

        Returns the receipt; downstream reads committed facts from ``self._store`` by observation_id."""
        if not self.native_available:
            raise RuntimeError("native commit path is not wired (no durable store/binding)")
        from ah.formalizer.selection_protocol import load_decision_schema
        from ah.formalizer.v7_pipeline import interpret_full

        schema = self._schema or load_decision_schema()
        state, rep = interpret_full(
            text, schema, self._selector, self._store, self._binding,
            morph=self._morph, context_facts=context_facts,
        )
        return NativePerceptionResult(
            perception=self._to_perception_result(state),   # full candidate set (I02: capability-complete)
            observation_id=rep.observation_id,
            version=rep.version,
            terminal=rep.terminal,
            committed_fragments=rep.committed_fragments,
            applied=rep.applied,
            batch_hash=rep.batch_hash,
            diagnostics=rep.diagnostics,
        )

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
            CommandCandidate,
            PerceptionResult,
            QueryCandidate,
            QueryMode,
        )
        from ah.formalizer.speech_act import detect_speech_act, detect_negation

        # I02 write-boundary gate: the speech act and NEG scope are decided ONCE for the utterance and
        # constrain EVERY emitted candidate regardless of what the selector answered. A question's content
        # is a goal to be answered (never an asserted world fact); an imperative is a directive; a negated
        # declarative is NOT(P), never a positive fact.
        readings = detect_speech_act(state.text, state.context_facts)
        kinds = {r.kind for r in readings}
        is_query = "QUERY" in kinds
        negated = detect_negation(state.text)

        assertions: list = []
        queries: list = []
        commands: list = []
        notes: list[str] = []
        for frame in state.frames:
            dec = state.decisions.get(f"{frame.frame_id}|predicate_value")
            if dec is None or not dec.selected:
                continue  # no candidate selected -> honest miss, never fabricated
            # A single candidate is emitted ONLY for a RESOLVED unique pick. An AMBIGUOUS/UNRESOLVED
            # decision is NOT collapsed to its first value (that would fabricate a fact); it is surfaced
            # as an explicit unresolved note so downstream sees honest incompleteness, not silence.
            if dec.outcome == "RESOLVED" and len(dec.selected) == 1:
                value = dec.selected[0]
                actant_pairs = self._assign_roles(frame, state)
                roles = tuple(role for role, _ in actant_pairs)
                predicate = self._build_predicate(frame, state, value, roles)
                actants = tuple(ActantCandidate(role=role, mention=mention) for role, mention in actant_pairs)
                local_id = f"{frame.frame_id}:A0"
                if is_query:
                    # DR27: a question's content is NOT asserted as a world fact — it is an EXISTS goal.
                    queries.append(QueryCandidate(predicate=predicate, actants=actants, query_mode=QueryMode.EXISTS, local_id=local_id))
                    notes.append(f"SPEECH_ACT_QUERY {frame.frame_id}: content not asserted")
                elif self._predicate_is_imperative(frame, state):
                    # An imperative is a directive, not an asserted fact about the world.
                    commands.append(CommandCandidate(predicate=predicate, actants=actants, negated=negated, local_id=local_id))
                    notes.append(f"SPEECH_ACT_COMMAND {frame.frame_id}: directive, not asserted")
                else:
                    # DECLARATIVE: assert — but a NEG scope makes it NOT(P), never a positive fact (I02).
                    assertions.append(AssertionCandidate(local_id=local_id, predicate=predicate, actants=actants, negated=negated))
                    if negated:
                        notes.append(f"NEGATED_ASSERTION {frame.frame_id}: represented as NOT(P)")
            else:
                notes.append(f"UNRESOLVED_PREDICATE {frame.frame_id}: outcome={dec.outcome} selected={list(dec.selected)}")

        # DR27/A37: an indirect request keeps linked QUERY/COMMAND alternatives; the embedded content is
        # NOT asserted. Surface the reading as a diagnostic (never a world fact).
        if len(readings) > 1 and any(not r.grounded for r in readings):
            notes.insert(0, f"SPEECH_ACT_LINKED {'/'.join(r.kind for r in readings)} (no action asserted; context determines the act)")

        diagnostics = tuple(f"{d.code}: {d.detail}" for d in state.diagnostics) + tuple(notes)
        return PerceptionResult(
            source_text=state.text,
            assertions=tuple(assertions),
            queries=tuple(queries),
            commands=tuple(commands),
            diagnostics=diagnostics,
        )

    # -- declared structural imperative cue (morphological mood; two-tier invariant) ---- #
    def _predicate_is_imperative(self, frame, state) -> bool:
        """True when the frame's predicate is a VERB in imperative mood — a directive, not a fact."""
        imp_spans = {ev.span for ev in state.evidence if any(v.pos == "VERB" and v.mood == "imperative" for v in ev.variants)}
        return bool(imp_spans & (set(frame.participants) | {frame.anchor_span}))

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
