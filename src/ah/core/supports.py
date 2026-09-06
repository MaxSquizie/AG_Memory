from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from ah.model import Ref


@dataclass(frozen=True, slots=True)
class SupportRecord:
    """Persistable dependency metadata for a materialized derived expression.

    A support is not an AH node and does not carry activation/truth strength. It
    only states which canonical premises/rule licensed one materialized result.
    """

    premise_refs: tuple[Ref, ...]
    rule_id: str | None = None
    relation_id: str | None = None

    def signature(self) -> tuple:
        return (
            tuple((ref.kind.value, ref.uid) for ref in self.premise_refs),
            self.rule_id,
            self.relation_id,
        )


class SupportLedger:
    """Dependency sidecar persisted with AH but not part of canonical q-types."""

    def __init__(self) -> None:
        self._by_conclusion: dict[str, list[SupportRecord]] = {}

    def clone(self) -> "SupportLedger":
        other = SupportLedger()
        other._by_conclusion = {
            uid: list(records) for uid, records in self._by_conclusion.items()
        }
        return other

    def replace_from(self, other: "SupportLedger") -> None:
        self._by_conclusion = {
            uid: list(records) for uid, records in other._by_conclusion.items()
        }

    def add(self, conclusion_uid: str, support: SupportRecord) -> bool:
        records = self._by_conclusion.setdefault(conclusion_uid, [])
        signature = support.signature()
        if any(existing.signature() == signature for existing in records):
            return False
        records.append(support)
        return True

    def get(self, conclusion_uid: str) -> tuple[SupportRecord, ...]:
        return tuple(self._by_conclusion.get(conclusion_uid, ()))

    def has_any(self, conclusion_uid: str) -> bool:
        return bool(self._by_conclusion.get(conclusion_uid))

    def remove_conclusion(self, conclusion_uid: str) -> tuple[SupportRecord, ...]:
        return tuple(self._by_conclusion.pop(conclusion_uid, ()))

    def invalidate_by_premise(self, premise_uid: str) -> tuple[str, ...]:
        """Drop only supports that depend on one invalidated premise.

        Returns conclusions that no longer have any support. Callers decide whether
        lifecycle/GC should later remove those conclusions.
        """

        unsupported: list[str] = []
        for conclusion_uid in tuple(self._by_conclusion):
            kept = [
                record
                for record in self._by_conclusion[conclusion_uid]
                if all(ref.uid != premise_uid for ref in record.premise_refs)
            ]
            if kept:
                self._by_conclusion[conclusion_uid] = kept
            else:
                self._by_conclusion.pop(conclusion_uid, None)
                unsupported.append(conclusion_uid)
        return tuple(sorted(unsupported))

    def rewire_ref(self, old: Ref, new: Ref) -> None:
        """Rewire support metadata during canonical merge/link replacement."""
        if old == new:
            return

        moved = self._by_conclusion.pop(old.uid, [])
        for record in moved:
            self.add(new.uid, record)

        rewritten: dict[str, list[SupportRecord]] = {}
        for conclusion_uid, records in self._by_conclusion.items():
            bucket: list[SupportRecord] = []
            for record in records:
                premise_refs = tuple(new if ref == old else ref for ref in record.premise_refs)
                candidate = SupportRecord(
                    premise_refs=premise_refs,
                    rule_id=record.rule_id,
                    relation_id=record.relation_id,
                )
                if not any(existing.signature() == candidate.signature() for existing in bucket):
                    bucket.append(candidate)
            if bucket:
                rewritten[conclusion_uid] = bucket
        self._by_conclusion = rewritten

    def items(self) -> tuple[tuple[str, tuple[SupportRecord, ...]], ...]:
        return tuple(
            (uid, tuple(self._by_conclusion[uid])) for uid in sorted(self._by_conclusion)
        )

    def restore(self, records: dict[str, Iterable[SupportRecord]]) -> None:
        self._by_conclusion = {
            uid: list(values) for uid, values in records.items() if values
        }
