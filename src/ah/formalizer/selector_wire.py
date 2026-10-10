"""Explicit reply codecs; raw provider bytes are logged before decoding.

Real workers advertise short-label selection. Authored legacy providers keep
their separately declared JSON contract. No decoder guesses or retries a wire.
"""
from .selection_protocol import (
    ProtocolError, build_selection_prompt, validate_selection_response,
)
from .selection_labels import (
    PROTOCOL_VERSION, build_label_selection_prompt, validate_selection_label_response,
)
from .tp_proposer import build_structure_prompt, parse_and_validate
from .tp_compact_protocol import (
    COMPACT_TP_PROTOCOL, build_compact_structure_prompt, parse_compact_structure_reply,
)
from .tp_readable_protocol import (
    READABLE_TP_PROTOCOL, build_readable_structure_prompt, parse_readable_structure_reply,
)

JSON_WIRE = 'JSON_V1'


def structure_wire(selector):
    wire = getattr(selector, 'structure_reply_format', JSON_WIRE)
    if wire not in {JSON_WIRE, COMPACT_TP_PROTOCOL, READABLE_TP_PROTOCOL}:
        raise ProtocolError('unsupported structure reply protocol: ' + str(wire))
    return wire


def build_structure_worker_prompt(selector, request, tokens):
    builder = {
        JSON_WIRE: build_structure_prompt,
        COMPACT_TP_PROTOCOL: build_compact_structure_prompt,
        READABLE_TP_PROTOCOL: build_readable_structure_prompt,
    }[structure_wire(selector)]
    return builder(request, tokens)


def validate_structure_worker_reply(selector, request, raw):
    parser = {
        JSON_WIRE: parse_and_validate,
        COMPACT_TP_PROTOCOL: parse_compact_structure_reply,
        READABLE_TP_PROTOCOL: parse_readable_structure_reply,
    }[structure_wire(selector)]
    return parser(request, raw)


def selection_wire(selector):
    wire = getattr(selector, 'selection_reply_format', JSON_WIRE)
    if wire not in {JSON_WIRE, PROTOCOL_VERSION}:
        raise ProtocolError('unsupported selection reply protocol: ' + str(wire))
    return wire


def build_selector_prompt(selector, **request):
    builder = build_label_selection_prompt if selection_wire(selector) == PROTOCOL_VERSION else build_selection_prompt
    return builder(**request)


def validate_selector_reply(selector, raw, schema, candidates, *, allowed=None):
    if selection_wire(selector) == PROTOCOL_VERSION:
        return validate_selection_label_response(raw, schema, candidates, allowed=allowed)
    return validate_selection_response(raw, schema, allowed=allowed)
