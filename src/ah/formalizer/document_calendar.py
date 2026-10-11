"""Released calendar-header grammar; partial dates remain symbolic."""
import calendar
import re
from .canonical_ledger import digest


def validate_policy(policy):
    for rule in policy['rules']:
        if not {'day','month'} <= re.compile(rule['pattern']).groupindex.keys():
            raise ValueError('INVALID_DOCUMENT_CALENDAR_RULE')
        for field in ('days','months'):
            if any(k != k.casefold() or not k.strip() for k in rule[field]):
                raise ValueError('INVALID_DOCUMENT_CALENDAR_RULE')


def parse(raw, rule):
    match = re.fullmatch(rule['pattern'], raw, re.I)
    if not match: return None
    groups = match.groupdict()
    day = rule['days'].get(groups['day'].casefold())
    month = rule['months'].get(groups['month'].casefold())
    try: year = int(groups['year']) if groups.get('year') else None
    except ValueError: return None
    if day is None or month is None: return None
    if year is not None and not 1 <= year <= 9999: return None
    if day > calendar.monthrange(year or 2000, month)[1]: return None
    return {'day':day,'month':month,'year':year,'weekday_surface':groups.get('weekday')}


def expression(row, release_sha):
    e = {'kind':'CALENDAR_SCOPE','status':'SYMBOLIC','raw':row['raw'],
         'source_range':row['source_range'],'calendar':row['calendar'],
         'scope_ref':row['scope_ref'],'scope_range':row['scope_range'],
         'decision_ref':row['decision_ref'],'resource_sha256':release_sha,'rule_id':row['rule_id']}
    e['expr_id'] = 'time-expr:'+digest(e)
    return e


def validate_evidence(e, region):
    if region.kind not in {'EXISTENTIAL','CONTINUOUS'} or region.lo is not None or region.hi is not None or region.point is not None or region.points:
        raise ValueError('SYMBOLIC_TIME_REQUIRES_UNKNOWN_REGION')
    span=e.get('source_range'); scope=e.get('scope_range'); date=e.get('calendar',{})
    if (e.get('status')!='SYMBOLIC' or any(not isinstance(e.get(k),str) or not e[k]
            for k in ('raw','scope_ref','decision_ref','resource_sha256','rule_id','expr_id')) or
            not isinstance(span,(list,tuple)) or len(span)!=2 or
            not isinstance(scope,(list,tuple)) or len(scope)!=2 or
            any(type(x) is not int for x in (*span,*scope)) or
            not 0<=scope[0]<=span[0]<span[1]<=scope[1] or span[1]-span[0]!=len(e['raw']) or
            type(date.get('day')) is not int or not 1<=date['day']<=31 or
            type(date.get('month')) is not int or not 1<=date['month']<=12 or
            date.get('year') is not None and (type(date['year']) is not int or not 1<=date['year']<=9999)):
        raise ValueError('TEMPORAL_EXPRESSION_INVALID')
    if date['day']>calendar.monthrange(date.get('year') or 2000,date['month'])[1]:
        raise ValueError('TEMPORAL_EXPRESSION_INVALID')
