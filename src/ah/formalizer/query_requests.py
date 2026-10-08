"""Closed runtime request vocabulary shared by host and reviewed rule emits."""
from copy import deepcopy

MODES={'FORMULA','WH','HOW','COUNT','WHY','WHEN','COMPARE','SUPERLATIVE'}
FIELDS={'mode','requested_roles','count_role','expected_count','comparison','domain_certificate',
        'count_unit','aggregate','measure_id','compare_entity_ref','compare_mention','ordering'}


def validate_request(request, roles=None):
    if not isinstance(request,dict) or not set(request)<=FIELDS:
        raise ValueError('QUERY_REQUEST_INVALID')
    mode=request.get('mode','FORMULA')
    if mode not in MODES:
        raise ValueError('QUERY_REQUEST_INVALID')
    for key in ('domain_certificate','measure_id','compare_entity_ref','compare_mention','count_role'):
        if key in request and (not isinstance(request[key],str) or not request[key]):
            raise ValueError('QUERY_REQUEST_INVALID')
    requested=request.get('requested_roles',[])
    if (not isinstance(requested,(list,tuple)) or len(requested)>8 or len(set(requested))!=len(requested)
            or any(not isinstance(r,str) or not r for r in requested)):
        raise ValueError('QUERY_REQUEST_INVALID')
    if roles is not None and (not set(requested)<=set(roles) or request.get('count_role') is not None and request['count_role'] not in roles):
        raise ValueError('QUERY_REQUEST_INVALID')
    if 'expected_count' in request and (type(request['expected_count']) is not int or not 0<=request['expected_count']<=10**12):
        raise ValueError('QUERY_REQUEST_INVALID')
    if request.get('comparison','EXACTLY_N') not in {'EXACTLY_N','AT_LEAST_N','AT_MOST_N'}:
        raise ValueError('QUERY_REQUEST_INVALID')
    if request.get('count_unit','ENTITY') not in {'ENTITY','EVENT'} or type(request.get('aggregate',False)) is not bool:
        raise ValueError('QUERY_REQUEST_INVALID')
    if mode in {'WH','HOW','SUPERLATIVE'} and not requested:
        raise ValueError('QUERY_REQUEST_INVALID')
    if mode=='SUPERLATIVE' and (len(requested)!=1 or not request.get('measure_id') or request.get('ordering','MAX') not in {'MAX','MIN'}):
        raise ValueError('QUERY_REQUEST_INVALID')
    if mode=='COMPARE' and (not request.get('measure_id') or bool(request.get('compare_entity_ref'))==bool(request.get('compare_mention')) or request.get('ordering','GT') not in {'GT','LT','EQ','GE','LE','NE'}):
        raise ValueError('QUERY_REQUEST_INVALID')
    if mode=='COUNT' and request.get('count_unit','ENTITY')=='ENTITY' and not request.get('count_role'):
        raise ValueError('QUERY_REQUEST_INVALID')
    allowed={
        'FORMULA':{'mode'}, 'WHY':{'mode'}, 'WHEN':{'mode'},
        'WH':{'mode','requested_roles'}, 'HOW':{'mode','requested_roles'},
        'COUNT':{'mode','count_role','expected_count','comparison','domain_certificate','aggregate','count_unit'},
        'COMPARE':{'mode','measure_id','compare_entity_ref','compare_mention','ordering'},
        'SUPERLATIVE':{'mode','measure_id','requested_roles','ordering','domain_certificate'},
    }[mode]
    if not set(request)<=allowed:
        raise ValueError('QUERY_REQUEST_INVALID')
    if mode=='COUNT' and request.get('count_unit','ENTITY')=='EVENT' and request.get('count_role'):
        raise ValueError('QUERY_REQUEST_INVALID')
    return deepcopy(request)
