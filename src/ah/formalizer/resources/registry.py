# -*- coding: utf-8 -*-
"""RoleRegistry / ProposalPolicy / OpenTemplatePolicy + EnsureOpenTemplate (V7 §2.1, §7.1 — WP0.4).

These are the resource contracts a minimal viable release must carry (§2.1 line 131): without them there
is no model proposal and no open-lexical materialization. The module is pure and deterministic:

- RoleRegistry MUST contain EXPERIENCER and SURFACE_ARG; an unknown role at the write boundary raises
  REGISTRY_REJECT (rolls back the whole T6 transaction, §7.1 line 396).
- ProposalPolicy / OpenTemplatePolicy gate model proposals and OPEN_LEXICAL materialization by a
  ``released`` flag: no release -> deterministic candidates continue with a diagnosed miss; no silent
  fallback to an existing T and NO "nearest" matching (there is deliberately no lookup here at all).
- EnsureOpenTemplate computes the occurrence-local isolation key per §7.1 line 364 — length-prefixed,
  NOT including interpretation_version (survives a contextual revision of the same text but never
  collides across independent observations), and it returns an UNLINKED open T whose only inference
  capability is EXACT_ATTESTATION (no paraphrase / IS_A / CAUSE / inverse_of / canonical alias).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from ..inference_policy import OPEN_LEXICAL_CAPABILITIES


# -- write-boundary errors (§7.1 line 396) ---------------------------------- #
class RegistryReject(Exception):
    """REGISTRY_REJECT — a reference to an unknown role / g.ID / L.ID at the write boundary."""


class OpenTemplateInvalid(Exception):
    """OPEN_TEMPLATE_INVALID — incompatible roles, malformed key inputs, or an unreleased policy."""


MANDATORY_ROLES = ("EXPERIENCER", "SURFACE_ARG")


@dataclass(frozen=True)
class Role:
    role_id: str
    allowed_argument_kinds: tuple[str, ...] = ()  # empty -> any kind allowed
    cardinality: int | None = None
    projection: bool = False
    schema_version: str = "role_v1"


@dataclass(frozen=True)
class RoleRegistry:
    """A released set of roles. A valid release MUST register EXPERIENCER and SURFACE_ARG."""

    roles: frozenset[Role]
    schema_version: str = "registry_v1"

    def __post_init__(self):
        present = {r.role_id for r in self.roles}
        missing = [m for m in MANDATORY_ROLES if m not in present]
        if missing:
            raise ValueError(f"RoleRegistry release must register mandatory roles; missing {missing}")

    def has_role(self, role_id: str) -> bool:
        return any(r.role_id == role_id for r in self.roles)

    def validate_roles(self, role_ids) -> None:
        """Raise REGISTRY_REJECT on the first unregistered role (write-boundary gate)."""
        for rid in role_ids:
            if not self.has_role(rid):
                raise RegistryReject(f"REGISTRY_REJECT: unknown role {rid!r}")

    def allowed_kinds(self, role_id: str) -> tuple[str, ...]:
        for r in self.roles:
            if r.role_id == role_id:
                return r.allowed_argument_kinds
        raise RegistryReject(f"REGISTRY_REJECT: unknown role {role_id!r}")


@dataclass(frozen=True)
class ProposalPolicy:
    """Gates model local-structure proposals. Unreleased -> no model proposal (deterministic continue)."""

    version: str = "proposal_v1"
    max_calls_per_unit: int = 0
    max_nodes: int = 0
    max_edges: int = 0
    max_depth: int = 0
    allowed_anchor_kinds: tuple[str, ...] = ()
    allowed_edge_kinds: tuple[str, ...] = ()
    allowed_read_sets: tuple[str, ...] = ()
    validation_schema_version: str = ""
    model_key: str | None = None
    params_hash: str | None = None
    released: bool = False


@dataclass(frozen=True)
class OpenTemplatePolicy:
    """Gates OPEN_LEXICAL materialization. Unreleased -> open T is not materialized; existing T stay
    reachable via TemplateMap and there is NO nearest-match fallback."""

    version: str = "open_template_v1"
    key_schema_version: str = "key_v1"
    allowed_argument_kinds: tuple[str, ...] = ()
    isolation_domain: str = ""
    migration_policy: str = ""
    permitted_query_mode: str = ""
    released: bool = False


@dataclass(frozen=True)
class RoleBinding:
    """One argument binding for the role signature. SURFACE_ARG carries its syntactic details so that
    changing the attachment changes the isolation key (never reuses an old T)."""

    role_id: str
    arg_kind: str = "ENTITY"
    slot_index: int | None = None          # SURFACE_ARG only
    syntax_relation: str | None = None     # SURFACE_ARG only
    case: str | None = None               # SURFACE_ARG only
    preposition: str | None = None        # SURFACE_ARG only
    anchor_spans: tuple[str, ...] = ()    # SURFACE_ARG only


def build_role_signature(bindings) -> str:
    """Deterministic role signature. For SURFACE_ARG the syntactic fields are included; for other roles
    only (role_id, arg_kind). Sorted so argument order does not leak into the key."""
    parts = []
    for b in bindings:
        if b.role_id == "SURFACE_ARG":
            parts.append(
                f"SURFACE_ARG|{b.arg_kind}|slot={b.slot_index}|rel={b.syntax_relation}|"
                f"case={b.case}|prep={b.preposition}|spans={','.join(b.anchor_spans)}")
        else:
            parts.append(f"{b.role_id}|{b.arg_kind}")
    return ";".join(sorted(parts))


def _length_prefixed(*parts) -> bytes:
    """Length-prefix every part (4-byte big-endian) so the concatenation is unambiguous — no delimiter
    collisions between adjacent fields."""
    out = b""
    for p in parts:
        blob = str(p).encode("utf-8")
        out += len(blob).to_bytes(4, "big") + blob
    return out


def compute_open_template_key(
    observation_id: str,
    source_revision: int | str,
    anchor_spans,
    normalized_surface_or_lemma: str,
    pos_or_unknown: str,
    role_signature: str,
    proposition_argument_signature: str = "",
) -> str:
    """§7.1 line 364 — the occurrence-local isolation key.

    Deliberately EXCLUDES interpretation_version (survives a contextual revision of the same text) and
    INCLUDES observation_id (never collides across independent observations)."""
    blob = _length_prefixed(
        observation_id, source_revision, ",".join(anchor_spans), normalized_surface_or_lemma,
        pos_or_unknown or "UNKNOWN", role_signature, proposition_argument_signature)
    return hashlib.sha256(blob).hexdigest()


@dataclass(frozen=True)
class OpenTemplate:
    """An occurrence-local open T: UNLINKED, EXACT_ATTESTATION only — no canonical alias by construction."""

    open_template_key: str
    semantic_status: str = "UNLINKED"
    inference_capabilities: tuple[str, ...] = OPEN_LEXICAL_CAPABILITIES
    source: str = ""


@dataclass(frozen=True)
class OpenPredicateCandidate:
    """Minimal sealed input to EnsureOpenTemplate (a lexical anchor with proven surface + roles)."""

    observation_id: str
    source_revision: int | str
    anchor_spans: tuple[str, ...]
    normalized_surface_or_lemma: str
    pos: str = ""
    bindings: tuple[RoleBinding, ...] = ()
    proposition_argument_signature: str = ""
    source: str = ""


def ensure_open_template(
    candidate: OpenPredicateCandidate, registry: RoleRegistry, policy: OpenTemplatePolicy
) -> OpenTemplate:
    """§7.1 write-boundary gate for an occurrence-local open T.

    Raises OpenTemplateInvalid if the policy is unreleased or a role's argument kind is incompatible;
    raises RegistryReject (REGISTRY_REJECT) on any unregistered role. Returns an UNLINKED open T keyed by
    its isolation key — it never searches for, aliases to, or falls back onto an existing canonical T."""
    if not policy.released:
        raise OpenTemplateInvalid("OpenTemplatePolicy not released — OPEN_LEXICAL is not materialized")

    role_ids = [b.role_id for b in candidate.bindings]
    registry.validate_roles(role_ids)  # unknown role -> REGISTRY_REJECT (rolls back the transaction)

    for b in candidate.bindings:
        allowed = registry.allowed_kinds(b.role_id)
        if allowed and b.arg_kind not in allowed:
            raise OpenTemplateInvalid(
                f"OPEN_TEMPLATE_INVALID: role {b.role_id!r} does not allow argument kind {b.arg_kind!r}")

    key = compute_open_template_key(
        candidate.observation_id, candidate.source_revision, candidate.anchor_spans,
        candidate.normalized_surface_or_lemma, candidate.pos, build_role_signature(candidate.bindings),
        candidate.proposition_argument_signature)
    return OpenTemplate(open_template_key=key, source=candidate.source)
