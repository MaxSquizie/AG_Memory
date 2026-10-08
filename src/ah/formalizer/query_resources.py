"""Cross-record and actual-store checks for declared question/count resources."""
from ah.model import RefKind, TimeLiteral


def validate_query_resources(release, roles, domains):
    measures={}
    for schema in release.resources.get('MeasureSchema',{}).get('entries',()):
        if schema['measure_id'] in measures or schema['subject_role']==schema['value_role'] or schema['numeric_property']=='name' or not {schema['subject_role'],schema['value_role']}<=roles:
            raise ValueError('RESOURCE_MISSING: invalid MeasureSchema')
        measures[schema['measure_id']]=schema
    ids=set()
    for schema in release.resources.get('CausalSchema',{}).get('entries',()):
        if schema['schema_id'] in ids or schema['cause_role']==schema['effect_role'] or not {schema['cause_role'],schema['effect_role']}<=roles:
            raise ValueError('RESOURCE_MISSING: invalid CausalSchema')
        ids.add(schema['schema_id'])
    domain_ids={c['domain_id'] for kind in ('CountDomain','DomainCertificate','FormulaDomainCertificate','ComparisonDomainCertificate')
                for c in release.resources.get(kind,{}).get('entries',())}
    for rule in getattr(release,'syntax_rules',()):
        if rule['output_kind']!='QUERY_INTENT': continue
        request=rule['output']['request']
        if 'measure_id' in request and request['measure_id'] not in measures:
            raise ValueError('RESOURCE_MISSING: query intent measure is not declared')
        if request.get('mode')=='SUPERLATIVE' and request['requested_roles']!=[measures[request['measure_id']]['subject_role']]:
            raise ValueError('RESOURCE_MISSING: superlative variable must be the measured subject')
        if request.get('domain_certificate') and request['domain_certificate'] not in domain_ids:
            raise ValueError('RESOURCE_MISSING: query intent domain is not declared')
    for kind in ('CountDomain','ComparisonDomainCertificate'):
        for cert in release.resources.get(kind,{}).get('entries',()):
            if cert['domain_id'] in domains:
                raise ValueError('RESOURCE_MISSING: duplicate domain_id')
            domains.add(cert['domain_id'])
            if len(set(cert['completeness_evidence']))!=len(cert['completeness_evidence']):
                raise ValueError('RESOURCE_MISSING: duplicate completeness evidence')
            if len(set(cert.get('identity_evidence',())))!=len(cert.get('identity_evidence',())):
                raise ValueError('RESOURCE_MISSING: duplicate identity evidence')
            if cert['request_window'] is not None:
                TimeLiteral(tuple(cert['request_window']))
            if kind=='ComparisonDomainCertificate':
                if cert['measure_id'] not in measures:
                    raise ValueError('RESOURCE_MISSING: comparison measure is not declared')
                continue
            if (cert['count_unit']=='ENTITY') != bool(cert.get('count_variable')):
                raise ValueError('RESOURCE_MISSING: count unit/variable mismatch')
            keys=set(); nodes=set(); entities=set()
            for member in cert['members']:
                if member['key'] in keys or nodes&set(member['node_refs']):
                    raise ValueError('RESOURCE_MISSING: ambiguous CountDomain member identity')
                keys.add(member['key']); nodes.update(member['node_refs'])
                if cert['count_unit']=='ENTITY':
                    entity=member.get('entity_ref')
                    if not entity or entity in entities or member['key']!=entity:
                        raise ValueError('RESOURCE_MISSING: invalid entity CountDomain key')
                    entities.add(entity)
                elif 'entity_ref' in member:
                    raise ValueError('RESOURCE_MISSING: event CountDomain has entity member')
            if cert['count_unit']=='EVENT' and not cert.get('identity_evidence'):
                raise ValueError('RESOURCE_MISSING: event grouping needs explicit identity evidence')


def validate_query_store(release, store):
    for kind, role_fields in (('MeasureSchema',('subject_role','value_role')),('CausalSchema',('cause_role','effect_role'))):
        for schema in release.resources.get(kind,{}).get('entries',()):
            uid=schema['template_ref']
            if not store.has_uid(uid) or store.kind_of(uid) is not RefKind.T or not {schema[r] for r in role_fields}<={r.value for r in store.get_template(uid).roles}:
                raise ValueError('RESOURCE_MISSING: question schema/actual T mismatch')
    for cert in release.resources.get('ComparisonDomainCertificate',{}).get('entries',()):
        if any(not store.has_uid(uid) or store.kind_of(uid) is not RefKind.M for uid in cert['member_refs']):
            raise ValueError('RESOURCE_MISSING: comparison domain member is not M')
    for cert in release.resources.get('CountDomain',{}).get('entries',()):
        for member in cert['members']:
            if cert['count_unit']=='ENTITY' and (not store.has_uid(member['entity_ref']) or store.kind_of(member['entity_ref']) is not RefKind.M):
                raise ValueError('RESOURCE_MISSING: CountDomain entity missing')
            if any(not store.has_uid(uid) or store.kind_of(uid) not in {RefKind.N,RefKind.G} for uid in member['node_refs']):
                raise ValueError('RESOURCE_MISSING: CountDomain witness missing')
