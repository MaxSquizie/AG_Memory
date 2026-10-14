"""Bounded GOAL certificates over an addressed active-memory projection.

Uses the ordinary Search and validate_goal. Ephemeral intermediate nodes never
reach AH, a write unit or a GOAL_DECISION. Structural descendants of active
nodes are visible as syntax, but only active conclusions supply fact supports.
"""
from collections import defaultdict
from copy import deepcopy
from dataclasses import asdict, replace
from types import SimpleNamespace
import json
from .canonical_ledger import CanonicalLedger, digest, region_data
from .goal_forms import formula, indexed_matches, spend
from .goal_queries import Search
from .goal_channel import validate_goal


class ProofStore:
    def __init__(self,base,active,excluded_source,budget,allowed_sources=()):
        self.ledger=CanonicalLedger();self._store=self
        self._core=SimpleNamespace(store=self);self.steps=[]
        self.templates=defaultdict(set);self.parents=defaultdict(set);self.kinds={}
        source=base.ledger; nodes=source.data['nodes']; pending=list(sorted(active)); visited=set()
        while pending:
            uid=pending.pop();spend(budget)
            if uid in visited:continue
            visited.add(uid)
            if uid not in nodes:
                if base._store.has_uid(uid):self.kinds[uid]=base._store.kind_of(uid).value
                continue
            spec=deepcopy(nodes[uid]);self.add_node(uid,spec)
            children=spec.get('operands',()) if spec.get('function_id') else spec.get('actants',{}).values()
            pending.extend(v for v in children if isinstance(v,str))
        from .native_records import record_index
        index=record_index(base._core,source)
        # Supports of an inactive structural leaf are deliberately absent.
        for uid in sorted(set(active)&self.ledger.data['nodes'].keys()):
            for sid in index['supports'].get(uid,()):
                spend(budget);support=source.data['supports'][sid]
                tag=support.get('source_tag') or [None]
                if tag[0]==excluded_source:continue
                if allowed_sources and tuple(tag) not in {tuple(t) for t in allowed_sources}:continue
                self.ledger.data['supports'][sid]=deepcopy(support)
                for aid in index['assertions'].get(sid,()):
                    spend(budget);self.ledger.data['assertions'][aid]=deepcopy(source.data['assertions'][aid])
                for bid in support.get('binding_refs',()):self._binding(source,bid,budget,set())
        self.original_supports=set(self.ledger.data['supports'])

    def _binding(self,source,bid,budget,seen):
        spend(budget)
        if bid in seen:return
        seen.add(bid)
        row=source.data['bindings'].get(bid)
        if not row:return
        self.ledger.data['bindings'][bid]=deepcopy(row)
        tag=row.get('source_tag')
        if tag and digest(tag) in source.data['observations']:
            self.ledger.data['observations'][digest(tag)]=deepcopy(source.data['observations'][digest(tag)])
        if row.get('anchor_binding_ref'):self._binding(source,row['anchor_binding_ref'],budget,seen)

    def add_node(self,uid,spec):
        self.ledger.data['nodes'][uid]=spec
        if spec.get('function_id'):
            self.kinds[uid]='G'
            for child in spec.get('operands',()):
                if isinstance(child,str):self.parents[child].add(uid)
        else:
            self.kinds[uid]='N';self.templates[spec['template_ref']].add(uid)

    def has_uid(self,uid):return uid in self.kinds
    def kind_of(self,uid):return SimpleNamespace(value=self.kinds[uid])
    def find_hypernodes_by_template(self,uid):return tuple(SimpleNamespace(uid=v) for v in sorted(self.templates[uid]))
    def function_parents(self,uid):return tuple(SimpleNamespace(uid=v) for v in sorted(self.parents[uid]))

    def derive(self,store,req):
        # Stable local IDs permit multi-step proofs and deterministic receipts.
        def rewrite(v):
            if isinstance(v,str):return local if v=='@conclusion' else v
            if isinstance(v,dict):return {k:rewrite(x) for k,x in v.items()}
            if isinstance(v,(tuple,list)):return [rewrite(x) for x in v]
            return v
        local='proof-node:'+digest([req.conclusion_signature,req.instantiation,req.conclusion_path])
        req=replace(req,goal_run_id='proof:'+digest([req.rule_id,req.premise_support_ids,
                    req.conclusion_signature,req.instantiation,req.conclusion_path]),
                    conclusion_ref=rewrite(req.conclusion_ref),
                    conclusion_ops=tuple(replace(op,payload=rewrite(op.payload)) for op in req.conclusion_ops))
        # If an earlier local step already materialized the exact node, reuse
        # it without proposing a second ENSURE of an existing ID.
        req=replace(req,conclusion_ops=tuple(op for op in req.conclusion_ops
            if op.payload.get('uid') not in self.ledger.data['nodes']
            and not (op.op_type=='MATERIALIZE_USAGE_LINK' and op.payload['parent_ref'] in self.ledger.data['nodes'])))
        reason,target,window=validate_goal(self.ledger,req,self._core)
        if reason:return {'outcome':'ABORTED','reason':reason}
        sid='proof-support:'+digest([req.rule_id,req.premise_support_ids,target,req.temporal_premise_assertion_refs])
        if sid in self.ledger.data['supports']:return {'outcome':'APPLIED_NOOP','conclusion_ref':target}
        for op in req.conclusion_ops:
            if op.op_type in {'ENSURE_NODE','ENSURE_FUNCTION'}:self.add_node(op.payload['uid'],deepcopy(op.payload))
        support={'record_id':sid,'conclusion_ref':target,'kind':'DERIVED','rule_id':req.rule_id,
            'premise_support_refs':list(req.premise_support_ids),
            'temporal_assertion_refs':list(req.temporal_premise_assertion_refs),'goal_run_id':req.goal_run_id}
        self.ledger.add_support(support)
        if window.kind!='UNDATED':
            self.ledger.add_assertion({'assertion_id':'proof-time:'+digest([sid,region_data(window)]),
                'target_ref':target,'support_record_id':sid,'region':region_data(window),'anchor':None,
                'provenance':{'source':{'kind':'GOAL_RUN','goal_run_id':req.goal_run_id},
                    'support':{'kind':'DERIVED','rule_id':req.rule_id,'premise_support_refs':list(req.premise_support_ids)}}})
        self.steps.append({'support_ref':sid,'request':json.loads(json.dumps(asdict(req)))})
        return {'outcome':'APPLIED','conclusion_ref':target}

    def certificate(self,uid,budget):
        from .native_records import record_index
        live=self.ledger.paths();index=record_index(self._core,self.ledger)
        pending=[sid for sid in index['supports'].get(uid,()) if sid in live]
        all_refs=set()
        while pending:
            sid=pending.pop();spend(budget)
            if sid in all_refs:continue
            all_refs.add(sid);pending.extend(self.ledger.data['supports'][sid].get('premise_support_refs',()))
        return {'conclusion':formula(self.ledger,uid,budget),
                'premise_support_refs':sorted(all_refs & self.original_supports),
                'derivations':[s for s in self.steps if s['support_ref'] in all_refs]}


