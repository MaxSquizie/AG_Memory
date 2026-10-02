from __future__ import annotations

from datetime import datetime

from ah.core import AHCore
from ah.model import Domain, Property, Ref, SemanticEntity

from .contracts import TemporalKind, TemporalPrecision, TemporalValue


_TIME_KEY = "temporal_key"


def temporal_value_from_entity(entity: SemanticEntity) -> TemporalValue | None:
    if not bool(entity.meta.get("semantic_time", False)):
        return None
    try:
        kind = TemporalKind(str(entity.properties["kind"].value))
        precision = TemporalPrecision(str(entity.properties["precision"].value))
    except (KeyError, ValueError):
        return None
    start_prop = entity.properties.get("start")
    end_prop = entity.properties.get("end")
    timezone_prop = entity.properties.get("timezone")
    source_prop = entity.properties.get("source_text")
    return TemporalValue(
        kind=kind,
        start=None if start_prop is None or start_prop.value in {None, ""} else str(start_prop.value),
        end=None if end_prop is None or end_prop.value in {None, ""} else str(end_prop.value),
        precision=precision,
        timezone=None if timezone_prop is None or timezone_prop.value in {None, ""} else str(timezone_prop.value),
        source_text=None if source_prop is None or source_prop.value in {None, ""} else str(source_prop.value),
    )


def temporal_value_from_ref(core: AHCore, ref: Ref) -> TemporalValue | None:
    if not core.store.has_uid(ref.uid):
        return None
    element = core.store.get_element_any_domain(ref.uid)
    if not isinstance(element, SemanticEntity):
        return None
    return temporal_value_from_entity(element)


def _semantic_time_match(core: AHCore, refs, value: TemporalValue) -> Ref | None:
    """Return one existing time entity with the same normalized semantic identity."""
    seen: set[str] = set()
    for ref in refs:
        if ref.uid in seen or ref.kind.value != "M":
            continue
        seen.add(ref.uid)
        element = core.store.get_element_any_domain(ref.uid)
        if not isinstance(element, SemanticEntity):
            continue
        existing = temporal_value_from_entity(element)
        if existing is not None and existing.canonical_key == value.canonical_key:
            return ref
    return None


def ensure_time_entity(core: AHCore, value: TemporalValue, *, domain: Domain = Domain.C) -> tuple[Ref, bool]:
    """Materialize/reuse semantic time as ordinary ``m``.

    ``temporal_key`` is a deterministic normalization key used only as an identity
    accelerator for semantic time values. It does not create a new canonical type.
    Calendar-date identity deliberately ignores source timezone once the date has
    been resolved.  The secondary start/end lookup keeps pre-migration entities
    reusable even when their stored ``temporal_key`` was produced by the older
    timezone-sensitive rule.
    """

    exact = core.store.find_elements_with_property(_TIME_KEY, value.canonical_key)
    matched = _semantic_time_match(core, exact, value)
    if matched is not None:
        return matched, False

    # Compatibility path for already persisted semantic-time entities whose old
    # temporal_key included an irrelevant timezone for YEAR/MONTH/DAY values.
    # Property-index lookup keeps this bounded; no global AH scan is introduced.
    legacy_candidates = []
    if value.start is not None:
        legacy_candidates.extend(
            core.store.find_elements_with_property("start", value.start)
        )
    if value.end is not None:
        legacy_candidates.extend(
            core.store.find_elements_with_property("end", value.end)
        )
    matched = _semantic_time_match(core, legacy_candidates, value)
    if matched is not None:
        return matched, False

    display = value.source_text or value.start or value.end or value.canonical_key
    properties = {
        "name": Property("name", display, "str"),
        "kind": Property("kind", value.kind.value, "str"),
        "start": Property("start", value.start or "", "str"),
        "end": Property("end", value.end or "", "str"),
        "precision": Property("precision", value.precision.value, "str"),
        "timezone": Property("timezone", value.timezone or "", "str"),
        _TIME_KEY: Property(_TIME_KEY, value.canonical_key, "str"),
    }
    if value.source_text:
        properties["source_text"] = Property("source_text", value.source_text, "str")
    entity = core.add_entity(
        domain,
        properties=properties,
        meta={"semantic_time": True, "gc_auto_created": True},
    )
    return core.ref(entity.uid), True


def exact_datetime_from_temporal_value(value: TemporalValue) -> datetime | None:
    if value.kind is not TemporalKind.POINT or value.start is None or "T" not in value.start:
        return None
    try:
        return datetime.fromisoformat(value.start)
    except ValueError:
        return None


def exact_datetime_from_ref(core: AHCore, ref: Ref) -> datetime | None:
    value = temporal_value_from_ref(core, ref)
    return None if value is None else exact_datetime_from_temporal_value(value)
