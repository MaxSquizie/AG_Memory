from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ah.config import AppConfig
from ah.core import AHCore
from ah.dsl import DSLInterpreter
from ah.model import Domain, RefKind


@dataclass(frozen=True, slots=True)
class HyperparameterRecord:
    key: str
    value: Any
    rationale: str


@dataclass(frozen=True, slots=True)
class HackathonPreflightReport:
    s_count: int
    semantic_element_count: int
    link_count: int
    graph_n: int
    dsl_operations: tuple[str, ...]
    missing_dsl_operations: tuple[str, ...]
    hyperparameters: tuple[HyperparameterRecord, ...]
    is_a_acyclic: bool
    h_follow_acyclic: bool
    symbols_have_r: bool
    broken_references: tuple[str, ...]
    minimum_s_target_met: bool
    minimum_graph_target_met: bool

    @property
    def structural_ok(self) -> bool:
        return (
            not self.missing_dsl_operations
            and len(self.hyperparameters) == 5
            and self.is_a_acyclic
            and self.h_follow_acyclic
            and self.symbols_have_r
            and not self.broken_references
        )


class HackathonPreflightInspector:
    """Deterministic structural preflight; it is *not* M1–M5 acceptance.

    This module exists so the implementation can prove that the mandatory AH/DSL/
    Ignition configuration surface is present before expensive acceptance runs.
    It reads canonical AH and current configuration only and never mutates memory.
    """

    REQUIRED_DSL = DSLInterpreter.NORMATIVE_OPERATIONS

    def __init__(self, core: AHCore, config: AppConfig) -> None:
        self.core = core
        self.config = config

    def inspect(self) -> HackathonPreflightReport:
        semantic = sum(len(self.core.store.elements(domain)) for domain in Domain)
        links = len(self.core.store.links())
        operations = DSLInterpreter.operation_names()
        missing = tuple(name for name in self.REQUIRED_DSL if name not in operations)
        return HackathonPreflightReport(
            s_count=len(self.core.store._state.symbols),
            semantic_element_count=semantic,
            link_count=links,
            graph_n=semantic + links,
            dsl_operations=operations,
            missing_dsl_operations=missing,
            hyperparameters=self._five_hyperparameters(),
            is_a_acyclic=self._relation_acyclic("IS-A"),
            h_follow_acyclic=self._relation_acyclic("FOLLOW", h_only=True),
            symbols_have_r=all(bool(symbol.forms) for symbol in self.core.store._state.symbols.values()),
            broken_references=self._broken_references(),
            minimum_s_target_met=len(self.core.store._state.symbols) >= 150,
            minimum_graph_target_met=(semantic + links) >= 1000,
        )

    def _five_hyperparameters(self) -> tuple[HyperparameterRecord, ...]:
        cfg = self.config
        decay = cfg.ignition.decay
        plasticity = cfg.ignition.plasticity
        # Exactly the five knobs required by the hackathon statement. Secondary
        # coefficients are rendered inside the g/h records rather than promoted to
        # extra top-level hyperparameters.
        return (
            HyperparameterRecord(
                "initial_lifetime",
                cfg.lifecycle.initial_lifetime_ticks,
                "Protects newly inserted canonical elements long enough for integration before structural GC.",
            ),
            HyperparameterRecord(
                "decay_g",
                {
                    "kind": decay.kind,
                    "alpha": decay.alpha,
                    "midpoint_ticks": decay.midpoint_ticks,
                    "steepness": decay.steepness,
                    "half_life_ticks": decay.half_life_ticks,
                },
                "Implements configurable excitation decay while preserving a sliding activation floor.",
            ),
            HyperparameterRecord(
                "workspace_threshold_t",
                cfg.workspace.threshold,
                "Defines the floating Workspace as canonical elements with x above threshold t.",
            ),
            HyperparameterRecord(
                "weight_update_h",
                {
                    "kind": plasticity.link_kind,
                    "hebb_increment": plasticity.link_hebb_increment,
                    "async_decrement": plasticity.link_async_decrement,
                    "floor": plasticity.link_weight_floor,
                },
                "Updates only existing L from same-tick activation events; it never creates topology.",
            ),
            HyperparameterRecord(
                "rhythm_frequency_nu",
                cfg.ignition.nu,
                "Drives the internal excitability pacemaker on the synchronous Ignition clock.",
            ),
        )

    def _relation_acyclic(self, relation: str, *, h_only: bool = False) -> bool:
        adjacency: dict[str, list[str]] = {}
        for link in self.core.store.links():
            if link.relation_id.upper() != relation.upper():
                continue
            if h_only:
                if self.core.store.domain_of(link.source.uid) is not Domain.H:
                    continue
                if self.core.store.domain_of(link.target.uid) is not Domain.H:
                    continue
            adjacency.setdefault(link.source.uid, []).append(link.target.uid)
            adjacency.setdefault(link.target.uid, [])

        visiting: set[str] = set()
        done: set[str] = set()

        def visit(uid: str) -> bool:
            if uid in done:
                return True
            if uid in visiting:
                return False
            visiting.add(uid)
            for child in adjacency.get(uid, ()):
                if not visit(child):
                    return False
            visiting.remove(uid)
            done.add(uid)
            return True

        return all(visit(uid) for uid in tuple(adjacency))

    def _broken_references(self) -> tuple[str, ...]:
        broken: list[str] = []
        for domain in Domain:
            for element in self.core.store.elements(domain):
                for ref in self.core.store.structural_children(element.uid):
                    if not self.core.store.has_uid(ref.uid):
                        broken.append(f"{element.uid}->{ref.kind.value}:{ref.uid}:missing")
                        continue
                    if self.core.store.kind_of(ref.uid) is not ref.kind:
                        broken.append(
                            f"{element.uid}->{ref.kind.value}:{ref.uid}:actual={self.core.store.kind_of(ref.uid).value}"
                        )
        for link in self.core.store.links():
            for side, ref in (("source", link.source), ("target", link.target)):
                if not self.core.store.has_uid(ref.uid):
                    broken.append(f"{link.uid}.{side}->{ref.uid}:missing")
                elif self.core.store.kind_of(ref.uid) is not ref.kind:
                    broken.append(
                        f"{link.uid}.{side}->{ref.uid}:actual={self.core.store.kind_of(ref.uid).value}"
                    )
        return tuple(sorted(broken))
