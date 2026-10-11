"""Released cardinal-clock grammar; unknown civil anchors never become dates."""
from datetime import datetime, timedelta
import re

from .canonical_ledger import digest


def cardinal(raw, values):
    """One atom or descending decimal tens + units; no lexical defaults."""
    words = raw.casefold().split()
    if len(words) == 1 and re.fullmatch(r'[0-9]{1,2}', words[0]):
        return int(words[0])
    ns = [values.get(w) for w in words]
    if not ns or any(type(n) is not int for n in ns):
        raise ValueError('TEMPORAL_EXPRESSION_INVALID')
    if len(ns) == 1:
        return ns[0]
    if len(ns) == 2 and 20 <= ns[0] <= 90 and ns[0] % 10 == 0 and 1 <= ns[1] <= 9:
        return sum(ns)
    raise ValueError('TEMPORAL_EXPRESSION_INVALID')


def validate_rule(rule):
    values = rule.get('number_values')
    groups = re.compile(rule['pattern']).groupindex
    if (not isinstance(values, dict) or not values or
            any(not isinstance(k, str) or not k or k != k.casefold() or
                type(v) is not int or not 0 <= v <= 90 for k, v in values.items()) or
            rule.get('clock_cycle') not in {12, 24} or
            not {rule.get('hour_group', 'hour'), rule.get('minute_group', 'minute')} <= set(groups)):
        raise ValueError('INVALID_WORD_CLOCK_RULE')


def resolve(text, observation, release, *, source_start=0):
    """None means no WORD_CLOCK match. Multiple clocks require another scope."""
    matches = [(rule, m) for rule in release.entries('TemporalRules')
               if rule['kind'] == 'WORD_CLOCK' for m in re.finditer(rule['pattern'], text, re.I)]
    if not matches:
        return None
    if len(matches) != 1 or any(re.search(r['pattern'], text, re.I)
                               for r in release.entries('TemporalRules') if r['kind'] != 'WORD_CLOCK'):
        return None, ['TEMPORAL_SCOPE_UNRESOLVED']
    rule, match = matches[0]
    try:
        hour = cardinal(match.group(rule.get('hour_group', 'hour')), rule['number_values'])
        minute = cardinal(match.group(rule.get('minute_group', 'minute')) or '0', rule['number_values'])
        if not 0 <= hour < 24 or not 0 <= minute < 60:
            raise ValueError('TEMPORAL_EXPRESSION_INVALID')
    except (ValueError, IndexError):
        return None, ['TEMPORAL_EXPRESSION_INVALID']
    hours = sorted({hour % 12, hour % 12 + 12}) if rule['clock_cycle'] == 12 and 1 <= hour <= 12 else [hour]
    expression = {'kind':'CLOCK', 'raw':match.group(),
        'source_range':[source_start+match.start(), source_start+match.end()],
        'hour_candidates':hours, 'minute':minute, 'anchor':observation.get('time_anchor'),
        'timezone':observation.get('timezone'), 'status':'SYMBOLIC',
        'resource_sha256':release.sha256, 'rule_id':rule.get('rule_id', digest(rule))}
    expression['expr_id'] = 'time-expr:'+digest([observation.get('observation_id'), expression])
    # A dated existential with unknown boundaries must not masquerade as an
    # undated support (which would incorrectly license propositional inference).
    symbolic = {'kind':'EXISTENTIAL', 'lo':None, 'hi':None, 'expressions':[expression]}
    anchor = observation.get('time_anchor')
    if anchor is None:
        return symbolic, ['REFERENCE_UNKNOWN']
    try:
        day = datetime.fromisoformat(anchor.replace('Z', '+00:00'))
        if day.tzinfo is None:
            if not observation.get('timezone'):
                return symbolic, ['REFERENCE_UNKNOWN']
            from zoneinfo import ZoneInfo
            day = day.replace(tzinfo=ZoneInfo(observation['timezone']))
        day = day.replace(hour=0, minute=0, second=0, microsecond=0)
        day += timedelta(days=rule.get('day_offset', 0))
    except (ValueError, AttributeError, KeyError):
        return None, ['TEMPORAL_EXPRESSION_INVALID']
    if len(hours) != 1:
        return symbolic, ['REFERENCE_AMBIGUOUS']
    local = day.replace(hour=hours[0], minute=minute)
    if local.replace(fold=0).utcoffset() != local.replace(fold=1).utcoffset():
        return symbolic, ['REFERENCE_UNKNOWN']
    expression['status'] = 'RESOLVED'
    return {'kind':'POINT', 'point':local.timestamp(), 'expressions':[expression]}, []


def validate_evidence(expressions, temporal_region):
    """Write boundary for immutable lexical constraints on a temporal path."""
    if not isinstance(expressions, list) or not expressions:
        raise ValueError('TEMPORAL_EXPRESSION_INVALID')
    for e in expressions:
        if isinstance(e, dict) and e.get('kind') == 'CLOCK_RANGE':
            from .clock_range_evidence import validate
            validate(e, temporal_region)
            continue
        if (not isinstance(e, dict) or e.get('kind') != 'CLOCK' or
                e.get('status') not in {'SYMBOLIC', 'RESOLVED'} or
                not all(isinstance(e.get(k), str) and e[k] for k in ('expr_id','raw','resource_sha256','rule_id'))):
            raise ValueError('TEMPORAL_EXPRESSION_INVALID')
        span, hours, minute = e.get('source_range'), e.get('hour_candidates'), e.get('minute')
        if (not isinstance(span, (list, tuple)) or len(span) != 2 or
                any(type(v) is not int for v in span) or not 0 <= span[0] < span[1] or
                span[1]-span[0] != len(e['raw']) or
                not isinstance(hours, list) or not hours or
                any(type(h) is not int or not 0 <= h < 24 for h in hours) or hours != sorted(set(hours)) or
                type(minute) is not int or not 0 <= minute < 60):
            raise ValueError('TEMPORAL_EXPRESSION_INVALID')
        if e['status'] == 'SYMBOLIC' and (temporal_region.kind != 'EXISTENTIAL' or
                temporal_region.lo is not None or temporal_region.hi is not None or temporal_region.points):
            raise ValueError('SYMBOLIC_TIME_REQUIRES_UNKNOWN_REGION')
        if e['status'] == 'RESOLVED' and (temporal_region.kind != 'POINT' or len(hours) != 1):
            raise ValueError('RESOLVED_CLOCK_REQUIRES_POINT')
