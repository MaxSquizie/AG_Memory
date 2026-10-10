"""Bounded TP hints are released constraints, never a gold answer or rewrite."""
from copy import deepcopy
from dataclasses import asdict
import json

from ah.formalizer.canonical_ledger import digest
from ah.formalizer.native_frontend import (
    _frames_for_hypotheses, _propose, _released_slot_evidence,
    _tp_speech_act_metadata,
)
from ah.formalizer.pipeline import t0
from ah.formalizer.state import MorphVariant
from ah.formalizer.tp_proposer import (
    Hypothesis, StructureProposalRequest, TEdge, TNode,
    build_structure_prompt, parse_and_validate,
)


class Release:
    """A fixed input snapshot for the pure projection; no canonical store."""
    def __init__(self, entries=None, policy=None):
        values={'R-S':[], 'R-V':[], 'AttitudeMap':[], 'TemporalRules':[],
                'ScopeLexicon':[], 'RoleRegistry':[{'role_id':r} for r in
                    ('SUBJECT','OBJECT','RECIPIENT','EXPERIENCER','SURFACE_ARG')],
                'ProposalPolicy':[{'max_nodes':64,'max_edges':128,'max_depth':16,
                    'max_source_tokens':256,'max_rule_steps':20000,
                    'verify_deterministic':True,**(policy or {})}]}
        values.update(deepcopy(entries or {}))
        self.resources={k:{'version':'version:'+k,'entries':v} for k,v in values.items()}
        self.sha256=digest(self.resources)
        self.manifest={'version':'fixed-test-release'}

    def entries(self, kind): return self.resources[kind]['entries']
    def version(self, kind): return self.resources[kind]['version']


def state_for(text, variants):
    state=t0(text)
    for token in state.evidence:
        token.variants=tuple(MorphVariant(lemma=lemma,pos=pos,cases=frozenset({'nom'}))
                             for lemma,pos in variants.get(token.span,()))
    state.source_uid='source:test'
    return state


def role(rid, kinds=('ENTITY',), cases=('nom',)):
    return {'role_id':rid,'argument_types':list(kinds),'allowed_cases':list(cases),
            'allowed_preps':[],'cardinality':{'min':1,'max':1},'optionality':False}


def constraints():
    return {'R-S':[
        {'lemma':'сказать','POS':'VERB','sense_id':'PRIVATE_CANONICAL_SENSE',
         'template_ref':'fixture:T:secret','semantic_types':['private semantic conclusion']},
        {'lemma':'сказать','POS':'INFN','sense_id':'PRIVATE_INFINITIVE_SENSE'},
        {'lemma':'спать','POS':'VERB','sense_id':'OUTSIDE_REGION_SENSE'}],
        'R-V':[
            {'sense_id':'PRIVATE_CANONICAL_SENSE','construction_id':'statement-slot',
             'evidence_rule_id':'released-valency-rule','roles':[role('SUBJECT'),role('OBJECT',('PROPOSITION',),())]},
            {'sense_id':'PRIVATE_CANONICAL_SENSE','construction_id':'other-construction',
             'roles':[role('SUBJECT'),role('RECIPIENT')]},
            {'sense_id':'PRIVATE_INFINITIVE_SENSE','construction_id':'infinitive-slot',
             'roles':[role('OBJECT',('PROPOSITION',),())]},
            {'sense_id':'OUTSIDE_REGION_SENSE','roles':[role('EXPERIENCER')]}],
        'AttitudeMap':[{'lemma':'сказать','argument_role':'OBJECT','holder_role':'SUBJECT',
                       'attitude':'QUOTED','factivity':False,'rule_id':'released-attitude-rule'}]}


