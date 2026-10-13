"""Write-boundary contract for an explicitly mentioned group of unknown members."""


def has_unspecified_members(core, entity_ids):
    """A group mention is not one enumerated member of a numerical domain."""
    return any(core.store.kind_of(uid).value == 'M' and
               (core.store.get_element_any_domain(uid).meta.get('qualitative_group') is not None or
                core.store.get_element_any_domain(uid).meta.get('implicit_participant',{}).get('participant_kind')=='GROUP')
               for uid in entity_ids)


def payload(frame, token_ref):
    rows = [r for r in frame.semantic.get('qualitative_groups', ()) if r['head_ref'] == token_ref]
    if not rows:
        return {}
    row = rows[0]
    return {'qualitative_group':{'membership_status':'UNKNOWN', 'cardinality_status':'UNSPECIFIED',
        **{k:row[k] for k in ('raw','source_range','head_ref','marker_ref','decision_ref','rule_id','resource_sha256')}}}


def validate(payload):
    value = payload.get('qualitative_group')
    if value is None:
        return
    keys = {'membership_status','cardinality_status','raw','source_range','head_ref',
            'marker_ref','decision_ref','rule_id','resource_sha256'}
    if (not isinstance(value, dict) or set(value) != keys or
            value['membership_status'] != 'UNKNOWN' or value['cardinality_status'] != 'UNSPECIFIED' or
            any(not isinstance(value[k], str) or not value[k] for k in keys-{'source_range'}) or
            payload.get('implicit_participant') is not None or payload.get('scalar_properties')):
        raise ValueError('QUALITATIVE_GROUP_INVALID')
    span = value['source_range']
    if (not isinstance(span, (list, tuple)) or len(span) != 2 or any(type(x) is not int for x in span)
            or not 0 <= span[0] < span[1] or span[1]-span[0] != len(value['raw'])):
        raise ValueError('QUALITATIVE_GROUP_INVALID')
