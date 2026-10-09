"""Scope/query stimuli bound to typed AH APIs, independently of gold checks."""
from copy import deepcopy
from dataclasses import replace
from ah.formalizer.store_interface import StoreOp
from ah.formalizer.canonical_ledger import digest
from ah.formalizer.native_queries import Pattern,QueryVar,NativeQueryRoot,compile_native_queries
from ah.inference.contracts import NativeFormulaGoal,AggregateCountGoal,CountConclusion
from ah.model import ActantRole,VariableSort
from tools import formalizer_v7_runtime_adapter as base
from tools.formalizer_v7_query_binding import ensure_templates,pattern,solve,STUDENT

SCOPE_ACTIONS={'exact_attestation_query','validate_scope','association_query',
               'disabled_rule_request','compile_goal','scope_roundtrip','count_window_aggregate'}


def exact_attestation(s,p):
    f=p['asserted_open_formula'];source=p['activated_source'];fragment='open-attestation'
    key=(f['predicate'],tuple(sorted(f['roles'])));spec=s.templates[key]
    tid='fixture:open:'+digest([source,f['predicate'],sorted(f['roles'])]);spec['uid']=tid
    ops=[];node,ck,prop,pol=s.tree(f,fragment,ops)
    ops=[replace(op,payload={**op.payload,'semantic_status':'UNLINKED'}) if op.op_type=='ENSURE_NODE' else op for op in ops]
    lemma=f['predicate'].split(':',1)[-1]
    ops.insert(0,StoreOp('ENSURE_TEMPLATE',{'uid':tid,'predicate_form':lemma,'roles':sorted(spec['roles'].values()),'semantic_status':'UNLINKED'},(fragment,)))
    tag=['oracle:'+source,1];sid='fixture:open-support:'+digest([source,node])
    ops.extend([StoreOp('ADD_ROOT_SUPPORT',{'record_id':sid,'conclusion_ref':node,'kind':'ROOT','ground_type':'O','source_tag':tag},(fragment,)),
                StoreOp('DECLARE_FRAGMENT',{'fragment_id':fragment,'node_ref':node,'content_key':ck,'proposition':prop,'polarity':pol,'source_tag':tag},(fragment,))])
    from tools.formalizer_v7_test_support import journal_plan
    dec=journal_plan(s.store,tuple(ops),run_id='exact:'+source,observation_id=tag[0],version=1,batch_hash=source,fragments=[fragment])
    s.batches[source]=(tuple(ops),dec,tag);s.commit(source);s.sources[source]=tag
    binding=p['fixture_identity_bindings'];roles=[]
    for role,value in f['roles'].items():
        explicit=binding['query:'+value['entity']]
        roles.append((ActantRole(spec['roles'][role]),s.core.ref('fixture:M:'+digest(explicit))))
    change=p['change'];anchor=lemma;source_scope=(tag[0],)
    if change=='verb':anchor='доставить'
    elif change=='role':roles=[(roles[0][0],roles[1][1]),(roles[1][0],roles[0][1])]
    elif change=='surface_as_agent':
        raw=s.core.add_abstract_symbol({'курьер:surface'});roles[0]=(roles[0][0],s.core.ref(raw.uid))
    elif change=='source_scope':source_scope=('oracle:other-source',)
    elif change=='dead_proof':s.store.retract(sid,reason='exact-attestation source stale')
    elif change not in {'none','scope','absolute_query_token_position'}:raise ValueError('UNSUPPORTED_ATTESTATION_MUTATION:'+change)
    target=Pattern(lexical_anchor=anchor,actants=tuple(roles))
    if change=='scope':target=Pattern('NOT',(target,))
    query_token_start=None
    if change=='absolute_query_token_position':
        from ah.formalizer.pipeline import t0
        from ah.agent.interaction_context import InteractionContext
        # A real shifted query span enters the same native query compiler.
        # Entity references are the explicitly declared fixture bindings.
        text='Уточняю: курьер '+lemma+' письмо?';state=t0(text)
        evidence=next(e for e in state.evidence if e.span.casefold()==lemma)
        query_token_start=evidence.start
        root=NativeQueryRoot({'frame_ref':'shifted-query'},{'shifted-query':{
            'template_ref':None,'roles':[(r.value,{'mention':binding_ref,'entity_ref':v.uid})
                for (r,v),binding_ref in zip(roles,sorted(binding))],
            'lexical_anchor':evidence.span.casefold(),'temporal':None}},None,{'mode':'FORMULA'},
            source_scope=source_scope,owner_frame_ref='shifted-query')
        compiled=compile_native_queries(s.core,(root,),InteractionContext(),(s.core.ref(node),))[0]
        if compiled.goal is None:raise ValueError('SHIFTED_ATTESTATION_QUERY_NOT_COMPILED:'+str(compiled.diagnostics))
        target=compiled.goal.goal.target.pattern
        s.api.add('pipeline.t0 shifted raw query span / native_queries.compile_native_queries')
    before_supports=set(s.store.ledger.data['supports']);before_markers=set(s.store.ledger.data['markers'])
    workspace=(s.core.ref(node),)
    answer,_=solve(s,NativeFormulaGoal(target,workspace_refs=workspace,source_scope=source_scope),workspace=workspace)
    new_supports=[v for k,v in s.store.ledger.data['supports'].items() if k not in before_supports and v['kind']=='DERIVED']
    s.api.add('native_queries exact-attestation workspace / explicit entity binding / source-scope projection')
    return {**s.snapshot(),'answer':{'status':{'PROVED':'YES','DISPROVED':'NO','UNKNOWN':'UNKNOWN'}[answer.status.value],
                                    'semantic_status':s.store.ledger.data['nodes'][node]['semantic_status']},
            'query':{'new_derived_supports':len(new_supports),'new_markers':len(set(s.store.ledger.data['markers'])-before_markers)},
            'aliases':[],'query_token_start':query_token_start,'diagnostics':{'codes':list(answer.diagnostics)}}


