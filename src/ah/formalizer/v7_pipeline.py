# -*- coding: utf-8 -*-
"""V7 interpretation runner — the single traceable production path (audit I01).

Composes the whole formalizer vertical for ONE observation into one flow, so a real user input no
longer bypasses C / T5 / T6 by being converted to the legacy ``PerceptionResult`` and handed to
``IntegrationService.integrate_external``:

    pipeline.run(text)  -> FormalizationState (T0..T4)
        --state_to_values--> ResolvedValue[]          (only RESOLVED single-value fragments assert a fact)
        --c_consolidate.consolidate--> ConsolidationPlan   (C: canonical mapping / identity unification)
        --state_to_fragments--> FragmentT5Input[]      (per-value FACT grounds O/C/W; interpretation-only R/D/M/A/P never commit)
        --t5_batch--> T5Result                        (commit gate + InterpretationRunBinding CAS)
        --commit_stage.commit--> CommitReport         (T6: durable atomic unit on the real store)

Design decisions (reasoned, not per-example rules):

* **Observation identity** is minted deterministically from content (text + context facts), so re-analysing
  the same input yields the SAME observation and an idempotent commit; a contextual revision bumps ``version``.
* **Run-binding lifecycle**: the run CAS-claims ``(observation_id, version)`` BEFORE any write. A foreign owner
  already holding it -> INTEGRITY_ERROR report and NO commit (concurrent interpretations are serialized; exactly
  one wins). The winner keeps ownership until superseded/retracted (no auto-release mid-flight).
* **C stage honesty**: only a RESOLVED single-value fragment produces a canonical value. An UNRESOLVED/AMBIGUOUS
  fragment yields no C value (observation record only, §7.2) — never collapsed to its first value.
* **Per-value fact grounding** (I12): a uniquely-resolved fragment inherits a slot-level FACT ground (O/C/W) for
  its single value; multiple survivors need their OWN per-value FACT ground or COND_5 refuses the fact. R/D/M/A/P
  are interpretation-only and never satisfy COND_5.

This is a large, self-contained module by design (audit point: big modules get their own file).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from typing import Mapping, Sequence

from ah.formalizer.c_consolidate import ResolvedValue, SenseKind, TemporalMode, consolidate
from ah.formalizer.pipeline import run as _run_t04
from ah.formalizer.resources.registry import (
    OpenTemplatePolicy, Role, RoleRegistry,
)
from ah.formalizer.run_binding import InterpretationRunBinding
from ah.formalizer.selection_protocol import DecisionSchema
from ah.formalizer.state import FormalizationState
from ah.formalizer.support_som import FACT_GROUNDS
from ah.formalizer.t5_batch import FragmentT5Input, t5_batch

# A released registry + policy are prerequisites for C consolidation (mandatory roles EXPERIENCER/SURFACE_ARG).
_DEFAULT_REGISTRY = RoleRegistry(frozenset({Role("EXPERIENCER"), Role("SURFACE_ARG")}))
_DEFAULT_POLICY = OpenTemplatePolicy(released=True)


@dataclass
class InterpretationReport:
    """Outcome of running one observation through the full V7 chain."""

    observation_id: str
    version: int
    run_id: str
    binding_ok: bool                 # did this run CAS-claim the interpretation?
    t5_eligibility: str             # OK | INTEGRITY_ERROR | MARKER_REFUSED
    committed_fragments: tuple[str, ...] = ()   # fragments whose FACT was asserted (T5)
    applied: bool = False           # T6 store acceptance (fresh write, not idempotent no-op)
    terminal: str = ""             # APPLIED | STALE_SUPERSEDED | REJECTED_ADMISSION
    batch_hash: str = ""
    diagnostics: tuple[str, ...] = field(default_factory=tuple)


def _mint_observation(text: str, context_facts: Sequence[str]) -> str:
    """Deterministic observation identity from content (same input -> same id; a revision bumps version)."""
    h = hashlib.sha1()
    h.update(text.encode("utf-8"))
    h.update(b"\x00")
    for f in context_facts:
        h.update(f.encode("utf-8"))
        h.update(b"\n")
    return "obs-" + h.hexdigest()[:16]


def _default_template_map(values: Sequence[ResolvedValue]) -> dict[tuple[str, str, str], str]:
    """Map each resolved value to a canonical template uid (KNOWN sense -> REF_T).

    Keyed by relation_key = (predicate_id, roles_signature, value_id). Built from the values actually
    produced (not per-word rules): every uniquely-resolved value gets its own canonical template identity.
    A KNOWN value absent here is an honest CANONICAL_MAPPING_MISSING, not a silent fallback."""
    # NOTE: resolve_known looks up (predicate_id, value_id, roles_signature) — a DIFFERENT order than
    # relation_key() (which is used only for dedup grouping). Match the lookup exactly.
    return {(v.predicate_id, v.value_id, v.roles_signature): f"T:{v.value_id}" for v in values}


# A single structural relation predicate for the demo closed set (no per-word lexeme is invented).
S_REL = "S_REL"
_ROLES_SIG_DEFAULT = "R:EXPERIENCER,SURFACE_ARG"


def _roles_sig(frame) -> str:
    """Stable role signature for a frame (from its declared construction; deterministic, not per-word)."""
    con = (frame.construction or "").upper()
    return f"R:{con}" if con else _ROLES_SIG_DEFAULT


# -- bridges: FormalizationState -> C values / T5 fragments ------------------- #

def state_to_values(state: FormalizationState, observation_id: str) -> list[ResolvedValue]:
    """C input: only RESOLVED single-value fragments assert a canonical value (UNRESOLVED/AMBIGUOUS -> none)."""
    values: list[ResolvedValue] = []
    for frame in state.frames:
        dec = state.decisions.get(f"{frame.frame_id}|predicate_value")
        if dec is None or dec.outcome != "RESOLVED" or len(dec.selected) != 1:
            continue  # not a uniquely-resolved fact -> observation record only, never collapsed to first value
        values.append(ResolvedValue(
            fragment_id=frame.frame_id,
            observation_id=observation_id,
            source_revision=state.context_version,
            predicate_id=S_REL,
            value_id=dec.selected[0],
            roles_signature=_roles_sig(frame),
            sense_kind=SenseKind.KNOWN,
            temporal_mode=TemporalMode.STATE,
        ))
    return values


def _value_fact_grounds(dec) -> dict[str, tuple[str, ...]]:
    """Per-value FACT grounds (O/C/W only). A uniquely-resolved fragment inherits a slot-level fact ground for
    its single value; multiple survivors need their OWN per-value fact ground or they are ungrounded (I12)."""
    per_value: dict[str, set] = {}
    slot_fact_types: set = set()
    for g in dec.grounds:
        if g.type not in FACT_GROUNDS:
            continue  # R/D/M/A/P are interpretation-only; they never assert a fact
        (per_value.setdefault(g.value, set()) if g.value else slot_fact_types).add(g.type)
    selected = list(dec.selected)
    if len(selected) == 1 and slot_fact_types:
        per_value.setdefault(selected[0], set()).update(slot_fact_types)
    return {v: tuple(sorted(ts)) for v, ts in per_value.items()}


def state_to_fragments(state: FormalizationState, plan) -> list[FragmentT5Input]:
    """T5 input: one fragment per frame with a predicate decision; carries outcome + per-value fact grounds and
    flags a C-blocked known mapping (CANONICAL_MAPPING_MISSING) so T6 is not called for it."""
    blocked = set(plan.blocked_fragment_ids) if plan else set()
    c_missing = {r.fragment_id for r in (plan.resolutions if plan else ()) if r.resolution == "CANONICAL_MAPPING_MISSING"}
    frags: list[FragmentT5Input] = []
    for frame in state.frames:
        dec = state.decisions.get(f"{frame.frame_id}|predicate_value")
        if dec is None:
            continue
        outcome = dec.outcome or "UNRESOLVED"
        selected = tuple(dec.selected) if dec.selected else tuple(dec.candidates)
        frags.append(FragmentT5Input(
            fragment_id=frame.frame_id,
            outcome=outcome,
            selected_values=selected,
            value_grounds=_value_fact_grounds(dec),
            known_mapping_missing=(frame.frame_id in c_missing or (frame.frame_id in blocked and not dec.selected)),
        ))
    return frags


# -- the full chain ---------------------------------------------------------- #

def run_from_state(
    state: FormalizationState,
    store,
    binding: InterpretationRunBinding,
    *,
    schema: DecisionSchema,
    run_id: str = "run",
    version: int = 1,
    observation_id: str | None = None,
    template_map: Mapping | None = None,
    registry: RoleRegistry | None = None,
    policy: OpenTemplatePolicy | None = None,
) -> InterpretationReport:
    """Run an already-built FormalizationState through C -> T5 gate (+binding CAS) -> T6 commit.

    Exposed separately so a re-analysis of an existing state (or a synthetic one in tests) can be driven
    through the SAME real C+T5+commit chain as fresh pipeline output."""
    from ah.formalizer.commit_stage import commit as _commit

    obs = observation_id or _mint_observation(state.text, ())

    # (2) run-binding CAS BEFORE any write: a foreign owner already holding this interpretation -> no commit.
    if not binding.acquire(run_id, obs, version):
        return InterpretationReport(
            observation_id=obs, version=version, run_id=run_id, binding_ok=False,
            t5_eligibility="INTEGRITY_ERROR", diagnostics=("RUN_BINDING_FOREIGN_OWNER:",),
        )

    # (3) C consolidation over the resolved values.
    values = state_to_values(state, obs)
    plan = consolidate(values, template_map or _default_template_map(values), registry or _DEFAULT_REGISTRY, policy or _DEFAULT_POLICY)

    # (4) T5 commit gate (+ per-value fact grounding).
    frags = state_to_fragments(state, plan)
    t5 = t5_batch(frags, run_id=run_id, observation_id=obs, version=version, binding=binding)
    if t5.eligibility != "OK":
        return InterpretationReport(
            observation_id=obs, version=version, run_id=run_id, binding_ok=True,
            t5_eligibility=t5.eligibility, diagnostics=(f"T5_{t5.eligibility}:",),
        )

    # (5) T6: durable atomic commit of the admitted interpretation on the real store.
    rep = _commit(state, store, run_id=run_id)
    return InterpretationReport(
        observation_id=obs, version=version, run_id=run_id, binding_ok=True,
        t5_eligibility="OK", committed_fragments=tuple(t5.committed_fragments),
        applied=rep.applied, terminal=rep.terminal.name, batch_hash=rep.batch_hash,
    )


def interpretation_run(
    text: str,
    schema: DecisionSchema,
    selector,
    store,
    binding: InterpretationRunBinding,
    *,
    morph=None,
    context_facts: Sequence[str] = (),
    run_id: str = "run",
    version: int = 1,
    observation_id: str | None = None,
    template_map: Mapping | None = None,
    registry: RoleRegistry | None = None,
    policy: OpenTemplatePolicy | None = None,
) -> InterpretationReport:
    """Run one observation through T0..T4 -> C -> T5 gate (+binding CAS) -> T6 commit on the real store."""
    state = _run_t04(text, schema, selector, morph=morph, context_facts=context_facts)
    return run_from_state(
        state, store, binding,
        schema=schema, run_id=run_id, version=version, observation_id=observation_id,
        template_map=template_map, registry=registry, policy=policy,
    )


def interpret_full(
    text: str,
    schema: DecisionSchema,
    selector,
    store,
    binding: InterpretationRunBinding,
    *,
    morph=None,
    context_facts: Sequence[str] = (),
    run_id: str = "run",
    version: int = 1,
    observation_id: str | None = None,
    template_map: Mapping | None = None,
    registry: RoleRegistry | None = None,
    policy: OpenTemplatePolicy | None = None,
) -> tuple["FormalizationState", InterpretationReport]:
    """Like :func:`interpretation_run` but ALSO returns the FormalizationState, so a caller can build the
    full perception candidate set (queries/commands/assertions via speech-act detection) from it — i.e. make
    the native path capability-complete vs the legacy parse() rather than assertion-only."""
    state = _run_t04(text, schema, selector, morph=morph, context_facts=context_facts)
    report = run_from_state(
        state, store, binding,
        schema=schema, run_id=run_id, version=version, observation_id=observation_id,
        template_map=template_map, registry=registry, policy=policy,
    )
    return state, report
