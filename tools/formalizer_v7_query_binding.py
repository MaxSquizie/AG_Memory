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
    if not supports_live or variant in {'STALE_SUPPORT','DEAD_COMPLETENESS_SUPPORT'}:s.store.retract(sid,reason='certificate evidence stale')
    return release

def solve(s,goal,limit=5000,workspace=None):
    before=len(s.store.ledger.data['supports']);engine=InferenceEngine(s.core,InferenceSettings(max_expanded_states=limit))
    answer=engine.solve(goal,workspace_refs=tuple(s.core.ref(u) for u in s.store.ledger.f_visible()) if workspace is None else tuple(workspace))
    s.api.add('InferenceEngine.solve / NativeBindingGoal / whole-pattern proof / FormulaDomainCertificate')
    return answer,len(s.store.ledger.data['supports'])-before

def binding_budget(s,p):
    """Observe the real Cartesian search, including its 1024-combination cap.

    Two independently populated roles avoid the separate per-variable cap.
    The observer delegates every proof to the unmodified production function.
    """
    from unittest.mock import patch
    from ah.formalizer import native_queries
    required=p['required_combinations']; limit=p['limit']
    if limit!=1024 or required<1:raise ValueError('UNSUPPORTED_ENUMERATION_LIMIT')
    factors=min(((n,required//n) for n in range(1,required+1)
                  if required%n==0 and n<=1024 and required//n<=1024),key=lambda pair:sum(pair),default=None)
    if factors is None:raise ValueError('ENUMERATION_FIXTURE_DOMAIN_TOO_LARGE')
    left={'predicate':'STUDENT','roles':{'THEME':{'bound_var':'left'}}}
    right={'predicate':'ARRIVE','roles':{'AGENT':{'bound_var':'right'}}}
    ensure_templates(s,[left,right]);forms=[]
    for f,var,n in [(left,'left',factors[0]),(right,'right',factors[1])]:
        forms.extend(subst(f,var,var+':'+str(i)) for i in range(n))
    s.prepare('enumeration-fixture',forms);s.commit('enumeration-fixture')
    pat=Pattern('AND',(pattern(s,left,'left'),pattern(s,right,'right')))
    goal=NativeBindingGoal(pat,('left','right'),mode='WH');visited=[]
    original=native_queries.solve_native_goal
    def observe(engine,actual_goal,*args,**kwargs):
        if isinstance(actual_goal,NativeFormulaGoal) and kwargs.get('_depth')==1:
            visited.append(actual_goal.pattern)
        return original(engine,actual_goal,*args,**kwargs)
    with patch.object(native_queries,'solve_native_goal',observe):
        answer,new=solve(s,goal,10000000)
    complete='COMPUTATION_LIMIT' not in answer.diagnostics
    s.api.add('query_bindings.solve_bindings Cartesian enumeration / delegated proof-call observer')
    return {'query':{'search_complete':complete,'combinations_visited':len(visited),
                     'domain_certificate_inferred_from_enumeration':bool(getattr(s.store,'resource_release',None) and s.store.resource_release.entries('FormulaDomainCertificate'))},
            'answer':{'status':answer.status.value},'diagnostics':{'codes':list(answer.diagnostics)}}

def certificate_mutation(s,p):
    """Bind each mutation to its own changed typed query input."""
    change=p['change'];before=STUDENT;after=deepcopy(before);window=None
    ensure_templates(s,[STUDENT,ARRIVE]);query_var='x'
    if change=='restriction':after={'operator':'AND','operands':[STUDENT,ARRIVE]}
    elif change=='nested_scope':after={'operator':'NOT','operands':[STUDENT]}
    elif change=='count_variable':query_var='y';after=subst_var(before,'x','y')
    elif change=='time_window':window=[0,1]
    s.obs('certificate-witness',subst(STUDENT,'x','e0'),{'kind':'INTERVAL','bounds':[0,1],'semantics':'CONTINUOUS'} if window else None)
    release=certify(s,pattern(s,before,'x'),'x',window,'VALID')
    source_scope=()
    if change=='source_scope':source_scope=('oracle:foreign-source',)
    if change=='dead_support':
        cert=release.entries('FormulaDomainCertificate')[0]
        s.store.retract(cert['completeness_evidence'][0],reason='explicit certificate evidence retraction')
    actual_window=[2,3] if change=='time_window' else window
    goal=NativeBindingGoal(pattern(s,after,query_var),(query_var,),mode='COUNT',
                          temporal_window=tuple(actual_window) if actual_window else None,
                          resource_snapshot=release.sha256,source_scope=source_scope)
    answer,_=solve(s,goal);c=answer.conclusion
    complete=isinstance(c,CountConclusion) and c.exact_count is not None
    return {'certificate':{'valid':complete},'answer':{'exact_count':c.exact_count if isinstance(c,CountConclusion) else None,'domain_complete':complete},
            'diagnostics':{'codes':list(answer.diagnostics)}}

def subst_var(f,old,new):
    if isinstance(f,dict):return {'bound_var':new} if f=={'bound_var':old} else {k:subst_var(v,old,new) for k,v in f.items()}
    if isinstance(f,list):return [subst_var(v,old,new) for v in f]
    return f

def query_action(s,a,p):
    if a=='validate_formula_certificate':
        if 'renaming' in p:
            old,new=next(iter(p['renaming'].items()));gap='count_gap'
            body={'operator':'FORALL','operands':[{'bound_var':old},{'operator':'AND','operands':[
                {'predicate':'STUDENT','roles':{'THEME':{'bound_var':old}}},
                {'predicate':'ARRIVE','roles':{'AGENT':{'bound_var':gap}}}]}]}
            ensure_templates(s,[body]);before=pattern(s,body,gap);after=pattern(s,subst_var(body,old,new),gap)
            release=certify(s,before,gap,None,'VALID')
            answer,_=solve(s,NativeBindingGoal(after,(gap,),mode='COUNT',resource_snapshot=release.sha256))
            s.api.add('query_bindings.pattern_signature alpha-renamed scoped BoundVar / fixed count gap certificate')
            return {'signature':{'alpha_equal':pattern_signature(before)==pattern_signature(after)},'certificate':{'valid':isinstance(answer.conclusion,CountConclusion) and answer.conclusion.exact_count is not None}}
        return certificate_mutation(s,p)
    if a=='frame_temporal_mode':
        # This old symbolic action describes resolved modes rather than a
        # release entry. Export the actual R-V mode lookup, not guessed tense.
        from tools.formalizer_v7_native_binding import fixture
        r,_=fixture(s.core,'known');modes={e['sense_id']:e.get('temporal_mode_hint',e.get('state_class')) for e in r.entries('R-V')}
        mapping={e['sense_id']:e['template_ref'] for e in r.entries('TemplateMap')};refs=[mapping[x['sense']] for x in p['frames']]
        s.api.add('ResourceRelease.entries R-V temporal_mode_hint / actual TemplateMap refs')
        return {'frames':{'modes':[modes.get(x['sense']) for x in p['frames']],'merged_across_modes':len(refs)!=len(set(refs))},'aliases':[]}
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
                              resource_snapshot=release.sha256 if release else None,
                              expected_count=p.get('threshold'),comparison={'EXACT':'EXACTLY_N','AT_LEAST':'AT_LEAST_N','AT_MOST':'AT_MOST_N'}.get(p.get('comparison','EXACT'),'EXACTLY_N'))
        answer,new=solve(s,goal);c=answer.conclusion
        return {'answer':{'status':{'PROVED':'YES','DISPROVED':'NO','UNKNOWN':'UNKNOWN'}[answer.status.value],'lower_bound':c.lower_bound if isinstance(c,CountConclusion) else None,
            'exact_count':c.exact_count if isinstance(c,CountConclusion) else None,
            'domain_complete':isinstance(c,CountConclusion) and c.exact_count is not None},
            'diagnostics':{'codes':list(answer.diagnostics)},'query':{'factual_result_materialized':new>0},
            'store':{'fictitious_entity_count':sum(e not in set(entities)|{'book','table'} for e in s.entities.values())}}
    if a=='compound_binding_budget':
        return binding_budget(s,p)
    if a in {'compound_binding_query','compound_binding_budget'}:
        var=p['runtime_variable'];left={'predicate':'STUDENT','roles':{'THEME':{'bound_var':var}}}
        right={'predicate':'ARRIVE','roles':{'AGENT':{'bound_var':var}}};scope=p['scope']
        body={'operator':scope,'operands':[left,right]} if scope in {'AND','OR','XOR','IMPLIES'} else {'operator':scope,'operands':[left]}
        if scope in {'FORALL','EXISTS'}:body={'operator':scope,'operands':[{'bound_var':'inner'},right]}
        if scope=='QUOTED':
            # The complete quoted scope is the asserted report, not the
            # unasserted content proposition. Query its argument without
            # introducing a truth support for that content.
            body={'predicate':'SAY','roles':{'AGENT':{'entity':'ivan'},'CONTENT':right}}
        ensure_templates(s,[body,left,right]);good=set(p.get('whole_pattern_proof_entities',[]))
        for i,e in enumerate(p.get('atomic_body_match_entities',[])):
            # Indexed atomic matches are structural candidates, not witnesses
            # of their own truth or of the complete requested scope.
            s.action('materialize_attitude_argument',{'source':'candidate:'+str(i),
                'attitude':'QUOTED','holder':'ivan','content':subst(left,var,e)})
        for i,e in enumerate(good):
            concrete=subst(body,var,e)
            if scope=='QUOTED':
                content=subst(right,var,e)
                s.action('materialize_attitude_argument',{'source':'quoted:'+str(i),'attitude':'QUOTED','holder':'ivan','content':content})
                if p.get('quoted_content_independent_assertion'):
                    s.obs('independent-content:'+str(i),content)
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