def read_goals(store,active,goals,excluded_source,limit=4096,allowed_sources=()):
    budget=[limit];results=[]
    try:
        projection=ProofStore(store,active,excluded_source,budget,allowed_sources)
        for goal in goals:
            spend(budget)
            search=Search(projection,budget,point=goal.get('point'),window=goal.get('window'),executor=projection.derive)
            found=None
            if 'formula' in goal:
                expected=goal['formula']
                for uid,_ in indexed_matches(projection._core,projection.ledger,expected,budget):
                    found=search.prove_node(uid)
                    if found:break
                if not found:found=search.derive(expected)
            else:
                template=goal['template_ref'];known=goal.get('known_roles',{})
                for node in projection.find_hypernodes_by_template(template):
                    spend(budget);spec=projection.ledger.data['nodes'][node.uid]
                    # Only closed instances can serve as an existential witness.
                    if any(not isinstance(v,str) for v in spec['actants'].values()):continue
                    if not all(spec['actants'].get(r)==v for r,v in known.items()):continue
                    if projection.ledger.query(node.uid,point=search.point,window=search.window)['answer']=='YES':
                        found=node.uid;break
                if not found:found=search.derive({'template_ref':template,'actants':known},constraints=(template,known))
            proved=bool(found and projection.ledger.query(found,point=search.point,window=search.window)['answer']=='YES')
            results.append({'goal':goal,'status':'PROVED' if proved else 'UNKNOWN',
                'scope':'ACTIVE_WORKSPACE','global_search_complete':False,
                **({'proof':projection.certificate(found,budget)} if proved else {})})
        return results,False
    except ValueError as exc:
        if str(exc) not in {'COMPUTATION_LIMIT','OPEN_LEXICAL_INFERENCE_FORBIDDEN','GOAL_FORM_MISMATCH'}:raise
        results.append({'status':'UNKNOWN','diagnostic':str(exc),'scope':'ACTIVE_WORKSPACE',
                        'global_search_complete':False})
        return results,True


def compile_goals(release,evidence,options,limit):
    """Compile source-licensed template questions, never infer entity identity.

An option may supply a typed formula already grounded by its constructor.
Otherwise ask for an existential witness of the released predicate senses in
this area. Such a witness informs interpretation, not a token/UID binding.
"""
    goals={digest(o['context_goal']):o['context_goal'] for o in options if o.get('context_goal')}
    senses={r['sense_id'] for r in release.entries('R-S') if not r.get('anchor_pattern')
            and any(v.lemma==r['lemma'] and v.pos==r['POS'] for token in evidence for v in token.variants)}
    for row in release.entries('TemplateMap'):
        if row['sense_id'] in senses:
            goal={'template_ref':row['template_ref'],'known_roles':{}}
            goals[digest(goal)]=goal
    if len(goals)>limit:raise ValueError('COMPUTATION_LIMIT')
    return [goals[k] for k in sorted(goals)]