def test_all_region_variants_and_constructions_are_pinned_without_memory_ids():
    state=state_for('сказал спит',{'сказал':[('сказать','VERB'),('сказать','INFN')],
                                 'спит':[('спать','VERB')]})
    release=Release(constraints())
    source=(state.evidence[0].token_id,)
    evidence=_released_slot_evidence(state,release,source,release.entries('ProposalPolicy')[0])
    assert evidence['status']=='COMPLETE'
    assert len(evidence['valency_alternatives'])==3
    assert {x['resource_refs'][1].get('construction_id') for x in evidence['valency_alternatives']}=={
        'statement-slot','other-construction','infinitive-slot'}
    assert all(x['anchor_refs']==list(source) for x in evidence['valency_alternatives'])
    assert evidence['attitude_alternatives'][0]['argument_role']=='OBJECT'
    assert evidence['attitude_alternatives'][0]['attitude']=='QUOTED'
    assert evidence['resource_snapshot']['release_sha256']==release.sha256
    assert evidence['resource_snapshot']['resource_versions']['R-V']==release.version('R-V')
    wire=json.dumps(evidence,ensure_ascii=False)
    for hidden in ('PRIVATE_CANONICAL_SENSE','PRIVATE_INFINITIVE_SENSE','OUTSIDE_REGION_SENSE',
                   'fixture:T:secret','private semantic conclusion','factivity'):
        assert hidden not in wire
    before=deepcopy(release.resources)
    assert _released_slot_evidence(state,release,source,release.entries('ProposalPolicy')[0])==evidence
    assert release.resources==before


def test_declared_multi_anchor_matches_preserve_every_ordered_alternative():
    state=state_for('a b a b',{'a':[('a','VERB')],'b':[('b','NOUN')]})
    release=Release({'R-S':[{'lemma':'phrase','POS':'VERB','sense_id':'phrase-sense',
        'anchor_pattern':[{'lemma':'a','POS':'VERB'},{'lemma':'b','POS':'NOUN'}]}],
        'R-V':[{'sense_id':'phrase-sense','construction_id':'phrase-rule','roles':[role('SUBJECT')]}]})
    source=tuple(e.token_id for e in state.evidence)
    evidence=_released_slot_evidence(state,release,source,release.entries('ProposalPolicy')[0])
    assert evidence['status']=='COMPLETE'
    assert {tuple(x['anchor_refs']) for x in evidence['valency_alternatives']}=={
        (source[0],source[1]),(source[0],source[3]),(source[2],source[3])}
    # The head word alone never licenses a phrase entry.
    single=_released_slot_evidence(state,release,(source[0],),release.entries('ProposalPolicy')[0])
    assert single['valency_alternatives']==[]


def test_matching_temporal_rules_export_anchors_without_timestamp_or_owner():
    state=state_for('завтра в 09:00',{})
    release=Release({'TemporalRules':[
        {'rule_id':'day-trigger','pattern':r'\bзавтра\b','kind':'DAY_INTERVAL',
         'day_offset':1,'interval_semantics':'EXISTENTIAL'},
        {'rule_id':'clock-trigger','pattern':r'\b09:00\b','kind':'POINT_CLOCK'},
        {'rule_id':'unmatched','pattern':r'\bвчера\b','kind':'DAY_INTERVAL'}]})
    source=tuple(e.token_id for e in state.evidence)
    evidence=_released_slot_evidence(state,release,source,release.entries('ProposalPolicy')[0])
    assert len(evidence['temporal_triggers'])==2
    assert {x['kind'] for x in evidence['temporal_triggers']}=={'DAY_INTERVAL','POINT_CLOCK'}
    wire=json.dumps(evidence)
    for forbidden in ('day_offset','timestamp','time_scope_owner','target_ref'):
        assert forbidden not in wire
    partial=_released_slot_evidence(state,release,(source[2],),release.entries('ProposalPolicy')[0])
    assert partial['temporal_triggers']==[]  # A clock expression crosses the region boundary.


class Capture:
    def __init__(self, reply=None):
        self.prompts=[]; self.reply=reply or {'abstain':True}
    def propose_local(self,prompt):
        self.prompts.append(json.loads(prompt));return json.dumps(self.reply)


def test_evidence_exhaustion_is_explicit_and_never_sends_a_valid_sense_prefix():
    state=state_for('сказал',{'сказал':[('сказать','VERB')]})
    release=Release(constraints(),{'max_edges':1})
    evidence=_released_slot_evidence(state,release,tuple(e.token_id for e in state.evidence),
                                     release.entries('ProposalPolicy')[0])
    assert evidence['status']=='LIMIT_EXCEEDED'
    assert evidence['limit']=='role_slots'
    assert evidence['valency_alternatives']==evidence['attitude_alternatives']==[]
    selector=Capture();_propose(state,selector,release)
    assert selector.prompts==[]
    assert any(d.code=='COMPUTATION_LIMIT' and 'no partial evidence sent' in d.detail for d in state.diagnostics)
    assert state.syntax_trace[-1]['status']=='LIMIT_EXCEEDED'


