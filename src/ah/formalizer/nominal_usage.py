"""Structural descriptions of an ENTITY slot, scoped to its source proof."""
from .canonical_ledger import digest


def link_id(p):
    key=[p['node_ref'],p['parent_ref'],p['position'],'NOMINAL',
         p['host_ref'],p['source_tag'],p['root_support_ref']]
    if p.get('host_path'): key.append(p['host_path'])
    return 'usage:'+digest(key)


def validate(p, ledger, store):
    parent=ledger.data['nodes'].get(p.get('parent_ref'),{})
    from .refinement_host_path import validate_path
    host_node=validate_path(p,ledger)
    child=ledger.data['nodes'].get(host_node,{})
    support=ledger.data['supports'].get(p.get('root_support_ref'),{})
    host=p.get('host_ref')
    if (not host or not store.has_uid(host) or store.kind_of(host).value!='M' or
        parent.get('actants',{}).get(p.get('position'))!=host or
        child.get('actants',{}).get(p.get('host_role'))!=host or
        not p.get('source_tag') or support.get('source_tag')!=p['source_tag'] or
        support.get('kind')!='ROOT' or support.get('status')!='LIVE' or p.get('attitude')!='UNKNOWN' or
        p.get('status')!='LIVE' or p.get('link_id')!=link_id(p)):
        raise ValueError('NOMINAL_USAGE_INVALID')
