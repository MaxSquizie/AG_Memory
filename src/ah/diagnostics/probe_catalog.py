"""Observation-only probe names and closed-label reply classification.

Nothing here changes a runtime slot, selection, or semantic permission. The
catalog's denominator is the declared static registry, not language coverage or
all call sites. Historical aliases align report names, never semantic contracts.
"""
from __future__ import annotations

import hashlib
import json
import re


ALIASES = {'structural_oov_reading': 'structural_oov_function'}
LABEL_PROTOCOL = 'SELECT_LABELS_V1'
VALID_OUTCOMES = ('CHOSEN_ONE', 'CHOSEN_MULTIPLE', 'NONE_FIT', 'INSUFFICIENT_CONTEXT')
OUTCOMES = (*VALID_OUTCOMES, 'MALFORMED', 'UNKNOWN_EVIDENCE', 'TRUNCATED',
            'PROVIDER_ERROR', 'UNFINISHED')
_PICKS = re.compile(r'[1-9][0-9]*(?:,[1-9][0-9]*)*', re.ASCII)


def catalog_snapshot():
    """Return an isolated JSON-compatible snapshot of the actual registry."""
    from ah.formalizer.probe_families import FAMILIES, SOURCE_COLLECTION
    registry = {'slots': {slot: json.loads(json.dumps(spec.record()))
                          for slot, spec in sorted(FAMILIES.items())},
                'source_collection': json.loads(json.dumps(SOURCE_COLLECTION.record()))}
    digest = hashlib.sha256(json.dumps(registry, ensure_ascii=False, sort_keys=True,
                                       separators=(',', ':')).encode('utf-8')).hexdigest()
    snapshot = {'schema_version': 'probe-catalog-1', 'registry_sha256': digest,
                **registry, 'aliases': dict(ALIASES)}
    snapshot['catalog_sha256'] = hashlib.sha256(json.dumps(
        snapshot, ensure_ascii=False, sort_keys=True,
        separators=(',', ':')).encode('utf-8')).hexdigest()
    return snapshot


def resolve_slot(raw_slot, catalog=None, declared_contract=None):
    """Retain the original name and distinguish registry from captured evidence."""
    catalog = catalog_snapshot() if catalog is None else catalog
    raw = raw_slot if isinstance(raw_slot, str) and raw_slot else None
    canonical = catalog.get('aliases', {}).get(raw, raw)
    spec = catalog.get('slots', {}).get(canonical)
    declared = declared_contract if isinstance(declared_contract, dict) else {}
    source_collection = declared.get('family') == 'SOURCE_COLLECTION'
    result = {'raw_slot': raw_slot, 'canonical_slot': canonical,
              'alias_applied': raw is not None and canonical != raw,
              'alias_semantic_equivalence': False,
              'family': spec.get('family') if spec else None,
              'level': spec.get('level') if spec else None,
              'family_evidence': 'STATIC_REPORTING_REGISTRY' if spec else 'UNKNOWN',
              'registry_status': 'REGISTERED' if spec else
                  'UNREGISTERED_OBSERVED' if raw else 'UNKNOWN_SLOT'}
    if result['alias_applied']:
        result['alias_note'] = ('Historical reporting name only; the old whole-reading '
                                'and current function-only output contracts are not equated.')
    if source_collection:
        result.update(family='SOURCE_COLLECTION', level=declared.get('level'),
                      family_evidence='RECORDED_CONTRACT',
                      registry_status='DYNAMIC_SOURCE_COLLECTION')
    elif declared.get('family'):
        result['declared_family'] = declared['family']
        result['declared_family_mismatch'] = bool(spec and spec['family'] != declared['family'])
        if not spec:
            result.update(family=declared['family'], level=declared.get('level'),
                          family_evidence='RECORDED_UNREGISTERED_CONTRACT')
    return result


def evidence_clipped(value):
    """Recognize export clipping and runtime serialization failure markers."""
    if isinstance(value, dict):
        return any((isinstance(key,str) and key.endswith('_truncated') and item is True)
                   or (key in {'_omitted_items', '_omitted_fields', '_omitted_progress_fields', '_trace_unserializable'} and bool(item))
                   or evidence_clipped(item) for key, item in value.items())
    if isinstance(value, (list, tuple)):
        return any(evidence_clipped(item) for item in value)
    return value == '<nested value omitted>'


def displayed_choices(prompt):
    """Read the explicit Options block and historical inline ID map separately."""
    if not isinstance(prompt, str):
        return {}, {}
    block = re.split(r'(?:^|\n)Options:\s*\n', prompt, maxsplit=1)
    labels = {}
    if len(block) == 2:
        body = re.split(r'\n(?:Reply with|Audit mapping|Task:)', block[1], maxsplit=1)[0]
        pairs = re.findall(r'^([1-9][0-9]*)\. (.*)$', body, re.M)
        if len({label for label, _ in pairs}) == len(pairs):
            labels = dict(pairs)
    mapping = {}
    for label, encoded in re.findall(r'^([1-9][0-9]*) = (".*")$', prompt, re.M):
        try:
            value = json.loads(encoded)
        except (ValueError, TypeError):
            return labels, {}
        if label in mapping or not isinstance(value, str) or not value:
            return labels, {}
        mapping[label] = value
    return labels, mapping


