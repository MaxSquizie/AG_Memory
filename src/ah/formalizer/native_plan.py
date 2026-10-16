"""Pure typed C/T5 plan. Every operation belongs to a fragment and its closure."""
from __future__ import annotations
import re
from .canonical_ledger import digest
from .store_interface import StoreOp
from .t5_batch import FragmentT5Input,evaluate_fragment
from .structural_content_time import payload as content_time
from .action_descriptions import schema_roles as description_schema_roles


def build_plan(state,release,store):
    evidence={e.token_id:e for e in state.evidence}; frames={f.frame_id:f for f in state.frames}
    nodes={}; op_by_id={}; diagnostics=[]; fragments=[]; blocked=set()
    nominal_links=[]
    tag=[state.source_uid,state.interpretation_version]
    def emit(kind,payload,frag):
        oid=payload.get('op_id') or kind+':'+str(payload.get('uid',payload.get('record_id',payload.get('assertion_id',digest(payload)))))
        payload={**payload,'op_id':oid}
        if oid in op_by_id:
            old=op_by_id[oid]
            op_by_id[oid]=StoreOp(old.op_type,old.payload,tuple(sorted(set(old.fragment_refs)|{frag})),old.deps)
        else: op_by_id[oid]=StoreOp(kind,payload,(frag,))
        return oid

    def node_for(fid,frag,structural=False,active=None):
        active=set() if active is None else active
        if fid in active: raise ValueError('CYCLIC_PROPOSITION_ARGUMENT')
        active=active|{fid}
        f=frames[fid]
        if f.semantic.get('structural_unresolved'): raise ValueError('STRUCTURAL_OPERAND_UNRESOLVED')
        if structural and f.semantic.get('temporal_unresolved'):raise ValueError('TEMPORAL_NESTED_SCOPE_UNRESOLVED')
        if structural and (f.semantic.get('relative_temporal') or f.semantic.get('relative_time_targets')):
            raise ValueError('TEMPORAL_NESTED_SCOPE_UNSUPPORTED')
        d=state.decisions.get(fid+'|predicate_value')
        selected=f.semantic.get('candidate_specs',{}).get(d.selected[0]) if d and len(d.selected)==1 else None
        if not selected or d is None or d.outcome!='RESOLVED': raise ValueError('STRUCTURAL_OPERAND_UNRESOLVED')
        e=evidence[f.predicate_token_ref]
        roles={}; mention_roles={}; mention_entities={}; mention_bindings={}
        selected_roles=description_schema_roles(selected,set(selected['roles'].values())|set(f.semantic.get('proposition_args',{}))|set(selected.get('implicit_roles',()))|set(selected.get('spatial_roles',())))
        mappings=[m for m in release.entries('TemplateMap') if m['sense_id']==selected.get('sense_id') and set(m.get('roles',()))==selected_roles]
        measures=[m for m in release.resources.get('MeasureSchema',{}).get('entries',())
                  if len(mappings)==1 and m['template_ref']==mappings[0]['template_ref'] and m.get('literal_syntax')]
        for tid,role in selected['roles'].items():
            if tid in state.observation.get('unresolved_references',()): raise ValueError('REFERENCE_UNKNOWN')
            from .bound_references import resolved as resolved_bound
            bound=f.semantic.get('bound_arguments',{}).get(tid)
            if bound is None:bound=resolved_bound(state,f,tid)
            if bound is not None:
                roles[role]={'bound_var':bound,'sort':'ENTITY'}
                continue
            from .group_references import emit as emit_group_reference
            group_ref=emit_group_reference(state,tid,tag,frag,emit)
            if group_ref:
                roles[role]=group_ref;continue
            ev=evidence[tid]
            unit=f.semantic.get('lexical_units',{}).get(tid,{})
            mention_ref=unit.get('mention_ref',tid)
            event_ref=state.observation.get('event_bindings',{}).get(mention_ref)
            if event_ref is not None:
                valencies=[v for v in release.entries('R-V') if v['sense_id']==selected.get('sense_id')]
                if not any(r['role_id']==role and set(r.get('argument_types',())) & {'EVENT','PROPOSITION'}
                           for v in valencies for r in v['roles']):
                    raise ValueError('EVENT_REFERENCE_TYPE_MISMATCH')
                if not store.has_uid(event_ref) or store._store.kind_of(event_ref).value not in {'N','G'}:
                    raise ValueError('EVENT_REFERENCE_STALE')
                bid='binding:event:'+digest([tag,mention_ref,event_ref])
                emit('SET_IDENTITY_BINDING',{'binding_id':bid,'binding_kind':'EVENT_REFERENCE','mention_ref':mention_ref,
                    'target_ref':event_ref,'source_tag':tag,
                    'premise_support_refs':state.observation.get('entity_binding_grounds',{}).get(mention_ref,[])},frag)
                roles[role]=event_ref
                continue
            from .nominal_reference_binding import payload as reference_payload
            reference=reference_payload(state,unit)
            local_place=reference.get('local_spatial_anchor') if reference else None
            if local_place:
                from .spatial_plan import emit_anchor
                emit_anchor(local_place,tag,frag,emit)
            known=reference['target_ref'] if reference else state.observation.get('entity_bindings',{}).get(mention_ref)
            from .referential_placeholder import payload as unknown_reference, uid as reference_uid
            placeholder=unknown_reference(state,unit)
            mid=reference_uid(placeholder['referential_placeholder']) if placeholder else known or 'M:'+digest([state.source_uid,mention_ref])
            local=state.observation.get('local_reference_targets',{}).get(mid)
            if known and not local and not local_place and (not store.has_uid(known) or store._store.kind_of(known).value!='M'): raise ValueError('IDENTITY_CONFLICT')
            name=None if placeholder else local['label'] if local else unit.get('surface',ev.span)
            scalar=[]
            for measure in measures:
                if measure['value_role']==role:
                    from .scalar_values import scalar_property
                    value=scalar_property(unit.get('surface',ev.span),measure)
                    if value is not None and value not in scalar: scalar.append(value)
            if len({v['name'] for v in scalar})!=len(scalar): raise ValueError('SCALAR_VALUE_CONFLICT')
            from .qualitative_group_entity import payload as quantity_payload
            emit('ENSURE_ENTITY',{'uid':mid,'name':name,'mention_ref':local['mention_ref'] if local else mention_ref,'source_tag':tag,'reference_existing':bool(known and not local),
                                  **quantity_payload(f,tid), **placeholder,
                                  **({'scalar_properties':scalar} if scalar else {})},frag)
            bid='binding:'+digest([tag,mention_ref,mid])
            from .coreference import mention_features
            reading=f.semantic.get('morph_bindings',{}).get(tid,{})
            if reading:
                from dataclasses import replace
                from .native_frontend import _frame_variants
                ev=replace(ev,variants=_frame_variants(f,ev))
            emit('SET_IDENTITY_BINDING',{'binding_id':bid,'mention_ref':mention_ref,'target_ref':mid,'source_tag':tag,'premise_support_refs':state.observation.get('entity_binding_grounds',{}).get(mention_ref,[]),'mention_features':mention_features(ev),**({'binding_kind':'UNRESOLVED_NOMINAL',
                'reference_constraint':unit['reference_constraint']} if placeholder else {}),**(reference or {})},frag)
            mention_roles.setdefault(role,[]).append(mid)
            mention_entities[tid]=mid;mention_bindings[tid]=bid
        from .implicit_plan import emit_implicit_roles
        emit_implicit_roles(state,store,f,selected,tag,frag,roles,mention_roles,emit,frames,release)
        from .spatial_plan import emit_roles as emit_spatial_roles
        emit_spatial_roles(f,selected,tag,frag,roles,emit)
        for role,members in mention_roles.items():
            if len(members)==1: roles[role]=members[0]
            elif role=='SURFACE_ARG' or f.semantic.get('nominal_groups'):
                if role!='SURFACE_ARG':
                    from .component_nominal_groups import group_for
                    group_for(f,role,selected['roles'])
                members=sorted(set(members))
                kid='K:'+digest(members)
                emit('ENSURE_GROUP',{'uid':kid,'members':members},frag); roles[role]=kid
            else: raise ValueError('ARGUMENT_CARDINALITY_UNRESOLVED')
        for role,child in f.semantic.get('proposition_args',{}).items():
            roles[role]=tree_node(child.get('tree') or {'frame_ref':child['frame_ref']},frag,active)[0]
        sense=selected.get('sense_id')
        from .lexical_forms import selected_forms
        for token_ref in f.semantic.get('morph_bindings',{}):
            token=evidence[token_ref]
            if token_ref==f.predicate_token_ref or not token.is_oov():continue
            surface,lemma=selected_forms(f,token)
            emit('ENSURE_LEXICAL_FORMS',{'surface':surface,'lemma':lemma,
                'source_ref':token_ref,'source_tag':tag},frag)
        predicate_surface,predicate_lemma=selected_forms(f,e)
        if selected['sense_kind']=='KNOWN':
            schema_roles=description_schema_roles(selected,roles)
            mapping=next((m for m in release.entries('TemplateMap') if m['sense_id']==sense and set(m.get('roles',()))==schema_roles),None)
            if mapping is None or not store.has_uid(mapping['template_ref']) or store._store.kind_of(mapping['template_ref']).value!='T': raise ValueError('CANONICAL_MAPPING_MISSING')
            if {r.value for r in store._store.get_template(mapping['template_ref']).roles}!=schema_roles: raise ValueError('CANONICAL_MAPPING_MISSING')
            tid=mapping['template_ref']
        else:
            tid='T:open:'+digest([state.source_uid,f.predicate_token_ref,selected['candidate_id'],roles])
            emit('ENSURE_TEMPLATE',{'uid':tid,'predicate_form':predicate_surface,
                **({'predicate_lemma':predicate_lemma} if predicate_lemma else {}),
                'roles':sorted(description_schema_roles(selected,roles)),'semantic_status':'UNLINKED','source_ref':f.predicate_token_ref,'source_tag':tag},frag)
        content={'predicate':sense or tid,'actants':roles}
        ck=digest(content); mode=selected['state_class']; open_=selected['sense_kind']=='OPEN_LEXICAL'
        identity=[ck]
        if open_: identity.extend([state.source_uid,f.predicate_token_ref])
        elif mode!='STATE' and not structural: identity.extend([state.source_uid,state.interpretation_version,fid])
        nid='N:'+digest(identity)
        emit('ENSURE_NODE',{'uid':nid,'template_ref':tid,'actants':roles,'semantic_status':'UNLINKED' if open_ else 'KNOWN','temporal_mode':mode,'identity_key':identity,'content_key':ck,'polarity':True,'proposition':content,'source_tag':tag,'source_ref':f.predicate_token_ref,
            **({'action_description':{'unassigned_roles':selected.get('description_roles',[])}} if f.semantic.get('action_description') else {}),
            **({'lexical_anchor':predicate_lemma or predicate_surface.casefold()} if open_ else {})},frag)
        for role,child in f.semantic.get('proposition_args',{}).items():
            target=roles[role]
            qualification=content_time(frames[child['frame_ref']],target,tag) if child.get('frame_ref') else {}
            link='usage:'+digest([target,nid,role,'ATTITUDE',tag,*([qualification] if qualification else [])])
            emit('MATERIALIZE_USAGE_LINK',{'link_id':link,'node_ref':target,'parent_ref':nid,'position':role,'kind':'ATTITUDE','attitude':child['attitude'],'holder_ref':roles.get(child.get('holder_role','SUBJECT')),'source_tag':tag,**qualification},frag)
        for child in f.semantic.get('nominal_args',()):
            target,_=tree_node(child['tree'],frag,active) if child.get('tree') else node_for(child['frame_ref'],frag,True,active)
            from .refinement_host_path import node_path
            host_path=node_path(child,frames,nodes,root_node=target,operations=op_by_id.values())
            host_role=child.get('host_implicit_role')
            if host_role is not None and host_role not in selected.get('implicit_roles',()):
                raise ValueError('NOMINAL_HOST_UNRESOLVED')
            if host_role is None:
                members=child.get('host_group_member_refs',[child['host_token_ref']])
                host_roles={selected['roles'].get(t) for t in members}
                if len(host_roles)!=1 or None in host_roles:raise ValueError('NOMINAL_HOST_UNRESOLVED')
                host_role=next(iter(host_roles))
            if host_role is None or host_role not in roles: raise ValueError('NOMINAL_HOST_UNRESOLVED')
            host_ref=roles[host_role];member_link={}
            single=child.get('host_token_ref') if not child.get('host_group_member_refs') else None
            if single in mention_entities and mention_entities[single]!=host_ref:
                from .component_nominal_groups import group_for
                group=group_for(f,host_role,selected['roles'])
                if single not in group['member_refs']:raise ValueError('NOMINAL_HOST_UNRESOLVED')
                member_link={'host_group_ref':host_ref,'host_member_binding_ref':mention_bindings[single]}
                host_ref=mention_entities[single]
            nominal_links.append((frag,{'node_ref':target,'parent_ref':nid,'position':host_role,
                'kind':'NOMINAL','attitude':'UNKNOWN','host_ref':host_ref,**member_link,
                'host_role':child['host_role'],'source_tag':tag,
                **content_time(frames[child['frame_ref']],target,tag),
                **({'scope_assumption':child['scope_assumption']} if child.get('scope_assumption') else {}),
                **({'host_path':host_path} if len(host_path)>1 else {})}))
        nodes[fid]=nid
        return nid,ck

    def tree_node(tree,frag,active=None):
        if 'count_literal' in tree: return tree,digest(tree)
        if 'time_literal' in tree: return tree,digest(tree)
        if 'bound_var' in tree: return tree,digest(tree)
        if 'frame_ref' in tree: return node_for(tree['frame_ref'],frag,True,active)
        fid=tree['operator']
        children=[tree_node(t,frag,active) for t in tree['operands']]
        if fid in {'AND','OR','XOR'}: children.sort(key=lambda item:item[0])
        ops=[n for n,c in children]
        if fid in {'BEFORE','AFTER','DURING'}:
            from ah.model import TimeLiteral
            from .temporal_order import compare_anchors
            if len(ops)!=2 or any(not isinstance(n,str) and (not isinstance(n,dict) or set(n)!={'time_literal'}) for n in ops): raise ValueError('TEMPORAL_ANCHOR_UNKNOWN')
            if all(isinstance(n,dict) for n in ops) and compare_anchors(fid,*(TimeLiteral(tuple(n['time_literal'])) for n in ops)) is False: raise ValueError('CONSTRAINT_CONFLICT')
        if fid in {'FORALL','EXISTS'} and (len(ops)!=2 or not isinstance(ops[0],dict) or 'bound_var' not in ops[0]): raise ValueError('BOUND_VAR_REQUIRED')
        if fid in {'AT_LEAST_N','EXACTLY_N','AT_MOST_N'}:
            if len(ops)!=3 or not isinstance(ops[0],dict) or 'bound_var' not in ops[0] or not isinstance(ops[2],dict) or set(ops[2])!={'count_literal'}:
                raise ValueError('NUMERIC_SCOPE_INVALID')
        uid='G:'+digest([fid,ops])
        content_key=children[0][1] if fid=='NOT' else digest([fid,[c for n,c in children]])
        polarity=True
        if fid=='NOT':
            child=next(o.payload for o in op_by_id.values() if o.op_type in {'ENSURE_NODE','ENSURE_FUNCTION'} and o.payload['uid']==ops[0])
            polarity=not child.get('polarity',True)
        emit('ENSURE_FUNCTION',{'uid':uid,'function_id':fid,'operands':ops,'content_key':content_key,'polarity':polarity},frag)
        for position,n in enumerate(ops):
            if not isinstance(n,str): continue
            emit('MATERIALIZE_USAGE_LINK',{'link_id':'usage:'+digest([n,uid,position,'OPERATOR']),'node_ref':n,'parent_ref':uid,'position':position,'kind':'OPERATOR'},frag)
        return uid,content_key

    def support(uid,frag,reg,*,kind='ROOT',premises=(),rule=None,witness_ref=None,formula_ref=None,include_nominal_links=True):
        sid='support:'+digest([tag,frag,uid,kind,rule,premises])
        bindings=[op.payload['binding_id'] for op in op_by_id.values() if op.op_type=='SET_IDENTITY_BINDING' and frag in op.fragment_refs]
        raw={'record_id':sid,'conclusion_ref':uid,'kind':kind,'source_tag':tag,'binding_refs':bindings}
        if kind=='ROOT': raw['ground_type']='O'
        else: raw.update(rule_id=rule,premise_support_refs=list(premises))
        if formula_ref is not None: raw['formula_ref']=formula_ref
        emit('ADD_ROOT_SUPPORT' if kind=='ROOT' else 'ADD_DERIVED_SUPPORT',raw,frag)
        if kind=='ROOT' and include_nominal_links:
            from .nominal_usage import link_id
            for owner,payload in nominal_links:
                if owner==frag:
                    payload={**payload,'root_support_ref':sid}
                    emit('MATERIALIZE_USAGE_LINK',{'link_id':link_id(payload),**payload},frag)
        if reg:
            aid='assertion:'+digest([sid,reg])
            prov={'source':{'kind':'OBSERVATION','source_tag':tag},'support':{'kind':kind}}
            if kind=='DERIVED': prov['support'].update(rule_id=rule,premise_support_refs=list(premises))
            emit('ADD_TIME_ASSERTION',{'assertion_id':aid,'target_ref':uid,'support_record_id':sid,'region':reg,'anchor':state.observation.get('time_anchor'),'provenance':prov,'witness_ref':witness_ref,
                **({'temporal_expressions':reg['expressions']} if reg.get('expressions') else {})},frag)
        if kind=='ROOT':
            rows=[]; morphology=[]; shapes=[]
            owned={op.payload['uid'] for op in op_by_id.values() if op.op_type=='ENSURE_NODE' and frag in op.fragment_refs}
            for frame in state.frames:
                if nodes.get(frame.frame_id) not in owned: continue
                dec=state.decisions.get(frame.frame_id+'|predicate_value')
                selected=frame.semantic.get('candidate_specs',{}).get(dec.selected[0]) if dec and len(dec.selected)==1 else None
                if not selected: continue
                ev=evidence[frame.predicate_token_ref]
                from .native_frontend import _frame_variants
                readings=_frame_variants(frame,ev)
                morphology.append({'surface':ev.span,'variants':[{'lemma':v.lemma,'POS':v.pos} for v in readings]})
                shapes.append({'construction':frame.construction,'role_ids':sorted(set(selected['roles'].values()))})
                # A grammatical constructor is not a lexical sense of the noun
                # serving as its source anchor. Never learn that false R-X prior.
                if (not frame.semantic.get('nominal_dependency_kind') and selected.get('sense_id')
                        and len(frame.semantic.get('lexical_units',{}).get(frame.predicate_token_ref,{}).get('anchor_refs',()))<=1):
                    rows.extend({'lemma':v.lemma,'POS':v.pos,'sense_id':selected['sense_id']} for v in readings if v.lemma)
            emit('WRITE_COMMITTED_RX',{'record_id':'rx:'+digest([tag,frag,sid]),'source_tag':tag,
                'support_record_id':sid,'resource_snapshot':state.resource_snapshot,
                'stages':{'T1':{'morphological_priors':morphology},'T2':{'structural_priors':shapes},'T3':{'semantic_priors':rows}}},frag)
        return sid

    from .composition_tree import forests as composition_forests, embedded, leaves as leaf_refs
    forests=composition_forests(state.frames,state.logical_roots)
    structural_leaves=embedded(state.frames,forests)
    from .component_policy import rejected
    roots=[(f.frame_id,{'frame_ref':f.frame_id}) for f in state.frames if f.frame_id not in structural_leaves and not f.semantic.get('coordination_owner') and not rejected(state,f)]
    roots += [('logical:'+digest(t)[:16],t) for t in forests]
    from .source_assertions import roots as source_asserted_roots
    roots += source_asserted_roots(state,release)
    for frag,t in roots:
        refs=leaf_refs(t); fs=[frames[f] for f in sorted(refs)]
        if any(f.semantic.get('temporal_unresolved') for f in fs):
            diagnostics.append('WAITING_CONTEXT:'+frag); continue
        # Speech act and attitudes are structural guards; they do not confirm content.
        is_query=any(f.semantic.get('query_request') or f.semantic.get('discourse_scope',{}).get('speech_act')=='QUERY' for f in fs)
        is_command=any(f.semantic.get('discourse_scope',{}).get('speech_act')=='COMMAND' for f in fs)
        if any(f.semantic.get('discourse_scope',{}).get('speech_act') in {None,'UNKNOWN'} for f in fs):
            diagnostics.append('SPEECH_ACT_UNRESOLVED:'+frag);continue
        quoted=any(f.semantic.get('quoted') for f in fs)
        requested=state.observation.get('request_kind')
        if requested in {'QUERY','COMMAND','UNKNOWN'}:
            diagnostics.append(('MODUS_UNKNOWN' if requested=='UNKNOWN' else 'SPEECH_ACT_'+requested)+':'+frag); continue
        if requested is not None and requested not in {'ASSERTION','STATEMENT','MIXED'}:
            diagnostics.append('INPUT_REJECTED:unknown request_kind:'+frag); continue
        quoted=quoted or any(f.semantic.get('discourse_scope',{}).get('speech_act')=='CONTENT' and not f.semantic.get('component_child') for f in fs)
        if is_query or is_command or quoted:
            diagnostics.append(('SPEECH_ACT_QUERY' if is_query else 'SPEECH_ACT_COMMAND' if is_command else 'QUOTED_CONTENT')+':'+frag); continue
        regions=[f.semantic.get('region') for f in fs]
        owners={f.semantic.get('time_scope_owner') for f in fs if 'time_scope_owner' in f.semantic}
        reg=t.get('region') or (regions[0] if regions and len({digest(r) for r in regions})==1 and len(owners)<=1 else None)
        before=dict(op_by_id)
        nominal_before=len(nominal_links)
        try:
            from .action_descriptions import validate_scope
            validate_scope(t,frames)
            if 'frame_ref' in t:
                f=frames[t['frame_ref']]
                # Scope belongs to the sealed tree. The writer must never
                # reinterpret a source span and introduce another NOT.
                uid,ck=node_for(f.frame_id,frag,False)
                polarity=next(op.payload['polarity'] for op in op_by_id.values() if op.op_type in {'ENSURE_NODE','ENSURE_FUNCTION'} and op.payload['uid']==uid)
            else:
                uid,ck=tree_node(t,frag)
                polarity=next(op.payload['polarity'] for op in op_by_id.values() if op.op_type in {'ENSURE_NODE','ENSURE_FUNCTION'} and op.payload['uid']==uid)
            observed = (state.observation.get('text') == state.text
                        and state.observation.get('observation_id') == state.source_uid
                        and state.observation.get('interpretation_version') == state.interpretation_version)
            gate=FragmentT5Input(frag,'RESOLVED',truth_grounds=('O',) if observed else ())
            ok,code=evaluate_fragment(gate)
            if not ok: raise ValueError(code)
            witness='witness:'+digest([tag,frag,reg]) if reg and t.get('operator')=='AND' else None
            sid=support(uid,frag,reg,witness_ref=witness)
            # A member is asserted only with the admitted fragment; no closed K.
            for op in list(op_by_id.values()):
                if op.op_type=='ENSURE_NODE' and op.payload.get('narrative_membership') and frag in op.fragment_refs:
                    support(op.payload['uid'],frag,None,include_nominal_links=False)
            def describe(n,key,polarity,own_region=reg):
                spec=next(op.payload for op in op_by_id.values() if op.op_type in {'ENSURE_NODE','ENSURE_FUNCTION'} and op.payload['uid']==n)
                prop=spec.get('proposition')
                if spec.get('function_id')=='NOT':
                    child=spec['operands'][0]
                    prop=next((op.payload.get('proposition') for op in op_by_id.values() if op.op_type=='ENSURE_NODE' and op.payload['uid']==child),None)
                emit('DECLARE_FRAGMENT',{'fragment_id':frag,'content_key':key,'polarity':polarity,'proposition':prop,'region':own_region,'source_tag':tag,'node_ref':n,'witness_ref':witness if own_region==reg else None,'incompatibility_rules':release.entries('IncompatibilityRules')},frag)
            describe(uid,ck,polarity)
            for op in list(op_by_id.values()):
                if op.op_type=='ENSURE_NODE' and op.payload.get('narrative_membership') and frag in op.fragment_refs:
                    describe(op.payload['uid'],op.payload['content_key'],True,None)
            # A single existential AND asserts a common witness. Preserve its
            # correlation ID on the derived conjunct evidence; don't infer two
            # independently timed occurrences from unrelated evidence.
            if t.get('operator')=='AND':
                for child in t['operands']:
                    n,key=tree_node(child,frag)
                    formula_ref=n
                    spec=next(op.payload for op in op_by_id.values() if op.op_type in {'ENSURE_NODE','ENSURE_FUNCTION'} and op.payload['uid']==n)
                    # A formula operand and an asserted EVENT occurrence are
                    # distinct identities. STATE keeps its canonical node.
                    if spec.get('template_ref') and spec.get('temporal_mode')!='STATE':
                        n='N:and:'+digest([tag,frag,sid,formula_ref])
                        occurrence={**spec,'uid':n,'formula_ref':formula_ref,
                                    'identity_key':[key,'AND_ELIMINATION',sid,formula_ref]}
                        occurrence.pop('op_id',None)
                        emit('ENSURE_NODE',occurrence,frag)
                    child_region=frames[child['frame_ref']].semantic.get('region') if 'frame_ref' in child else child.get('region',reg)
                    describe(n,key,spec.get('polarity',True),child_region)
                    support(n,frag,child_region,kind='DERIVED',premises=[sid],rule='AND_ELIMINATION',witness_ref=witness if child_region==reg else None,formula_ref=formula_ref)
            from .relative_time_plan import emit_relative_time
            scope_owner=next((f for f in state.frames if f.semantic.get('component_scope_tree')==t
                              and not f.semantic.get('component_child') and not f.semantic.get('structural_unresolved')),None)
            if 'frame_ref' in t or scope_owner is not None:
                owner=scope_owner if scope_owner is not None else frames[t['frame_ref']]
                emit_relative_time(state,owner,uid,ck,frag,tag,emit,support)
                for scope in owner.semantic.get('relative_time_targets',()):
                    target=nodes[scope['frame_ref']]
                    spec=next(op.payload for op in op_by_id.values() if op.op_type=='ENSURE_NODE' and op.payload['uid']==target)
                    emit_relative_time(state,owner,target,spec['content_key'],frag,tag,emit,support,rows=scope['rows'])
            fragments.append(frag)
        except (ValueError,KeyError) as exc:
            del nominal_links[nominal_before:]
            op_by_id=before; blocked.add(frag); diagnostics.append(str(exc)+':'+frag)
    previous=state.observation.get('supersedes_version')
    if previous is not None and fragments:
        if not isinstance(previous,int) or isinstance(previous,bool) or not 0<previous<state.interpretation_version or not state.observation.get('trigger_ref'):
            return (),(),tuple(diagnostics+['DECLARED_TRIGGER_REQUIRED']),nodes
        # RESOLUTION_ONLY has a durable input/decision but no stored assertion
        # version to retire. A clarified first commit must not fail admission.
        if digest([state.source_uid, previous]) in store.ledger.data['observations']:
            for frag in fragments:
                emit('SUPERSEDE_VERSION',{'source_tag':[state.source_uid,previous],
                     'replacement_tag':tag,'trigger_ref':state.observation['trigger_ref']},frag)
        live_paths=store.ledger.paths()
        for link in state.observation.get('open_template_links',()):
            source,target=link.get('source_t_ref'),link.get('canonical_t_ref')
            old_nodes=[n for n in store.ledger.data['nodes'].values() if n.get('template_ref')==source and n.get('semantic_status')=='UNLINKED']
            anchors={n.get('source_ref') or (n.get('identity_key') or [None,None,None])[-1] for n in old_nodes}
            replay=digest({'observation_id':state.source_uid,'interpretation_version':state.interpretation_version}) in store.ledger.data['markers']
            valid_evidence={sid for sid,s in store.ledger.data['supports'].items()
                            if (sid in live_paths or replay and s.get('status')=='SUPERSEDED')
                            and s.get('source_tag')==[state.source_uid,previous]
                            and any(n.get('uid')==s['conclusion_ref'] for n in old_nodes)}
            matching=[op for op in op_by_id.values() if op.op_type=='ENSURE_NODE'
                      and op.payload.get('semantic_status')=='KNOWN' and op.payload['template_ref']==target
                      and op.payload.get('source_ref') in anchors]
            if not source or not matching or not link.get('evidence_refs') or not set(link['evidence_refs'])<=valid_evidence:
                return (),(),tuple(diagnostics+['MIGRATION_LINK_INVALID']),nodes
            payload={'link_id':'template-migration:'+digest([source,target,tag]),
                     'source_t_ref':source,'canonical_t_ref':target,'source_tag':[state.source_uid,previous],
                     'replacement_tag':tag,'evidence_refs':list(link['evidence_refs']),
                     'resource_snapshot':state.resource_snapshot,'migration_version':state.interpretation_version,
                     'trigger_ref':state.observation['trigger_ref']}
            for op in matching:
                for frag in op.fragment_refs: emit('LINK_OPEN_TEMPLATE',payload,frag)
    return tuple(op_by_id.values()),tuple(fragments),tuple(diagnostics),nodes