def test_multi_anchor_search_and_serialized_payload_have_explicit_limits():
    state=state_for('a b a b',{'a':[('a','VERB')],'b':[('b','NOUN')]})
    release=Release({'R-S':[{'lemma':'phrase','POS':'VERB','sense_id':'s',
        'anchor_pattern':[{'lemma':'a'},{'lemma':'b'}]}]}, {'max_rule_steps':4})
    evidence=_released_slot_evidence(state,release,tuple(e.token_id for e in state.evidence),
                                     release.entries('ProposalPolicy')[0])
    assert evidence['status']=='LIMIT_EXCEEDED' and evidence['limit']=='search_steps'
    release=Release(policy={'max_source_tokens':1,'max_edges':1})
    evidence=_released_slot_evidence(state,release,(),release.entries('ProposalPolicy')[0])
    assert evidence['status']=='LIMIT_EXCEEDED' and evidence['limit']=='serialized_bytes'


def test_boolean_default_and_reviewed_wh_metadata_never_export_entity_refs():
    state=state_for('Верно ли, что Иван вошёл?',{})
    release=Release()
    state.observation={'request_kind':'QUERY','goal_request':{}}
    metadata=_tp_speech_act_metadata(state,release,tuple(e.token_id for e in state.evidence))
    assert metadata['query_form']=='BOOLEAN' and metadata['query_modes']==['FORMULA']
    state.observation={'request_kind':'QUERY','goal_request':{
        'mode':'COMPARE','measure_id':'length','compare_entity_ref':'fixture:M:secret'}}
    metadata=_tp_speech_act_metadata(state,release,tuple(e.token_id for e in state.evidence))
    assert metadata['query_form']=='COMPARE'
    assert 'fixture:M:secret' not in json.dumps(metadata)
    state.observation={'request_kind':'QUERY'}
    assert _tp_speech_act_metadata(state,release,())['query_form']=='UNDETERMINED'
    state.query_intents=[{'token_ref':state.evidence[0].token_id,
        'request':{'mode':'WH','requested_roles':['SUBJECT']},
        'provenance':{'pattern_ids':['reviewed-question-rule'],'resource_versions':{'SyntaxRules':'1'}}}]
    metadata=_tp_speech_act_metadata(state,release,(state.evidence[0].token_id,))
    assert metadata['query_form']=='WH'
    assert metadata['reviewed_query_intents'][0]['request']['requested_roles']==['SUBJECT']
    state.query_intents[0]['request']={}
    assert _tp_speech_act_metadata(state,release,(state.evidence[0].token_id,))['query_form']=='BOOLEAN'


def test_complementizer_does_not_publish_a_grounded_query_reading():
    state=state_for('Иван сказал, что Пётр пришёл.',{})
    state.observation={'request_kind':'ASSERTION'}
    metadata=_tp_speech_act_metadata(state,Release(),tuple(e.token_id for e in state.evidence))
    assert metadata['declared_request_kind']=='ASSERTION'
    assert metadata['query_form']=='UNDETERMINED'
    assert metadata['query_modes']==metadata['reviewed_query_intents']==[]
    assert 'readings' not in metadata


def test_unrelated_attitudes_do_not_consume_local_search_budget():
    state=state_for('a',{'a':[('a','VERB')]})
    unrelated=[{'lemma':'unrelated:'+str(i),'argument_role':'OBJECT','attitude':'QUOTED'}
               for i in range(1000)]
    release=Release({'AttitudeMap':unrelated},{'max_rule_steps':2})
    evidence=_released_slot_evidence(state,release,tuple(e.token_id for e in state.evidence),
                                     release.entries('ProposalPolicy')[0])
    assert evidence['status']=='COMPLETE' and evidence['search_steps']==1
    assert evidence['attitude_alternatives']==[]


