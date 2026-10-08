# -*- coding: utf-8 -*-
"""Native V7 entry and compatibility projection (V7 §14 / integration).

The native path commits through C/T5/T6 and returns a receipt that prevents a
second legacy fact write. Projection carries supported queries/directives and
diagnostics; nested proposition trees stay SOM content, never separate facts.
Compound goals retain the sealed native syntax for the read-only compiler.
The demo pipeline is a separate, noncommittable preview only.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Declared relation labels for the demo-boundary closed set (already declared in decision_schema_v1.json).
_PREDICATE_LABELS = {"V1": "HAVE", "V2": "HAS_PART", "V3": "LOCATIVE", "V4": "LIKE"}


@dataclass(frozen=True)
class NativePerceptionResult:
    """Outcome of the V7-native perception path (I01/I02): real input committed durably on the store.

    ``perception`` projects supported assertions/queries/commands and diagnostics.
    Unsupported goal surfaces remain explicit gaps, not a claim of legacy parity.
    The durable receipt fields below record which resolved assertion facts were committed; downstream
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
    node_refs: tuple[str,...] = ()


class FormalizerAdapter:
    """Drop-in replacement for AdaptivePerceptionParser.parse(): text -> PerceptionResult.

    ``selector`` is any object with ``select(prompt) -> raw JSON string`` (RealBackendSelector in production,
    FakeSelector.demo() in the deterministic dry run). ``morph``/``schema`` are optional overrides.

    Two modes:
      * preview — :meth:`parse` translates demo state to a noncommittable PerceptionResult;
      * native  — :meth:`interpret` runs the full V7 chain (T0..T4 -> C -> T5 gate + binding CAS -> T6 durable
        commit) on ``store`` and returns a NativePerceptionResult; downstream reads committed facts from the store.
    The native path is only available when a durable ``store`` + ``binding`` are wired (see bootstrap)."""

    def __init__(self, selector, morph=None, schema=None, store=None, binding=None, release=None):
        self._release = release
        self._selector = selector
        self._morph = morph
        self._schema = schema  # lazily loaded if None
        self._store = store      # AHStoreAdapter (durable) — native path prerequisite
        self._binding = binding  # InterpretationRunBinding — native path prerequisite
        if store is not None:
            store.resource_release = release

    @property
    def native_available(self) -> bool:
        return self._store is not None and self._binding is not None

    # -- V7-native entry (I01): real input committed durably on the store ---- #
    def interpret(self, text: str, context_facts: tuple[str, ...] = (), raw_input=None, *, version=1, observation_id=None, run_id=None) -> NativePerceptionResult:
        """Run one observation through T0..T4 -> C -> T5 gate (+binding CAS) -> T6 durable commit.

        Returns the receipt; downstream reads committed facts from ``self._store`` by observation_id."""
        if not self.native_available:
            raise RuntimeError("native commit path is not wired (no durable store/binding)")
        from ah.formalizer.selection_protocol import load_decision_schema
        from ah.formalizer.v7_pipeline import interpret_full

        schema = self._schema or load_decision_schema()
        state, rep = interpret_full(
            text, schema, self._selector, self._store, self._binding,
            morph=self._morph, context_facts=context_facts, release=self._release, raw_input=raw_input, version=version, observation_id=observation_id, run_id=run_id,
        )
        return NativePerceptionResult(
            perception=self._to_perception_result(state),
            observation_id=rep.observation_id,
            version=rep.version,
            terminal=rep.terminal,
            committed_fragments=rep.committed_fragments,
            applied=rep.applied,
            batch_hash=rep.batch_hash,
            diagnostics=rep.diagnostics,
            node_refs=rep.node_refs,
        )

    # -- public entry (mirrors AdaptivePerceptionParser.parse) -------------- #
    def parse(self, text: str, context_facts: tuple[str, ...] = ()) -> "PerceptionResult":
        from ah.formalizer.pipeline import run as _run
        from ah.formalizer.selection_protocol import load_decision_schema

        schema = self._schema or load_decision_schema()
        state = _run(text, schema, self._selector, morph=self._morph, context_facts=context_facts)
        from dataclasses import replace
        return replace(self._to_perception_result(state), formalizer_preview=True)

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
        def leaves(tree):
            if 'frame_ref' in tree: return {tree['frame_ref']}
            return set().union(*(leaves(c) for c in tree.get('operands',())))
        embedded=set()
        for f in state.frames:
            for child in f.semantic.get('proposition_args',{}).values():
                embedded.update(leaves(child.get('tree') or {'frame_ref':child['frame_ref']}))
        for frame in state.frames:
            if frame.frame_id in embedded or frame.semantic.get('quoted') or frame.semantic.get('structural_unresolved'):
                continue
            dec = state.decisions.get(f"{frame.frame_id}|predicate_value")
            if dec is None or not dec.selected:
                continue  # no candidate selected -> honest miss, never fabricated
            # A single candidate is emitted ONLY for a RESOLVED unique pick. An AMBIGUOUS/UNRESOLVED
            # decision is NOT collapsed to its first value (that would fabricate a fact); it is surfaced
            # as an explicit unresolved note so downstream sees honest incompleteness, not silence.
            if dec.outcome == "RESOLVED" and len(dec.selected) == 1:
                value = dec.selected[0]
                ev=next((e for e in state.evidence if e.token_id==frame.predicate_token_ref),None)
                pos=ev.start if ev else frame.source_range[0]
                lo=max(state.text.rfind(c,0,pos) for c in '.!?;')+1
                ends=[state.text.find(c,pos) for c in '.!?;' if state.text.find(c,pos)>=0]
                hi=min(ends) if ends else len(state.text)
                local=state.text[lo:hi]
                requested=state.observation.get('request_kind')
                is_query=requested=='QUERY' or hi<len(state.text) and state.text[hi]=='?'
                if requested=='UNKNOWN':
                    notes.append('MODUS_UNKNOWN '+frame.frame_id); continue
                negated=detect_negation(local)
                actant_pairs = self._assign_roles(frame, state)
                roles = tuple(role for role, _ in actant_pairs)
                if len(set(roles))!=len(roles):
                    notes.append("PROJECTION_ARGUMENT_GROUP_REQUIRED "+frame.frame_id)
                    continue
                predicate = self._build_predicate(frame, state, value, roles)
                actants = tuple(ActantCandidate(role=role, mention=mention) for role, mention in actant_pairs)
                local_id = f"{frame.frame_id}:A0"
                if is_query and any(frame.semantic.get("operator_forest",())):
                    notes.append("NATIVE_QUERY_SCOPE_OWNED "+frame.frame_id)
                    continue
                if is_query:
                    # DR27: a question's content is NOT asserted as a world fact — it is an EXISTS goal.
                    queries.append(QueryCandidate(predicate=predicate, actants=actants, query_mode=QueryMode.EXISTS, local_id=local_id, temporal_point=frame.semantic.get('region',{}).get('point') if frame.semantic.get('region') else None, temporal_window=(frame.semantic['region']['lo'],frame.semantic['region']['hi']) if (frame.semantic.get('region') or {}).get('kind') in {'EXISTENTIAL','CONTINUOUS'} else None))
                    notes.append(f"SPEECH_ACT_QUERY {frame.frame_id}: content not asserted")
                elif requested=='COMMAND' or self._predicate_is_imperative(frame, state):
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

        from .native_queries import project_native_queries
        native_queries=project_native_queries(state,self._release) if self._release is not None else ()
        diagnostics = tuple(f"{d.code}: {d.detail}" for d in state.diagnostics) + tuple(notes)
        return PerceptionResult(
            source_text=state.text,
            assertions=tuple(assertions),
            queries=tuple(queries),
            commands=tuple(commands),
            diagnostics=diagnostics,
            native_query_roots=native_queries,
        )

    # -- declared structural imperative cue (morphological mood; two-tier invariant) ---- #
    def _predicate_is_imperative(self, frame, state) -> bool:
        """True when the frame's predicate is a VERB in imperative mood — a directive, not a fact."""
        imp_spans = {ev.span for ev in state.evidence if any(v.pos == "VERB" and v.mood == "imperative" for v in ev.variants)}
        return bool(imp_spans & (set(frame.participants) | {frame.anchor_span}))

    # -- predicate: real verb when present, else a declared STRUCTURAL predicate ---- #
    def _build_predicate(self, frame, state, value, roles=()):
        from ah.perception.contracts import EvidenceSpan, PredicateCandidate, TemplateCandidate

        specs=frame.semantic.get('candidate_specs',{})
        selected=specs.get(value)
        selection=None
        if selected and selected.get('sense_kind')=='KNOWN' and self._release is not None:
            from ah.perception.contracts import TemplateSelection
            mappings=[m for m in self._release.entries('TemplateMap') if m['sense_id']==selected['sense_id'] and tuple(sorted(m.get('roles',())))==tuple(sorted(r.value for r in roles))]
            if len(mappings)==1: selection=TemplateSelection(existing_template_uid=mappings[0]['template_ref'])
        # The frame's role structure IS the valency declaration: integration needs a TemplateCandidate
        # to materialize an unknown predicate (structural rule, no LLM probe).
        template = TemplateCandidate(tuple(roles)) if roles else None
        for ev in state.evidence:
            if frame.predicate_token_ref and ev.token_id != frame.predicate_token_ref:
                continue
            if not frame.predicate_token_ref and ev.span != frame.anchor_span:
                continue
            for var in ev.variants:
                if var.pos in {"VERB", "INFN", "PRED", "ADJS", "ADJF", "NOUN", "PRTF", "PRTS", "GRND"}:
                    return PredicateCandidate(
                        surface=frame.semantic.get('lexical_units',{}).get(ev.token_id,{}).get('surface',ev.span),
                        normalized_hint=var.lemma if len(frame.semantic.get('lexical_units',{}).get(ev.token_id,{}).get('anchor_refs',()))<=1 else None,
                        evidence=EvidenceSpan(text=frame.semantic.get('lexical_units',{}).get(ev.token_id,{}).get('surface',ev.span)),
                        template_candidate=template, template_selection=selection,
                    )
        # relation-only frame (copula/ellipsis): a declared STRUCTURAL predicate, never a fake lexeme.
        label = _PREDICATE_LABELS.get(value, value)
        return PredicateCandidate(
            surface=label, normalized_hint=value, sense_hint=f"STRUCTURAL_{label}", template_candidate=template
        )

    # -- declared structural role assignment (from T2 frame construction) -- #
    def _assign_roles(self, frame, state):
        from ah.model.types import ActantRole as R

        dec = state.decisions.get(frame.frame_id+"|predicate_value")
        specs = frame.semantic.get('candidate_specs',{})
        if dec and len(dec.selected)==1 and dec.selected[0] in specs:
            evs={e.token_id:e for e in state.evidence}
            return [(R(role),evs[tid].span) for tid,role in specs[dec.selected[0]]['roles'].items()]
        # Legacy preview: cases may propose roles; positional assignment is forbidden.
        pairs=[]
        for tid in frame.argument_token_refs:
            ev=next((e for e in state.evidence if e.token_id==tid),None)
            if ev is None: continue
            cases=ev.cases
            if cases==frozenset({'nom'}): pairs.append((R.SUBJECT,ev.span))
            elif cases==frozenset({'acc'}): pairs.append((R.OBJECT,ev.span))
        return pairs
