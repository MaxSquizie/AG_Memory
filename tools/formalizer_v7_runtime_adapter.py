"""Concrete component/WAL bindings. No gold checks are received or consulted.

The payload formula is an input fixture; observations are decoded from actual AH
objects. This is not a raw-text front-end adapter and does not claim gate PASS.
"""
from copy import deepcopy
from dataclasses import asdict,replace
from pathlib import Path
import json,tempfile,hashlib,sys
from ah.core.operations import AHCore
from ah.core.store import AHStore
from ah.core.journal import JournalChannel
from ah.model.types import ActantRole,Domain,Hypernode,FunctionSymbol
from ah.model.operands import BoundVar,CountLiteral,TimeLiteral
from ah.model.types import Ref
from ah.formalizer.ah_adapter import AHStoreAdapter
from ah.formalizer.canonical_ledger import digest,region_data,region,simultaneity_result
from ah.formalizer.temporal_license import or_elimination_license,forall_inst_license
from ah.formalizer.store_interface import StoreOp
from ah.formalizer.graph_ops import ensure_entity,ensure_node,native_operand
from ah.formalizer.goal_executor import GoalRequest
from ah.formalizer.goal_channel import execute,validate_goal
from ah.formalizer.t5_batch import FragmentT5Input,evaluate_fragment
from tools.formalizer_v7_test_support import test_release,role,journal_plan

SUPPORTED={'query_time','derive_or','derive_forall','check_simultaneity','nary_or_query','commit_grounded_fragment','journal_batch','journal_batches','crash','recover','execute_head_calls','admit_batch','function_identity','numeric_scope_literal','validate_selector_reply','repeat_goal'}
ROLE_MAP={'AGENT':'SUBJECT','THEME':'OBJECT','CONTENT':'OBJECT','EXPERIENCER':'EXPERIENCER','LOCATION':'LOCATION','DESTINATION':'LOCATION','RECIPIENT':'RECIPIENT','ADDRESSEE':'RECIPIENT','SOURCE':'SOURCE','LEFT':'SUBJECT','RIGHT':'OBJECT'}
RESOURCE_ARTIFACT_DIR=None


def witness(raw):
    if raw is None:return None
    if raw['kind']=='POINT':return region_data(region({'kind':'POINT','point':raw['t']}))
    lo,hi=raw['bounds'];return region_data(region({'kind':raw['semantics'],'lo':lo if isinstance(lo,(int,float)) else None,'hi':hi if isinstance(hi,(int,float)) else None}))


def symbolic_time(raw):
    r=region(raw)
    if r.kind=='UNDATED':return None
    if r.kind=='POINT':return {'kind':'POINT','t':r.point}
    bounds=[r.lo,r.hi] if not r.points else [min(r.points),max(r.points)]
    return {'kind':'INTERVAL','bounds':bounds,'semantics':r.kind}


def unique(items):return [v for _,v in sorted({digest(x):x for x in items}.items())]


