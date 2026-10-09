"""T4 and write-boundary stimuli; outcomes are read from project validators."""
from dataclasses import replace
from ah.formalizer.state import Decision,Ground,FormalizationState
from ah.formalizer.pipeline import t4
from ah.formalizer.selection_protocol import Relation,DecisionSchema
from ah.formalizer.t3_sources import CandidateSourceTrace
from ah.formalizer.store_interface import StoreOp,TerminalOutcome
from ah.formalizer.canonical_ledger import digest
from tools.formalizer_v7_test_support import journal_plan

def decision_action(s,a,p):
    if a=='resolve_control':
        state=FormalizationState.new(p['text']);values=tuple(p['variants']);d=Decision('reference','control',values,selected=values,lifecycle='PROVISIONAL')
        for value,grounds in p['value_grounds'].items():
            d.grounds.extend(Ground(g,'declared control ground',value) for g in grounds)
        state.decisions['control']=d;t4(state,None);s.api.add('pipeline.t4 per-value control/reference grounds')
        return {**s.snapshot(),'decision':{'outcome':d.outcome},'alternatives':{'entities':list(d.candidates)},'diagnostics':{'codes':[x.code for x in state.diagnostics]}}
    if a=='resolve_tuples':
        n=p['surviving_tuple_count'];ids=tuple('v'+str(i) for i in range(n));state=FormalizationState.new('declared cluster fixture')
        d=Decision('predicate_value','F',ids,selected=ids,lifecycle='PROVISIONAL',selector_outcome=('ONE_SELECTED' if n==1 else 'MULTIPLE_ADMISSIBLE' if n>1 else 'NONE_FIT') if p['search_complete'] else None)
        statuses=p['source_statuses'];d.source_traces=[CandidateSourceTrace('F','predicate_value',i+1,x,ids if x=='FOUND' else (),reason='COMPUTATION_LIMIT' if x=='BLOCKED' else 'source fixture') for i,x in enumerate(statuses)]
        if not p['source_complete']:d.source_traces[-1]=CandidateSourceTrace('F','predicate_value',5,'BLOCKED',reason='source incomplete')
        if p['each_value_has_positive_ground']:d.grounds=[Ground('R','fixture value-specific evidence',value) for value in ids]
        schema=DecisionSchema('fixture',{cid:Relation(cid,cid,2,('SUBJECT','OBJECT'),cid) for cid in ids})
        state.decisions['F|predicate_value']=d;t4(state,schema)
        s.api.add('pipeline.t4 joint candidate/value-ground/source-completeness validation')
        return {'decision':{'outcome':d.outcome,'materializable':d.outcome=='RESOLVED','source_complete':not any(x.status=='BLOCKED' for x in d.source_traces),'search_complete':bool(d.selector_outcome)},'diagnostics':{'codes':[x.code for x in state.diagnostics]}}
    if a=='non_factual_path':
        from ah.formalizer.integration_ir import IntegrationCandidateIRV2,StagedElement,can_encode_legacy_graph
        from ah.formalizer.native_plan import build_plan
        from ah.formalizer.seal import structural_seal
        st=FormalizationState.new('non-factual fixture');structural_seal(st)
        before_nodes=len(s.store.ledger.data['nodes']);before_markers=len(s.store.ledger.data['markers'])
        plan=build_plan(st,s.release,s.store)
        s.api.add('native_plan.build_plan read-only C / integration staged output')
        return {'store':{'new_factual_record_count':len(s.store.ledger.data['nodes'])-before_nodes,'new_marker_count':len(s.store.ledger.data['markers'])-before_markers},'plan':{'operation_count':len(plan[0])}}
    if a=='invalid_write_transaction':
        from tools.formalizer_v7_extended_binding import ATOM
        roots,sids,_=s.prepare('invalid',[ATOM]);ops,d,tag=s.batches['invalid'];ops=list(ops);fault=p['fault']
        # All faults are inside a real atomic draft write. A new entity before
        # the failure ensures rollback cannot appear successful by no-op.
        ops.insert(0,StoreOp('ENSURE_ENTITY',{'uid':'rollback:M','name':'rollback entity'},d.committed))
        if p.get('create_open_t_first'):
            ops.insert(1,StoreOp('ENSURE_OPEN_TEMPLATE',{'uid':'rollback:T','predicate_form':'fixture-open','semantic_status':'UNLINKED','roles':['SUBJECT']},d.committed))
        if fault=='unknown_g':ops.append(StoreOp('ENSURE_FUNCTION',{'uid':'bad:G','function_id':'FOREIGN','operands':roots},d.committed))
        elif fault=='unknown_L':ops.append(StoreOp('ENSURE_LINK',{'uid':'bad:L','link_type':'FOREIGN','source_ref':roots[0],'target_ref':roots[0]},d.committed))
        elif fault=='open_role_mismatch':
            ops.append(StoreOp('ENSURE_NODE',{'uid':'bad:N','template_ref':s.templates[('LOCATIVE',('LOCATION','THEME'))]['uid'],'actants':{'FOREIGN_ROLE':'rollback:M'},'content_key':'bad','identity_key':['bad']},d.committed))
        else:
            provenance={'source':{'kind':'OBSERVATION','source_tag':tag},'support':{'kind':'ROOT'}}
            if fault=='GOAL_RUN_ROOT':provenance['source']={'kind':'GOAL_RUN','goal_run_id':'foreign'}
            elif fault=='OBSERVATION_OR_DERIVED':provenance['support']={'kind':'DERIVED','rule_id':'OR_ELIMINATION','premise_support_refs':sids}
            ops.append(StoreOp('ADD_TIME_ASSERTION',{'assertion_id':'bad:A','target_ref':'bad:target' if fault=='conclusion_target_mismatch' else roots[0],'support_record_id':'missing' if fault=='missing_support_record' else sids[0],
                'region':{'kind':'POINT','point':5},'anchor':None,'provenance':provenance},d.committed))
        s.store.append_terminal('batch:invalid',TerminalOutcome.STALE_SUPERSEDED,'fixture invalid-write plan prepared')
        decision=journal_plan(s.store,tuple(ops),run_id=d.run_id,observation_id=tag[0],version=1,batch_hash='invalid:actual',fragments=d.committed)
        from ah.formalizer.resources.authoring import template_catalog
        before=s.store._codec.export(s.core);template_count=len(template_catalog(s.core.store)['entries']);codes=[]
        try:s.store.commit_transaction(tuple(ops),decision.marker,decision)
        except Exception as exc:codes=[str(exc).split(':',1)[0]]
        after=s.store._codec.export(s.core);s.api.add('AHStoreAdapter.commit_transaction typed registry/provenance validation and draft rollback')
        return {'diagnostics':{'codes':codes},'store':{'new_node_count':len(s.store.ledger.data['nodes']),'new_template_count':len(template_catalog(s.core.store)['entries'])-template_count,
              'new_support_count':len(s.store.ledger.data['supports']),'new_marker_count':len(s.store.ledger.data['markers']),'canonical_unchanged':digest(before)==digest(after)}}
    raise ValueError('UNBOUND_DECISION_ACTION:'+a)
