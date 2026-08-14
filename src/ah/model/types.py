from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

UID = str


class Domain(str, Enum):
    C = "C"
    P = "P"
    H = "H"


class RefKind(str, Enum):
    S = "S"
    M = "M"
    G = "G"
    K = "K"
    T = "T"
    N = "N"
    L = "L"


class ActantRole(str, Enum):
    SUBJECT = "SUBJECT"
    OBJECT = "OBJECT"
    AUXILLIARY = "AUXILLIARY"
    RECIPIENT = "RECIPIENT"
    SOURCE = "SOURCE"
    ABSENTEE = "ABSENTEE"
    LOCATION = "LOCATION"
    STATE = "STATE"
    TIME = "TIME"
    DURATION = "DURATION"
    CAUSE = "CAUSE"
    PURPOSE = "PURPOSE"
    TOOL = "TOOL"
    MATERIAL = "MATERIAL"
    AMOUNT = "AMOUNT"
    HOW_TO = "HOW-TO"


@dataclass(frozen=True, slots=True)
class Ref:
    uid: UID
    kind: RefKind


@dataclass(frozen=True, slots=True)
class Property:
    name: str
    value: Any
    type_name: str
    unit: str | None = None


PropertyMap = Mapping[str, Property]
MetaMap = Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class AbstractSymbol:
    uid: UID
    forms: frozenset[str]

    def __post_init__(self) -> None:
        if not self.forms:
            raise ValueError("AbstractSymbol.forms must be non-empty")


@dataclass(frozen=True, slots=True)
class SemanticEntity:
    uid: UID
    properties: PropertyMap = field(default_factory=dict)
    meta: MetaMap = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class FunctionSymbol:
    uid: UID
    function_id: str
    operands: tuple[Ref, ...]


@dataclass(frozen=True, slots=True)
class Group:
    uid: UID
    members: tuple[Ref, ...]
    properties: PropertyMap = field(default_factory=dict)
    meta: MetaMap = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class Template:
    uid: UID
    predicate: Ref
    roles: tuple[ActantRole, ...]

    def __post_init__(self) -> None:
        if self.predicate.kind is not RefKind.S:
            raise ValueError("Template.predicate must reference S")
        if len(set(self.roles)) != len(self.roles):
            raise ValueError("Template.roles must be unique")


@dataclass(frozen=True, slots=True)
class Hypernode:
    uid: UID
    weight: float
    template: Ref
    actants: Mapping[ActantRole, Ref]
    properties: PropertyMap = field(default_factory=dict)
    meta: MetaMap = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.template.kind is not RefKind.T:
            raise ValueError("Hypernode.template must reference T")
        if not 0.0 <= self.weight <= 1.0:
            raise ValueError("Hypernode.weight must be in [0, 1]")


@dataclass(frozen=True, slots=True)
class Link:
    uid: UID
    relation_id: str
    weight: float
    source: Ref
    target: Ref

    def __post_init__(self) -> None:
        if not 0.0 <= self.weight <= 1.0:
            raise ValueError("Link.weight must be in [0, 1]")


@dataclass(slots=True)
class RuntimeState:
    excitation: float = 0.0
    output: float = 0.0
    activation_function_id: str = "DEFAULT"
    activation_event: bool = False
    decay_age: int = 0
    decay_origin_excitation: float = 0.0
    first_excitation_tick: int | None = None
    last_activation_tick: int | None = None
    last_output_tick: int | None = None


CanonicalElement = SemanticEntity | FunctionSymbol | Group | Template | Hypernode
