from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
import re

from ah.core import AHCore, SupportRecord
from ah.model import ActantRole, Domain, Ref, RefKind

from .contracts import TemporalKind, TemporalRelation, TemporalValue
from .storage import temporal_value_from_ref


class TemporalTruth(str, Enum):
    PROVED = "PROVED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class TemporalRelationResult:
    status: TemporalTruth
    relation: TemporalRelation | None = None
    ref: Ref | None = None


def _parse_bound(value: str | None) -> tuple[datetime, datetime] | None:
    """Convert only fully orderable normalized bounds to a closed range.

    Partial values deliberately return ``None`` rather than inventing missing year,
    date or clock components. A day/month/year denotes its natural covered range.
    """
    if value is None or value.startswith("--") or value.startswith("T"):
        return None
    try:
        if re.fullmatch(r"\d{4}", value):
            year = int(value)
            return datetime(year, 1, 1), datetime(year, 12, 31, 23, 59, 59, 999999)
        if re.fullmatch(r"\d{4}-\d{2}", value):
            year, month = (int(x) for x in value.split("-"))
            start = datetime(year, month, 1)
            if month == 12:
                next_month = datetime(year + 1, 1, 1)
            else:
                next_month = datetime(year, month + 1, 1)
            return start, next_month - timedelta(microseconds=1)
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            start = datetime.fromisoformat(value)
            return start, start.replace(hour=23, minute=59, second=59, microsecond=999999)
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is not None:
            dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt, dt
    except (ValueError, TypeError):
        return None


def _interval(value: TemporalValue) -> tuple[datetime | None, datetime | None] | None:
    if value.kind is TemporalKind.POINT:
        parsed = _parse_bound(value.start)
        if parsed is None:
            return None
        return parsed
    left = _parse_bound(value.start) if value.start is not None else None
    right = _parse_bound(value.end) if value.end is not None else None
    start = None if left is None else left[0]
    end = None if right is None else right[1]
    if value.start is not None and left is None:
        return None
    if value.end is not None and right is None:
        return None
    return start, end


class TemporalReasoner:
    """Deterministic interval relation evaluator over canonical TIME ``m`` nodes."""

    def __init__(self, core: AHCore) -> None:
        self.core = core

    def compare(self, left: Ref, right: Ref) -> TemporalRelationResult:
        left_value = temporal_value_from_ref(self.core, left)
        right_value = temporal_value_from_ref(self.core, right)
        if left_value is None or right_value is None:
            return TemporalRelationResult(TemporalTruth.UNKNOWN)
        a = _interval(left_value); b = _interval(right_value)
        if a is None or b is None:
            return TemporalRelationResult(TemporalTruth.UNKNOWN)
        a_start, a_end = a; b_start, b_end = b

        if a_end is not None and b_start is not None and a_end < b_start:
            return TemporalRelationResult(TemporalTruth.PROVED, TemporalRelation.BEFORE)
        if b_end is not None and a_start is not None and b_end < a_start:
            return TemporalRelationResult(TemporalTruth.PROVED, TemporalRelation.AFTER)
        if a_start is not None and b_start is not None and a_end is not None and b_end is not None:
            if a_start <= b_start and a_end >= b_end:
                return TemporalRelationResult(TemporalTruth.PROVED, TemporalRelation.CONTAINS)
            if max(a_start, b_start) <= min(a_end, b_end):
                return TemporalRelationResult(TemporalTruth.PROVED, TemporalRelation.OVERLAP)
        return TemporalRelationResult(TemporalTruth.UNKNOWN)

    def materialize(self, left: Ref, right: Ref) -> TemporalRelationResult:
        result = self.compare(left, right)
        if result.status is not TemporalTruth.PROVED or result.relation is None:
            return result
        form = result.relation.value
        symbols = self.core.store.find_symbols_by_form(form)
        if len(symbols) > 1:
            raise ValueError(f"Ambiguous system temporal predicate symbol: {form}")
        symbol = symbols[0] if symbols else self.core.add_abstract_symbol({form})
        templates = [
            t for t in self.core.store.find_templates_by_predicate(symbol.uid)
            if t.roles == (ActantRole.SUBJECT, ActantRole.OBJECT)
        ]
        template = templates[0] if templates else self.core.add_template(
            Domain.C, self.core.ref(symbol.uid), (ActantRole.SUBJECT, ActantRole.OBJECT)
        )
        node, _created = self.core.add_hypernode(
            Domain.C,
            self.core.ref(template.uid),
            {ActantRole.SUBJECT: left, ActantRole.OBJECT: right},
            weight=0.2,
            meta={"temporal_derived": True},
            count_occurrence=False,
        )
        ref = self.core.ref(node.uid)
        self.core.add_support(
            ref,
            SupportRecord(
                premise_refs=(left, right),
                rule_id="TEMPORAL_INTERVAL_COMPARISON",
                relation_id=result.relation.value,
            ),
        )
        return TemporalRelationResult(result.status, result.relation, ref)