class Session:
    def __init__(self,payloads,path):
        self.path=Path(path);self.core=AHCore(AHStore());self.templates={};self.entities={};self.variables={};self.formulas={};self.batches={};self.api=set();self.mode_overrides={}
        atoms={}
        def visit(x):
            if isinstance(x,dict):
                if 'predicate' in x and 'roles' in x:atoms[(x['predicate'],tuple(sorted(x['roles'])))]=x
                for v in x.values():visit(v)
            elif isinstance(x,list):
                for v in x:visit(v)
        visit(payloads)
        senses=[]
        for (pred,roles),atom in sorted(atoms.items()):
            mapped=[ROLE_MAP[r] for r in roles]
            if len(set(mapped))!=len(mapped):raise ValueError('NONINJECTIVE_FIXTURE_ROLE_MAP')
            sid=pred+':'+digest(roles)[:12]
            self.templates[(pred,roles)]={'sense_id':sid,'uid':'fixture:T:'+sid,'roles':dict(zip(roles,mapped))}
            senses.append((sid,pred.casefold(),'VERB',[role(r) for r in mapped],'STATE' if pred in {'LOCATIVE','STUDENT'} else 'EVENT'))
        self.release=test_release(self.core,senses)
        self.store=AHStoreAdapter(self.core.store,JournalChannel(self.path),self.core)
        self.initial_snapshot=digest(self.store._codec.export(self.core))
        self.bootstrap=self.store._codec.export(self.core)
        if RESOURCE_ARTIFACT_DIR:
            dest=Path(RESOURCE_ARTIFACT_DIR);dest.mkdir(parents=True,exist_ok=True)
            (dest/(self.release.sha256+'.json')).write_text(json.dumps(self.release.manifest,ensure_ascii=False,sort_keys=True,indent=2)+'\n')

    def tree(self,formula,fragment,ops):
        def emit(k,p):ops.append(StoreOp(k,p,(fragment,)))
        if 'entity' in formula:
            symbol=formula['entity'];uid='fixture:M:'+digest(symbol);self.entities[uid]=symbol
            emit('ENSURE_ENTITY',{'uid':uid,'name':symbol});return uid,digest(uid),None,True
        if 'bound_var' in formula:
            name=formula['bound_var'];self.variables.setdefault(name,len(self.variables)+1)
            value={'bound_var':self.variables[name],'sort':'ENTITY'};return value,digest(value),None,True
        if 'time_literal' in formula:
            t=formula['time_literal'];value={'time_literal':[t,t] if not isinstance(t,list) else t};return value,digest(value),None,True
        if 'count_literal' in formula:return formula,digest(formula),None,True
        if 'predicate' in formula:
            template=self.templates[(formula['predicate'],tuple(sorted(formula['roles'])))]
            actants={template['roles'][r]:self.tree(v,fragment,ops)[0] for r,v in sorted(formula['roles'].items())}
            prop={'predicate':template['sense_id'],'actants':actants};ck=digest(prop);uid='fixture:N:'+digest([template['uid'],actants])
            mode=self.mode_overrides.get(formula['predicate'],'STATE' if formula['predicate'] in {'LOCATIVE','STUDENT'} else 'EVENT')
            emit('ENSURE_NODE',{'uid':uid,'template_ref':template['uid'],'actants':actants,'proposition':prop,'content_key':ck,'identity_key':[ck],'semantic_status':'KNOWN','temporal_mode':mode,'polarity':True})
            self.formulas[digest(formula)]=uid;return uid,ck,prop,True
        fid=formula['operator'];parts=[self.tree(v,fragment,ops) for v in formula['operands']]
        if fid in {'AND','OR','XOR'}:parts.sort(key=lambda part:str(part[0]))
        operands=[v[0] for v in parts];uid='G:'+digest([fid,operands]);ck=parts[0][1] if fid=='NOT' else digest([fid,[v[1] for v in parts]])
        prop=parts[0][2] if fid=='NOT' else None;polarity=not parts[0][3] if fid=='NOT' else True
        emit('ENSURE_FUNCTION',{'uid':uid,'function_id':fid,'operands':operands,'content_key':ck,'proposition':prop,'polarity':polarity,'semantic_status':'KNOWN'})
        for pos,(child,*_) in enumerate(parts):
            if isinstance(child,str):emit('MATERIALIZE_USAGE_LINK',{'link_id':'usage:'+digest([child,uid,pos,'OPERATOR']),'kind':'OPERATOR','node_ref':child,'parent_ref':uid,'position':pos})
        self.formulas[digest(formula)]=uid;return uid,ck,prop,polarity

    def prepare(self,batch,formulas,windows=None,grounds=('O',),rules=(),extra_windows=None):
        tag=['oracle:'+batch,1];ops=[];roots=[];supports=[];assertions=[]
        entries=list(formulas.items()) if isinstance(formulas,dict) else [(batch+':F'+str(i),f) for i,f in enumerate(formulas)]
        for i,(fragment,formula) in enumerate(entries):
            uid,ck,prop,polarity=self.tree(formula,fragment,ops);roots.append(uid)
            for ground in grounds:
                sid='fixture:support:'+digest([tag,fragment,uid,ground]);supports.append(sid)
                ops.append(StoreOp('ADD_ROOT_SUPPORT',{'record_id':sid,'conclusion_ref':uid,'kind':'ROOT','ground_type':ground,'source_tag':tag},(fragment,)))
                reg=windows[i] if windows else None
                if reg:
                    aid='fixture:assertion:'+digest([sid,reg]);assertions.append(aid)
                    ops.append(StoreOp('ADD_TIME_ASSERTION',{'assertion_id':aid,'target_ref':uid,'support_record_id':sid,'region':reg,'anchor':None,'provenance':{'source':{'kind':'OBSERVATION','source_tag':tag},'support':{'kind':'ROOT'}}},(fragment,)))
            for extra in (extra_windows or {}).get(i,()):
                aid='fixture:assertion:'+digest([sid,extra]);assertions.append(aid)
                ops.append(StoreOp('ADD_TIME_ASSERTION',{'assertion_id':aid,'target_ref':uid,'support_record_id':sid,'region':extra,'anchor':None,'provenance':{'source':{'kind':'OBSERVATION','source_tag':tag},'support':{'kind':'ROOT'}}},(fragment,)))
            ops.append(StoreOp('DECLARE_FRAGMENT',{'fragment_id':fragment,'node_ref':uid,'content_key':ck,'proposition':prop,'polarity':polarity,'region':windows[i] if windows else None,'source_tag':tag,'incompatibility_rules':list(rules)},(fragment,)))
        merged={}
        for op in ops:
            key=(op.op_type,digest(op.payload))
            merged[key]=replace(op,fragment_refs=tuple(sorted(set(merged[key].fragment_refs)|set(op.fragment_refs)))) if key in merged else op
        ops=tuple(merged.values());decision=journal_plan(self.store,ops,run_id='run:'+batch,observation_id=tag[0],version=1,batch_hash=batch,fragments=[f for f,_ in entries])
        self.batches[batch]=(ops,decision,tag);self.api.add('AHStoreAdapter.append_journal / InterpretationRunBinding.acquire')
        return roots,supports,assertions

    def commit(self,batch):
        ops,d,_=self.batches[batch];self.api.add('AHStoreAdapter.commit_transaction');return self.store.commit_transaction(ops,d.marker,d)

    def decode(self,uid):
        if isinstance(uid,Ref):uid=uid.uid
        if isinstance(uid,BoundVar):return {'bound_var':next(k for k,v in self.variables.items() if v==uid.local_id)}
        if isinstance(uid,CountLiteral):return {'count_literal':uid.value}
        if isinstance(uid,TimeLiteral):return {'time_literal':uid.bounds[0] if uid.bounds[0]==uid.bounds[1] else list(uid.bounds)}
        obj=self.store._store.get_element_any_domain(uid)
        if uid in self.entities:
            if self.store._store.kind_of(uid).value!='M':raise ValueError('ENTITY_ALIAS_TYPE_CHANGED')
            return {'entity':self.entities[uid]}
        if isinstance(obj,Hypernode):
            key,spec=next((k,s) for k,s in self.templates.items() if s['uid']==obj.template.uid)
            reverse={v:k for k,v in spec['roles'].items()}
            return {'predicate':key[0],'roles':{reverse[r.value]:self.decode(a) for r,a in obj.actants.items()}}
        if isinstance(obj,FunctionSymbol):
            operands=[self.decode(v) for v in obj.operands]
            if obj.function_id in {'AND','OR','XOR'}:operands.sort(key=lambda v:json.dumps(v,sort_keys=True))
            return {'operator':obj.function_id,'operands':operands}
        raise ValueError('UNBOUND_ACTUAL_REF:'+str(uid))

    def snapshot(self):
        L=self.store.ledger;visible=L.f_visible();facts=unique([self.decode(uid) for uid in visible])
        admitted=[]
        for batch,(ops,_,_) in self.batches.items():
            actual=L.data['decisions'].get(batch,{})
            admitted.extend(self.decode(op.payload['node_ref']) for op in ops if op.op_type=='DECLARE_FRAGMENT' and op.payload['fragment_id'] in actual.get('committed',()) and op.payload['node_ref'] in visible)
        reports=[r for r in L.data['reports'].values() if L.report_open(r)]
        terminal={key.removeprefix('batch:'):v['outcome'] for key,v in self.store._terminal_records().items() if key.startswith('batch:')}
        markers=sorted(v['batch_hash'] if isinstance(v,dict) else v for v in L.data['markers'].values())
        self.api.add('CanonicalLedger.f_visible / report_open / JsonPersistence.export')
        return {'assertions':{'ah':facts,'ir':unique(admitted),'journal':unique(admitted)},'journal':{'batch_terminal':terminal,'batch_pending':[r['payload']['batch_hash'] for r in self.store.pending_batches()],'goal_pending_count':sum(r['payload'].get('kind')=='GOAL_PENDING' for r in self.store._journal.scan_unprocessed(0)),'pending_admission_order_records':sum(r['payload'].get('kind')=='PENDING_ADMISSION_ORDER' for r in self.store._journal.scan_unprocessed(0))},'store':{'marker_count':len(markers),'markers':markers,'commit_decisions':sorted(L.data['decisions']),'fact_count':len(facts)},'reports':{'open_count':len(reports),'evidence_kinds':sorted([sorted(e['kind'] for e in r['evidence_refs']) for r in reports])},'candidates':{'count':len(L.data['candidates'])},'state':{'semantic_digest':digest(self.store._codec.export(self.store._core))}}

    def goal_request(self,rule,root,other,windows,run_id='GR1',extra_windows=None):
        roots,sids,aids=self.prepare('premises',[root,*other],windows,extra_windows=extra_windows);self.commit('premises')
        if extra_windows:aids=[next(a for a in aids if self.store.ledger.data['assertions'][a]['support_record_id']==sid) for sid in sids]
        if rule=='OR_ELIMINATION':target_formula=root['operands'][0]
        else:
            variable=root['operands'][0]['bound_var'];replacement=next(iter(other[0]['roles'].values()))
            def subst(x):
                if isinstance(x,dict):return replacement if x=={'bound_var':variable} else {k:subst(v) for k,v in x.items()}
                if isinstance(x,list):return [subst(v) for v in x]
                return x
            target_formula=subst(root['operands'][1]['operands'][1])
        target=self.formulas.get(digest(target_formula));conclusion_ops=()
        if target is None:
            ops=[];target,_,_,_=self.tree(target_formula,'goal',ops)
            conclusion_ops=tuple(replace(op,payload={**op.payload,'uid':'@conclusion'}) if op.payload.get('uid')==target else op for op in ops if op.op_type!='ENSURE_ENTITY')
            target='@conclusion'
            prop=next(op.payload['proposition'] for op in conclusion_ops if op.payload.get('uid')==target)
        else:prop=self.store.ledger.data['nodes'][target]['proposition']
        req=GoalRequest(run_id,rule,tuple(sids),digest(prop),temporal_premise_assertion_refs=tuple(aids),conclusion_ref=None if target=='@conclusion' else target,conclusion_ops=conclusion_ops)
        return req,target

    def derived_snapshot(self,req,target,decision,diagnostics=()):
        L=self.store.ledger;paths=[s for s in L.data['supports'].values() if s['kind']=='DERIVED'];aa=[a for a in L.data['assertions'].values() if a['support_record_id'] in {s['record_id'] for s in paths}]
        target=decision.get('conclusion_ref') or target
        answer=L.query_proposition(target,**self.query_args(req.request_window))['answer'] if target!='@conclusion' else 'UNKNOWN'
        self.api.add('goal_channel.validate_goal / execute / CanonicalLedger.query_proposition')
        return {**self.snapshot(),'license':{'valid':decision.get('outcome') in {'APPLIED','APPLIED_NOOP'}},'derived':{'support_count':len(paths),'premise_count':len(paths[0]['premise_support_refs']) if paths else 0,'time':symbolic_time(aa[0]['region']) if aa else None},'answer':{'status':answer},'diagnostics':{'codes':list(diagnostics)},'commit':{'instances_before_goal':0}}

    @staticmethod
    def query_args(query):
        if not query:return {}
        if isinstance(query,dict):
            if query['kind']=='POINT':return {'point':query['t']}
            if query['kind'] in {'EXISTS_WINDOW','EXISTS'}:return {'window':tuple(query['bounds'])}
            return {}
        return {'window':tuple(query)}

    def action(self,action,p):
        if action=='validate_selector_reply':
            from ah.formalizer.selection_protocol import DecisionSchema,Relation,validate_selection_response,ProtocolError
            accepted=True;grounded=False;codes=[]
            schema=DecisionSchema('oracle',{'A':Relation('A','A',1,('SUBJECT',),'A'),'B':Relation('B','B',1,('SUBJECT',),'B')})
            base={'outcome':'ONE_SELECTED','selected':['A'],'note':'not a proof'}
            mutations={'unknown_id':{**base,'selected':['FOREIGN']},'duplicate_id':{'outcome':'MULTIPLE_ADMISSIBLE','selected':['A','A']},'wrong_shape':['A'],'non_json':'not json','wrong_request_id':{**base,'request_id':'FOREIGN'},'empty_one_selected':{**base,'selected':[]}}
            if p.get('reply_mutation'):
                raw=mutations[p['reply_mutation']];raw=raw if isinstance(raw,str) else json.dumps(raw)
                try:validate_selection_response(raw,schema,frozenset({'A','B'}))
                except ProtocolError:accepted=False;codes=['PROTOCOL_ERROR']
                self.api.add('selection_protocol.validate_selection_response')
            else:
                from tools.formalizer_v7_test_support import native_fixture,FixtureMorph
                from ah.formalizer.native_frontend import run_native
                from ah.formalizer.v7_pipeline import _observation
                self.store,_,self.release=native_fixture(self.path)
                self.core=self.store._core;self.initial_snapshot=digest(self.store._codec.export(self.core))
                class Script:
                    def select(script,prompt):
                        section=prompt.split('closed set):\n',1)[1].split('\nTask:',1)[0]
                        ids=[line.split('. ',1)[0] for line in section.splitlines() if '. ' in line]
                        aliases=dict(zip(p['candidate_ids'],ids))
                        return json.dumps({'outcome':p['response_kind'],'selected':[aliases[x] for x in p['selected_ids']],'note':p['note']})
                    def propose(script,prompt):return None
                text='У Ивана есть книга.'
                state=run_native(text,Script(),self.release,_observation(text,version=1,raw_input={'source_id':'oracle:selection'}),morph=FixtureMorph())
                decisions=list(state.decisions.values());accepted=not any(d.code=='PROTOCOL_ERROR' for d in state.diagnostics)
                grounded=any(g.type=='M' and g.value is not None for d in decisions for g in d.grounds)
                self.api.add('native_frontend.run_native T4 / selection_protocol.validate_selection_response')
            return {**self.snapshot(),'selector':{'accepted':accepted,'value_specific_m_ground':grounded,'arbitrary_known_template_selected':bool(self.store.ledger.data['supports'])},'diagnostics':{'codes':codes},'store':{**self.snapshot()['store'],'new_record_count':len(self.store.ledger.data['supports'])+len(self.store.ledger.data['nodes'])}}
        if action=='repeat_goal':
            root,not_root=p['_root'],p['_not'];self.mode_overrides['LOCATIVE']=p['mode']
            W=witness({'kind':'POINT','t':5});V=witness({'kind':'INTERVAL','bounds':[3,7],'semantics':'CONTINUOUS'})
            extras={0:[witness({'kind':'POINT','t':6})],1:[witness({'kind':'INTERVAL','bounds':[3,8],'semantics':'CONTINUOUS'})]} if p['change']=='temporal_assertion' else None
            req,target=self.goal_request('OR_ELIMINATION',root,[not_root],[W,V],extra_windows=extras)
            first=execute(self.store,req)
            if first['outcome']!='APPLIED':raise ValueError('INVALID_DEDUP_INPUT_FIXTURE:'+str(first))
            again=replace(req,goal_run_id='GR2')
            if p['change']=='request_window':again=replace(again,request_window=(9,10))
            elif p['change']=='temporal_assertion':
                primary=set(req.temporal_premise_assertion_refs)
                aids=[a for a,x in self.store.ledger.data['assertions'].items() if x['support_record_id'] in req.premise_support_ids and a not in primary]
                again=replace(again,temporal_premise_assertion_refs=tuple(aids))
            elif p['change']=='support':
                _,sids,aids=self.prepare('other-premises',[root,not_root],[W,V]);self.commit('other-premises')
                again=replace(again,premise_support_ids=tuple(sids),temporal_premise_assertion_refs=tuple(aids))
            before_nodes=set(self.store.ledger.data['nodes']);before_times=set(self.store.ledger.data['assertions'])
            second=execute(self.store,again);L=self.store.ledger
            derived=list(s for s in L.data['supports'].values() if s['kind']=='DERIVED')
            times=[a for aid,a in L.data['assertions'].items() if aid not in before_times]
            new_nodes=set(L.data['nodes'])-before_nodes
            mode_ok=second['conclusion_ref']==first['conclusion_ref'] if second['outcome']=='APPLIED_NOOP' or p['mode']=='STATE' else second['conclusion_ref']!=first['conclusion_ref']
            match=all(L.data['supports'][a['support_record_id']]['conclusion_ref']==a['target_ref'] for a in times)
            same=all(self.decode(s['formula_ref'])==self.decode(s['conclusion_ref']) for s in derived)
            self.api.add('goal_channel.execute four-component dedup / request-window independence')
            return {**self.snapshot(),'goal':{'outcome':second['outcome'],'created_path':second['created']},'store':{**self.snapshot()['store'],'new_occurrence_count':len(new_nodes)},'time_assertions':{'new_count':len(times)},'derived':{'target_matches_mode':mode_ok,'time_target_matches_support':match,'formula_ref_matches_content':same}}
        if action=='query_time':
            roots,_,_=self.prepare('query',[p['formula']],[witness(p['witness'])]);self.commit('query')
            uid=roots[0]
            if p['formula'].get('operator')=='NOT':uid=self.store.ledger.data['nodes'][uid]['operands'][0]
            before=len(self.store.ledger.data['supports']);answer=self.store.ledger.query_proposition(uid,**self.query_args(p['query']))
            self.api.add('CanonicalLedger.query_proposition')
            return {**self.snapshot(),'answer':{'status':answer['answer']},'query':{'new_root_supports':len(self.store.ledger.data['supports'])-before}}
        if action in {'derive_or','derive_forall','nary_or_query'}:
            rule='FORALL_INST' if action=='derive_forall' else 'OR_ELIMINATION'
            root=p['quantified_root'] if rule=='FORALL_INST' else p['root'] if action=='nary_or_query' else p['or_formula']
            others=[p['restriction']] if rule=='FORALL_INST' else p['not_roots'] if action=='nary_or_query' else [p['not_formula']]
            windows=[None]*(len(others)+1) if action=='nary_or_query' else [witness(p['root_witness']),witness(p['restriction_witness'] if rule=='FORALL_INST' else p['not_witness'])]
            req,target=self.goal_request(rule,root,others,windows)
            reason,_,_=validate_goal(self.store.ledger,req,self.store._core)
            decision={'outcome':'ABORTED','reason':reason} if reason else execute(self.store,req)
            codes=[]
            if reason=='GOAL_LICENSE_FAILED':
                license_fn=forall_inst_license if rule=='FORALL_INST' else or_elimination_license
                lic=license_fn(region(windows[0]),region(windows[1]));codes.append('FORALL_INST_TEMPORAL_MISMATCH' if rule=='FORALL_INST' else 'OR_ELIMINATION_TEMPORAL_MISMATCH')
                if lic.diagnostic and lic.diagnostic not in codes:codes.append(lic.diagnostic)
            elif reason:codes.append(reason)
            return self.derived_snapshot(req,target,decision,codes)
        if action=='commit_grounded_fragment':
            grounds=tuple(g for g in p['selected_value_ground_types'] if g in {'O','C','W'})
            ok,code=evaluate_fragment(FragmentT5Input('F','RESOLVED',integrity_ok=p['otherwise_integrity_valid'],truth_grounds=grounds))
            if ok:self.prepare('grounded',[p['formula']],grounds=grounds);self.commit('grounded')
            self.api.add('t5_batch.evaluate_fragment')
            return {**self.snapshot(),'supports':{'root_ground_types':sorted({s['ground_type'] for s in self.store.ledger.data['supports'].values()})},'commit':{'materialized':ok},'diagnostics':{'codes':[code] if code else []}}
        if action=='check_simultaneity':
            a,b=witness(p['witness_a']),witness(p['witness_b'])
            formulas=[{'predicate':'LOCATIVE','roles':{'THEME':{'entity':'book'},'LOCATION':{'entity':place}}} for place in ('table','shelf')]
            sid=self.templates[('LOCATIVE',('LOCATION','THEME'))]['sense_id']
            rules=[{'kind':'ROLE_EXCLUSIVE','rule_id':p['incompatibility_rule'],'sense_id':sid,'role_id':'LOCATION','key_roles':['OBJECT']}]
            self.prepare('first',[formulas[0]],[a],rules=rules);self.commit('first')
            self.prepare('second',[formulas[1]],[b],rules=rules);self.commit('second')
            result=simultaneity_result(a,b);self.api.add('canonical_ledger.simultaneity_result')
            return {**self.snapshot(),'time':{'guaranteed_simultaneity':result['guaranteed']},'diagnostics':{'codes':[result['diagnostic']] if result['diagnostic'] else []}}
        if action in {'journal_batch','admit_batch'}:
            self.prepare(p['batch'],p.get('fragments',p.get('formulas')))
            if action=='admit_batch':self.commit(p['batch'])
            return self.snapshot()
        if action=='journal_batches':
            for b in sorted(p['batches'],key=lambda x:x['seq']):
                self.prepare(b['batch'],b['fragments'])
                if b.get('stale'):self.store.retract_observation(*self.batches[b['batch']][2],trigger_ref='oracle:stale:'+b['batch'])
            return self.snapshot()
        if action=='execute_head_calls':
            batches=list(self.batches)
            for i in p['call_order']:self.commit(batches[i-1])
            return self.snapshot()
        if action=='crash':return self.snapshot()
        if action=='recover':
            restored=self.store._codec.import_payload(deepcopy(self.bootstrap),uid_generator=self.core.uid).core
            self.store=AHStoreAdapter(restored.store,JournalChannel(self.path),restored);self.store.recover_from_head();self.api.add('AHStoreAdapter.recover_from_head / JsonPersistence.import_payload')
            return self.snapshot()
        if action=='numeric_scope_literal':
            try:CountLiteral(p['literal']);accepted=True
            except (TypeError,ValueError):accepted=False
            self.api.add('CountLiteral validation')
            return {**self.snapshot(),'literal':{'accepted':accepted},'store':{**self.snapshot()['store'],'fictitious_entity_count':len(self.entities)},'usage':{'nonproposition_link_count':len(self.store.ledger.data['usage_links'])}}
        if action=='function_identity':
            tree={'operator':p['operator'],'operands':p['operands']};ops=[];self.tree(tree,'identity',ops)
            from ah.formalizer.graph_ops import ensure_function
            first=None
            for op in ops:
                if op.op_type=='ENSURE_ENTITY':ensure_entity(self.core,op.payload)
                elif op.op_type=='ENSURE_NODE':ensure_node(self.core,op.payload)
                elif op.op_type=='ENSURE_FUNCTION':
                    raw=op.payload;operands=tuple(native_operand(self.core,v) for v in raw['operands']);self.core.function_registry.validate(raw['function_id'],operands)
                    first=self.core.add_function(Domain.C,raw['function_id'],operands,uid=raw['uid'])
            syntax_operands=tuple(native_operand(self.core,self.tree(v,'identity',[])[0]) for v in p['operands'])
            if p['operator'] in {'AND','OR','XOR'}:syntax_operands=tuple(sorted(syntax_operands,key=lambda v:str(v.uid)))
            preserved=first.operands==syntax_operands
            other=[]
            for v in p['compare_operands']:other.append(native_operand(self.core,self.tree(v,'identity',[])[0]))
            try:
                self.core.function_registry.validate(p['operator'],tuple(other));valid=True
                if p['operator'] in {'AND','OR','XOR'}:other.sort(key=lambda v:str(v.uid))
                second,_=self.core.ensure_function(Domain.C,p['operator'],tuple(other));same=second.uid==first.uid
            except (ValueError,TypeError):valid=False;same=False
            self.api.add('AHCore.ensure_function / FunctionRegistry.validate')
            return {'functions':{'second_well_typed':valid,'same_key':same,'syntax_order_preserved':preserved}}
        raise ValueError('UNBOUND_ACTION:'+action)

    def manifest(self):
        if RESOURCE_ARTIFACT_DIR:
            dest=Path(RESOURCE_ARTIFACT_DIR);dest.mkdir(parents=True,exist_ok=True)
            (dest/(self.release.sha256+'.json')).write_text(json.dumps(self.release.manifest,ensure_ascii=False,sort_keys=True,indent=2)+'\n')
        return {'execution_level':'COMPONENT_OR_WAL','python_version':sys.version.split()[0],'resource_sha256':self.release.sha256,'initial_ah_sha256':self.initial_snapshot,'api_refs':sorted(self.api),'template_aliases':self.templates_list(),'entity_aliases':self.entities,'variable_aliases':self.variables,'symbolic_role_map':ROLE_MAP,'derived_support_records':[s for s in self.store.ledger.data['supports'].values() if s['kind']=='DERIVED'],'time_assertion_records':list(self.store.ledger.data['assertions'].values()),'node_refs':sorted(self.store.ledger.data['nodes']),'final_ah_sha256':digest(self.store._codec.export(self.store._core)),'fixture_mode_overrides':self.mode_overrides,'source_snapshot_ref':digest(source_snapshot())}
    def templates_list(self):return [{'predicate':k[0],'roles':list(k[1]),**v} for k,v in sorted(self.templates.items())]

