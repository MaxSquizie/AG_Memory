# -*- coding: utf-8 -*-
"""Bounded-selection micro-shot protocol.

Implements docs/PILOT_DEMO_REFERENCES_V1.md (frozen v1), section 8.2:

- Protocol language: English.
- The LLM only SELECTS from a closed candidate set pre-formed by Python; it never
  generates values. A response containing an unknown ID, malformed JSON, or a
  cardinality/outcome mismatch is REJECTED as a protocol error (a failed call,
  counted in budget) — accepting such a response would be the mechanism violation.
- Outcome-to-JSON binding is unambiguous:
    ONE_SELECTED         -> exactly one selected ID
    MULTIPLE_ADMISSIBLE  -> at least two distinct selected IDs
    INSUFFICIENT_CONTEXT -> empty selection (keeps its own status)
    NONE_FIT             -> empty selection (the only outcome that becomes
                           NO_CANDIDATE + miss report)
- The validator returns a VERIFIED PROTOCOL OUTCOME and nothing more. It never grants
  a semantic outcome: RESOLVED/UNRESOLVED/etc. are granted by T4 joint validation only.
- rev8: the closed set is per DECISION, not global. ``candidates_for_slot`` applies the
  schema's declared candidate_generation rule (all declared relations minus provable
  type/arity incompatibility; no semantic form->value prefiltering), and the validator
  checks selected ids against THAT decision's set — a schema id outside the decision's
  candidates is a protocol error even though it exists in the schema.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping

OUTCOMES = ("ONE_SELECTED", "MULTIPLE_ADMISSIBLE", "INSUFFICIENT_CONTEXT", "NONE_FIT")


class ProtocolError(Exception):
    """A rejected micro-shot response: malformed JSON, unknown ID, or an
    outcome/cardinality mismatch. This is a failed call (budget), NOT a mechanism
    violation. Accepting such a response downstream would be C3."""


@dataclass(frozen=True)
class Relation:
    id: str
    name: str
    arity: int
    args: tuple[str, ...]
    meaning_en: str


@dataclass(frozen=True)
class DecisionSchema:
    version: str
    relations: Mapping[str, Relation] = field(compare=False)

    def candidate_lines(self) -> list[str]:
        return [f"{r.id}. {r.name}({', '.join(r.args)}) — {r.meaning_en}" for r in self.relations.values()]


def candidates_for_slot(schema: DecisionSchema, arity: int) -> tuple[str, ...]:
    """The declared candidate_generation rule (schemas/decision_schema_v1.json):
    propose ALL declared relations minus provable type/arity incompatibility.
    No semantic form->value filters — a construction does not determine the value,
    and pre-filtering would hint the answer to the selector."""
    return tuple(r.id for r in schema.relations.values() if r.arity == arity)


def load_decision_schema(path: str | Path | None = None) -> DecisionSchema:
    if path is None:
        # repo root / schemas/decision_schema_v1.json (src layout)
        path = Path(__file__).resolve().parents[3] / "schemas" / "decision_schema_v1.json"
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    relations = {
        item["id"]: Relation(
            id=item["id"],
            name=item["name"],
            arity=int(item["arity"]),
            args=tuple(item["args"]),
            meaning_en=item["meaning_en"],
        )
        for item in raw["relations"]
    }
    return DecisionSchema(version=raw["version"], relations=relations)


@dataclass(frozen=True)
class SelectionResponse:
    """A VERIFIED protocol response. ``outcome`` is a protocol outcome (enum above),
    not a semantic one: the validator proves well-formedness and cardinality binding
    only. The semantic outcome of the decision is granted by T4 joint validation,
    which also checks positive grounds — a unique pick here is PROVISIONAL, never RESOLVED."""

    outcome: str  # ONE_SELECTED | MULTIPLE_ADMISSIBLE | INSUFFICIENT_CONTEXT | NONE_FIT
    selected: tuple[str, ...]
    note: str = ""


def build_selection_prompt(
    *,
    slot_id: str,
    frame_id: str,
    context_span: str,
    mentions: Mapping[str, str],
    schema: DecisionSchema,
    contextual_statements: tuple[str, ...] = (),
    candidates: tuple[str, ...] | None = None,
) -> str:
    """Strict English template (docs §8.2). Participants are mentions and
    preliminary structural links — the frame is committed only together with its
    validated bindings, so no final roles are asserted here.

    ``contextual_statements`` are DECLARED contextual statements (C grounds) that
    the selector may rely on; the baseline run passes none. They appear in the
    prompt verbatim, so a model judgment citing them is traceable to its input.

    rev8: ``candidates`` is THIS decision's closed set (from candidates_for_slot);
    when given, only those relations are listed — the selector may not select from
    the rest of the schema."""
    mention_lines = "\n".join(f"  {k}={v}" for k, v in mentions.items())
    if candidates is None:
        candidate_lines = "\n".join(schema.candidate_lines())
    else:
        known = [schema.relations[c] for c in candidates if c in schema.relations]
        candidate_lines = "\n".join(f"{r.id}. {r.name} — {r.meaning_en}" for r in known)
    context_block = (
        f"Declared contextual statements (C grounds):\n"
        + "\n".join(f"  - {s}" for s in contextual_statements)
        if contextual_statements
        else "Declared contextual statements: none"
    )
    return (
        f"Decision slot: {slot_id} — predicate value of frame {frame_id}\n"
        f"Context span: {context_span}\n"
        f"{context_block}\n"
        f"Mentions and preliminary structural links:\n{mention_lines}\n"
        f"Candidates (schema {schema.version}, closed set):\n{candidate_lines}\n"
        "Task: select the admissible candidate(s), or report that none fits / context is insufficient.\n"
        'Respond with JSON only: {"outcome": "ONE_SELECTED" | "MULTIPLE_ADMISSIBLE" |'
        ' "INSUFFICIENT_CONTEXT" | "NONE_FIT", "selected": ["<id>"], "note": "..."}\n'
        "Rules: outcome ONE_SELECTED requires exactly one selected id; MULTIPLE_ADMISSIBLE"
        " requires at least two distinct ids; INSUFFICIENT_CONTEXT and NONE_FIT require an empty"
        " selected list. Only select from the closed candidate set."
    )


def validate_selection_response(
    raw: str,
    schema: DecisionSchema,
    allowed: frozenset[str] | None = None,
) -> SelectionResponse:
    """Validate a raw LLM response against the protocol.

    Raises ProtocolError on any violation (malformed JSON, unknown ID, outcome not in
    the enum, or outcome/cardinality mismatch). A raised error means the call is
    rejected and counted as a failed call — it must never be accepted downstream.

    rev8: ``allowed`` is the DECISION's closed candidate set. When given, selected ids
    are checked against it — an id that exists in the schema but not in this decision's
    candidates is still a protocol error (selecting outside the declared set).
    """
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ProtocolError(f"malformed JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise ProtocolError("response is not a JSON object")

    outcome = data.get("outcome")
    if outcome not in OUTCOMES:
        raise ProtocolError(f"unknown outcome: {outcome!r}")

    selected_raw = data.get("selected", [])
    if not isinstance(selected_raw, list) or not all(isinstance(i, str) for i in selected_raw):
        raise ProtocolError(f"'selected' must be a list of id strings: {selected_raw!r}")

    pool = allowed if allowed is not None else set(schema.relations)
    unknown = [i for i in selected_raw if i not in pool]
    if unknown:
        raise ProtocolError(
            f"selection outside the decision's closed candidate set: {unknown}"
            + (f" (allowed: {sorted(pool)})" if allowed is not None else "")
        )

    distinct = set(selected_raw)
    required = {
        "ONE_SELECTED": lambda n: n == 1,
        "MULTIPLE_ADMISSIBLE": lambda n: n >= 2,
        "INSUFFICIENT_CONTEXT": lambda n: n == 0,
        "NONE_FIT": lambda n: n == 0,
    }[outcome]
    if not required(len(distinct)):
        raise ProtocolError(
            f"outcome {outcome} requires its cardinality binding; got selected={selected_raw}"
        )

    note = data.get("note", "")
    if not isinstance(note, str):
        raise ProtocolError(f"'note' must be a string: {note!r}")

    return SelectionResponse(outcome=outcome, selected=tuple(selected_raw), note=note)
