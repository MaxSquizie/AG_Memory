"""Production validators/readers invoked by extended oracle actions."""
from copy import deepcopy
from dataclasses import asdict
import base64, json
from ah.formalizer.canonical_ledger import digest

COMPONENT_ACTIONS={'validate_input','input_identity','validate_proposal','proposal_budget',
 'post_seal_proposal','compile_query_kind','consolidate','load_release'}

def released_fixture(session):
    """Valid baseline first; negative cases mutate only one stated dimension."""
    cached=getattr(session,'_component_release_fixture',None)
    if cached is not None:
        valid,trust=cached
        return valid,deepcopy(trust)
    from tools.formalizer_v7_native_binding import fixture
    from tools.formalizer_v7_test_support import sign_test_release
    release,_=fixture(session.core,'known');m=deepcopy(release.manifest)
    rr={r['kind']:r for r in m['entries']}
    rr['PredicateSchema']['entries']=[{'lemma':'быть','value_ids':['LOCATIVE']}]
    rr['R-X3']['entries']=[{'lemma':'быть','sense_id':'LOCATIVE'}]
    rr['DeclaredReads']['entries']=[{'read_id':'fixture-read','lemma':'быть','snapshot_version':'test-v1'}]
    rr['SyntaxRules']['entries']=[{'rule_id':'fixture-noun','stage':'SRL',
        'input_feature_pattern':{'captures':{'n':{'POS':['NOUN']}}},
        'output_kind':'TOKEN_HYPOTHESIS','output':{'capture':'n','variants':['keep_as_is']},
        'constraints':[],'priority':0,'min_evidence':1,'coverage_tag':'TEST_ONLY'}]
    rr['R1']={'kind':'R1','version':'test-v1','schema_version':'v7','dependency_versions':{},'entries':[{'surface':'книга','lemma':'книга','POS':'NOUN','case':'nom','gender':'femn','number':'sing','person':None,'tense':None,'animacy':'inan','score':1.0,'source_tag':'TEST_ONLY:morph-v1'}]}
    rr['R-WK']={'kind':'R-WK','version':'test-v1','schema_version':'v7','dependency_versions':{},'entries':[{'record_id':'TEST_ONLY:wk-1','subject_type':'ENTITY','predicate':'LOCATIVE','object':'table','polarity':True,'provenance':{'source':'TEST_ONLY:world'}}]}
    rr['EvidencePriorityPolicy']={'kind':'EvidencePriorityPolicy','version':'test-v1','schema_version':'v7','dependency_versions':{},'entries':[{'domain':'TEST_ONLY','source_order':['O','C','W'],'conflict_rule':'NO_DOMINANCE','no_auto_winner_conditions':['SOURCE_CONFLICT']}]}
    rr['DomainCertificate']={'kind':'DomainCertificate','version':'test-v1','schema_version':'v7','dependency_versions':{},'entries':[{'domain_id':'TEST_ONLY:count-domain','template_ref':'fixture:T:LOCATIVE','count_role':'SUBJECT','known_roles':{},'request_window':None,'completeness_evidence':['TEST_ONLY:closed-domain-proof'],'version':'test-v1'}]}
    rr['CorefPolicy']={'kind':'CorefPolicy','version':'test-v1','schema_version':'v7','dependency_versions':{},'entries':[{'window_size':32,'hard_features':['gender','number'],'ranking_criteria':['EXPLICIT_REF'],'tie_policy':'KEEP_ALL','event_anaphora_rules':[]}]}
    m['entries']=list(rr.values());m['dependency_versions']={kind:'test-v1' for kind in rr}
    rehash_coverage(m)
    valid,trust=sign_test_release(m);valid.validate_store(session.core.store)
    session._component_release_fixture=(valid,deepcopy(trust))
    return valid,deepcopy(trust)

def rehash_coverage(m):
    m['coverage_report']['resource_content_sha256']=digest({k:m[k] for k in ('kind','version','schema_version','entries','dependency_versions')})
    m['coverage_report']['units_by_kind']={r['kind']:len(r['entries']) for r in m['entries']}

