"""A nominal description may target one established member of a parent's K."""


def parent_matches(p,parent,ledger,store):
    slot=parent.get('actants',{}).get(p.get('position'))
    group=p.get('host_group_ref')
    if group is None:
        return 'host_member_binding_ref' not in p and slot==p.get('host_ref')
    if slot!=group or not store.has_uid(group) or store.kind_of(group).value!='K':return False
    binding=ledger.data['bindings'].get(p.get('host_member_binding_ref'),{})
    support=ledger.data['supports'].get(p.get('root_support_ref'),{})
    return (p.get('host_ref') in {r.uid for r in store.get_element_any_domain(group).members}
        and binding.get('target_ref')==p.get('host_ref') and binding.get('source_tag')==p.get('source_tag')
        and binding.get('status')=='LIVE' and p.get('host_member_binding_ref') in support.get('binding_refs',()))
