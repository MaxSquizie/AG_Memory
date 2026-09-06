from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Any, TYPE_CHECKING
import json
import os
import tempfile

from ah.agent.interaction_context import ExistentialDiscourseAnchor, InteractionContext
from ah.config import PersistenceSettings
from ah.model import (
    AbstractSymbol,
    ActantRole,
    Domain,
    FunctionSymbol,
    Group,
    Hypernode,
    Link,
    BoundVar,
    VariableSort,
    Property,
    Ref,
    RefKind,
    RuntimeState,
    SemanticEntity,
    Template,
)

from .operations import AHCore
from .supports import SupportRecord
from .store import AHStore
from .uid import UidGenerator, UuidUidGenerator
from .validation import validate_hypernode, validate_ref_exists

if TYPE_CHECKING:
    from ah.ignition.engine import IgnitionEngine, IgnitionSnapshot


SCHEMA_VERSION = 1


@dataclass(frozen=True, slots=True)
class PersistenceBundle:
    core: AHCore
    ignition_snapshot: "IgnitionSnapshot | None"
    interaction_context: InteractionContext | None


class PersistenceError(RuntimeError):
    pass


def _ref(ref: Ref) -> dict[str, str]:
    return {"uid": ref.uid, "kind": ref.kind.value}


def _parse_ref(raw: dict[str, Any]) -> Ref:
    return Ref(str(raw["uid"]), RefKind(str(raw["kind"])))


def _operand(value: Ref | BoundVar) -> dict[str, Any]:
    if isinstance(value, Ref):
        # Keep legacy shape for ordinary AH refs so old schema-1 dumps remain
        # byte-shape compatible where no BoundVar is used.
        return _ref(value)
    if isinstance(value, BoundVar):
        return {
            "__operand__": "BOUND_VAR",
            "local_id": value.local_id,
            "sort": value.sort.value,
        }
    raise PersistenceError(f"Unsupported function operand: {type(value).__name__}")


def _parse_operand(raw: dict[str, Any]) -> Ref | BoundVar:
    if raw.get("__operand__") == "BOUND_VAR":
        return BoundVar(
            int(raw["local_id"]),
            VariableSort(str(raw.get("sort", VariableSort.UNKNOWN.value))),
        )
    return _parse_ref(raw)