def _contiguous(mapping):
    return bool(mapping) and set(mapping) == {str(i) for i in range(1, len(mapping) + 1)}


def classify_reply(raw, *, audit=None, prompt=None, prompt_complete=True,
                   response_present=True, response_truncated=False,
                   provider_error=None, unfinished=False, protocol=None):
    """Classify only observed wire bytes and the supported closed-label domain.

    Full displayed labels can validate ordinal membership without pretending to
    recover internal candidate IDs. Unknown protocols and incomplete domains
    remain UNKNOWN_EVIDENCE. This does not certify downstream semantic admission.
    """
    audit = audit if isinstance(audit, dict) else {}
    declared_protocol = protocol or (None if audit.get('protocol_truncated') else audit.get('protocol'))
    protocol_evidence = 'EXPLICIT' if declared_protocol else 'UNKNOWN'
    if not declared_protocol and isinstance(prompt, str) and prompt_complete:
        if ('Reply with the number' in prompt and 'Insufficient context: ?' in prompt
                and 'No candidate fits: 0' in prompt):
            declared_protocol, protocol_evidence = LABEL_PROTOCOL, 'EXPLICIT_PROMPT_INSTRUCTIONS'
    normalized = raw.strip() if isinstance(raw, str) else None
    response_clipped = evidence_clipped(raw)
    result = {'outcome': None, 'reason': None, 'normalized_response': normalized,
              'selected_labels': [], 'selected_ids': None,
              'protocol': declared_protocol, 'protocol_evidence': protocol_evidence,
              'mapping_complete': False, 'domain_evidence': 'UNKNOWN',
              'response_complete': bool(response_present and not response_truncated and not response_clipped),
              'response_truncated': bool(response_truncated),
              'audit_clipped': evidence_clipped(audit)}

    def finish(outcome, reason):
        result.update(outcome=outcome, reason=reason)
        return result

    if unfinished:
        return finish('UNFINISHED', 'REQUEST_HAS_NO_FINISH')
    if provider_error is not None and provider_error is not False:
        result['provider_error'] = provider_error
        return finish('PROVIDER_ERROR', 'TRANSPORT_REPORTED_ERROR')
    if response_truncated:
        return finish('TRUNCATED', 'FULL_REPLY_NOT_AVAILABLE')
    if not response_present:
        return finish('UNKNOWN_EVIDENCE', 'RESPONSE_NOT_RECORDED')
    if response_clipped:
        return finish('UNKNOWN_EVIDENCE', 'RESPONSE_EVIDENCE_INCOMPLETE')
    if declared_protocol != LABEL_PROTOCOL:
        return finish('UNKNOWN_EVIDENCE', 'PROTOCOL_NOT_SUPPORTED_BY_AUDITOR' if declared_protocol else 'PROTOCOL_NOT_RECORDED')
    if not isinstance(raw, str):
        return finish('MALFORMED', 'NON_TEXT_REPLY')
    if normalized in {'?', '0'}:
        result['selected_ids'] = []
        return finish('INSUFFICIENT_CONTEXT' if normalized == '?' else 'NONE_FIT', 'VALID_LABEL_SENTINEL')
    if not _PICKS.fullmatch(normalized):
        return finish('MALFORMED', 'LABEL_GRAMMAR_INVALID')
    selected = normalized.split(',')
    result['selected_labels'] = selected
    if len(set(selected)) != len(selected):
        return finish('MALFORMED', 'DUPLICATE_LABELS')
    labels, inline_ids = displayed_choices(prompt)
    candidate_ids = audit.get('candidates')
    id_mapping = {}
    if ('candidates' in audit and not result['audit_clipped']
            and isinstance(candidate_ids, (list, tuple))
            and all(isinstance(value, str) and value for value in candidate_ids)
            and len(set(candidate_ids)) == len(candidate_ids)):
        id_mapping = {str(i): value for i, value in enumerate(candidate_ids, 1)}
        domain = set(id_mapping)
        result.update(mapping_complete=True, domain_evidence='COMPLETE_CANDIDATE_AUDIT')
    elif 'candidates' in audit:
        return finish('UNKNOWN_EVIDENCE', 'CANDIDATE_AUDIT_INCOMPLETE_OR_INVALID')
    elif prompt_complete and _contiguous(inline_ids) and len(set(inline_ids.values())) == len(inline_ids):
        id_mapping = inline_ids
        domain = set(id_mapping)
        result.update(mapping_complete=True, domain_evidence='COMPLETE_INLINE_ID_MAP')
    elif prompt_complete and _contiguous(labels):
        domain = set(labels)
        result['domain_evidence'] = 'COMPLETE_DISPLAYED_LABELS_ONLY'
    else:
        return finish('UNKNOWN_EVIDENCE', 'CLOSED_LABEL_DOMAIN_NOT_RECORDED')
    # Compare strings, avoiding huge-integer conversion and its arbitrary limit.
    if any(label not in domain for label in selected):
        return finish('MALFORMED', 'LABEL_OUTSIDE_CLOSED_DOMAIN')
    if result['mapping_complete']:
        result['selected_ids'] = [id_mapping[label] for label in selected]
    result['selected_display_labels'] = [labels.get(label) for label in selected]
    return finish('CHOSEN_ONE' if len(selected) == 1 else 'CHOSEN_MULTIPLE',
                  'VALID_CLOSED_LABEL_SELECTION')
