"""Write-boundary validation for immutable two-boundary temporal expressions."""
from .clock_ranges import realizations


def validate(expression, region):
    e = expression
    def fail():
        raise ValueError('TEMPORAL_EXPRESSION_INVALID')
    if (e.get('status') not in {'SYMBOLIC', 'RESOLVED'} or
            not all(isinstance(e.get(k), str) and e[k] for k in ('expr_id','raw','resource_sha256','rule_id')) or
            e.get('interval_semantics') not in {'EXISTENTIAL','CONTINUOUS'}):
        fail()
    span = e.get('source_range')
    if (not isinstance(span, (tuple,list)) or len(span) != 2 or
            any(type(v) is not int for v in span) or not 0 <= span[0] < span[1] or
            span[1]-span[0] != len(e['raw'])):
        fail()
    boundaries = e.get('boundaries')
    if not isinstance(boundaries, list) or len(boundaries) != 2:
        fail()
    previous = span[0]
    for b in boundaries:
        if not isinstance(b, dict): fail()
        s, hours, minute = b.get('source_range'), b.get('hour_candidates'), b.get('minute')
        if (not isinstance(s, (tuple,list)) or len(s) != 2 or any(type(v) is not int for v in s) or
                not previous <= s[0] < s[1] <= span[1] or
                e['raw'][s[0]-span[0]:s[1]-span[0]] != b.get('raw') or
                not isinstance(hours, list) or not hours or
                any(type(h) is not int or not 0 <= h < 24 for h in hours) or hours != sorted(set(hours)) or
                type(minute) is not int or not 0 <= minute < 60):
            fail()
        previous = s[1]
    offsets = e.get('end_day_offsets')
    if (not isinstance(offsets, list) or not offsets or len(offsets) > 8 or
            any(type(d) is not int or d < 0 for d in offsets) or offsets != sorted(set(offsets))):
        fail()
    expected = realizations(*boundaries, offsets)
    if not expected or e.get('realizations') != expected:
        fail()
    if e['status'] == 'SYMBOLIC':
        if region.kind != 'EXISTENTIAL' or region.lo is not None or region.hi is not None or region.points:
            raise ValueError('SYMBOLIC_TIME_REQUIRES_UNKNOWN_REGION')
    elif (len(expected) != 1 or region.kind != e['interval_semantics'] or
          region.lo is None or region.hi is None or region.points or
          e.get('resolved_bounds') != [region.lo, region.hi]):
        raise ValueError('RESOLVED_RANGE_REQUIRES_INTERVAL')
