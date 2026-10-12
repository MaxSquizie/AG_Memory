"""Mention-local referents with unknown identity, not known-distinct objects."""
from copy import deepcopy
from .canonical_ledger import digest


def payload(state, unit):
    constraint=unit.get('reference_constraint')
    if constraint is None or unit['mention_ref'] in state.observation.get('nominal_reference_bindings',{}):
        return {}
    return {'referential_placeholder':{'identity_status':'UNRESOLVED',
        'distinctness_status':'UNKNOWN', 'source_tag':[state.source_uid,state.interpretation_version],
        'mention_ref':unit['mention_ref'],'constraint':deepcopy(constraint)}}


def uid(value):
    return 'M:reference:'+digest(value)


def validate(p):
    value=p.get('referential_placeholder')
    if value is None:return
    fields={'identity_status','distinctness_status','source_tag','mention_ref','constraint'}
    if (not isinstance(value,dict) or set(value)!=fields or value['identity_status']!='UNRESOLVED'
        or value['distinctness_status']!='UNKNOWN' or p.get('uid')!=uid(value)
        or value['source_tag']!=p.get('source_tag') or value['mention_ref']!=p.get('mention_ref')
        or p.get('name') or p.get('reference_existing') or p.get('scalar_properties')
        or p.get('implicit_participant') or p.get('relative_place') or p.get('qualitative_group')):
        raise ValueError('REFERENTIAL_PLACEHOLDER_INVALID')
    tag=value['source_tag']
    if (not isinstance(tag,list) or len(tag)!=2 or not isinstance(tag[0],str) or not tag[0]
        or type(tag[1]) is not int or tag[1]<1 or not isinstance(value['mention_ref'],str) or not value['mention_ref']):
        raise ValueError('REFERENTIAL_PLACEHOLDER_INVALID')
    c=value['constraint']; span=c.get('source_range') if isinstance(c,dict) else None
    if (not isinstance(c,dict) or c.get('identity_constraint') not in {'SAME','CONTEXTUAL'}
        or not isinstance(c.get('raw'),str) or not isinstance(span,(tuple,list)) or len(span)!=2
        or any(type(n) is not int for n in span) or not 0<=span[0]<span[1]
        or span[1]-span[0]!=len(c['raw']) or not c.get('head_ref')
        or c['head_ref'] not in c.get('anchor_refs',()) or not c.get('rule_ids')
        or not c.get('decision_ref') or not c.get('resource_sha256')):
        raise ValueError('REFERENTIAL_PLACEHOLDER_INVALID')


def has_unresolved_identity(core, entity_ids):
    return any(core.store.kind_of(u).value=='M' and
        core.store.get_element_any_domain(u).meta.get('referential_placeholder') is not None for u in entity_ids)