def test_matching_senses_without_valency_still_use_bounded_search():
    state=state_for('a',{'a':[('a','VERB')]})
    release=Release({'R-S':[{'lemma':'a','POS':'VERB','sense_id':'s'+str(i)} for i in range(100)]},
                    {'max_rule_steps':4})
    evidence=_released_slot_evidence(state,release,tuple(e.token_id for e in state.evidence),
                                     release.entries('ProposalPolicy')[0])
    assert evidence['status']=='LIMIT_EXCEEDED' and evidence['limit']=='search_steps'
    assert evidence['valency_alternatives']==[]


def test_proposer_receives_the_projection_but_does_not_rewrite_a_role():
    state=state_for('сказал содержимое',{'сказал':[('сказать','VERB')],
                                     'содержимое':[('содержимое','VERB')]})
    release=Release(constraints())
    source=tuple(e.token_id for e in state.evidence)
    reply={'hypotheses':[{'local_id':'local','nodes':[
        {'kind':'PREDICATE','anchor_spans':[source[0]]},
        {'kind':'PREDICATE','anchor_spans':[source[1]]}],
        'edges':[{'kind':'ATTITUDE','from':0,'to':1,'role_id':'SURFACE_ARG'}],
        'alignment':list(source)}]}
    selector=Capture(reply);_propose(state,selector,release)
    request=selector.prompts[0]['request']
    assert request['released_slot_evidence']['resource_snapshot']['release_sha256']==release.sha256
    assert request['released_slot_evidence']['attitude_alternatives'][0]['argument_role']=='OBJECT'
    assert state.frames[0].semantic['proposition_args']['SURFACE_ARG']['attitude']=='UNKNOWN'
    assert any(d.code=='ATTITUDE_UNKNOWN' for d in state.diagnostics)
    assert 'OBJECT' not in state.frames[0].semantic['proposition_args']


def test_validated_entity_only_alternative_is_retained_and_blocks_unique_sibling():
    state=state_for('a b',{'a':[('a','NOUN')],'b':[('b','VERB')]})
    release=Release();source=tuple(e.token_id for e in state.evidence)
    empty=Hypothesis('entity-only',(TNode('ENTITY',(source[0],)),),alignment=(source[0],))
    valid=Hypothesis('predicate',(TNode('PREDICATE',(source[1],)),TNode('ENTITY',(source[0],))),
        (TEdge('ARGUMENT',0,1,'SUBJECT'),),alignment=source)
    assert _frames_for_hypotheses(state,[empty,valid],release)==[]
    assert state.grammar_search_incomplete
    assert any(d.code=='STRUCTURE_NOT_COVERED' and 'entity-only' in d.detail for d in state.diagnostics)
    assert {a.alt_id for a in state.linked_alternatives}=={'entity-only','predicate'}
    retained=[r['hypothesis'] for r in state.syntax_trace if r.get('event')=='UNINTERPRETED_STRUCTURAL_ALTERNATIVE']
    assert retained==[asdict(empty),asdict(valid)]
    assert state.frames==state.logical_roots==[]


def test_wire_evidence_preserves_ambiguous_and_unknown_replies():
    request=StructureProposalRequest('request','pre-seal',('a','b'),
        allowed_node_kinds=frozenset({'PREDICATE','ENTITY'}),
        allowed_edge_kinds=frozenset({'ARGUMENT'}),
        allowed_role_ids=frozenset({'SUBJECT','SURFACE_ARG'}),
        released_slot_evidence={'status':'COMPLETE','valency_alternatives':[]},
        speech_act_metadata={'query_form':'UNDETERMINED'})
    response={'hypotheses':[{'local_id':name,'nodes':[
        {'kind':'PREDICATE','anchor_spans':['a']},{'kind':'ENTITY','anchor_spans':['b']}],
        'edges':[{'kind':'ARGUMENT','from':0,'to':1,'role_id':rid}],
        'alignment':['a','b']} for name,rid in [('one','SUBJECT'),('two','SURFACE_ARG')]]}
    prompt=json.loads(build_structure_prompt(request,[]))
    assert prompt['request']['speech_act_metadata']['query_form']=='UNDETERMINED'
    parsed=parse_and_validate(request,json.dumps(response))
    assert [(h.local_id,h.edges[0].role_id) for h in parsed]==[('one','SUBJECT'),('two','SURFACE_ARG')]
    assert parse_and_validate(request,'{"abstain":true}')==[]
