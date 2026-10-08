"""Versioned, closed runtime record and Emit schemas (JSON Schema 2020-12)."""
from __future__ import annotations
from copy import deepcopy
from jsonschema import Draft202012Validator

S = {'type': 'string', 'minLength': 1}
I = {'type': 'integer', 'minimum': 0}
B = {'type': 'boolean'}
O = {'type': 'object'}


def array(items=S, *, minimum=0):
    return {'type': 'array', 'items': items, 'minItems': minimum, 'maxItems': 100000}


def obj(required, properties, *, extra=False):
    return {'type': 'object', 'required': list(required), 'properties': properties,
            'additionalProperties': extra}


def enum(*values):
    return {'enum': list(values)}


NODE = obj(('id', 'kind', 'anchors'), {
    'id': S, 'kind': S, 'anchors': array(S, minimum=1), 'head': S})
EDGE = obj(('kind', 'from', 'to'), {'kind': S, 'from': S, 'to': S, 'role_id': S, 'scope': B})
EMIT_SCHEMAS = {
    'CANDIDATE_GRAPH': obj(('nodes', 'edges'), {'nodes': array(NODE, minimum=1), 'edges': array(EDGE)}),
    'CLAUSE_BOUNDARY': obj(('capture',), {'capture': S, 'side': enum('BEFORE', 'AFTER')}),
    'ELLIPSIS': obj(('capture', 'gap_kind'), {'capture': S, 'gap_kind': enum('PREDICATE_GAP', 'ARGUMENT_GAP', 'SUBORDINATOR_GAP'), 'antecedent': S}),
    'TOKEN_HYPOTHESIS': obj(('capture', 'variants'), {'capture': S, 'variants': array(S, minimum=1)}),
    'QUERY_INTENT': obj(('capture','request'), {'capture':S,'request':O,'compare_capture':S}),
}
BASE_EMITS=frozenset({'CANDIDATE_GRAPH','CLAUSE_BOUNDARY','ELLIPSIS','TOKEN_HYPOTHESIS'})

ROLE = obj(('role_id',), {'role_id': S, 'allowed_cases': array(), 'allowed_preps': array(),
    'argument_types': array(), 'cardinality': obj((), {'min': I, 'max': {'type': ['integer', 'null'], 'minimum': 0}}),
    'optionality': B, 'evidence_rule_id': S})
READ = obj(('read_id', 'lemma', 'snapshot_version'), {'read_id': S, 'lemma': S, 'snapshot_version': S,
    'sense_id': S, 'value_id': S, 'fact_ref': S, 'ground_type': enum('C', 'W'), 'provenance': O,
    'premise_support_refs': array(), 'binding_refs': array()})
