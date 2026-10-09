"""Fixture formulas become actual AH inputs; answers come from InferenceEngine."""
from copy import deepcopy
from dataclasses import replace
from ah.config import InferenceSettings
from ah.inference.engine import InferenceEngine
from ah.inference.contracts import NativeBindingGoal, NativeFormulaGoal,CountConclusion,NativeBindingsConclusion
from ah.formalizer.native_queries import Pattern,QueryVar
from ah.formalizer.query_bindings import pattern_signature
from ah.formalizer.canonical_ledger import digest
from ah.model import ActantRole,VariableSort,BoundVar,CountLiteral
from tools.formalizer_v7_test_support import sign_test_release
from tools.formalizer_v7_component_binding import rehash_coverage
from tools import formalizer_v7_runtime_adapter as base

QUERY_ACTIONS={'count_query','count_from_asserted_bounds','compound_binding_query',
              'compound_binding_budget','modus_ponens_query','frame_temporal_mode','validate_formula_certificate'}
STUDENT={'predicate':'STUDENT','roles':{'THEME':{'bound_var':'x'}}}
ARRIVE={'predicate':'ARRIVE','roles':{'AGENT':{'bound_var':'x'}}}

def ensure_templates(s,formulas):
    # Independent language fixture, registered against the actual AH store.
    specs={}
    def visit(f):
        if isinstance(f,dict):
            if 'predicate' in f:specs[(f['predicate'],tuple(sorted(f['roles'])))]=f
            for v in f.values():visit(v)
        elif isinstance(f,list):
            for v in f:visit(v)
    visit(formulas)
    from tools.formalizer_v7_test_support import test_release,role
    senses=[]
    for (pred,roles),f in specs.items():
        if (pred,roles) in s.templates:continue
        mapped=[base.ROLE_MAP[r] for r in roles];sid=pred+':'+digest(roles)[:12]
        s.templates[(pred,roles)]={'sense_id':sid,'uid':'fixture:T:'+sid,'roles':dict(zip(roles,mapped))}
        senses.append((sid,pred.casefold(),'VERB',[role(r) for r in mapped],'STATE' if pred=='STUDENT' else 'EVENT'))
    if senses:test_release(s.core,senses)

def subst(f,var,value):
    if isinstance(f,dict):return {'entity':value} if f=={'bound_var':var} else {k:subst(v,var,value) for k,v in f.items()}
    if isinstance(f,list):return [subst(v,var,value) for v in f]
    return f

def pattern(s,f,query_var='x'):
    if 'bound_var' in f:
        return QueryVar(query_var,VariableSort.ENTITY) if f['bound_var']==query_var else BoundVar(s.variables.setdefault(f['bound_var'],len(s.variables)+1),VariableSort.ENTITY)
    if 'entity' in f:
        uid='fixture:M:'+digest(f['entity'])
        return s.core.ref(uid)
    if 'count_literal' in f:return CountLiteral(f['count_literal'])
    if 'operator' in f:return Pattern(f['operator'],tuple(pattern(s,v,query_var) for v in f['operands']))
    spec=s.templates[(f['predicate'],tuple(sorted(f['roles'])))];return Pattern(template_ref=spec['uid'],actants=tuple((ActantRole(spec['roles'][r]),pattern(s,v,query_var)) for r,v in sorted(f['roles'].items())))

def certify(s,pat,var,win,variant,closure='ENUMERATED',supports_live=True,body_matches=True):
    _,sid,_=s.obs('domain-evidence',{'predicate':'LOCATIVE','roles':{'THEME':{'entity':'book'},'LOCATION':{'entity':'table'}}})
    m=deepcopy(s.release.manifest)
    sig=pattern_signature(pat) if body_matches and variant!='WRONG_BODY' else digest('foreign body')
    cert={'domain_id':'fixture-domain','pattern_signature':sig,'count_variable':var,'request_window':win,
          'completeness_evidence':[sid],'version':'test-v1','closure_mode':closure}
    if variant=='WRONG_VARIABLE':cert['count_variable']='foreign-variable'
    if variant=='WRONG_WINDOW':cert['request_window']=[999,1000]
    m['entries'].append({'kind':'FormulaDomainCertificate','version':'test-v1','schema_version':'v7','dependency_versions':{},'entries':[cert]})
    m['dependency_versions']['FormulaDomainCertificate']='test-v1';rehash_coverage(m)
    release,_=sign_test_release(m);release.validate_store(s.core.store);s.store.resource_release=release
    if not supports_live or variant=='STALE_SUPPORT':s.store.retract(sid,reason='certificate evidence stale')
    return release

def solve(s,goal,limit=5000):
    before=len(s.store.ledger.data['supports']);engine=InferenceEngine(s.core,InferenceSettings(max_expanded_states=limit))
    answer=engine.solve(goal,workspace_refs=tuple(s.core.ref(u) for u in s.store.ledger.f_visible()))
    s.api.add('InferenceEngine.solve / NativeBindingGoal / whole-pattern proof / FormulaDomainCertificate')
    return answer,len(s.store.ledger.data['supports'])-before

