"""Write-boundary validation for local and memory-backed relative-place identity."""
from .canonical_ledger import digest


def validate_entity(payload):
    place = payload.get('relative_place')
    if place is None: return
    fields = {'anchor_ref','source_tag','source_range','raw','rule_id','resource_sha256',
              'location_kind','coordinates_status'}
    if not isinstance(place,dict) or set(place)!=fields: raise ValueError('RELATIVE_PLACE_INVALID')
    span = place['source_range']; tag = place['source_tag']
    if (any(not isinstance(place[k],str) or not place[k] for k in fields-{'source_tag','source_range'})
        or not isinstance(span,(tuple,list)) or len(span)!=2 or any(type(n) is not int for n in span)
        or not 0<=span[0]<span[1] or span[1]-span[0]!=len(place['raw'])
        or not isinstance(tag,list) or len(tag)!=2 or not isinstance(tag[0],str) or not tag[0]
        or type(tag[1]) is not int or tag[1]<1 or payload.get('source_tag')!=tag
        or payload.get('mention_ref')!=place['anchor_ref'] or place['coordinates_status']!='UNKNOWN'
        or place['location_kind'] not in {'DESTINATION','LOCATION','ORIGIN'}
        or payload.get('uid')!='M:place:'+digest(place) or payload.get('name') or payload.get('implicit_participant')):
        raise ValueError('RELATIVE_PLACE_INVALID')


def validate_binding(p, ledger, store, journal=None):
    if p.get('binding_kind') not in {'SPATIAL_ANCHOR','SPATIAL_REFERENCE'}: return
    meta = store.get_element_any_domain(p['target_ref']).meta.get('relative_place')
    if not meta: raise ValueError('SPATIAL_BINDING_INVALID')
    anchor = 'binding:place:'+digest([meta['source_tag'],meta['anchor_ref'],meta['rule_id'],p['target_ref']])
    if p['binding_kind']=='SPATIAL_ANCHOR':
        valid = meta['source_tag']==p.get('source_tag') and p['binding_id']==anchor and p['mention_ref']==meta['anchor_ref']
    else:
        proof = ledger.data['bindings'].get(anchor,{})
        valid = (p.get('anchor_binding_ref')==anchor and proof.get('status')=='LIVE'
                 and proof.get('binding_kind')=='SPATIAL_ANCHOR'
                 and proof.get('target_ref')==p['target_ref'] and bool(p.get('interpretation_decision_ref'))
                 and ledger.binding_live(anchor,ledger.paths())
                 and (meta['source_tag']==p.get('source_tag') or bool(p.get('context_read_hash'))))
    if not valid: raise ValueError('SPATIAL_BINDING_INVALID')
    if p['binding_kind']=='SPATIAL_REFERENCE':
        expected='binding:place-reference:'+digest([p['source_tag'],p['mention_ref'],p['target_ref'],p['interpretation_decision_ref']])
        if p['binding_id']!=expected: raise ValueError('SPATIAL_BINDING_INVALID')
        if meta['source_tag']!=p['source_tag']:
            from .spatial_memory import validate_receipt
            validate_receipt(p,journal)