RESOURCE_SCHEMAS = {
    'MeasureSchema': obj(('measure_id','template_ref','subject_role','value_role','numeric_property','unit','version'), {
        'measure_id':S,'template_ref':S,'subject_role':S,'value_role':S,'numeric_property':S,'unit':S,'version':S,
        'literal_syntax':enum('INTEGER','DECIMAL_DOT','DECIMAL_COMMA')}),
    'CausalSchema': obj(('schema_id','template_ref','cause_role','effect_role','version'), {
        'schema_id':S,'template_ref':S,'cause_role':S,'effect_role':S,'version':S,
        'temporal_policy':enum('SAME_SCOPE','ATEMPORAL_RULE')}),
    'ComparisonDomainCertificate': obj(('domain_id','pattern_signature','variable','measure_id','request_window','member_refs','completeness_evidence','version'), {
        'domain_id':S,'pattern_signature':{'type':'string','pattern':'^[0-9a-f]{64}$'},'variable':S,
        'measure_id':S,'request_window':{'type':['array','null'],'items':{'type':'number'},'minItems':2,'maxItems':2},
        'member_refs':{'type':'array','items':S,'uniqueItems':True,'maxItems':1024},
        'completeness_evidence':array(S,minimum=1),'version':S}),
    'CountDomain': obj(('domain_id','pattern_signature','count_unit','request_window','members','completeness_evidence','version'), {
        'domain_id':S,'pattern_signature':{'type':'string','pattern':'^[0-9a-f]{64}$'},'count_unit':enum('ENTITY','EVENT'),
        'count_variable':S,'request_window':{'type':'array','items':{'type':'number'},'minItems':2,'maxItems':2},
        'members':{'type':'array','maxItems':1024,'items':obj(('key','node_refs'),{'key':S,'node_refs':{'type':'array','items':S,'minItems':1,'maxItems':1024,'uniqueItems':True},'entity_ref':S})},
        'identity_evidence':array(S),'completeness_evidence':array(S,minimum=1),'version':S}),
    'FormulaDomainCertificate': obj(('domain_id','pattern_signature','count_variable','request_window','completeness_evidence','version'), {
        'domain_id':S,'pattern_signature':{'type':'string','pattern':'^[0-9a-f]{64}$'},'count_variable':S,
        'closure_mode':enum('ENUMERATED','ASSERTED_BOUND'),
        'request_window':{'type':['array','null'],'items':{'type':'number'},'minItems':2,'maxItems':2},
        'completeness_evidence':array(S,minimum=1),'version':S}),
    'NumeralRules': obj(('lemma','value'), {'lemma':S,'value':{'type':'integer','minimum':0,'maximum':10**12},'evidence_rule_id':S}),
    'R-S': obj(('lemma', 'POS', 'sense_id'), {'lemma': S, 'POS': S, 'sense_id': S,
        'predicate_schema_id': S, 'semantic_types': array(), 'paraphrase_group': S,
        'evidence_rule_id': S, 'anchor_pattern': array(obj((), {'lemma': S, 'POS': S}), minimum=2)}),
    'R-V': obj(('sense_id', 'roles'), {'sense_id': S, 'lemma': S, 'POS': S, 'aspect': S,
        'construction_id': S, 'roles': array(ROLE), 'state_class': enum('STATE', 'EVENT', None),
        'temporal_mode_hint': enum('STATE', 'EVENT', 'PROCESS', 'TRANSITION', None)}),
    'TemplateMap': obj(('sense_id', 'template_ref', 'roles'), {'sense_id': S, 'template_ref': S, 'roles': array(),
        'predicate_id': S, 'value_id': S, 'domain': S, 'property_mapping': O, 'expansion_rule_id': S}),
    'RoleRegistry': obj(('role_id',), {'role_id': S, 'allowed_argument_kinds': array(),
        'cardinality': I, 'projection': B, 'schema_version': S}),
    'PredicateSchema': obj(('lemma', 'value_ids'), {'lemma': S, 'POS': S, 'predicate_id': S,
        'roles': array(), 'argument_type_constraints': O, 'optional_roles': array(), 'cardinality': O,
        'value_ids': array(), 'truth_status': S, 'mapping_id': S,
        'value_expansions': array(obj(('rule_id', 'value_ids'), {'rule_id': S, 'value_ids': array()}))}),
    'R-X3': obj(('lemma', 'sense_id'), {'lemma': S, 'POS': S, 'sense_id': S, 'evidence_rule_id': S}),
    'DeclaredReads': READ,
    'SyntaxRules': {'oneOf': [obj(('dsl',), {'dsl': S}), obj(('rule_id', 'input_feature_pattern', 'output_kind', 'output', 'constraints', 'priority', 'min_evidence', 'coverage_tag'), {
        'rule_id': S, 'input_feature_pattern': O, 'output_kind': enum(*EMIT_SCHEMAS), 'output': O,
        'constraints': array(O), 'priority': {'type': 'integer'}, 'min_evidence': {'type': 'integer', 'minimum': 1}, 'coverage_tag': S, 'stage': enum('SRL', 'T2')})]},
    'ScopeLexicon': obj(('pattern',), {'pattern': S, 'operator': S, 'role': S, 'trigger': S,
        'lemma': S, 'POS': S, 'attachment_kinds': array(), 'variable_sort': S,
        'restriction_pattern': O, 'precedence_constraints': array(O)}),
    'AttitudeMap': obj(('lemma', 'argument_role', 'attitude'), {'lemma': S, 'argument_role': S,
        'attitude': enum('QUOTED', 'EMBEDDED', 'HYPOTHETICAL', 'UNKNOWN'), 'holder_role': S, 'factivity': B}),
    'TemporalRules': obj(('pattern', 'kind'), {'pattern': S, 'kind': enum('POINT_CLOCK', 'DAY_INTERVAL', 'INTERVAL_CLOCK'),
        'day_offset': {'type': 'integer'}, 'interval_semantics': enum('EXISTENTIAL', 'CONTINUOUS'), 'rule_id': S,
        'hour_group': S, 'minute_group': S}),
    'OpenTemplatePolicy': obj(('allow',), {'allow': B, 'version': S, 'key_schema_version': S,
        'allowed_argument_kinds': array(), 'isolation_domain': S, 'migration_policy': S, 'permitted_query_mode': S}),
    'ProposalPolicy': obj(('max_nodes', 'max_edges', 'max_depth', 'max_source_tokens'), {
        **{k: {'type': 'integer', 'minimum': 1} for k in ('max_nodes', 'max_edges', 'max_depth', 'max_source_tokens', 'max_rule_steps', 'max_rule_matches')},
        'max_calls_per_unit': I, 'verify_deterministic': B, 'version': S,
        'allowed_anchor_kinds': array(), 'allowed_edge_kinds': array(), 'allowed_read_sets': array(),
        'validation_schema_version': S, 'model_key': S, 'params_hash': S}),
    'IncompatibilityRules': obj(('kind', 'rule_id', 'sense_id', 'role_id', 'key_roles'), {
        'kind': enum('ROLE_EXCLUSIVE'), 'rule_id': S, 'sense_id': S, 'role_id': S, 'key_roles': array()}),
    'DomainCertificate': obj(('domain_id', 'template_ref', 'count_role', 'known_roles', 'request_window', 'completeness_evidence', 'version'), {
        'domain_id': S, 'template_ref': S, 'count_role': S, 'known_roles': {'type': 'object', 'additionalProperties': S},
        'closure_mode': enum('ENUMERATED','ASSERTED_BOUND'),
        'request_window': {'type': ['array', 'null'], 'items': {'type': 'number'}, 'minItems': 2, 'maxItems': 2},
        'completeness_evidence': array(S, minimum=1), 'version': S}),
    'CorefPolicy': obj(('window_size', 'hard_features', 'ranking_criteria', 'tie_policy', 'event_anaphora_rules'), {
        'window_size': I, 'hard_features': array(enum('gender', 'number', 'person', 'animacy', 'semantic_type')),
        'ranking_criteria': array(enum('EXPLICIT_REF', 'SAME_SOURCE', 'RECENCY')), 'tie_policy': enum('KEEP_ALL'),
        'event_anaphora_rules': array(obj(('rule_id','pattern','role_ids'), {
            'rule_id':S, 'pattern':S, 'role_ids':array(S,minimum=1),
            'template_refs':array(S), 'temporal_modes':array(enum('EVENT','PROCESS','TRANSITION'))}))}),
    'CandidateSchema': obj(('candidate_kind', 'schema_version', 'schema'), {
        'candidate_kind': enum(*EMIT_SCHEMAS), 'schema_version': enum('emit-v1'), 'schema': O}),
}


def candidate_schema_entries():
    return [{'candidate_kind': k, 'schema_version': 'emit-v1', 'schema': deepcopy(v)}
            for k, v in sorted(EMIT_SCHEMAS.items())]


def validate_resources(resources):
    for kind, resource in resources.items():
        if kind not in RESOURCE_SCHEMAS:
            raise ValueError('RESOURCE_SCHEMA_UNREGISTERED:' + kind)
        validator = Draft202012Validator(RESOURCE_SCHEMAS[kind])
        for i, entry in enumerate(resource['entries']):
            errors = list(validator.iter_errors(entry))
            if errors:
                error = errors[0]
                raise ValueError(f'{kind}[{i}] {list(error.path)}: {error.message}')
    candidate_entries = resources['CandidateSchema']['entries']
    schemas = {e['candidate_kind']: e['schema'] for e in candidate_entries}
    if (len(schemas)!=len(candidate_entries) or not BASE_EMITS<=set(schemas) or not set(schemas)<=set(EMIT_SCHEMAS)
            or any(schema!=EMIT_SCHEMAS[k] for k,schema in schemas.items())):
        raise ValueError('CandidateSchema must pin the base and every used optional Emit exactly')
    return {k: Draft202012Validator(v) for k, v in schemas.items()}
