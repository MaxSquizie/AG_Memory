"""Released two-boundary clocks, preserving alternatives and discontinuous spans."""
from datetime import datetime, timedelta
from itertools import product
import re
from .canonical_ledger import digest
from .clock_expressions import cardinal, validate_rule as validate_clock


def validate_rule(rule):
    groups = re.compile(rule['pattern']).groupindex
    if not {'start', 'end'} <= set(groups):
        raise ValueError('INVALID_CLOCK_RANGE_RULE')
    offsets = rule.get('end_day_offsets')
    if (not isinstance(offsets, list) or not offsets or
            any(type(x) is not int or x < 0 for x in offsets) or
            offsets != sorted(set(offsets)) or len(offsets) > 8):
        raise ValueError('INVALID_CLOCK_RANGE_RULE')
    for key in ('start_clock', 'end_clock'):
        spec = rule.get(key, {})
        if not isinstance(spec, dict):
            raise ValueError('INVALID_CLOCK_RANGE_RULE')
        if spec.get('kind') == 'FIXED':
            if (set(spec) != {'kind', 'hour', 'minute'} or
                    type(spec['hour']) is not int or not 0 <= spec['hour'] < 24 or
                    type(spec['minute']) is not int or not 0 <= spec['minute'] < 60):
                raise ValueError('INVALID_CLOCK_RANGE_RULE')
        elif spec.get('kind') == 'WORD_CLOCK':
            validate_clock(spec)
        else:
            raise ValueError('INVALID_CLOCK_RANGE_RULE')


def boundary_spans(rule, match):
    """Only the two boundary expressions are temporal, never the intervening verb."""
    if rule['kind'] == 'CLOCK_RANGE':
        return [match.span('start'), match.span('end')]
    return [match.span()]


def endpoint(raw, spec):
    if spec['kind'] == 'FIXED':
        return {'hour_candidates': [spec['hour']], 'minute': spec['minute']}
    match = re.fullmatch(spec['pattern'], raw, re.I)
    if not match:
        raise ValueError('TEMPORAL_EXPRESSION_INVALID')
    hour = cardinal(match.group(spec.get('hour_group', 'hour')), spec['number_values'])
    minute = cardinal(match.group(spec.get('minute_group', 'minute')) or '0', spec['number_values'])
    if not 0 <= hour < 24 or not 0 <= minute < 60:
        raise ValueError('TEMPORAL_EXPRESSION_INVALID')
    hours = sorted({hour % 12, hour % 12 + 12}) if spec['clock_cycle'] == 12 and 1 <= hour <= 12 else [hour]
    return {'hour_candidates': hours, 'minute': minute}


def realizations(start, end, offsets):
    return [[a, b, d] for a, b, d in product(start['hour_candidates'], end['hour_candidates'], offsets)
            if a * 60 + start['minute'] <= d * 1440 + b * 60 + end['minute']]


def resolve(text, observation, release, *, source_start=0):
    matches = [(r, m) for r in release.entries('TemporalRules') if r['kind'] == 'CLOCK_RANGE'
               for m in re.finditer(r['pattern'], text, re.I)]
    if not matches:
        return None
    if len(matches) != 1:
        return None, ['TEMPORAL_SCOPE_UNRESOLVED']
    rule, match = matches[0]
    spans = boundary_spans(rule, match)
    if any(lo < 0 or lo >= hi for lo, hi in spans) or spans[0][1] > spans[1][0]:
        return None, ['TEMPORAL_EXPRESSION_INVALID']
    # An overlapping release rule may assign a different meaning even to the
    # same boundary. Do not silently suppress that competing interpretation.
    from .symbolic_temporal_bounds import range_constituent
    if any(not range_constituent(r, m, spans)
           for r in release.entries('TemporalRules') if r['kind'] != 'CLOCK_RANGE'
           for m in re.finditer(r['pattern'], text, re.I)):
        return None, ['TEMPORAL_SCOPE_UNRESOLVED']
    try:
        endpoints = [dict(endpoint(match.group(k), rule[k+'_clock']), raw=match.group(k),
                          source_range=[source_start+v for v in match.span(k)]) for k in ('start', 'end')]
    except (ValueError, IndexError):
        return None, ['TEMPORAL_EXPRESSION_INVALID']
    choices = realizations(*endpoints, rule['end_day_offsets'])
    if not choices:
        return None, ['TEMPORAL_EXPRESSION_INVALID']
    expression = {'kind': 'CLOCK_RANGE', 'raw': match.group(),
        'source_range': [source_start+v for v in match.span()], 'boundaries': endpoints,
        'realizations': choices, 'end_day_offsets': rule['end_day_offsets'],
        'interval_semantics': rule.get('interval_semantics', 'EXISTENTIAL'),
        'anchor': observation.get('time_anchor'), 'timezone': observation.get('timezone'),
        'status': 'SYMBOLIC', 'resource_sha256': release.sha256,
        'rule_id': rule.get('rule_id', digest(rule))}
    symbolic = {'kind': 'EXISTENTIAL', 'lo': None, 'hi': None, 'expressions': [expression]}
    result, diagnostics = symbolic, ['REFERENCE_UNKNOWN']
    if observation.get('time_anchor') is not None:
        try:
            day = datetime.fromisoformat(observation['time_anchor'].replace('Z', '+00:00'))
            if day.tzinfo is None and observation.get('timezone'):
                from zoneinfo import ZoneInfo
                day = day.replace(tzinfo=ZoneInfo(observation['timezone']))
            if day.tzinfo is not None:
                day = day.replace(hour=0, minute=0, second=0, microsecond=0)
                day += timedelta(days=rule.get('day_offset', 0))
                if len(choices) != 1:
                    diagnostics = ['REFERENCE_AMBIGUOUS']
                else:
                    a, b, d = choices[0]
                    lo = day.replace(hour=a, minute=endpoints[0]['minute'])
                    hi = (day+timedelta(days=d)).replace(hour=b, minute=endpoints[1]['minute'])
                    if all(t.replace(fold=0).utcoffset() == t.replace(fold=1).utcoffset() for t in (lo, hi)):
                        expression['status'] = 'RESOLVED'
                        expression['resolved_bounds'] = [lo.timestamp(), hi.timestamp()]
                        result = {'kind': expression['interval_semantics'], 'lo': lo.timestamp(),
                                  'hi': hi.timestamp(), 'expressions': [expression]}
                        diagnostics = []
        except (ValueError, AttributeError, KeyError, OverflowError):
            return None, ['TEMPORAL_EXPRESSION_INVALID']
    expression['expr_id'] = 'time-expr:'+digest([observation.get('observation_id'), expression])
    return result, diagnostics


def consumed_scope_spans(text, observation, release):
    """Exact boundary markers occupy temporal syntax, not an extra G operator."""
    result = resolve(text, observation, release)
    if result is None:
        from .symbolic_temporal_bounds import resolve as resolve_bound
        result = resolve_bound(text, observation, release)
        if result and result[0]:
            return [tuple(e['source_range']) for e in result[0]['expressions']]
    if not result or not result[0]:
        return []
    return [tuple(b['source_range']) for b in result[0]['expressions'][0]['boundaries']]


def scope_consumed(rule, match, spans):
    return ('TEMPORAL_NOMINAL' in rule.get('attachment_kinds', ()) and
            rule.get('operator') in {'BEFORE','AFTER','DURING'} and
            any(lo <= match.start() and match.end() <= hi for lo, hi in spans))