_SOURCE=None
def source_snapshot():
    global _SOURCE
    if _SOURCE is None:
        root=Path(__file__).resolve().parents[1]
        paths=[*sorted((root/'src/ah').rglob('*.py')),Path(__file__),Path(__file__).with_name('formalizer_v7_test_support.py')]
        _SOURCE={str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    return _SOURCE


def run_case(case,fixtures):
    blockers=[]
    for s in case['steps']:
        if s['action'] not in SUPPORTED:blockers.append({'action':s['action'],'reason':'BLOCKED_UNBOUND_ACTION'})
        elif s['action']=='execute_head_calls' and s['payload'].get('crash_at','NONE')!='NONE':blockers.append({'action':s['action'],'reason':'BLOCKED_CRASH_BINDING'})
        elif s['action']=='repeat_goal' and s['payload'].get('change') in {'rule','conclusion'}:blockers.append({'action':s['action'],'reason':'BLOCKED_TYPED_CHANGED_FORM_BINDING'})
        elif s['action']=='numeric_scope_literal' and s['payload']['source']=='MODEL_NUMBER_ONLY':blockers.append({'action':s['action'],'reason':'BLOCKED_NUMERAL_SOURCE_BINDING'})
    base={'schema_version':'v7-oracle-trace-1','case_id':case['case_id'],'checkpoints':[]}
    if blockers:return {**base,'execution_status':'BLOCKED','blockers':blockers}
    case=deepcopy(case)
    for step in case['steps']:
        if step['action']=='repeat_goal':
            atom={'predicate':'LOCATIVE','roles':{'THEME':{'entity':'book'},'LOCATION':{'entity':'table'}}}
            other={'predicate':'LOCATIVE','roles':{'THEME':{'entity':'book'},'LOCATION':{'entity':'shelf'}}}
            step['payload']['_root']={'operator':'OR','operands':[atom,other]}
            step['payload']['_not']={'operator':'NOT','operands':[other]}
    payloads=deepcopy([s['payload'] for s in case['steps']])
    if any(s['action']=='check_simultaneity' for s in case['steps']):payloads += [{'predicate':'LOCATIVE','roles':{'THEME':{'entity':'book'},'LOCATION':{'entity':place}}} for place in ('table','shelf')]
    with tempfile.TemporaryDirectory(prefix='ag-oracle-') as directory:
        session=Session(payloads,Path(directory)/'journal.log')
        checkpoints=[{'step_id':s['id'],'actual':session.action(s['action'],s['payload'])} for s in case['steps']]
        manifest=session.manifest()
    return {**base,'execution_status':'EXECUTED','checkpoints':checkpoints,'binding_manifest':manifest,'binding_manifest_ref':digest(manifest)}