def invalid_scope(s,p):
    """Malformed closed formulas exercise the actual transaction boundary.

    An accepted malformed scope is exported as valid=True, allowing the
    independent oracle to flag a production validation defect.
    """
    student=deepcopy(STUDENT);base_formula={'operator':'FORALL','operands':[{'bound_var':'x'},student]}
    mutation=p['mutation']
    if mutation=='free_variable':formula=student
    elif mutation=='double_binder':
        formula={'operator':'FORALL','operands':[{'bound_var':'x'},base_formula]}
    elif mutation=='capture_after_substitution':
        from ah.formalizer.goal_forms import substitute
        # Instantiating outer x with a free y must rename the inner y binder;
        # the remaining free y then cannot be asserted as a closed fact.
        form={'function_id':'EXISTS','operands':[{'bound_var':2,'sort':'ENTITY'},
            {'template_ref':'fixture-symbolic-KNOW','actants':{'SUBJECT':{'bound_var':1,'sort':'ENTITY'},'OBJECT':{'bound_var':2,'sort':'ENTITY'}}}]}
        result=substitute(form,{1:{'bound_var':2,'sort':'ENTITY'}})
        binder=result['operands'][0]['bound_var'];args=result['operands'][1]['actants']
        formula={'operator':'EXISTS','operands':[{'bound_var':'v'+str(binder)},
            {'predicate':'KNOW','roles':{'AGENT':{'bound_var':'v'+str(args['SUBJECT']['bound_var'])},'THEME':{'bound_var':'v'+str(args['OBJECT']['bound_var'])}}}]}
        ensure_templates(s,[formula]);s.api.add('goal_forms.substitute capture-avoiding alpha rename / final factual scope validation')
    elif mutation=='three_slot_FORALL':formula={'operator':'FORALL','operands':[{'bound_var':'x'},student,student]}
    elif mutation=='quantifier_scope_first_wins':
        from tools.formalizer_v7_decision_binding import decision_action
        result=decision_action(s,'resolve_control',{'text':'declared competing scope fixture','variants':['FORALL_NOT','NOT_FORALL'],
                                                   'value_grounds':{'FORALL_NOT':['R'],'NOT_FORALL':['R']}})
        return {'scope':{'valid':result['decision']['outcome']=='RESOLVED'},'store':{'new_asserted_fact_count':len(s.store.ledger.f_visible())},'decision':result['decision']}
    else:formula=base_formula
    ensure_templates(s,[student]);before=len(s.store.ledger.f_visible());codes=[]
    try:
        fragment='invalid-scope:F0';ops=[];uid,ck,prop,pol=s.tree(formula,fragment,ops)
        if mutation=='string_restriction':
            ops=[replace(op,payload={**op.payload,'operands':[op.payload['operands'][0],'raw restriction string']})
                      if op.op_type=='ENSURE_FUNCTION' and op.payload['function_id']=='FORALL' else op for op in ops]
        tag=['oracle:invalid-scope',1];sid='scope-support'
        ops.extend([StoreOp('ADD_ROOT_SUPPORT',{'record_id':sid,'conclusion_ref':uid,'kind':'ROOT','ground_type':'O','source_tag':tag},(fragment,)),
                    StoreOp('DECLARE_FRAGMENT',{'fragment_id':fragment,'node_ref':uid,'content_key':ck,'proposition':prop,'polarity':pol,'source_tag':tag},(fragment,))])
        from tools.formalizer_v7_test_support import journal_plan
        decision=journal_plan(s.store,tuple(ops),run_id='invalid:scope',observation_id=tag[0],version=1,batch_hash='invalid-scope',fragments=[fragment])
        s.batches['invalid-scope']=(tuple(ops),decision,tag);s.commit('invalid-scope')
        valid=True
    except (ValueError,TypeError,KeyError) as exc:valid=False;codes=[str(exc)]
    s.api.add('AHStoreAdapter.commit_transaction / typed scope write-boundary validation')
    return {'scope':{'valid':valid},'store':{'new_asserted_fact_count':len(s.store.ledger.f_visible())-before},'diagnostics':{'codes':codes}}


