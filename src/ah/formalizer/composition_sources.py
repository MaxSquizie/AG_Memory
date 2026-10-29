"""Run-local inventory of source-owned subtrees, independent of their producer.

Coverage belongs to a complete alternative, never to the union of competing
hypotheses. Reuse copies the selected IR; it does not assert the child content.
"""
from collections import defaultdict
from copy import deepcopy
from .canonical_ledger import digest
from .composition_tree import forests, roots, validate, leaves


def token_key(tokens):
    return frozenset(t.token_id for t in tokens if any(v.pos!='PNCT' for v in t.variants))


class CompositionSources:
    def __init__(self,state,release):
        from .native_frontend import _required_operators
        self.state=state;self.release=release;self.by_tokens=defaultdict(list);self.child_domains={};self.projected=set();self.failed={}
        self.evidence={e.token_id:e for e in state.evidence}
        self.required=_required_operators(state,release)
        required_by_token=defaultdict(set)
        for i,(_,refs) in enumerate(self.required):
            for ref in refs:required_by_token[ref].add(i)
        groups=defaultdict(list)
        for f in state.frames:
            groups[f.semantic.get('hypothesis',f.frame_id)].append(f)
        for source_id,frames in groups.items():
            if any((f.semantic.get('structural_unresolved') and not f.semantic.get('grammar_ambiguity')) or f.semantic.get('structural_rejection') for f in frames):continue
            frames=deepcopy(frames)
            for f in frames:
                if f.semantic.get('grammar_ambiguity'):f.semantic['structural_unresolved']=False
            covered=set()
            for f in frames:
                covered.add(f.predicate_token_ref);covered.update(f.argument_token_refs)
                covered.update(f.semantic.get('owned_token_refs',()))
                for unit in f.semantic.get('lexical_units',{}).values():covered.update(unit['anchor_refs'])
            trees=forests(frames)
            operators=[]
            def collect(tree):
                refs=set(tree.get('anchor_refs',()))
                covered.update(refs)
                if tree.get('operator'):operators.append((tree['operator'],refs))
                for child in tree.get('operands',()):collect(child)
            for tree in trees:collect(tree)
            from .composition_tree import slots
            for f in frames:
                for slot in slots(f):collect(slot.tree)
            if not covered<=self.evidence.keys():continue
            key=token_key([self.evidence[t] for t in covered])
            relevant={i for ref in key for i in required_by_token[ref]}
            if any(set(refs)<=key and not any(name==op and set(refs)<=anchors for name,anchors in operators)
                   for i in sorted(relevant) for op,refs in [self.required[i]] if refs):continue
            try:validate(frames,trees)
            except ValueError:continue
            # A forest with several unconnected roots is not a typed child.
            if len(trees)>1:continue
            boundary=roots(frames)
            if trees:
                refs=leaves(trees[0])
                if any(f.frame_id not in refs for f in boundary):continue
            elif len(boundary)!=1:continue
            self.by_tokens[key].append((source_id,deepcopy(frames)))

    def alternatives(self,tokens):
        return self.by_tokens.get(token_key(tokens),())

    def complete(self,tokens):
        return len(self.alternatives(tokens))==1

    def project_grammar(self,tokens):
        from .composition_session import current
        runtime=current(self.state)
        if runtime is None:return self._project_grammar(tokens)
        from .morphology_domain import clean
        owner='grammar:'+digest([t.token_id for t in tokens])
        return runtime.dispatcher.run(owner,
            [[t.token_id,[clean(v) for v in t.variants]] for t in tokens],
            lambda:self._project_grammar(tokens),kind='GRAMMAR',
            source_range=(tokens[0].start,tokens[-1].end) if tokens else None,
            token_refs=[t.token_id for t in tokens])

    def _project_grammar(self,tokens):
        """Close the same released capture domains in an addressed child area.

        Source token IDs/readings are reused. No second tokenizer, grammar DSL
        or model-generated subtree is introduced by a recursive boundary.
        """
        from copy import copy
        from .morphology_domain import clean
        key=digest([[t.token_id,[clean(v) for v in t.variants]] for t in tokens])
        if key in self.failed:
            code,detail=self.failed[key]
            self.state.grammar_search_incomplete=True
            if not any(d.code==code and d.detail==detail for d in self.state.diagnostics):
                self.state.diag(code,detail)
            return False
        if key in self.projected:return
        from .grammar_domains import chart
        chart(self.state)
        local=copy(self.state);local.evidence=list(tokens);local.frames=[];local.clause_candidates=[]
        from .tp_proposer import StructureProposalRequest
        from .native_frontend import OPERATORS, _frames_for_hypotheses
        from .syntax_rules import propose_graphs, SearchLimit
        from .selection_protocol import ProtocolError
        p=self.release.entries('ProposalPolicy')[0];owned={t.token_id for t in tokens}
        request=StructureProposalRequest('syntax-child:'+key,'',tuple(t.token_id for t in tokens),
            allowed_node_kinds=frozenset({'PREDICATE','ENTITY','BOUND_VAR','TIME','WH','COUNT_REQUEST','NUMERAL',*OPERATORS}),
            allowed_edge_kinds=frozenset({'ARGUMENT','OPERAND','ATTITUDE','BIND','TIME_SCOPE','QUERY_SLOT'}),
            allowed_role_ids=frozenset(x['role_id'] for x in self.release.entries('RoleRegistry')),
            max_nodes=p['max_nodes'],max_edges=p['max_edges'],max_depth=p['max_depth'],
            required_operators=tuple((op,refs) for op,refs in self.required if set(refs)<=owned))
        try:
            hypotheses,provenance,bindings=propose_graphs(local,self.release,request)
            accepted=_frames_for_hypotheses(local,hypotheses,self.release,provenance,bindings)
        except (SearchLimit,ProtocolError) as exc:
            self.failed[key]=('COMPONENT_SEARCH_INCOMPLETE',str(exc))
            self.state.grammar_search_incomplete=True
            self.state.diag('COMPONENT_SEARCH_INCOMPLETE',str(exc));return False
        local.frames=[f for _,frames in accepted for f in frames]
        inventory=CompositionSources(local,self.release)
        target=token_key(tokens)
        existing={cid for cid,_ in self.by_tokens[target]}
        self.by_tokens[target].extend((cid,frames) for cid,frames in inventory.by_tokens.get(target,()) if cid not in existing)
        self.projected.add(key)
        self.state.syntax_trace.append({'kind':'GRAMMAR_CHILD_PROJECTED','projection_ref':key,
            'owned_token_refs':[t.token_id for t in tokens],
            'candidate_refs':[cid for cid,_ in self.by_tokens[target]]})

    def reuse(self,region,tokens,attachment,infinitive,request):
        if attachment is not None or infinitive is not None:return None
        if request and (request.output_sort!='PROPOSITION' or request.head_ref or request.allowed_cases
                        or request.proposition_slots or request.agreement_source or request.pending_proposition_roles
                        or request.pending_propositions):return None
        if self.project_grammar(tokens) is False:return []
        from .morphology_domain import clean
        available={t.token_id:{digest(clean(v)) for v in t.variants} for t in tokens}
        choices=[(cid,frames) for cid,frames in self.alternatives(tokens) if all(
            tid not in available or digest(clean(reading)) in available[tid]
            for frame in frames for tid,reading in frame.semantic.get('morph_bindings',{}).items())]
        if not choices:return None
        if len(choices)>1:
            combined=[]
            for source_id,stored in choices:
                frames=self._reuse_one(region,tokens,attachment,infinitive,request,source_id,stored)
                if frames is None:return None
                boundary=roots(frames)
                if len(boundary)!=1:return None
                root=boundary[0]
                root.semantic['composition_domain']={'decision_ref':'source-domain:'+digest(sorted(token_key(tokens))),
                    'frame_refs':[f.frame_id for f in frames],
                    'label':'; '.join('Predicate «'+f.anchor_span+'»; roles='+str({
                        self.evidence[t].span+'@'+str(self.evidence[t].start):r for t,r in f.semantic.get('proposed_roles',{}).items()})+
                        '; linked readings='+str({self.evidence[t].span+'@'+str(self.evidence[t].start):
                            {k:v for k,v in m.items() if k in {'lemma','pos','cases','number','gender','features'}}
                            for t,m in f.semantic.get('morph_bindings',{}).items()}) for f in frames)+
                        '; scope='+str(forests(frames))}
                for f in frames:f.semantic['structural_unresolved']=True
                combined.extend(frames)
            return combined
        return self._reuse_one(region,tokens,attachment,infinitive,request,*choices[0])

    def _reuse_one(self,region,tokens,attachment,infinitive,request,source_id,stored):
        # Contextual morphology supplied by a parent must not be overwritten
        # by a source parse built with a different token inventory.
        from .morphology_domain import clean
        available={t.token_id:{digest(clean(v)) for v in t.variants} for t in tokens}
        if any(t in available and digest(clean(reading)) not in available[t]
               for f in stored for t,reading in f.semantic.get('morph_bindings',{}).items()):return None
        if any(f.semantic.get('query_request') for f in stored):return None
        from .composition_session import child_key
        key=child_key(region,tokens,attachment,infinitive,request)
        mapping={f.frame_id:'composition-grammar:'+digest([key,f.frame_id]) for f in stored}
        def remap(value):
            if isinstance(value,str):return mapping.get(value,value)
            if isinstance(value,dict):return {k:remap(v) for k,v in value.items()}
            if isinstance(value,(list,tuple)):return [remap(v) for v in value]
            return value
        frames=deepcopy(stored)
        for f in frames:
            original=f.frame_id;f.frame_id=mapping[original];f.semantic=remap(f.semantic)
            f.semantic.update(composition_source='GRAMMAR',composition_source_ref=source_id,
                              source_frame_ref=original,component_region=region.region_id)
            for name,default in {'component_questions':[],'uncovered_token_refs':[],
                    'missing_required_roles':[],'requires_attachment_probe':False,
                    'preposition_bindings':{},'relative_temporal':[]}.items():f.semantic.setdefault(name,default)
        trees=forests(frames)
        if trees:
            carrier=next(f for f in reversed(frames) if f.frame_id in leaves(trees[0]))
            carrier.semantic['component_scope_tree']=deepcopy(trees[0])
            for f in frames:f.semantic['composition_group_root']=carrier.frame_id
        from .scope_boundaries import rebase as rebase_scope_boundaries
        rebase_scope_boundaries(frames,mapping)
        self.state.syntax_trace.append({'kind':'COMPOSITION_SOURCE_REUSED','source':'GRAMMAR',
            'source_ref':source_id,'region_ref':region.region_id,'source_frame_refs':list(mapping),
            'frame_refs':list(mapping.values()),'owned_token_refs':sorted(token_key(tokens))})
        return frames

    def retain(self,key,region,tokens,frames,request):
        """Both producers publish addressable roots with their morphology."""
        from .composition_domains import DomainNetwork
        from .morphology_domain import clean, frame_readings
        choices={}
        by_id={f.frame_id:f for f in frames}
        for frame in frames:
            pending=frame.semantic.get('composition_domain')
            if pending:
                owned=[by_id[r] for r in pending['frame_refs'] if r in by_id]
                choices[frame.frame_id]=(owned,pending['label'])
        for frame in roots(frames):
            choices.setdefault(frame.frame_id,([f for f in frames if not f.semantic.get('structural_unresolved')],frame.anchor_span))
        if not choices:return
        domains={'ROOT':{cid:{'frames':[f.frame_id for f in owned],'label':label}
                         for cid,(owned,label) in choices.items()}}
        readings={};bindings={}
        for cid,(owned,label) in choices.items():
            bound={}
            for f in owned:
                for slot,tid,reading in frame_readings(f):
                    address=slot+':'+tid
                    rid=digest(clean(reading));bound.setdefault(address,set()).add(rid)
                    readings.setdefault(address,{})[rid]=clean(reading)
            bindings[cid]=bound
        # A candidate cannot use two incompatible EXTERNAL readings of one
        # source occurrence. Internal quantity heads have their own slot.
        domains['ROOT']={cid:v for cid,v in domains['ROOT'].items()
                         if all(len(rs)==1 for rs in bindings[cid].values())}
        domains.update(readings)
        graph=DomainNetwork(domains)
        for address in readings:
            graph.connect('ROOT',address,
                lambda root,reading,address=address:any(
                    root is domains['ROOT'].get(cid) and (address not in bindings[cid] or digest(reading) in bindings[cid][address])
                    for cid in domains['ROOT']), 'SHARED_OCCURRENCE_READING')
        if request:
            allowed=[]
            for cid,(owned,_) in choices.items():
                frame=by_id[cid]
                if frame.semantic.get('output_sort','PROPOSITION')!=request.output_sort:continue
                if request.head_ref:
                    reading=frame.semantic.get('morph_bindings',{}).get(request.head_ref)
                    if reading is None or request.allowed_cases and not set(reading['cases'])&set(request.allowed_cases):continue
                allowed.append(cid)
            graph.restrict('ROOT',allowed,'PARENT_TYPED_SLOT')
        graph.propagate()
        allowed=set(graph.domains['ROOT'])
        for frame in roots(frames):
            if frame.frame_id not in allowed:
                frame.semantic['structural_unresolved']=True
                self.state.diag('COMPOSITION_CHILD_CONSTRAINT_CONFLICT',frame.frame_id)
        self.child_domains[key]=graph
        self.state.syntax_trace.append({'kind':'COMPOSITION_SOURCE_DOMAIN','child_key':key,
            'region_ref':region.region_id,'sources':sorted({f.semantic.get('composition_source','COMPONENT') for f in frames}),
            'constraint_state':graph.snapshot()})

    def allowed(self,key):
        graph=self.child_domains.get(key)
        return set(graph.domains['ROOT']) if graph is not None else None