def component_action(s,a,p):
    if a=='validate_input':
        from ah.formalizer.v7_pipeline import _observation
        from ah.formalizer.clarifications import validate_input
        raw={**p['base'],**p['override']};before=s.store.read_global_head();codes=[]
        try:obs=_observation(raw['text'],version=1,raw_input=raw);validate_input(s.store,obs);accepted=True
        except (ValueError,TypeError,KeyError):accepted=False;codes=['INPUT_REJECTED']
        s.api.add('v7_pipeline._observation / clarifications.validate_input')
        return {'input':{'accepted':accepted},'diagnostics':{'codes':codes},'durable':{'new_record_count':s.store.read_global_head()-before}}
    if a=='input_identity':
        from ah.formalizer.v7_pipeline import _observation
        records=[_observation(r['text'],version=i+1,raw_input={**r,'range':p['force_equal_range']}) for i,r in enumerate(p['records'])]
        s.api.add('v7_pipeline._observation observation identity')
        return {'identity':{'same_observation':len({r['observation_id'] for r in records})==1,'interpretation_versions':[r['interpretation_version'] for r in records]}}
    if a=='validate_proposal':
        from ah.formalizer.tp_proposer import StructureProposalRequest,parse_and_validate
        req=StructureProposalRequest('fixture','seal',('t0','t1'),allowed_node_kinds=frozenset({'PREDICATE','ENTITY'}),allowed_edge_kinds=frozenset({'ARGUMENT'}),allowed_role_ids=frozenset({'SUBJECT'}))
        h={'local_id':'h','nodes':[{'kind':'PREDICATE','anchor_spans':['t0']},{'kind':'ENTITY','anchor_spans':['t1']}],'edges':[{'kind':'ARGUMENT','from':0,'to':1,'role_id':'SUBJECT'}],'alignment':['t0','t1']}
        m=p['mutation'];reply={'hypotheses':[h]}
        if m in {'canonical_uid','new_g_id'}:h['nodes'][0]['uid']='canonical:foreign'
        elif m in {'foreign_span','out_of_bounds_anchor'}:h['nodes'][0]['anchor_spans']=['outside']
        elif m=='unknown_node_kind':h['nodes'][0]['kind']='NEW_FUNCTION'
        elif m=='unknown_edge_kind':h['edges'][0]['kind']='NEW_LINK'
        elif m in {'invented_role','role_not_registered'}:h['edges'][0]['role_id']='INVENTED_ROLE'
        elif m=='undeclared_read':h['reads']=['private-source']
        elif m=='new_text':h['nodes'][0]['text']='invented input'
        elif m=='truth_claim':h['nodes'][0]['truth']=True
        elif m=='sealed_mutation':
            from ah.formalizer.pipeline import t0
            from ah.formalizer.seal import structural_seal
            st=t0('fixture');structural_seal(st)
            # Attempt the production pre-seal admission guard with a valid proposal.
            # A sealed state cannot accept it even though its schema is valid.
            parse_and_validate(req,json.dumps(reply))
            accepted=True;codes=[]
            try:st.require_structures_open('TP')
            except RuntimeError:accepted=False;codes=['PROPOSAL_INVALID']
            s.api.add('tp_proposer.parse_and_validate / FormalizationState.require_structures_open')
            return {'proposal':{'accepted':accepted},'diagnostics':{'codes':codes},'registry':{'new_entry_count':len(s.store.ledger.data['nodes'])},'store':{'new_record_count':len(s.store.ledger.data['supports'])}}
        elif m=='cycle':h['edges'].append({'kind':'ARGUMENT','from':1,'to':0,'role_id':'SUBJECT'})
        else:raise ValueError('UNBOUND_PROPOSAL_MUTATION:'+m)
        accepted=True;codes=[]
        try:parse_and_validate(req,json.dumps(reply))
        except Exception as exc:
            from ah.formalizer.selection_protocol import ProtocolError
            if not isinstance(exc,(ValueError,RuntimeError,ProtocolError)):raise
            accepted=False;codes=['PROPOSAL_INVALID']
        s.api.add('tp_proposer.parse_and_validate / deterministic typed TP validator')
        return {'proposal':{'accepted':accepted},'diagnostics':{'codes':codes},'registry':{'new_entry_count':0},'store':{'new_record_count':0}}
    if a=='post_seal_proposal':
        from ah.formalizer.pipeline import t0
        from ah.formalizer.seal import structural_seal
        st=t0('fixture');structural_seal(st);before=st.structural_hash;codes=[]
        try:st.require_structures_open('TP')
        except RuntimeError:codes=['INTEGRITY_ERROR']
        s.api.add('seal.structural_seal / FormalizationState.require_structures_open')
        return {'diagnostics':{'codes':codes},'structure':{'hash_unchanged':st.structural_hash==before,'seal_changed':st.structural_hash!=before},'proposal':{'accepted':not codes}}
    if a=='proposal_budget':
        from ah.formalizer.provider_adapter import ProviderAdapter,BudgetSnapshot,BudgetExceeded
        limits=dict(tp_calls=100,lexical_calls=100,max_nodes=100,max_edges=100,max_depth=100,token_limit=10000)
        key={'nodes':'max_nodes','edges':'max_edges','depth':'max_depth','tokens':'token_limit'}.get(p['limit_name'],p['limit_name']);limits[key]=p['limit']
        adapter=ProviderAdapter('budget',frozenset({'select','propose_local'}),lambda _: '{}',budget=BudgetSnapshot(**limits));exceeded=False
        try:
            if p['limit_name'] in {'nodes','edges','depth'}:
                counts={'nodes':1,'edges':1,'depth':1};counts[p['limit_name']]=p['used'];adapter.validate_structure(counts['nodes'],counts['edges'],counts['depth'])
            elif p['limit_name']=='tokens':adapter._check_tokens(p['used'])
            elif p['limit_name']=='tp_calls':
                for i in range(p['used']):adapter.propose_local('bounded '+str(i),'fixture')
            elif p['limit_name']=='lexical_calls':
                for i in range(p['used']):adapter.propose_lexical('bounded lexical '+str(i),'fixture')
            else:raise ValueError('UNKNOWN_PROPOSAL_BUDGET')
        except BudgetExceeded:exceeded=True
        s.api.add('ProviderAdapter.validate_structure / token precheck / propose_local budget')
        return {'budget':{'limit_exceeded':exceeded,'unvalidated_prefix_committed':bool(s.store.ledger.data['supports'])},'decision':{'search_complete':not exceeded}}
    if a=='compile_query_kind':
        from ah.formalizer.interrogatives import compile
        q=compile(p['query_kind'],handler_available=p.get('declared_handler',True));s.api.add('interrogatives.compile registered request kinds')
        return {'goal':{'compiled':q.status=='COMPILED','kinds':list(q.goal_kinds),'arbitrary_exists_fallback':q.goal_kinds==('ExistsGoal',),'kind':q.goal_kinds[0] if q.goal_kinds else None},'query':{'factual_result_materialized':bool(s.store.ledger.data['supports'])},'diagnostics':{'codes':[q.status] if q.status!='COMPILED' else []}}
    if a=='consolidate':
        from ah.formalizer.c_consolidate import ResolvedValue,SenseKind,TemporalMode,resolve_known
        v=ResolvedValue('F','fixture',1,p['known_sense'],p['known_sense'],'SUBJECT',SenseKind.KNOWN,TemporalMode.EVENT)
        r=resolve_known(v,{} if p['mapping'] is None else p['mapping'])
        s.api.add('c_consolidate.resolve_known')
        return {**s.snapshot(),'diagnostics':{'codes':[r.resolution] if r.blocked else []},'plan':{'operations':[]},'store':{**s.snapshot()['store'],'open_template_count':sum(n.get('semantic_status')=='UNLINKED' for n in s.store.ledger.data['nodes'].values())}}
    if a=='load_release':
        from ah.formalizer.resources.loader import ResourceRelease
        from ah.formalizer.resources.schemas import RESOURCE_SCHEMAS
        from tools.formalizer_v7_test_support import sign_test_release
        baseline,trust=released_fixture(s);m=deepcopy(baseline.manifest);mut=p.get('mutation');kind=p.get('mutate_kind');available=False;codes=[]
        try:
            if kind:
                resource=next(r for r in m['entries'] if r['kind']==kind);entry=resource['entries'][0]
                schema=RESOURCE_SCHEMAS[kind];required=schema.get('required',[])
                if kind=='SyntaxRules':required=schema['oneOf'][1]['required']
                if mut=='missing_required_field':entry.pop(required[0])
                elif mut=='unknown_field':entry['UNREGISTERED_FIELD']=True
                elif mut=='wrong_field_type':entry[required[0]]={'invalid_type':True}
                elif mut=='duplicate_id':resource['entries'].append(deepcopy(entry))
                elif mut=='unresolved_dependency':resource['dependency_versions']['Absent']='v1'
                elif mut=='dependency_version_mismatch':resource['dependency_versions']['R-S']='WRONG'
                else:raise ValueError('UNBOUND_RESOURCE_MUTATION:'+str(mut))
                rehash_coverage(m);tested,trust=sign_test_release(m)
                tested.validate_store(s.core.store);available=True
            else:
                r=m['signed_review_id'];sha=baseline.sha256
                if mut=='signature_bytes':r['signature']=base64.b64encode(bytes(64)).decode()
                elif mut=='signature_length':r['signature']=base64.b64encode(bytes(5)).decode()
                elif mut=='public_key_length':trust['keys']['TEST_ONLY']['public_key_b64']=base64.b64encode(bytes(5)).decode()
                elif mut=='untrusted_reviewer':r['reviewer']='FOREIGN'
                elif mut=='revoked_key':trust['keys']['TEST_ONLY']['revoked']=True
                elif mut=='naive_timestamp':r['timestamp']='2026-10-09T00:00:00'
                elif mut=='expired_review':
                    # A correctly signed old review isolates trust expiry from
                    # signature tampering. This public fixture key is TEST_ONLY.
                    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
                    from ah.formalizer.resources.signatures import review_message
                    r['timestamp']='1970-01-01T00:00:00+00:00'
                    r['signature']=base64.b64encode(Ed25519PrivateKey.from_private_bytes(bytes.fromhex('7f'*32)).sign(review_message(r))).decode()
                    trust['keys']['TEST_ONLY']['valid_from']='2000-01-01T00:00:00+00:00'
                elif mut=='reviewed_sha256_mismatch':r['reviewed_sha256']='0'*64
                elif mut=='resource_content_sha256_mismatch':m['coverage_report']['resource_content_sha256']='0'*64
                elif mut=='tampered_entry':m['entries'][0]['entries'][0]['foreign']='tampered'
                elif mut=='tampered_dependency':m['dependency_versions']['R-S']='WRONG'
                elif mut=='tampered_coverage':m['coverage_report']['corpus_id']='tampered'
                elif mut=='dependency_cycle':
                    rr={r['kind']:r for r in m['entries']};rr['R-S']['dependency_versions']={'R-V':'test-v1'};rr['R-V']['dependency_versions']={'R-S':'test-v1'};rehash_coverage(m);m,trust=release_resigned(m)
                elif mut in {'transitive_dependency_missing','role_ref_missing','capture_ref_missing','unregistered_emit_kind','emit_arity','conflicting_entries'}:
                    rr={r['kind']:r for r in m['entries']}
                    if mut=='transitive_dependency_missing':rr['R-S']['dependency_versions']={'MISSING_TRANSITIVE':'v1'}
                    elif mut=='role_ref_missing':rr['R-V']['entries'][0]['roles'][0]['role_id']='FOREIGN_ROLE'
                    elif mut=='capture_ref_missing':rr['SyntaxRules']['entries'][0]['output']['capture']='foreign'
                    elif mut=='unregistered_emit_kind':rr['SyntaxRules']['entries'][0]['output_kind']='FOREIGN_EMIT'
                    elif mut=='emit_arity':rr['SyntaxRules']['entries'][0]['output']['variants']=[]
                    elif mut=='conflicting_entries':rr['TemplateMap']['entries'].append({**rr['TemplateMap']['entries'][0],'template_ref':'foreign:T'})
                    rehash_coverage(m);m,trust=release_resigned(m)
                elif mut is not None:raise ValueError('UNBOUND_TRUST_MUTATION:'+str(mut))
                # Pinned attribution is updated only for an intentional trust
                # mutation so signature verification itself is exercised.
                if mut in {'signature_bytes','signature_length','untrusted_reviewer','naive_timestamp','expired_review'}:trust['reviews'][sha]=deepcopy(r)
                tested=ResourceRelease(m,trusted_reviews=trust);tested.validate_store(s.core.store);available=True
        except (ValueError,TypeError,KeyError) as exc:
            if str(exc).startswith('UNBOUND_'):raise
            codes=['RESOURCE_MISSING']
        s.api.add('ResourceRelease / Ed25519 verify_review / JSON Schema / dependency closure / actual TemplateMap T')
        return {'release':{'available':available,'dependency_closure_checked':available,'review_content_coverage_verified':available},'runtime':{'t0_started':False},'diagnostics':{'codes':codes}}
    raise ValueError('UNBOUND_COMPONENT_ACTION:'+a)

def release_resigned(m):
    from tools.formalizer_v7_test_support import sign_test_release
    r,trust=sign_test_release(m)
    return r.manifest,trust