def _encode_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, datetime):
        return {"__type__": "datetime", "value": value.isoformat()}
    if isinstance(value, date):
        return {"__type__": "date", "value": value.isoformat()}
    if isinstance(value, Enum):
        return {"__type__": "enum", "class": type(value).__name__, "value": value.value}
    if isinstance(value, tuple):
        return {"__type__": "tuple", "items": [_encode_value(v) for v in value]}
    if isinstance(value, frozenset):
        return {"__type__": "frozenset", "items": [_encode_value(v) for v in value]}
    if isinstance(value, set):
        return {"__type__": "set", "items": [_encode_value(v) for v in value]}
    if isinstance(value, list):
        return [_encode_value(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _encode_value(v) for k, v in value.items()}
    raise PersistenceError(f"Unsupported persisted value type: {type(value).__name__}")


def _decode_value(value: Any) -> Any:
    if isinstance(value, list):
        return [_decode_value(v) for v in value]
    if not isinstance(value, dict):
        return value
    marker = value.get("__type__")
    if marker == "datetime":
        return datetime.fromisoformat(str(value["value"]))
    if marker == "date":
        return date.fromisoformat(str(value["value"]))
    if marker == "tuple":
        return tuple(_decode_value(v) for v in value.get("items", []))
    if marker == "set":
        return set(_decode_value(v) for v in value.get("items", []))
    if marker == "frozenset":
        return frozenset(_decode_value(v) for v in value.get("items", []))
    if marker == "enum":
        # Meta/Pr must not depend on Python enum class identity. Preserve semantic value.
        return value.get("value")
    return {str(k): _decode_value(v) for k, v in value.items()}


def _properties(raw) -> dict[str, Any]:
    return {
        name: {
            "name": prop.name,
            "value": _encode_value(prop.value),
            "type_name": prop.type_name,
            "unit": prop.unit,
        }
        for name, prop in raw.items()
    }


def _parse_properties(raw: dict[str, Any]) -> dict[str, Property]:
    out: dict[str, Property] = {}
    for key, item in raw.items():
        out[str(key)] = Property(
            name=str(item.get("name", key)),
            value=_decode_value(item.get("value")),
            type_name=str(item.get("type_name", "object")),
            unit=(None if item.get("unit") is None else str(item.get("unit"))),
        )
    return out


def _serialize_element(domain: Domain, element: Any) -> dict[str, Any]:
    base = {"uid": element.uid, "domain": domain.value}
    if isinstance(element, SemanticEntity):
        return {**base, "kind": "M", "properties": _properties(element.properties), "meta": _encode_value(dict(element.meta))}
    if isinstance(element, FunctionSymbol):
        return {**base, "kind": "G", "function_id": element.function_id, "operands": [_operand(r) for r in element.operands]}
    if isinstance(element, Group):
        return {
            **base,
            "kind": "K",
            "members": [_ref(r) for r in element.members],
            "properties": _properties(element.properties),
            "meta": _encode_value(dict(element.meta)),
        }
    if isinstance(element, Template):
        return {
            **base,
            "kind": "T",
            "predicate": _ref(element.predicate),
            "roles": [r.value for r in element.roles],
        }
    if isinstance(element, Hypernode):
        return {
            **base,
            "kind": "N",
            "weight": element.weight,
            "template": _ref(element.template),
            "actants": {role.value: _operand(value) for role, value in element.actants.items()},
            "properties": _properties(element.properties),
            "meta": _encode_value(dict(element.meta)),
        }
    raise PersistenceError(f"Unsupported canonical element: {type(element).__name__}")


def _serialize_runtime(state: RuntimeState) -> dict[str, Any]:
    return {
        "excitation": state.excitation,
        "output": state.output,
        "activation_function_id": state.activation_function_id,
        "activation_event": state.activation_event,
        "decay_age": state.decay_age,
        "decay_origin_excitation": state.decay_origin_excitation,
        "first_excitation_tick": state.first_excitation_tick,
        "last_activation_tick": state.last_activation_tick,
        "last_output_tick": state.last_output_tick,
    }


def _parse_runtime(raw: dict[str, Any]) -> RuntimeState:
    return RuntimeState(
        excitation=float(raw.get("excitation", 0.0)),
        output=float(raw.get("output", 0.0)),
        activation_function_id=str(raw.get("activation_function_id", "DEFAULT")),
        activation_event=bool(raw.get("activation_event", False)),
        decay_age=int(raw.get("decay_age", 0)),
        decay_origin_excitation=float(raw.get("decay_origin_excitation", 0.0)),
        first_excitation_tick=(None if raw.get("first_excitation_tick") is None else int(raw["first_excitation_tick"])),
        last_activation_tick=(None if raw.get("last_activation_tick") is None else int(raw["last_activation_tick"])),
        last_output_tick=(None if raw.get("last_output_tick") is None else int(raw["last_output_tick"])),
    )


def _serialize_context(context: InteractionContext | None) -> dict[str, Any] | None:
    if context is None:
        return None
    return {
        "self_ref": _ref(context.self_ref) if context.self_ref else None,
        "user_ref": _ref(context.user_ref) if context.user_ref else None,
        "now_ref": _ref(context.now_ref) if context.now_ref else None,
        "active_location_ref": _ref(context.active_location_ref) if context.active_location_ref else None,
        "pronoun_refs": {k: _ref(v) for k, v in context.pronoun_refs.items()},
        "existential_pronoun_anchors": {
            k: {
                "existential_ref": _ref(anchor.existential_ref),
                "member_refs": [_ref(ref) for ref in anchor.member_refs],
                "variable_id": anchor.variable_id,
            }
            for k, anchor in context.existential_pronoun_anchors.items()
        },
        "last_experience_ref": _ref(context.last_experience_ref) if context.last_experience_ref else None,
        "pending_clarification_refs": [_ref(ref) for ref in context.pending_clarification_refs],
    }




def _parse_context(core: AHCore, raw: dict[str, Any] | None) -> InteractionContext | None:
    if raw is None:
        return None

    def existing(value: Any) -> Ref | None:
        if not value:
            return None
        ref = _parse_ref(value)
        if not core.store.has_uid(ref.uid):
            return None
        return core.ref(ref.uid)

    ctx = InteractionContext(
        self_ref=existing(raw.get("self_ref")),
        user_ref=existing(raw.get("user_ref")),
        now_ref=existing(raw.get("now_ref")),
        active_location_ref=existing(raw.get("active_location_ref")),
        last_experience_ref=existing(raw.get("last_experience_ref")),
    )
    ctx.pronoun_refs = {
        str(k): ref
        for k, value in (raw.get("pronoun_refs") or {}).items()
        if (ref := existing(value)) is not None
    }
    anchors: dict[str, ExistentialDiscourseAnchor] = {}
    for key, value in (raw.get("existential_pronoun_anchors") or {}).items():
        if not isinstance(value, dict):
            continue
        root = existing(value.get("existential_ref"))
        members = tuple(
            ref
            for item in (value.get("member_refs") or [])
            if (ref := existing(item)) is not None
        )
        if root is None or root.kind is not RefKind.G or not members:
            continue
        try:
            anchors[str(key)] = ExistentialDiscourseAnchor(
                root, members, int(value.get("variable_id", 0))
            )
        except (TypeError, ValueError):
            continue
    ctx.existential_pronoun_anchors = anchors
    ctx.pending_clarification_refs = [
        ref
        for value in (raw.get("pending_clarification_refs") or [])
        if (ref := existing(value)) is not None and ref.kind is RefKind.K
    ]
    return ctx


class JsonPersistence:
    """Atomic JSON persistence for canonical AH + optional runtime snapshot.

    Indexes are intentionally not serialized. Loading always rebuilds them from
    canonical records, which enforces the architecture's source-of-truth boundary.
    """

    def __init__(self, path: str | Path, settings: PersistenceSettings) -> None:
        self.path = Path(path)
        self.settings = settings
        self._last_saved_tick: int | None = None

    def exists(self) -> bool:
        return self.path.is_file()

    def save(
        self,
        core: AHCore,
        *,
        ignition: "IgnitionEngine | None" = None,
        context: InteractionContext | None = None,
    ) -> None:
        if not self.settings.enabled:
            return
        payload: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "canonical": {
                "symbols": [
                    {"uid": s.uid, "forms": sorted(s.forms)}
                    for s in sorted(core.store._state.symbols.values(), key=lambda x: x.uid)
                ],
                "elements": [
                    _serialize_element(domain, element)
                    for domain in Domain
                    for element in sorted(core.store.elements(domain), key=lambda x: x.uid)
                ],
                "links": [
                    {
                        "uid": link.uid,
                        "relation_id": link.relation_id,
                        "weight": link.weight,
                        "source": _ref(link.source),
                        "target": _ref(link.target),
                    }
                    for link in sorted(core.store.links(), key=lambda x: x.uid)
                ],
            },
            "interaction_context": _serialize_context(context),
            # Diagnostic insertion chronology is persisted separately from
            # canonical AH. It never participates in identity/inference and is
            # optional for backward compatibility with older schema-1 files.
            "store_metadata": {
                "creation_sequence": {
                    uid: int(seq)
                    for uid, seq in sorted(core.store.creation_items(), key=lambda item: item[1])
                },
                "next_creation_sequence": int(core.store._state.next_creation_sequence),
                "lifetime_clock_tick": int(core.store._state.lifetime_clock_tick),
                "lifetime_birth_tick": {
                    uid: int(tick)
                    for uid, tick in sorted(core.store.lifetime_birth_items())
                    if core.store.has_uid(uid)
                },
                "lifetime_managed_uids": sorted(core.store.lifetime_managed_uids()),
                "proof_supports": {
                    conclusion_uid: [
                        {
                            "premise_refs": [_ref(ref) for ref in support.premise_refs],
                            "rule_id": support.rule_id,
                            "relation_id": support.relation_id,
                        }
                        for support in supports
                    ]
                    for conclusion_uid, supports in core.supports.items()
                },
            },
        }

        if self.settings.save_runtime_state:
            payload["runtime_states"] = {
                uid: _serialize_runtime(state)
                for uid, state in sorted(core.store.runtime_items())
            }
        if ignition is not None:
            snap = ignition.export_snapshot(include_pending=self.settings.save_pending_impulses)
            payload["ignition"] = {
                "tick_index": snap.tick_index,
                "incoming": snap.incoming,
                "seed_reasons": {k: list(v) for k, v in snap.seed_reasons.items()},
                "pending_refutations": list(snap.pending_refutations),
                "pacemaker_incoming": dict(snap.pacemaker_incoming),
                "pacemaker_only_excitation": list(snap.pacemaker_only_excitation),
                "pacemaker": {
                    "phase": snap.pacemaker.phase,
                    "cursor": snap.pacemaker.cursor,
                    "pulse_count": snap.pacemaker.pulse_count,
                },
            }
            self._last_saved_tick = snap.tick_index

        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
        fd, tmp_name = tempfile.mkstemp(prefix=self.path.name + ".", suffix=".tmp", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
                fh.write(data)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp_name, self.path)
        finally:
            if os.path.exists(tmp_name):
                os.unlink(tmp_name)

    def maybe_autosave(
        self,
        core: AHCore,
        *,
        ignition: "IgnitionEngine",
        context: InteractionContext | None,
    ) -> bool:
        if not self.settings.enabled:
            return False
        tick = ignition.tick_index
        if tick <= 0 or tick % self.settings.autosave_every_ticks != 0:
            return False
        if self._last_saved_tick == tick:
            return False
        self.save(core, ignition=ignition, context=context)
        return True

    def load(self, *, uid_generator: UidGenerator | None = None) -> PersistenceBundle:
        if not self.exists():
            raise FileNotFoundError(self.path)
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise PersistenceError(f"Cannot read persistence file {self.path}: {exc}") from exc
        version = int(raw.get("schema_version", 0))
        if version != SCHEMA_VERSION:
            raise PersistenceError(f"Unsupported persistence schema {version}; expected {SCHEMA_VERSION}")

        store = AHStore()
        canonical = raw.get("canonical") or {}

        # Insert canonical records without depending on serialization order; validate
        # references only after every UID is registered.
        for item in canonical.get("symbols", []):
            store._state.symbols[str(item["uid"])] = AbstractSymbol(
                str(item["uid"]), frozenset(str(v) for v in item.get("forms", []))
            )

        for item in canonical.get("elements", []):
            domain = Domain(str(item["domain"]))
            kind = str(item["kind"])
            uid = str(item["uid"])
            if kind == "M":
                element = SemanticEntity(uid, _parse_properties(item.get("properties", {})), _decode_value(item.get("meta", {})))
            elif kind == "G":
                element = FunctionSymbol(uid, str(item["function_id"]), tuple(_parse_operand(v) for v in item.get("operands", [])))
            elif kind == "K":
                element = Group(
                    uid,
                    tuple(_parse_ref(v) for v in item.get("members", [])),
                    _parse_properties(item.get("properties", {})),
                    _decode_value(item.get("meta", {})),
                )
            elif kind == "T":
                element = Template(
                    uid,
                    _parse_ref(item["predicate"]),
                    tuple(ActantRole(str(v)) for v in item.get("roles", [])),
                )
            elif kind == "N":
                element = Hypernode(
                    uid,
                    float(item["weight"]),
                    _parse_ref(item["template"]),
                    {ActantRole(str(role)): _parse_operand(value) for role, value in item.get("actants", {}).items()},
                    _parse_properties(item.get("properties", {})),
                    _decode_value(item.get("meta", {})),
                )
            else:
                raise PersistenceError(f"Unknown canonical element kind: {kind}")
            store._state.domains[domain][uid] = element

        for item in canonical.get("links", []):
            link = Link(
                str(item["uid"]),
                str(item["relation_id"]),
                float(item["weight"]),
                _parse_ref(item["source"]),
                _parse_ref(item["target"]),
            )
            store._state.links[link.uid] = link

        store.rebuild_indexes()
        metadata = raw.get("store_metadata") or {}
        creation_raw = metadata.get("creation_sequence") or {}
        if creation_raw:
            store._restore_creation_sequence(
                {str(uid): int(seq) for uid, seq in creation_raw.items()},
                next_sequence=(
                    None
                    if metadata.get("next_creation_sequence") is None
                    else int(metadata.get("next_creation_sequence"))
                ),
            )
        store.restore_lifetime_metadata(
            {
                str(uid): int(tick)
                for uid, tick in (metadata.get("lifetime_birth_tick") or {}).items()
            },
            clock_tick=int(metadata.get("lifetime_clock_tick", 0)),
            managed_uids={str(uid) for uid in (metadata.get("lifetime_managed_uids") or [])},
        )
        core = AHCore(store, uid_generator or UuidUidGenerator())
        self._validate_loaded_core(core)

        support_raw = metadata.get("proof_supports") or {}
        restored_supports: dict[str, list[SupportRecord]] = {}
        for conclusion_uid, raw_supports in support_raw.items():
            if not core.store.has_uid(str(conclusion_uid)):
                continue
            records: list[SupportRecord] = []
            for item in raw_supports or []:
                premise_refs = tuple(_parse_ref(value) for value in item.get("premise_refs", []))
                if any(not core.store.has_uid(ref.uid) for ref in premise_refs):
                    continue
                records.append(
                    SupportRecord(
                        premise_refs=premise_refs,
                        rule_id=(None if item.get("rule_id") is None else str(item.get("rule_id"))),
                        relation_id=(None if item.get("relation_id") is None else str(item.get("relation_id"))),
                    )
                )
            if records:
                restored_supports[str(conclusion_uid)] = records
        core.supports.restore(restored_supports)

        if self.settings.save_runtime_state:
            states_raw = raw.get("runtime_states") or {}
            states = {
                uid: _parse_runtime(states_raw.get(uid, {}))
                for uid, _ in core.store.runtime_items()
            }
            core.store._replace_runtime_states(states)

        if not (raw.get("store_metadata") or {}).get("creation_sequence"):
            # Pre-v0.31 files did not persist insertion chronology. Reconstruct the
            # best possible order now that runtime first-excitation ticks are known.
            core.store._rebuild_legacy_creation_sequence()

        ign_raw = raw.get("ignition")
        ignition_snapshot = None
        if isinstance(ign_raw, dict):
            from ah.ignition.engine import IgnitionSnapshot
            from ah.ignition.pacemaker import PacemakerSnapshot
            pac_raw = ign_raw.get("pacemaker") or {}
            ignition_snapshot = IgnitionSnapshot(
                tick_index=int(ign_raw.get("tick_index", 0)),
                incoming={str(k): float(v) for k, v in (ign_raw.get("incoming") or {}).items()},
                seed_reasons={str(k): tuple(str(x) for x in v) for k, v in (ign_raw.get("seed_reasons") or {}).items()},
                pending_refutations=tuple(str(x) for x in (ign_raw.get("pending_refutations") or [])),
                pacemaker=PacemakerSnapshot(
                    phase=float(pac_raw.get("phase", 0.0)),
                    cursor=int(pac_raw.get("cursor", 0)),
                    pulse_count=int(pac_raw.get("pulse_count", 0)),
                ),
                pacemaker_incoming={
                    str(k): float(v)
                    for k, v in (ign_raw.get("pacemaker_incoming") or {}).items()
                },
                pacemaker_only_excitation=tuple(
                    str(x) for x in (ign_raw.get("pacemaker_only_excitation") or [])
                ),
            )
            self._last_saved_tick = ignition_snapshot.tick_index

        context = _parse_context(core, raw.get("interaction_context"))
        return PersistenceBundle(core, ignition_snapshot, context)

    @staticmethod
    def _validate_loaded_core(core: AHCore) -> None:
        for domain in Domain:
            for element in core.store.elements(domain):
                if isinstance(element, Template):
                    validate_ref_exists(core.store, element.predicate)
                elif isinstance(element, Hypernode):
                    validate_hypernode(core.store, element)
                elif isinstance(element, FunctionSymbol):
                    try:
                        core.function_registry.validate(element.function_id, element.operands)
                    except (KeyError, ValueError) as exc:
                        raise PersistenceError(
                            f"Invalid deterministic function {element.uid}/{element.function_id}: {exc}"
                        ) from exc
                    for operand in element.operands:
                        if isinstance(operand, Ref):
                            validate_ref_exists(core.store, operand)
                elif isinstance(element, Group):
                    for ref in element.members:
                        validate_ref_exists(core.store, ref)
        for link in core.store.links():
            validate_ref_exists(core.store, link.source)
            validate_ref_exists(core.store, link.target)
