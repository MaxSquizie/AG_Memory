"""Source-grounded BEFORE/AFTER bounds without fabricated civil endpoints."""
import re
from .canonical_ledger import digest


def validate_rule(rule):
    if (rule.get('operator') not in {'BEFORE','AFTER'} or
            'anchor' not in re.compile(rule['pattern']).groupindex):
        raise ValueError('INVALID_TEMPORAL_BOUND_RULE')


def range_constituent(rule, match, boundaries):
    """A range already owns its same boundary; unrelated overlaps still fail."""
    index = {'AFTER':0, 'BEFORE':1}.get(rule.get('operator'))
    return (rule['kind'] == 'TEMPORAL_BOUND' and index is not None and
            match.span() == boundaries[index])


def resolve(text, observation, release, *, source_start=0):
    matches = [(r,m) for r in release.entries('TemporalRules') if r['kind'] == 'TEMPORAL_BOUND'
               for m in re.finditer(r['pattern'], text, re.I)]
    if not matches:
        return None
    if len(matches) != 1 or any(re.search(r['pattern'], text, re.I)
                              for r in release.entries('TemporalRules') if r['kind'] != 'TEMPORAL_BOUND'):
        return None, ['TEMPORAL_SCOPE_UNRESOLVED']
    rule, match = matches[0]
    a,b = match.span('anchor')
    if not match.start() <= a < b <= match.end():
        return None, ['TEMPORAL_EXPRESSION_INVALID']
    expression = {'kind':'TEMPORAL_BOUND', 'status':'SYMBOLIC', 'operator':rule['operator'],
        'raw':match.group(), 'source_range':[source_start+v for v in match.span()],
        'boundary':{'raw':match.group('anchor'), 'source_range':[source_start+a,source_start+b]},
        'resource_sha256':release.sha256, 'rule_id':rule.get('rule_id',digest(rule))}
    expression['expr_id'] = 'time-expr:'+digest([observation.get('observation_id'),expression])
    return {'kind':'EXISTENTIAL','lo':None,'hi':None,'expressions':[expression]}, []


def validate_evidence(e, region):
    keys = {'kind','status','operator','raw','source_range','boundary','resource_sha256','rule_id','expr_id'}
    if (set(e) != keys or e['status'] != 'SYMBOLIC' or e['operator'] not in {'BEFORE','AFTER'} or
            any(not isinstance(e.get(k),str) or not e[k] for k in ('raw','resource_sha256','rule_id','expr_id')) or
            not isinstance(e['boundary'],dict) or set(e['boundary']) != {'raw','source_range'}):
        raise ValueError('TEMPORAL_EXPRESSION_INVALID')
    for value in (e,e['boundary']):
        span = value['source_range']
        if (not isinstance(value['raw'],str) or not value['raw'] or not isinstance(span,(list,tuple)) or
                len(span)!=2 or any(type(x) is not int for x in span) or not 0 <= span[0] < span[1] or
                span[1]-span[0] != len(value['raw'])):
            raise ValueError('TEMPORAL_EXPRESSION_INVALID')
    lo,hi = e['source_range']; a,b = e['boundary']['source_range']
    if not lo <= a < b <= hi or e['raw'][a-lo:b-lo] != e['boundary']['raw']:
        raise ValueError('TEMPORAL_EXPRESSION_INVALID')
    if region.kind != 'EXISTENTIAL' or region.lo is not None or region.hi is not None or region.points:
        raise ValueError('SYMBOLIC_TIME_REQUIRES_UNKNOWN_REGION')
