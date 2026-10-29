"""Explicit short-label transport for a precomputed closed selection set.

``SELECT_LABELS_V1`` changes only the model's wire format. Python assigns labels
to existing candidate IDs and creates the ordinary ``SelectionResponse``. It
does not create candidates, grant semantic resolution or supply truth grounds.
The legacy JSON protocol remains separate: neither decoder guesses the other
format or silently retries a rejected reply.
"""
from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence

from .selection_protocol import (
    DecisionSchema,
    ProtocolError,
    SelectionResponse,
    validate_selection_response,
)

PROTOCOL_VERSION = "SELECT_LABELS_V1"
_PICKS = re.compile(r"[1-9][0-9]*(?:,[1-9][0-9]*)*", re.ASCII)


def _closed_ids(candidate_ids: Sequence[str]) -> tuple[str, ...]:
    if isinstance(candidate_ids, (str, bytes)):
        raise ValueError("candidate IDs must be an ordered sequence, not text")
    if not isinstance(candidate_ids, Sequence):
        raise ValueError("candidate IDs must have an explicit stable order")
    ids = tuple(candidate_ids)
    if not all(isinstance(cid, str) and cid for cid in ids):
        raise ValueError("candidate IDs must be nonempty strings")
    if len(set(ids)) != len(ids):
        raise ValueError("closed selection set contains duplicate candidate IDs")
    return ids


def selection_label_instructions(candidate_ids: Sequence[str]) -> str:
    """Reply grammar only; candidate IDs belong to the separate audit record."""
    ids = _closed_ids(candidate_ids)
    return (
        "Reply with the number of the supported option. "
        "If multiple interpretations remain supported, list their numbers separated by commas. "
        "These are alternative readings, not jointly selected objects. "
        "Insufficient context: ?\n"
        "No candidate fits: 0\n"
        "One line, no spaces. No JSON or explanation."
        + ("\n(empty candidate set)" if not ids else "")
    )


def build_label_selection_prompt(
    *,
    slot_id: str,
    frame_id: str,
    context_span: str,
    mentions: Mapping[str, str],
    schema: DecisionSchema,
    contextual_statements: tuple[str, ...] = (),
    candidates: tuple[str, ...] | None = None,
) -> str:
    """English bounded-selection prompt retaining all declared context.

    The labels describe preformed candidates only; final roles and semantic
    outcomes remain the responsibility of joint validation after selection.
    """
    ids = _closed_ids(tuple(schema.relations) if candidates is None else candidates)
    missing = [cid for cid in ids if cid not in schema.relations]
    if missing:
        raise ValueError(f"candidate IDs missing from decision schema: {missing}")
    mention_lines = "\n".join(f"  {key}={value}" for key, value in mentions.items())
    candidate_lines = "\n".join(
        f"{index}. {schema.relations[cid].name}" +
        (f" — {schema.relations[cid].meaning_en}" if schema.relations[cid].meaning_en
         and schema.relations[cid].meaning_en != schema.relations[cid].name else "")
        for index, cid in enumerate(ids, 1)
    )
    context_block = (
        "Supplied context:\n"
        + "\n".join(f"  - {statement}" for statement in contextual_statements)
        if contextual_statements
        else ""
    )
    from .selection_prompt import SelectionPrompt
    return SelectionPrompt(
        f"Decision slot: {slot_id}\n"
        f"Context span: {context_span}\n"
        + (context_block + '\n' if context_block else '')
        + (f"Mentioned words:\n{mention_lines}\n" if mention_lines else '')
        + f"Options:\n{candidate_lines}\n"
        + selection_label_instructions(ids),
        {'protocol': PROTOCOL_VERSION, 'slot': slot_id, 'frame_id': frame_id,
         'schema': schema.version, 'candidates': list(ids), 'multiplicity':'ALTERNATIVE_READINGS'},
    )


def validate_selection_label_response(
    raw: str,
    schema: DecisionSchema,
    candidates: Sequence[str],
    allowed: frozenset[str] | None = None,
) -> SelectionResponse:
    """Decode a label reply, then apply the ordinary closed-ID/cardinality gate.

    Outer whitespace is transport-only. Internal whitespace, malformed labels,
    duplicates, unknown ordinals, legacy JSON and additional text are rejected.
    The response's optional diagnostic note is empty: model-generated free text
    is not needed to establish any selection or truth ground.
    """
    ids = _closed_ids(candidates)
    missing = [cid for cid in ids if cid not in schema.relations]
    if missing:
        raise ValueError(f"candidate IDs missing from decision schema: {missing}")
    if not isinstance(raw, str):
        raise ProtocolError("selection-label response must be text")
    reply = raw.strip()
    if reply == "?":
        outcome, selected = "INSUFFICIENT_CONTEXT", []
    elif reply == "0":
        outcome, selected = "NONE_FIT", []
    else:
        # No valid reply can exceed selecting each label in the closed set once.
        # Reject before numeric conversion, including arbitrarily long integers.
        limit = max(1, sum(len(str(i)) for i in range(1, len(ids) + 1)) + max(0, len(ids) - 1))
        if len(reply) > limit or not _PICKS.fullmatch(reply):
            raise ProtocolError("malformed SELECT_LABELS_V1 reply")
        labels = reply.split(",")
        if any(len(label) > len(str(len(ids))) for label in labels):
            raise ProtocolError("selection label outside the decision's closed set")
        if len(labels) != len(set(labels)):
            raise ProtocolError("duplicate selected labels")
        indexes = [int(label) for label in labels]
        if any(index > len(ids) for index in indexes):
            raise ProtocolError("selection label outside the decision's closed set")
        selected = [ids[index - 1] for index in indexes]
        outcome = "ONE_SELECTED" if len(selected) == 1 else "MULTIPLE_ADMISSIBLE"
    pool = frozenset(ids) if allowed is None else frozenset(ids) & allowed
    # JSON is built by Python, never generated by the model. Reuse the existing
    # verifier so outcome cardinality and allowed candidate IDs remain unchanged.
    return validate_selection_response(
        json.dumps({"outcome": outcome, "selected": selected}), schema, allowed=pool
    )
