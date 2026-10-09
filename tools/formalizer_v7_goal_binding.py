"""Concrete multi-path goals and decision/retraction durable boundaries."""
from dataclasses import replace
from ah.formalizer.canonical_ledger import digest
from ah.formalizer.goal_channel import execute,recover as recover_goals,decision_for
from tools import formalizer_v7_runtime_adapter as base

GOAL_ACTIONS={'seed_derived_paths','seed_goal_path','interleave_dbn_retraction',
              'admit_with_crash','partial_commit_before_terminal','commit_partial_plan'}

def goal_action(s,a,p):
    from tools.formalizer_v7_extended_binding import ATOM,OR,NOT
    if a in {'seed_goal_path','seed_derived_paths'}:
        windows=[base.witness({'kind':'POINT','t':15})]*2
        extra={0:[base.witness({'kind':'POINT','t':16})],1:[base.witness({'kind':'POINT','t':16})]} if a=='seed_derived_paths' else None
        req,target=s.goal_request('OR_ELIMINATION',OR,[NOT],windows,run_id='GR15',extra_windows=extra)
        first=execute(s.store,req);s.aliases['N']=first['conclusion_ref'];s.active_goal=req
        if first.get('assertion_refs'):s.aliases['A_D']=first['assertion_refs'][0]
        s.aliases.update(dict(zip(['S1','S2'],req.premise_support_ids)))
        s.aliases['S_or']=req.premise_support_ids[0]
        s.aliases.update(dict(zip(['A1','A2'],req.temporal_premise_assertion_refs)))
        if a=='seed_derived_paths':
            s.aliases.update(dict(zip(['A_or15','A_not15'],req.temporal_premise_assertion_refs)))
            extra_aids=[next(a for a,r in s.store.ledger.data['assertions'].items() if r['support_record_id']==sid and r['region']['point']==16) for sid in req.premise_support_ids]
            s.aliases.update(dict(zip(['A_or16','A_not16'],extra_aids)))
            again=replace(req,goal_run_id='GR16',temporal_premise_assertion_refs=tuple(extra_aids))
            if p['variant']=='different_supports_same_node':
                _,ss,aa=s.prepare('second-premises',[OR,NOT],[base.witness({'kind':'POINT','t':16})]*2);s.commit('second-premises')
                again=replace(again,premise_support_ids=tuple(ss),temporal_premise_assertion_refs=tuple(aa))
                s.aliases.update(dict(zip(['A_or16','A_not16'],aa)))
            second=execute(s.store,again);s.aliases.update(SD15=first['support_record_id'],SD16=second['support_record_id'])
        s.api.add('goal_channel.execute independent assertion-specific proof paths')
        return s.snapshot()
    if a=='interleave_dbn_retraction':
        import ah.formalizer.goal_channel as channel
        req=replace(s.active_goal,goal_run_id='GR2');count=len(s.store.ledger.data['supports'])
        def retract():s.store.retract(req.premise_support_ids[1] if p['retract_kind']=='SUPPORT' else req.temporal_premise_assertion_refs[1],reason='DB-N race fixture')
        class Stop(Exception):pass
        if p['durable_order']=='RETRACTION_FIRST':retract()
        old=channel.finish
        if p.get('crash_after_decision'):channel.finish=lambda *args:(_ for _ in ()).throw(Stop())
        try:execute(s.store,req)
        except Stop:pass
        finally:channel.finish=old
        if p['durable_order']!='RETRACTION_FIRST':retract()
        recover_goals(s.store);d=decision_for(s.store,'GR2')
        s.api.add('goal_channel.execute DB-N serialized retraction / decision-first replay')
        return {**s.snapshot(),'goal':{'decision_outcome':d['outcome'],'decision_reason':d.get('reason'),'new_derived_support_count':len(s.store.ledger.data['supports'])-count}}
    if a in {'admit_with_crash','partial_commit_before_terminal'}:
        batch=p.get('batch','B')
        if a=='partial_commit_before_terminal':
            fragments=p.get('fragments')
            if fragments is None:
                from tools.formalizer_v7_query_binding import ensure_templates
                read={'predicate':'READ','roles':{'AGENT':{'entity':'ivan'},'THEME':{'entity':'book'}}}
                arrive={'predicate':'ARRIVE','roles':{'AGENT':{'entity':'ivan'}}}
                ensure_templates(s,[read,arrive])
                s.obs('O_X',{'operator':'NOT','operands':[arrive]},{'kind':'INTERVAL','bounds':[0,1],'semantics':'CONTINUOUS'})
                s.partial_focus_batch=batch
                s.fixture_metrics_baseline={'marker_count':len(s.store.ledger.data['markers']),'decision_count':len(s.store.ledger.data['decisions']),'applied_count':sum(t['outcome']=='APPLIED' for t in s.store._terminal_records().values())}
                fragments={'F1':read,'F2':arrive}
                s.prepare(batch,fragments,[base.witness({'kind':'INTERVAL','bounds':[0,1],'semantics':'EXISTENTIAL'})]*2)
            else:s.prepare(batch,fragments)
            p={**p,'stop':'AFTER_DECISION'}
        class Stop(Exception):pass
        old=s.store._finish_batch
        if p['stop']=='BEFORE_DECISION':return s.snapshot()
        if p['stop']!='AFTER_TERMINAL':s.store._finish_batch=lambda *args:(_ for _ in ()).throw(Stop())
        try:s.commit(batch)
        except Stop:pass
        finally:s.store._finish_batch=old
        s.api.add('AHStoreAdapter COMMIT_DECISION/marker atomic boundary before _finish_batch')
        return s.snapshot()
    if a=='commit_partial_plan':
        batch=p['batch'];frags=p['fragments']
        s.partial_focus_batch=batch
        s.fixture_metrics_baseline={'marker_count':len(s.store.ledger.data['markers']),'decision_count':len(s.store.ledger.data['decisions']),'applied_count':sum(t['outcome']=='APPLIED' for t in s.store._terminal_records().values())}
        s.prepare(batch,frags,[base.witness(p['windows'][f]) for f in frags],typed_bindings=True,write_rx=True);s.commit(batch)
        D=s.store.ledger.data['decisions'][batch];result=s.snapshot()
        result['plan']={'committed':D['committed'],'excluded':D['excluded']}
        excluded=set(D['excluded']);ops=s.batches[batch][0];ids=[op.payload.get('record_id',op.payload.get('assertion_id',op.payload.get('binding_id'))) for op in ops if set(op.fragment_refs)<=excluded and op.op_type in {'ADD_ROOT_SUPPORT','ADD_TIME_ASSERTION','SET_IDENTITY_BINDING','WRITE_COMMITTED_RX'}]
        result['store'].update(entities=sorted(alias for uid,alias in s.entities.items() if s.store.has_uid(uid)),records_for_excluded_fragments=[u for u in ids if any(u in s.store.ledger.data[k] for k in ('supports','assertions','bindings','rx_cache'))])
        return result
    raise ValueError('UNBOUND_GOAL_ACTION:'+a)
