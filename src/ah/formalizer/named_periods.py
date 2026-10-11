"""Released named intervals retain unknown boundaries instead of invented hours."""
import re
from .canonical_ledger import digest


def validate_rule(rule):
    if not isinstance(rule.get('period_id'),str) or not rule['period_id']:
        raise ValueError('INVALID_NAMED_PERIOD_RULE')
    if rule.get('interval_semantics') not in {'CONTINUOUS','EXISTENTIAL'}:
        raise ValueError('INVALID_NAMED_PERIOD_RULE')


def resolve(text,observation,release,*,source_start=0):
    matches=[(r,m) for r in release.entries('TemporalRules') if r['kind']=='NAMED_PERIOD'
             for m in re.finditer(r['pattern'],text,re.I)]
    if not matches:return None
    if len(matches)!=1 or any(re.search(r['pattern'],text,re.I) for r in release.entries('TemporalRules') if r['kind']!='NAMED_PERIOD'):
        return None,['TEMPORAL_SCOPE_UNRESOLVED']
    rule,m=matches[0]
    expression={'kind':'NAMED_PERIOD','status':'SYMBOLIC','period_id':rule['period_id'],
        'raw':m.group(),'source_range':[source_start+m.start(),source_start+m.end()],
        'interval_semantics':rule['interval_semantics'],'anchor':observation.get('time_anchor'),
        'resource_sha256':release.sha256,'rule_id':rule.get('rule_id',digest(rule))}
    expression['expr_id']='time-expr:'+digest([observation.get('observation_id'),expression])
    return {'kind':rule['interval_semantics'],'lo':None,'hi':None,'expressions':[expression]},['REFERENCE_UNKNOWN']


def validate_evidence(e,region):
    span=e.get('source_range')
    if (e.get('status')!='SYMBOLIC' or not all(isinstance(e.get(k),str) and e[k] for k in
        ('expr_id','period_id','raw','resource_sha256','rule_id')) or
        not isinstance(span,(list,tuple)) or len(span)!=2 or any(type(x) is not int for x in span)
        or not 0<=span[0]<span[1] or span[1]-span[0]!=len(e['raw']) or
        e.get('interval_semantics') not in {'CONTINUOUS','EXISTENTIAL'} or
        region.kind!=e['interval_semantics'] or region.lo is not None or region.hi is not None or region.points):
        raise ValueError('TEMPORAL_EXPRESSION_INVALID')
