from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Any, TYPE_CHECKING
import json
import os
import tempfile

from ah.agent.interaction_context import InteractionContext
from ah.config import PersistenceSettings
from ah.model import (
    AbstractSymbol,
    ActantRole,
    Domain,
    FunctionSymbol,
    Group,
    Hypernode,
    Link,
    Property,
    Ref,
    RefKind,
    RuntimeState,
    SemanticEntity,
    Template,
)

from .operations import AHCore
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
        return {**base, "kind": "G", "function_id": element.function_id, "operands": [_ref(r) for r in element.operands]}
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
            "actants": {role.value: _ref(ref) for role, ref in element.actants.items()},
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
        "last_experience_ref": _ref(context.last_experience_ref) if context.last_experience_ref else None,
    }




def _repair_duplicate_symbol_payload(raw: dict[str, Any]) -> tuple[str, ...]:
    """Repair legacy persisted S duplicates produced by the pre-0.7.5 GUI.

    Canonical S is global (not C/P/H scoped) and one case-folded wordform may belong
    to only one S. Older manual GUI code could insert a second S and fail only while
    indexing, leaving the canonical record in memory and later on disk. This migration
    merges overlapping S components and rewrites every serialized S reference before
    indexes are rebuilt. It is intentionally narrow: m/N/domain dedup is not changed.
    """
    canonical = raw.get("canonical")
    if not isinstance(canonical, dict):
        return ()
    symbols = canonical.get("symbols")
    if not isinstance(symbols, list) or len(symbols) < 2:
        return ()

    parent: dict[str, str] = {}
    by_uid: dict[str, dict[str, Any]] = {}

    def find(uid: str) -> str:
        parent.setdefault(uid, uid)
        while parent[uid] != uid:
            parent[uid] = parent[parent[uid]]
            uid = parent[uid]
        return uid

    def union(a: str, b: str) -> None:
        ra, rb = find(a), find(b)
        if ra == rb:
            return
        # Stable root makes the repaired file deterministic.
        if ra < rb:
            parent[rb] = ra
        else:
            parent[ra] = rb

    form_owner: dict[str, str] = {}
    for item in symbols:
        if not isinstance(item, dict) or "uid" not in item:
            continue
        uid = str(item["uid"])
        by_uid[uid] = item
        find(uid)
        for value in item.get("forms", []):
            key = str(value).casefold()
            previous = form_owner.get(key)
            if previous is not None and previous != uid:
                union(previous, uid)
            else:
                form_owner[key] = uid

    components: dict[str, list[str]] = {}
    for uid in by_uid:
        components.setdefault(find(uid), []).append(uid)
    duplicate_components = [sorted(values) for values in components.values() if len(values) > 1]
    if not duplicate_components:
        return ()

    remap: dict[str, str] = {}
    merged_forms: dict[str, set[str]] = {}
    for component in duplicate_components:
        keep = component[0]
        merged_forms.setdefault(keep, set()).update(str(v) for v in by_uid[keep].get("forms", []))
        for uid in component[1:]:
            remap[uid] = keep
            merged_forms[keep].update(str(v) for v in by_uid[uid].get("forms", []))

    new_symbols: list[dict[str, Any]] = []
    for item in symbols:
        uid = str(item.get("uid", "")) if isinstance(item, dict) else ""
        if uid in remap:
            continue
        if uid in merged_forms:
            item = dict(item)
            item["forms"] = sorted(merged_forms[uid])
        new_symbols.append(item)
    canonical["symbols"] = new_symbols

    def rewrite_refs(value: Any) -> Any:
        if isinstance(value, list):
            return [rewrite_refs(v) for v in value]
        if not isinstance(value, dict):
            return value
        out = {k: rewrite_refs(v) for k, v in value.items()}
        if out.get("kind") == RefKind.S.value and str(out.get("uid")) in remap:
            out["uid"] = remap[str(out["uid"])]
        return out

    canonical["elements"] = rewrite_refs(canonical.get("elements", []))
    canonical["links"] = rewrite_refs(canonical.get("links", []))
    raw["interaction_context"] = rewrite_refs(raw.get("interaction_context"))

    # Runtime records are keyed directly by UID rather than serialized Ref objects.
    states = raw.get("runtime_states")
    if isinstance(states, dict):
        for old_uid, keep_uid in remap.items():
            old = states.pop(old_uid, None)
            if not isinstance(old, dict):
                continue
            current = states.get(keep_uid)
            if not isinstance(current, dict):
                states[keep_uid] = old
                continue
            # Preserve the more excited state while retaining an activation event from
            # either legacy duplicate. This avoids inventing additive excitation.
            if float(old.get("excitation", 0.0)) > float(current.get("excitation", 0.0)):
                chosen = dict(old)
            else:
                chosen = dict(current)
            chosen["activation_event"] = bool(old.get("activation_event", False)) or bool(
                current.get("activation_event", False)
            )
            states[keep_uid] = chosen

    ignition = raw.get("ignition")
    if isinstance(ignition, dict):
        incoming = ignition.get("incoming")
        if isinstance(incoming, dict):
            for old_uid, keep_uid in remap.items():
                if old_uid in incoming:
                    incoming[keep_uid] = float(incoming.get(keep_uid, 0.0)) + float(incoming.pop(old_uid))
        reasons = ignition.get("seed_reasons")
        if isinstance(reasons, dict):
            for old_uid, keep_uid in remap.items():
                old_reasons = reasons.pop(old_uid, None)
                if old_reasons is None:
                    continue
                merged = list(reasons.get(keep_uid, []))
                for reason in old_reasons:
                    if reason not in merged:
                        merged.append(reason)
                reasons[keep_uid] = merged

    return tuple(
        f"merged duplicate S {', '.join(component[1:])} -> {component[0]}"
        for component in duplicate_components
    )


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

        repairs = _repair_duplicate_symbol_payload(raw)
        if repairs:
            import warnings
            warnings.warn(
                "Persistence compatibility repair: " + "; ".join(repairs),
                RuntimeWarning,
                stacklevel=2,
            )

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
                element = FunctionSymbol(uid, str(item["function_id"]), tuple(_parse_ref(v) for v in item.get("operands", [])))
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
                    {ActantRole(str(role)): _parse_ref(ref) for role, ref in item.get("actants", {}).items()},
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
        core = AHCore(store, uid_generator or UuidUidGenerator())
        self._validate_loaded_core(core)

        if self.settings.save_runtime_state:
            states_raw = raw.get("runtime_states") or {}
            states = {
                uid: _parse_runtime(states_raw.get(uid, {}))
                for uid, _ in core.store.runtime_items()
            }
            core.store._replace_runtime_states(states)

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
                    for ref in element.operands:
                        validate_ref_exists(core.store, ref)
                elif isinstance(element, Group):
                    for ref in element.members:
                        validate_ref_exists(core.store, ref)
        for link in core.store.links():
            validate_ref_exists(core.store, link.source)
            validate_ref_exists(core.store, link.target)