def query_action(s,a,p):
    if a=='validate_formula_certificate':
        change=p['change'];variant={'count_variable':'WRONG_VARIABLE','window':'WRONG_WINDOW','completeness_evidence':'STALE_SUPPORT','source_snapshot':'NONE'}.get(change,'WRONG_BODY')
        result=query_action(s,'count_query',{'body':STUDENT,'count_variable':'x','certificate':variant,'window':None,'witness_entities':['e0']})
        result['certificate']={'valid':result['answer']['domain_complete']}
        return result
    if a=='frame_temporal_mode':
        # This old symbolic action describes resolved modes rather than a
        # release entry. Export the actual R-V mode lookup, not guessed tense.
        from tools.formalizer_v7_native_binding import fixture
        r,_=fixture(s.core,'known');modes={e['sense_id']:e.get('temporal_mode_hint',e.get('state_class')) for e in r.entries('R-V')}
        return {'frames':{'temporal_modes':[modes.get(x['sense']) for x in p['frames']]},'aliases':[]}
    if a in {'count_query','count_from_asserted_bounds'}:
        body=p.get('body',STUDENT);var=p.get('count_variable','x');ensure_templates(s,[body,STUDENT])
        entities=p.get('witness_entities',p.get('counted_distinct_entities',[]));window=p.get('window')
        for i,e in enumerate(entities):s.obs('count-witness'+str(i),subst(body,var,e),window)
        if a=='count_from_asserted_bounds':
            bound_body=body if p['bounds_body_matches'] else {'predicate':'ARRIVE','roles':{'AGENT':{'bound_var':var}}};ensure_templates(s,[bound_body])
            for name,value in [('AT_LEAST_N',p['asserted_lower']),('AT_MOST_N',p['asserted_upper'])]:
                uid,sid,_=s.obs('bound:'+name,{'operator':name,'operands':[{'bound_var':var},bound_body,{'count_literal':value}]})
                if not p['bounds_proof_live']:s.store.retract(sid,reason='bounds proof stale')
        pat=pattern(s,body,var);variant=p.get('certificate','VALID' if p.get('certificate_present') else 'NONE')
        release=None
        if variant!='NONE':release=certify(s,pat,var,window,variant,p.get('closure_mode','ENUMERATED'),p.get('certificate_supports_live',True),p.get('certificate_body_matches',True))
        goal=NativeBindingGoal(pat,(var,),mode='COUNT',temporal_window=tuple(window) if window else None,
                              resource_snapshot=release.sha256 if release else None)
        answer,new=solve(s,goal);c=answer.conclusion
        return {'answer':{'lower_bound':c.lower_bound if isinstance(c,CountConclusion) else None,
            'exact_count':c.exact_count if isinstance(c,CountConclusion) else None,
            'domain_complete':isinstance(c,CountConclusion) and c.exact_count is not None},
            'diagnostics':{'codes':list(answer.diagnostics)},'query':{'factual_result_materialized':new>0},
            'store':{'fictitious_entity_count':sum(e not in set(entities)|{'book','table'} for e in s.entities.values())}}
    if a=='compound_binding_budget':
        # An actual tiny inference budget over a populated indexed search.
        entities=['e'+str(i) for i in range(p.get('candidate_count',32))];p={**p,'candidate_bindings':entities,'atomic_body_match_entities':entities,'whole_pattern_proof_entities':entities,'scope':'AND','runtime_variable':'q'}
    if a in {'compound_binding_query','compound_binding_budget'}:
        var=p['runtime_variable'];left={'predicate':'STUDENT','roles':{'THEME':{'bound_var':var}}}
        right={'predicate':'ARRIVE','roles':{'AGENT':{'bound_var':var}}};scope=p['scope']
        body={'operator':scope,'operands':[left,right]} if scope in {'AND','OR','XOR','IMPLIES'} else {'operator':scope,'operands':[left]}
        if scope in {'FORALL','EXISTS'}:body={'operator':scope,'operands':[{'bound_var':'inner'},right]}
        if scope=='QUOTED':body=right
        ensure_templates(s,[body,left,right]);good=set(p.get('whole_pattern_proof_entities',[]))
        for i,e in enumerate(p.get('atomic_body_match_entities',[])):
            s.obs('candidate:'+str(i),subst(left,var,e))
        for i,e in enumerate(good):
            concrete=subst(body,var,e)
            if scope=='QUOTED' and not p.get('quoted_content_independent_assertion'):
                s.action('materialize_attitude_argument',{'source':'quoted:'+str(i),'attitude':'QUOTED','holder':'ivan','content':concrete})
            else:s.obs('whole:'+str(i),concrete)
        pat=pattern(s,body,var);goal=NativeBindingGoal(pat,(var,),mode=p.get('mode','WH'))
        answer,new=solve(s,goal,1 if a=='compound_binding_budget' else 5000);c=answer.conclusion
        bindings=[s.entities[r[0].uid] for r in c.rows] if isinstance(c,NativeBindingsConclusion) else []
        return {'answer':{'binding_entities':bindings,'status':answer.status.value},'diagnostics':{'codes':list(answer.diagnostics)},
            'query':{'variable_has_ah_uid':s.core.store.has_uid(var),'chosen_branch_materialized':new>0,'new_root_supports':new,'factual_result_materialized':new>0}}
    if a=='modus_ponens_query':
        implication=p['implication'];left,right=implication['operands'];target=p['target']
        ensure_templates(s,[implication,p['asserted'],target])
        s.obs('O_implication',implication)
        s.obs('O_antecedent' if p['asserted']==left else 'O_consequent',p['asserted'])
        s.active_query_target=s.formulas[digest(target)]
        answer,new=solve(s,NativeFormulaGoal(pattern(s,target)))
        proofs=[q for q in s.store.ledger.data['supports'].values() if q['kind']=='DERIVED']
        return {'answer':{'status':{'PROVED':'YES','DISPROVED':'NO','UNKNOWN':'UNKNOWN'}[answer.status.value]},'query':{'new_root_supports':new},
                'derived':{'support_count':len(proofs),'premise_count':len(proofs[0]['premise_support_refs']) if proofs else 0}}
    raise ValueError('UNBOUND_QUERY_ACTION:'+a)
