"""Pair a description with an addressed host when the later occurrence arrives."""
from .component_policy import _features, _morph, compatible
from .nominal_readings import description_heads, variant


def match(description, host):
    token, adjective = description
    head, noun = host
    if adjective.cases & noun.cases and compatible(_features(adjective), _features(noun)):
        yield {'token': token, 'variant': adjective, 'refs': (token.token_id,),
               'entities': [], 'adjectives': [], 'bound_host': head,
               'host_reading': _morph(noun), 'requires_host_probe': True}


def units(tokens, missing, frame, established, *, state):
    covered = {ref for unit in established for ref in unit['refs']}
    readings = description_heads(frame, state=state)
    hosts = []
    descriptions = []
    for token in tokens:
        head_reading = readings.get(token.token_id)
        host = None
        if head_reading and head_reading['pos'] in {'NOUN', 'NPRO'}:
            host = token.token_id, variant(head_reading)
            for description in descriptions:
                yield from match(description, host)
        if token.token_id in missing and token.token_id not in covered:
            for reading in token.variants:
                if reading.pos in {'ADJF', 'PRTF'}:
                    description = token, reading
                    for previous_host in hosts:
                        yield from match(description, previous_host)
                    descriptions.append(description)
        if host is not None:
            hosts.append(host)
