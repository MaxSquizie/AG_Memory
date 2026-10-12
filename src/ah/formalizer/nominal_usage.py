"""Structural descriptions of an ENTITY slot, scoped to its source proof."""
from .canonical_ledger import digest


def link_id(p):
    key=[p['node_ref'],p['parent_ref'],p['position'],'NOMINAL',
         p['host_ref'],p['source_tag'],p['root_support_ref']]
    if p.get('host_path'): key.append(p['host_path'])
    if p.get('content_time'): key.append(p['content_time'])
    if p.get('host_group_ref'):key.append([p['host_group_ref'],p['host_member_binding_ref']])
    if p.get('scope_assumption'): key.append(p['scope_assumption'])
    return 'usage:'+digest(key)


def validate(p, ledger, store):
    from .refinement_uncertainty import validate as validate_assumption
    validate_assumption(p)
    parent=ledger.data['nodes'].get(p.get('parent_ref'),{})
    from .refinement_host_path import validate_path
    host_node=validate_path(p,ledger)
    child=ledger.data['nodes'].get(host_node,{})
    support=ledger.data['supports'].get(p.get('root_support_ref'),{})
    host=p.get('host_ref')
    from .nominal_group_member import parent_matches
    if (not host or not store.has_uid(host) or store.kind_of(host).value not in {'M','K'} or
        not parent_matches(p,parent,ledger,store) or
        child.get('actants',{}).get(p.get('host_role'))!=host or
        not p.get('source_tag') or support.get('source_tag')!=p['source_tag'] or
        support.get('kind')!='ROOT' or support.get('status')!='LIVE' or p.get('attitude')!='UNKNOWN' or
        p.get('status')!='LIVE' or p.get('link_id')!=link_id(p)):
        raise ValueError('NOMINAL_USAGE_INVALID')
