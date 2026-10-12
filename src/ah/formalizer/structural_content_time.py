"""Time qualification of nonasserted content, scoped to its UsageLink."""
from copy import deepcopy
from .canonical_ledger import region, digest


def payload(frame, node_ref, source_tag):
    if frame.semantic.get('temporal_unresolved'):
        raise ValueError('TEMPORAL_NESTED_SCOPE_UNRESOLVED')
    value=frame.semantic.get('region')
    if not value:return {}
    return {'content_time':{'target_ref':node_ref,'source_tag':list(source_tag),
                            'region':deepcopy(value)}}


def validate(link):
    value=link.get('content_time')
    if value is None:return
    if (link.get('kind') not in {'ATTITUDE','NOMINAL'} or
        set(value)!={'target_ref','source_tag','region'} or
        value['target_ref']!=link['node_ref'] or value['source_tag']!=link.get('source_tag')):
        raise ValueError('STRUCTURAL_CONTENT_TIME_INVALID')
    if link['kind']=='ATTITUDE':
        expected='usage:'+digest([link['node_ref'],link['parent_ref'],link['position'],
            'ATTITUDE',link['source_tag'],{'content_time':value}])
        if link['link_id']!=expected:raise ValueError('STRUCTURAL_CONTENT_TIME_ID_INVALID')
    r=region(value['region'])
    if (r.kind not in {'POINT','CONTINUOUS','EXISTENTIAL'} or
        (r.kind=='POINT' and r.point is None) or
        (r.lo is not None and r.hi is not None and r.lo>r.hi)):
        raise ValueError('STRUCTURAL_CONTENT_TIME_INVALID')
    if value['region'].get('expressions'):
        from .clock_expressions import validate_evidence
        validate_evidence(value['region']['expressions'],r)
