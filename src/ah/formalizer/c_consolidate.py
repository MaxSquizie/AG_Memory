# -*- coding: utf-8 -*-
"""WP2.1 — C-consolidation (V7 §7.1): the pure decision step between T4 and the commit stage.

C takes T4-resolved semantic values and produces a deterministic :class:`ConsolidationPlan` that the
commit stage materializes. It performs, in order:

1. **Identity unification** — declared naming/identity rules; ``merge_identity`` only merges two refs to
   ONE entity (never predicates). A conflict blocks the fragment (T6 is not called for it) (§7.1 step 2, A21).
2. **Sense resolution per value**:
   * KNOWN — TemplateMap lookup ``(predicate_id, value_id, roles_signature) -> canonical_template_uid``; a hit
     yields Ref(T); a miss of the chosen known sense is ``CANONICAL_MAPPING_MISSING`` and blocks ONLY this
     fragment. The open path is NEVER an automatic fallback for a broken known mapping (§7.1 step 3).
   * OPEN_LEXICAL — C forms an occurrence-local :func:`ensure_open_template` (UNLINKED, EXACT_ATTESTATION only)
     without choosing any existing T. Two incompatible lexical senses sharing one isolation key do NOT merge:
     until a versioned ground distinguishes them both stay AMBIGUOUS with no open T (§7.1 step 3).
3. **Deduplication** — canonical relation identity is ``RelationKey = (predicate S, roles, declared value)``; the
   temporal part is NOT in the key (§6.3/§7.1 step 4). Repeated mentions with an equal RelationKey merge into one
   N for a RESOLVED STATE frame; EVENT occurrences never merge (separate node each); OPEN_LEXICAL stays
   occurrence-local (its key embeds observation_id, so independent observations are never merged by lemma/roles).

This module is pure: it performs no store writes. Materialization happens in the commit stage (WP2.3).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Mapping, Sequence

from .resources.registry import (
    OpenPredicateCandidate,
    OpenTemplatePolicy,
    RoleBinding,
    RoleRegistry,
    build_role_signature,
    compute_open_template_key,
    ensure_open_template,
)


# --------------------------------------------------------------------------- #
# Input records (lightweight; produced by T4 / the pipeline)
# --------------------------------------------------------------------------- #
class SenseKind(str, Enum):
    KNOWN = "KNOWN"
    OPEN_LEXICAL = "OPEN_LEXICAL"


class TemporalMode(str, Enum):
    STATE = "STATE"
    EVENT = "EVENT"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class ResolvedValue:
    """One T4-resolved semantic value awaiting consolidation."""

    fragment_id: str
    observation_id: str
    source_revision: int            # contextual revision; deliberately NOT in the open isolation key
    predicate_id: str              # S (known sense id, or lexical anchor for OPEN_LEXICAL)
    value_id: str                 # declared value
    roles_signature: str          # canonical role signature string
    sense_kind: SenseKind
    temporal_mode: TemporalMode
    anchor_spans: tuple[str, ...] = ()
    normalized_surface_or_lemma: str = ""
    pos: str = "UNKNOWN"
    proposition_argument_signature: str = ""
    sense_label: str = ""         # non-empty for incompatible-sense detection (OPEN_LEXICAL)
    bindings: tuple[RoleBinding, ...] = ()  # structured role bindings; the single source of the open isolation key


@dataclass(frozen=True)
class IdentityRef:
    """A mention that may unify with another via a declared identity rule."""

    ref_id: str
    fragment_id: str
    entity_key: str               # declared identity cluster (e.g. coreference id); "" = unassigned


# --------------------------------------------------------------------------- #
# Output records
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class FragmentResolution:
    """How one fragment is resolved by C."""

    fragment_id: str
    resolution: str              # REF_T | OPEN_TEMPLATE | CANONICAL_MAPPING_MISSING | AMBIGUOUS_SENSE | IDENTITY_CONFLICT
    template_uid: str | None = None       # for REF_T
    open_template_key: str | None = None  # for OPEN_TEMPLATE
    node_id: str | None = None           # canonical N after dedup (STATE merge / EVENT separate)
    blocked: bool = False            # True -> T6 is not called for this fragment


@dataclass(frozen=True)
class ConsolidationPlan:
    """The deterministic output of C — the only thing the commit stage materializes."""

    resolutions: tuple[FragmentResolution, ...]
    node_groups: Mapping[str, tuple[str, ...]] = field(default_factory=dict)  # node_id -> fragment_ids
    diagnostics: tuple[str, ...] = ()
    blocked_fragment_ids: frozenset[str] = frozenset()


# --------------------------------------------------------------------------- #
# RelationKey and per-value resolution
# --------------------------------------------------------------------------- #
def relation_key(v: ResolvedValue) -> tuple[str, str, str]:
    """§7.1 step 4 — canonical relation identity (predicate S, roles, declared value).

    The temporal part is deliberately excluded (§6.3). For OPEN_LEXICAL the key embeds the occurrence-local
    isolation key instead of the raw value, so independent observations are never merged by lemma/roles alone."""
    if v.sense_kind is SenseKind.OPEN_LEXICAL:
        return (v.predicate_id, v.roles_signature, _open_key(v))
    return (v.predicate_id, v.roles_signature, v.value_id)


def _open_key(v: ResolvedValue) -> str:
    """§7.1 step 3 — occurrence-local isolation key (excludes interpretation_version; includes observation_id).

    The role signature is derived from the structured ``bindings`` so it matches EXACTLY the key that
    :func:`ensure_open_template` computes for the same candidate (single source of truth)."""
    return compute_open_template_key(
        observation_id=v.observation_id,
        source_revision=v.source_revision,
        anchor_spans=v.anchor_spans,
        normalized_surface_or_lemma=v.normalized_surface_or_lemma,
        pos_or_unknown=v.pos or "UNKNOWN",
        role_signature=build_role_signature(v.bindings),
        proposition_argument_signature=v.proposition_argument_signature,
    )


def resolve_known(v: ResolvedValue, template_map: Mapping) -> FragmentResolution:
    """§7.1 step 3(a) — KNOWN sense via TemplateMap; a miss blocks the fragment (no open-path bypass)."""
    uid = template_map.get((v.predicate_id, v.value_id, v.roles_signature))
    if uid is not None:
        return FragmentResolution(v.fragment_id, "REF_T", template_uid=uid)
    # CANONICAL_MAPPING_MISSING: block ONLY this fragment; the open path must NOT be an automatic fallback.
    return FragmentResolution(v.fragment_id, "CANONICAL_MAPPING_MISSING", blocked=True)


def _resolve_open_group(group: Sequence[ResolvedValue], registry: RoleRegistry, policy: OpenTemplatePolicy):
    """§7.1 step 3(b) — OPEN_LEXICAL values sharing one isolation key.

    A single consistent sense yields an occurrence-local UNLINKED open T (EXACT_ATTESTATION only). Two or more
    incompatible senses (distinct non-empty sense_labels) with no distinguishing ground stay AMBIGUOUS: no open T."""
    labels = {v.sense_label for v in group if v.sense_label}
    if len(labels) > 1:
        return [FragmentResolution(v.fragment_id, "AMBIGUOUS_SENSE", blocked=True) for v in group]

    head = group[0]
    candidate = OpenPredicateCandidate(
        observation_id=head.observation_id,
        source_revision=head.source_revision,
        anchor_spans=head.anchor_spans,
        normalized_surface_or_lemma=head.normalized_surface_or_lemma,
        pos=head.pos,
        bindings=head.bindings,
        proposition_argument_signature=head.proposition_argument_signature,
    )
    open_t = ensure_open_template(candidate, registry, policy)  # raises on unregistered role / unreleased policy
    return [FragmentResolution(v.fragment_id, "OPEN_TEMPLATE", open_template_key=open_t.open_template_key) for v in group]


# --------------------------------------------------------------------------- #
# Deduplication (RelationKey groups) and identity unification
# --------------------------------------------------------------------------- #
def _dedup_group(key: tuple[str, str, str], members: Sequence[ResolvedValue]):
    """Assign canonical N node ids to a RelationKey group per the temporal-mode rule (§7.1 step 4)."""
    base = "N:" + "|".join(key)
    if any(m.temporal_mode is TemporalMode.EVENT for m in members):
        # EVENT occurrences never merge: one separate node each, even within the same observation.
        return {m.fragment_id: f"{base}#{m.fragment_id}" for m in members}, []
    unknowns = [m for m in members if m.temporal_mode is TemporalMode.UNKNOWN]
    if unknowns:
        # FrameTemporalMode=UNKNOWN -> NOT merged (separate N) + STATE_CLASS_UNKNOWN miss report.
        nodes = {m.fragment_id: f"{base}#{m.fragment_id}" for m in members}
        diags = [f"STATE_CLASS_UNKNOWN:{m.fragment_id}" for m in unknowns]
        return nodes, diags
    # All RESOLVED STATE with an equal RelationKey -> merge into ONE canonical N.
    shared = base
    return {m.fragment_id: shared for m in members}, []


def unify_identity(refs: Sequence[IdentityRef]) -> tuple[frozenset[str], list[str]]:
    """§7.1 step 2 — declared identity unification. Returns (conflicting_fragment_ids, diagnostics).

    A ref is a conflict when it is claimed under two different entity_keys, or an entity_key is asserted to be a
    predicate (identity only merges refs to one ENTITY, never predicates)."""
    by_ref: dict[str, set[str]] = {}
    for r in refs:
        if not r.entity_key:
            continue
        by_ref.setdefault(r.ref_id, set()).add(r.entity_key)
    conflicting: set[str] = set()
    diags: list[str] = []
    for ref_id, keys in sorted(by_ref.items()):
        if len(keys) > 1:
            owner = next(r.fragment_id for r in refs if r.ref_id == ref_id)
            conflicting.add(owner)
            diags.append(f"IDENTITY_CONFLICT:{ref_id}")
    return frozenset(conflicting), diags


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
def consolidate(
    values: Sequence[ResolvedValue],
    template_map: Mapping,
    registry: RoleRegistry,
    policy: OpenTemplatePolicy,
    identity_refs: Sequence[IdentityRef] = (),
) -> ConsolidationPlan:
    """Run C-consolidation over the resolved values; return the deterministic plan."""
    conflict_frags, id_diags = unify_identity(identity_refs)

    resolutions: list[FragmentResolution] = []
    node_of_fragment: dict[str, str] = {}
    diagnostics: list[str] = list(id_diags)

    # 1) per-value sense resolution (KNOWN via map; OPEN_LEXICAL grouped by isolation key).
    open_groups: dict[str, list[ResolvedValue]] = {}
    for v in values:
        if v.fragment_id in conflict_frags:
            resolutions.append(FragmentResolution(v.fragment_id, "IDENTITY_CONFLICT", blocked=True))
            continue
        if v.sense_kind is SenseKind.KNOWN:
            res = resolve_known(v, template_map)
        else:
            open_groups.setdefault(_open_key(v), []).append(v)
            continue  # resolved below as a group
        resolutions.append(res)

    for key in sorted(open_groups):
        group = open_groups[key]
        try:
            resolutions.extend(_resolve_open_group(group, registry, policy))
        except Exception as exc:  # REGISTRY_REJECT / OPEN_TEMPLATE_INVALID -> block the fragment(s)
            code = type(exc).__name__
            for v in group:
                resolutions.append(FragmentResolution(v.fragment_id, f"BLOCKED_{code}", blocked=True))
            diagnostics.append(f"{code}:{key[:12]}")

    # 2) deduplication by RelationKey (assigns node ids; STATE merges, EVENT/UNKNOWN separate).
    groups: dict[tuple[str, str, str], list[ResolvedValue]] = {}
    for v in values:
        if any(r.fragment_id == v.fragment_id and r.blocked for r in resolutions):
            continue  # blocked fragments are not materialized -> no node
        groups.setdefault(relation_key(v), []).append(v)

    node_groups: dict[str, list[str]] = {}
    for key in sorted(groups):
        nodes, diags = _dedup_group(key, groups[key])
        diagnostics.extend(diags)
        for frag_id, node_id in nodes.items():
            node_of_fragment[frag_id] = node_id
            node_groups.setdefault(node_id, []).append(frag_id)

    # attach node ids to the (non-blocked) resolutions.
    final: list[FragmentResolution] = []
    for r in resolutions:
        if not r.blocked and r.fragment_id in node_of_fragment:
            r = FragmentResolution(
                r.fragment_id, r.resolution, template_uid=r.template_uid,
                open_template_key=r.open_template_key, node_id=node_of_fragment[r.fragment_id])
        final.append(r)

    blocked = frozenset(r.fragment_id for r in final if r.blocked)
    return ConsolidationPlan(
        resolutions=tuple(final),
        node_groups={k: tuple(v) for k, v in sorted(node_groups.items())},
        diagnostics=tuple(diagnostics),
        blocked_fragment_ids=blocked,
    )