def scope_action(s,a,p):
    if a=='exact_attestation_query':return exact_attestation(s,p)
    if a=='validate_scope':return invalid_scope(s,p)
    if a=='compile_goal':
        from ah.agent.interaction_context import InteractionContext
        formulas=[{'predicate':name,'roles':{'AGENT':{'bound_var':'who'}}} for name in p['activated_templates']]
        ensure_templates(s,formulas+[p['unactivated_fact']]);s.obs('unactivated',p['unactivated_fact'])
        roots=[]
        for name in p['activated_templates']:
            spec=s.templates[(name,('AGENT',))]
            roots.append(NativeQueryRoot({'frame_ref':'query'}, {'query':{'template_ref':spec['uid'],'roles':[],
                'lexical_anchor':None,'temporal':None}},None,{'mode':'WH','requested_roles':['SUBJECT']},owner_frame_ref='query'))
        # Count only forbidden global-enumeration APIs, without suppressing them.
        from unittest.mock import patch
        scans=[]
        def observe(original):
            def call(*args,**kwargs):scans.append(True);return original(*args,**kwargs)
            return call
        with patch.object(s.core.store,'elements',observe(s.core.store.elements)) if hasattr(s.core.store,'elements') else _null_context():
            results=compile_native_queries(s.core,roots,InteractionContext())
        goals=[r.goal.goal.target for r in results if r.goal is not None]
        refs={g.template_ref.uid for g in goals if hasattr(g,'template_ref')}
        sources=[name for (name,roles),spec in s.templates.items() if spec['uid'] in refs]
        s.api.add('native_queries.compile_native_queries / declared activated-template roots')
        return {'goal':{'kind':type(goals[0]).__name__ if goals else None,'template_sources':sources},'reads':{'global_scan_count':len(scans)}}
    if a=='association_query':
        from ah.association.coordinator import AssociationCoordinator
        from ah.association.contracts import AssociationGoal,AssociationBudget
        from ah.ignition import IgnitionEngine
        from ah.config import IgnitionSettings,WorkspaceSettings
        left,_,_=s.obs('association-left',p['left']);right,_,_=s.obs('association-right',p['right'])
        s.core.add_link(p['relation_id'],s.core.ref(left),s.core.ref(right),1.0)
        result=AssociationCoordinator(s.core,IgnitionEngine(s.core,IgnitionSettings(),WorkspaceSettings())).solve(
            AssociationGoal(s.core.ref(left),s.core.ref(right)),budget=AssociationBudget(max_ticks=4))
        s.api.add('AssociationCoordinator.solve / independent associative goal channel')
        return {**s.snapshot(),'answer':{'kind':'ASSOCIATIVE' if type(result).__name__=='AssociationOutcome' else type(result).__name__,
                                       'is_entailment':hasattr(result,'proof_support'),'status':result.status.value}}
    if a=='scope_roundtrip':
        from ah.formalizer.goal_forms import canonical,formula
        tree=p['tree'];ensure_templates(s,[tree]);uid,_,_=s.obs('scope-roundtrip',tree)
        before=canonical(formula(s.store.ledger,uid,[10000]))
        from ah.formalizer.ah_adapter import AHStoreAdapter
        from ah.core.journal import JournalChannel
        encoded=s.store._codec.export(s.core);s.core=s.store._codec.import_payload(deepcopy(encoded),uid_generator=s.core.uid).core
        s.store=AHStoreAdapter(s.core.store,JournalChannel(s.path),s.core)
        after=canonical(formula(s.store.ledger,uid,[10000]));binders=[];free=[]
        def walk(node):
            if not isinstance(node,dict):return
            if 'bound_var' in node and isinstance(node['bound_var'],(tuple,list)):free.append(node['bound_var'][1])
            if node.get('function_id') in {'FORALL','EXISTS'}:
                value=node['operands'][0]['bound_var'];binders.append('x'+str(value))
            for val in node.values():
                if isinstance(val,list):
                    for child in val:walk(child)
                elif isinstance(val,dict):walk(val)
        walk(after);s.api.add('JsonPersistence export/import / goal_forms.canonical alpha normalization')
        return {'scope':{'roundtrip_equal':before==after,'binder_ids':binders,'free_variables':free}}
    if a=='count_window_aggregate':
        f=p['asserted_scope'];ensure_templates(s,[f]);s.obs('numeric-window',f,p['witness'])
        body=f['operands'][1];var=f['operands'][0]['bound_var'];pat=pattern(s,body,var)
        answer,_=solve(s,AggregateCountGoal(pat,'ENTITY',tuple(p['witness']['bounds']),var))
        c=answer.conclusion;s.api.add('aggregate_count.solve_aggregate / no implicit aggregate domain')
        return {'answer':{'exact_count':c.exact_count if isinstance(c,CountConclusion) else None,
                          'domain_complete':isinstance(c,CountConclusion) and c.exact_count is not None},
                'store':{'fictitious_entity_count':len(s.entities)},'diagnostics':{'codes':list(answer.diagnostics)}}
    if a=='disabled_rule_request':
        atom={'predicate':'ARRIVE','roles':{'AGENT':{'entity':'petr'}}};ensure_templates(s,[atom])
        s.action('materialize_attitude_argument',{'source':'rule-parent','attitude':'QUOTED','holder':'ivan','content':atom})
        before=set(s.store.ledger.f_visible());old_supports=set(s.store.ledger.data['supports'])
        answer,_=solve(s,NativeFormulaGoal(pattern(s,atom)))
        fresh=[v for k,v in s.store.ledger.data['supports'].items() if k not in old_supports]
        rule_ids={v.get('rule_id') for v in fresh}|{getattr(v,'rule_id',None) for v in answer.proof_support}
        s.api.add('InferenceEngine.solve / registered rules only / non-factive attitude operand')
        return {'inference':{'rule_fired':p['rule'] in rule_ids,'unsupported_truth_count':len(set(s.store.ledger.f_visible())-before)},
                'diagnostics':{'codes':list(answer.diagnostics)}}
    raise ValueError('UNBOUND_SCOPE_ACTION:'+a)


def _null_context():
    from contextlib import nullcontext
    return nullcontext()
