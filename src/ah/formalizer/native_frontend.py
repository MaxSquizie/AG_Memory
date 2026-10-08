"""Resource-driven frame generation and sealed, bounded semantic selection.

Syntax proposes; released R-S/R-V resources and a validated local TP proposal
supply candidates. No word order heuristic asserts roles, no demo sense set is
used, and missing resources never become CHECKED_EMPTY.
"""
from __future__ import annotations
from dataclasses import asdict
from datetime import datetime, timedelta
import itertools
import json
import re
from .canonical_ledger import digest
from .pipeline import t0,t1,td
from .state import FrameCandidate,Decision,Ground,LinkedAlternative,ResourceProvenance,MorphVariant
from .seal import structural_seal
from .selection_protocol import Relation,DecisionSchema,build_selection_prompt,validate_selection_response,ProtocolError
from .t3_sources import build_source_traces
from .tp_proposer import StructureProposalRequest,parse_and_validate
from .syntax_rules import run_srl, propose_graphs, SearchLimit

OPERATORS={'NOT','AND','OR','XOR','IMPLIES','FORALL','EXISTS','POSSIBLE','NECESSARY','COUNTERFACTUAL','BEFORE','AFTER','DURING','ASSOCIATION'}


def _failure_code(exc,default):
    from .provider_adapter import BudgetExceeded,IntegrityError,ProviderUnavailable
    from .fake_selector import ProviderUnavailableError
    if isinstance(exc,BudgetExceeded): return exc.code
    if isinstance(exc,IntegrityError): return 'REPLAY_MISMATCH'
    if isinstance(exc,(ProviderUnavailable,ProviderUnavailableError)): return 'PROVIDER_UNAVAILABLE'
    return default


def _temporal(text, observation, release):
    def clock(day,hour,minute):
        if not 0<=hour<24 or not 0<=minute<60: raise ValueError('TEMPORAL_EXPRESSION_INVALID')
        local=day.replace(hour=hour,minute=minute)
        if local.replace(fold=0).utcoffset()!=local.replace(fold=1).utcoffset():
            raise ValueError('REFERENCE_UNKNOWN')  # ambiguous/nonexistent civil time
        return local.timestamp()
    matched=[]
    resources=release.resources.get('TemporalRules')
    if resources is None:
        return None,[]
    for rule in resources['entries']:
        m=re.search(rule['pattern'],text,flags=re.I)
        if not m: continue
        anchor=observation.get('time_anchor')
        if anchor is None: return None,['REFERENCE_UNKNOWN']
        try: day=datetime.fromisoformat(anchor.replace('Z','+00:00')).replace(hour=0,minute=0,second=0,microsecond=0)
        except (ValueError,AttributeError): return None,['TEMPORAL_EXPRESSION_INVALID']
        if day.tzinfo is None:
            if not observation.get('timezone'): return None,['REFERENCE_UNKNOWN']
            from zoneinfo import ZoneInfo,ZoneInfoNotFoundError
            try: day=day.replace(tzinfo=ZoneInfo(observation['timezone']))
            except (ZoneInfoNotFoundError,ValueError): return None,['REFERENCE_UNKNOWN']
        day+=timedelta(days=int(rule.get('day_offset',0)))
        start=day.timestamp()
        if rule['kind']=='POINT_CLOCK':
            hour=int(m.group(rule.get('hour_group','hour'))); minute=int(m.group(rule.get('minute_group','minute')))
            if not 0<=hour<24 or not 0<=minute<60: return None,['TEMPORAL_EXPRESSION_INVALID']
            try: timestamp=clock(day,hour,minute)
            except ValueError as exc: return None,[str(exc)]
            matched.append({'kind':'POINT','point':timestamp})
        elif rule['kind']=='DAY_INTERVAL':
            matched.append({'kind':rule.get('interval_semantics','EXISTENTIAL'),'lo':start,'hi':(day+timedelta(days=1)).timestamp()-0.000001})
        elif rule['kind']=='INTERVAL_CLOCK':
            try:
                lo=clock(day,int(m.group('start_hour')),int(m.group('start_minute')))
                hi=clock(day,int(m.group('end_hour')),int(m.group('end_minute')))
            except ValueError as exc: return None,[str(exc)]
            if lo>hi: return None,['TEMPORAL_EXPRESSION_INVALID']
            matched.append({'kind':rule.get('interval_semantics','EXISTENTIAL'),'lo':lo,'hi':hi})
        else: return None,['TEMPORAL_RULE_UNKNOWN']
    if len({digest(x) for x in matched})>1: return None,['TEMPORAL_SCOPE_UNRESOLVED']
    return (matched[0] if matched else None),[]


def _required_operators(state,release):
    required=[]
    for entry in release.entries('ScopeLexicon'):
        if not entry.get('operator') or not entry.get('pattern'): continue
        for match in re.finditer(entry['pattern'],state.text,re.I):
            required.append((entry['operator'],tuple(e.token_id for e in state.evidence if e.start<match.end() and e.end>match.start())))
    return tuple(required)


def _grammar_frames(state,release):
    p=release.entries('ProposalPolicy')[0]
    source=tuple(e.token_id for e in state.evidence)
    request=StructureProposalRequest('syntax:'+state.source_uid,'',source,allowed_node_kinds=frozenset({'PREDICATE','ENTITY','BOUND_VAR',*OPERATORS}),
        allowed_edge_kinds=frozenset({'ARGUMENT','OPERAND','ATTITUDE','BIND'}),allowed_role_ids=frozenset(x['role_id'] for x in release.entries('RoleRegistry')),
        max_nodes=p['max_nodes'],max_edges=p['max_edges'],max_depth=p['max_depth'],required_operators=_required_operators(state,release))
    try:
        hypotheses,provenance,morph_bindings=propose_graphs(state,release,request)
        accepted=_frames_for_hypotheses(state,hypotheses,release,provenance,morph_bindings)
    except (SearchLimit,ProtocolError) as exc:
        state.grammar_search_incomplete=True
        state.diag('COMPUTATION_LIMIT' if isinstance(exc,SearchLimit) else 'STRUCTURE_NOT_COVERED',str(exc)); return []
    # Multiple overlapping structures are alternatives, never multiple facts.
    by_anchor={}
    for h,frames in accepted:
        for frame in frames:
            by_anchor.setdefault(frame.predicate_token_ref,set()).add(h.local_id)
    frames=[]
    for h,local in accepted:
        ambiguous=any(len(by_anchor[f.predicate_token_ref])>1 for f in local)
        state.linked_alternatives.append(LinkedAlternative(h.local_id,'STRUCTURAL_HYPOTHESIS',digest(asdict(h)),h.local_id,provenance=provenance[h.local_id]))
        for f in local:
            f.semantic['structural_unresolved'] |= ambiguous
        frames.extend(local)
    return frames


def _frame_variants(frame, evidence):
    bindings=frame.semantic.get('morph_bindings',{})
    if evidence.token_id not in bindings: return evidence.variants
    value=bindings[evidence.token_id]
    if value is None: return ()
    return (MorphVariant(**{**value,'cases':frozenset(value['cases']),'features':frozenset(value['features'])}),)


def _frames_for_hypotheses(state,hypotheses,release,provenance=None,morph_bindings=None):
    provenance=provenance or {}
    morph_bindings=morph_bindings or {}
    bytoken={e.token_id:e for e in state.evidence}
    accepted=[]
    unsupported=False
    for h in hypotheses:
        if any(n.kind in {'PREDICATE','ENTITY'} and len(n.anchor_spans)!=1 for n in h.nodes):
            unsupported=True
            state.grammar_search_incomplete=True
            state.diag('STRUCTURE_NOT_COVERED','multi-head lexical anchors are not closed by the runtime'); continue
        localframes={}
        proposition_nodes={}
        variable_ids={i:i+1 for i,n in enumerate(h.nodes) if n.kind=='BOUND_VAR'}
        for i,n in enumerate(h.nodes):
            if n.kind!='PREDICATE': continue
            if len(n.anchor_spans)!=1: state.diag('PROPOSAL_INVALID','predicate must have one lexical anchor'); continue
            anchor=bytoken[n.anchor_spans[0]]
            args=[]; roles={}; propositions={}; bound_args={}; incomplete=False
            for edge in h.edges:
                if edge.from_idx!=i or edge.kind not in {'ARGUMENT','ATTITUDE'}: continue
                target=h.nodes[edge.to_idx]
                if target.kind=='PREDICATE' or target.kind in OPERATORS:
                    proposition_nodes[(i,edge.role_id)]=edge.to_idx
                    bound=morph_bindings.get(h.local_id,{}).get(anchor.token_id)
                    lemmas={bound['lemma']} if bound is not None else {v.lemma for v in anchor.variants}
                    attitudes=[a for a in release.entries('AttitudeMap') if a['lemma'] in lemmas and a.get('argument_role')==edge.role_id]
                    if not attitudes:
                        state.diag('ATTITUDE_UNKNOWN','proposition slot has no declared attitude')
                        propositions[edge.role_id]={'attitude':'UNKNOWN'}
                        continue
                    if len({(a['attitude'],a.get('holder_role','SUBJECT')) for a in attitudes})>1:
                        state.diag('ATTITUDE_UNKNOWN','different admissible parses give different attitudes')
                        propositions[edge.role_id]={'attitude':'UNKNOWN'}
                    else:
                        propositions[edge.role_id]={'attitude':attitudes[0].get('attitude','UNKNOWN'),'holder_role':attitudes[0].get('holder_role','SUBJECT')}
                    continue
                if target.kind!='ENTITY' or len(target.anchor_spans)!=1:
                    state.diag('PROPOSAL_INVALID','entity argument not closed'); incomplete=True; continue
                tid=target.anchor_spans[0]; args.append(tid)
                if edge.role_id: roles[tid]=edge.role_id
                for binding in h.edges:
                    if binding.kind=='BIND' and binding.to_idx==edge.to_idx and binding.from_idx in variable_ids:
                        bound_args[tid]=variable_ids[binding.from_idx]
            fid='TP:'+h.local_id+':'+str(i)
            f=FrameCandidate(fid,'FLAT',anchor.span,tuple([anchor.span,*[bytoken[a].span for a in args]]),tuple(bytoken[a].span for a in args),construction='GRAMMAR' if h.local_id in provenance else 'TP',predicate_token_ref=anchor.token_id,argument_token_refs=tuple(args),source_range=(min(bytoken[a].start for a in h.alignment),max(bytoken[a].end for a in h.alignment)),semantic={'proposed_roles':roles,'hypothesis':h.local_id,'proposition_args':propositions,'bound_arguments':bound_args,'structural_unresolved':incomplete,'morph_bindings':morph_bindings.get(h.local_id,{})},provenance=provenance.get(h.local_id,ResourceProvenance(('TP_VALIDATED',),{'release':release.sha256})))
            localframes[i]=f
        # Logical roots preserve the entire operator tree and operand directions.
        roots=set(range(len(h.nodes)))-{e.to_idx for e in h.edges if e.kind in {'OPERAND','ATTITUDE','ARGUMENT','BIND'}}
        def tree(i):
            n=h.nodes[i]
            if n.kind=='BOUND_VAR': return {'bound_var':variable_ids[i],'sort':'ENTITY'}
            if n.kind=='PREDICATE': return {'frame_ref':localframes[i].frame_id} if i in localframes else None
            if n.kind not in OPERATORS: return None
            children=[tree(e.to_idx) for e in h.edges if e.from_idx==i and e.kind=='OPERAND']
            if not children or any(c is None for c in children): return None
            return {'operator':n.kind,'operands':children,'anchor_refs':list(n.anchor_spans)}
        forest=[tree(i) for i in sorted(roots) if h.nodes[i].kind in OPERATORS]
        children={key:tree(idx) for key,idx in proposition_nodes.items()}
        if any(t is None for t in [*forest,*children.values()]):
            unsupported=True
            state.grammar_search_incomplete=True
            state.diag('PROPOSAL_INVALID','incomplete logical root'); continue
        for (idx,role),child in children.items():
            localframes[idx].semantic['proposition_args'][role]['tree']=child
        for f in localframes.values(): f.semantic['operator_forest']=forest
        accepted.append((h,list(localframes.values())))
    # An unsupported reading cannot silently disappear and turn the remaining
    # prefix into a uniquely resolved structure.
    return [] if unsupported else accepted


def _propose(state,selector,release):
    covered={f.predicate_token_ref for f in state.frames}
    uncovered=[e.token_id for e in state.evidence if e.token_id not in covered and any(v.pos in {'VERB','INFN','PRED','ADJS'} for v in e.variants)]
    attitude_lemmas={a['lemma'] for a in release.entries('AttitudeMap')}
    scope_required=state.grammar_search_incomplete or any(f.semantic.get('structural_unresolved') for f in state.frames)
    scope_required |= any(e.token_id not in covered and any(v.lemma in attitude_lemmas for v in e.variants) for e in state.evidence)
    trees=[t for f in state.frames for t in f.semantic.get('operator_forest',())]
    trees.extend(child['tree'] for f in state.frames for child in f.semantic.get('proposition_args',{}).values() if child.get('tree'))
    def scoped(operator,anchors,tree):
        return (tree.get('operator')==operator and bool(set(tree.get('anchor_refs',())) & set(anchors))) or any(scoped(operator,anchors,t) for t in tree.get('operands',()))
    required=_required_operators(state,release)
    scope_required |= any(not any(scoped(operator,anchors,t) for t in trees) for operator,anchors in required)
    scope_required |= any(e.span in {'«','»','"'} for e in state.evidence) and not any(f.semantic.get('proposition_args') for f in state.frames)
    verify=bool(release.entries('ProposalPolicy')[0].get('verify_deterministic',False))
    if state.frames and not uncovered and not scope_required and not verify: return
    if scope_required or verify:
        # An unclosed scope may not be flattened into independently asserted clauses.
        for f in state.frames: f.semantic['structural_unresolved']=True
    policy=release.entries('ProposalPolicy')
    if not policy or not hasattr(selector,'propose_local'):
        state.diag('STRUCTURE_NOT_COVERED','no declared TP capability/policy'); return
    if state.budget.llm_exhausted:
        state.diag('COMPUTATION_LIMIT','TP budget exhausted'); return
    p=policy[0]
    source=tuple(e.token_id for e in state.evidence)
    if len(source)>p.get('max_source_tokens',256):
        state.diag('COMPUTATION_LIMIT','local TP source region too large; no truncation'); return
    req=StructureProposalRequest('TP:'+state.source_uid,digest([asdict(f) for f in state.frames]),source,deterministic_candidates=tuple(asdict(f) for f in state.frames),uncovered_spans=tuple(uncovered),allowed_node_kinds=frozenset({'PREDICATE','ENTITY','BOUND_VAR',*OPERATORS}),allowed_edge_kinds=frozenset({'ARGUMENT','OPERAND','ATTITUDE','BIND'}),allowed_role_ids=frozenset(x['role_id'] for x in release.entries('RoleRegistry')),schema_version='v7',max_nodes=p.get('max_nodes',64),max_edges=p.get('max_edges',128),max_depth=p.get('max_depth',16),budget_ok=not state.budget.llm_exhausted,required_operators=tuple(required))
    prompt=json.dumps({'task':'propose bounded local syntax; return hypotheses or abstain. Each node has kind and anchor_spans of supplied token IDs; each edge has kind, from, to, optional role_id, scope. No canonical IDs.','request':{**asdict(req),'allowed_node_kinds':sorted(req.allowed_node_kinds),'allowed_edge_kinds':sorted(req.allowed_edge_kinds),'allowed_role_ids':sorted(req.allowed_role_ids)},'tokens':[{'id':e.token_id,'text':e.span,'variants':[asdict(v) for v in e.variants]} for e in state.evidence]},ensure_ascii=False,default=lambda x:sorted(x) if isinstance(x,(set,frozenset)) else str(x))
    try:
        state.budget.spend_llm(); raw=selector.propose_local(prompt)
        hypotheses=parse_and_validate(req,raw)
    except Exception as exc:
        state.diag(_failure_code(exc,'PROPOSAL_INVALID'),str(exc)); return
    if not hypotheses:
        state.diag('STRUCTURE_NOT_COVERED','TP abstained'); return
    accepted=_frames_for_hypotheses(state,hypotheses,release)
    if not accepted: return
    tp_provenance=ResourceProvenance(('TP_VALIDATED',),{'release':release.sha256})
    for h,fs in accepted:
        state.linked_alternatives.append(LinkedAlternative(h.local_id,'STRUCTURAL_HYPOTHESIS',digest(asdict(h)),h.local_id,provenance=tp_provenance))
    if len(accepted)>1:
        if state.budget.llm_exhausted:
            state.diag('COMPUTATION_LIMIT','TP hypothesis selection'); return
        ids={h.local_id for h,fs in accepted}
        relations={cid:Relation(cid,cid,0,(),json.dumps(asdict(h),ensure_ascii=False)) for h,fs in accepted for cid in [h.local_id]}
        schema=DecisionSchema(release.sha256,relations)
        prompt=json.dumps({'task':'select one grounded local hypothesis, MULTIPLE_ADMISSIBLE or INSUFFICIENT_CONTEXT; return outcome, selected and optional note',
                           'text':state.text,'candidates':[{'candidate_id':h.local_id,'structure':asdict(h)} for h,fs in accepted]},ensure_ascii=False)
        try:
            state.budget.spend_llm(); raw=selector.select(prompt)
            reply=validate_selection_response(raw,schema,allowed=frozenset(ids))
            state.syntax_trace.append({'stage':'TP','event':'STRUCTURE_SELECTION','candidates':sorted(ids),
                                       'outcome':reply.outcome,'selected':list(reply.selected)})
            if reply.outcome!='ONE_SELECTED':
                state.diag('STRUCTURE_UNRESOLVED','TP alternatives retained'); return
            chosen=reply.selected[0]
        except Exception as exc: state.diag(_failure_code(exc,'PROTOCOL_ERROR'),str(exc)); return
        for h,fs in accepted:
            if h.local_id!=chosen: state.reject(h.local_id,'TP_SELECTION','different validated hypothesis selected: '+chosen,tp_provenance)
        accepted=[pair for pair in accepted if pair[0].local_id==chosen]
    # A validated proposal replaces overlapping deterministic hypotheses only by
    # recorded discard; unrelated deterministic frames remain.
    fs=accepted[0][1]; anchors={f.predicate_token_ref for f in fs}
    for f in list(state.frames):
        if f.predicate_token_ref in anchors:
            state.reject(f.frame_id,'TP','selected validated TP hypothesis'); state.frames.remove(f)
    state.frames.extend(fs)


def _bindings(frame,evidence,valency):
    roles=valency.get('roles',())
    if any(not any(r['role_id']==role and set(r.get('argument_types',())) & {'PROPOSITION','EVENT'} for r in roles) for role in frame.semantic.get('proposition_args',{})):
        return []
    candidates=[]
    for tid in frame.argument_token_refs:
        e=evidence[tid]
        prep=None
        preceding=sorted((x for x in evidence.values() if frame.source_range[0]<=x.start<e.start),key=lambda x:x.start,reverse=True)
        for previous in preceding:
            variants=_frame_variants(frame,previous)
            if any(v.pos=='PREP' for v in variants):
                prep=next(v.lemma for v in variants if v.pos=='PREP'); break
            if not any(v.pos in {'ADJF','ADJS'} for v in variants): break
        allowed=[r['role_id'] for r in roles if any(set(r.get('allowed_cases',())) & set(v.cases) for v in _frame_variants(frame,e)) and (not r.get('allowed_preps') or prep in r['allowed_preps'])]
        proposed=frame.semantic.get('proposed_roles',{}).get(tid)
        if proposed and proposed not in allowed: return []
        if proposed: allowed=[proposed]
        if not allowed: return []
        candidates.append([(tid,r) for r in allowed])
    size=1
    for c in candidates: size*=len(c)
    if size>64: raise ValueError('COMPUTATION_LIMIT')
    out=[]
    for choice in itertools.product(*candidates):
        rs=[r for _,r in choice]
        if len(rs)!=len(set(rs)): continue
        if any(r.get('cardinality',{}).get('min',0)>0 and r['role_id'] not in rs and r['role_id'] not in frame.semantic.get('proposition_args',{}) for r in roles): continue
        out.append(dict(choice))
    return out


def run_native(text,selector,release,observation,morph=None):
    release.assert_integrity()
    state=t0(text); state.source_uid=observation['observation_id']; state.interpretation_version=observation['interpretation_version']; state.observation=dict(observation)
    state.resource_snapshot={'snapshot_id':release.sha256,'release_version':release.manifest['version']}
    state.context_facts=tuple(observation.get('context_facts',()))
    run_srl(state,release,morph)
    t1(state,morph=morph,preserve_variants=True,shared_form_expansion=False)
    # R-X is ordering experience only; it never adds/removes dictionary parses.
    rx1=[x for rec in observation.get('rx_reads',{}).get('T1',()) for x in rec['payload'].get('morphological_priors',())]
    for ev in state.evidence:
        preferred={(v['lemma'],v['POS']) for x in rx1 if x['surface']==ev.span for v in x['variants']}
        ev.variants=tuple(sorted(ev.variants,key=lambda v:(-int((v.lemma,v.pos) in preferred),-v.score)))
    state.frames=_grammar_frames(state,release)
    _propose(state,selector,release)
    preferred_shapes={x['construction'] for rec in observation.get('rx_reads',{}).get('T2',()) for x in rec['payload'].get('structural_priors',())}
    state.frames.sort(key=lambda f:(f.construction not in preferred_shapes,f.source_range,f.frame_id))
    td(state)
    evidence={e.token_id:e for e in state.evidence}
    candidate_specs={}
    for frame in state.frames:
        e=evidence[frame.predicate_token_ref]
        frame.semantic['quoted']=state.text[:e.start].count('«')>state.text[:e.start].count('»') or state.text[:e.start].count('\"')%2==1
        predicate_variants=_frame_variants(frame,e)
        lemmas={v.lemma for v in predicate_variants}
        schema_entries=[x for x in release.entries('PredicateSchema') if x['lemma'] in lemmas]
        declared_ids={sid for x in schema_entries for sid in x.get('value_ids',())}
        for x in schema_entries:
            for expansion in x.get('value_expansions',()): declared_ids.update(expansion['value_ids'])
        priors={x['sense_id'] for x in release.entries('R-X3') if x['lemma'] in lemmas}
        priors.update(x['sense_id'] for rec in observation.get('rx_reads',{}).get('T3',()) for x in rec['payload'].get('semantic_priors',()) if x['lemma'] in lemmas)
        context_senses=set(); blocked=set(); blocked_reasons={}
        for read in release.entries('DeclaredReads'):
            if read['lemma'] not in lemmas: continue
            records=observation.get('declared_reads',{}).get(read['read_id'])
            if records is None:
                blocked.add(4); blocked_reasons[4]='declared read unavailable:'+read['read_id']; continue
            for r in records:
                if r.get('source_kind') not in {'W','C'} or not r.get('source_ref') or r.get('snapshot_version')!=read['snapshot_version']:
                    blocked.add(4); blocked_reasons[4]='declared read provenance invalid:'+read['read_id']; continue
                context_senses.update(r.get('candidate_sense_ids',()))
        supplied_ids=declared_ids|priors|context_senses
        senses=[s for s in release.entries('R-S') if s['sense_id'] in supplied_ids or any(s['lemma']==v.lemma and s.get('POS') in {None,v.pos} for v in predicate_variants)]
        frame.semantic['has_known_senses']=bool(senses)
        specs=[]
        for s in senses:
            valencies=[v for v in release.entries('R-V') if v['sense_id']==s['sense_id']]
            for v in valencies:
                try: bindings=_bindings(frame,evidence,v)
                except ValueError:
                    frame.semantic['binding_budget_exhausted']=True; state.diag('COMPUTATION_LIMIT',frame.frame_id); continue
                for bs in bindings:
                    mode=v.get('temporal_mode_hint') or v.get('state_class') or 'UNKNOWN'
                    cid=s['sense_id']+':'+digest([bs,v])[:16]
                    specs.append({'candidate_id':cid,'sense_id':s['sense_id'],'label':s.get('label',s['sense_id']),'sense_kind':'KNOWN','roles':bs,'state_class':mode,'valency_ref':v.get('construction_id',digest(v))})
        open_spec=None
        if not senses:
            policy=release.entries('OpenTemplatePolicy')
            if policy and policy[0].get('allow',False):
                bs=frame.semantic.get('proposed_roles') or {tid:'SURFACE_ARG' for tid in frame.argument_token_refs}
                open_spec={'candidate_id':'open:'+digest([state.source_uid,frame.frame_id]),'label':e.span,'sense_kind':'OPEN_LEXICAL','roles':bs,'state_class':'UNKNOWN'}
                specs.append(open_spec)
        if senses and not specs: state.diag('VALENCY_UNKNOWN',frame.frame_id)
        known_specs=[s for s in specs if s['sense_kind']=='KNOWN']
        schema_ids=[s['candidate_id'] for s in known_specs if s['sense_id'] in declared_ids]
        traces=build_source_traces(frame.frame_id,'predicate_value',schema_candidates=schema_ids,rs_senses=[s['candidate_id'] for s in known_specs],rx3_prior=[s['candidate_id'] for s in known_specs if s['sense_id'] in priors],wc_reads=[s['candidate_id'] for s in known_specs if s['sense_id'] in context_senses],rx3_applicable=True,wc_applicable=True,open_candidate=open_spec['candidate_id'] if open_spec else None,open_path_verified=True,resource_versions=(release.sha256,),blocked=blocked,blocked_reasons=blocked_reasons)
        frame.semantic['source_blocked']=bool(blocked) or frame.semantic.get('binding_budget_exhausted',False)
        if any(x in priors|context_senses and not any(s['sense_id']==x for s in known_specs) for x in priors|context_senses):
            frame.semantic['source_blocked']=True
            state.diag('VALENCY_UNKNOWN','candidate source has sense without closed R-V:'+frame.frame_id)
        frame.semantic['candidate_specs']={s['candidate_id']:s for s in specs}
        frame.semantic['source_traces']=traces
        # Context and prior may rank, but never invent a canonical semantic value.
        frame.semantic['region'],temporal_diag=_temporal(text[frame.source_range[0]:frame.source_range[1]],observation,release)
        for code in temporal_diag: state.diag(code,frame.frame_id)
        frame.semantic['temporal_unresolved']=bool(temporal_diag)
        candidate_specs[frame.frame_id]=specs
    structural_seal(state)
    for f in state.frames:
        specs=candidate_specs[f.frame_id]; ids=tuple(s['candidate_id'] for s in specs)
        d=Decision('predicate_value',f.frame_id,ids); d.source_traces=f.semantic['source_traces']; state.decisions[f.frame_id+'|predicate_value']=d
        if f.semantic.get('source_blocked'):
            d.outcome='UNRESOLVED'; state.diag('SEARCH_INCOMPLETE',f.frame_id); continue
        if not specs:
            d.outcome='UNRESOLVED' if f.semantic['has_known_senses'] else 'NO_CANDIDATE'
            state.diag('CANDIDATE_SOURCE_EXHAUSTED' if not f.semantic['has_known_senses'] else 'VALENCY_UNKNOWN',f.frame_id); continue
        if len(specs)==1 and not f.semantic.get('structural_unresolved'):
            d.selected=ids; d.lifecycle='PROVISIONAL'; d.outcome='RESOLVED'
            d.grounds.append(Ground('R' if specs[0]['sense_kind']=='KNOWN' else 'D','one compatible released sense/valency or validated literal open structure',ids[0]))
            continue
        if state.budget.llm_exhausted:
            d.outcome='COMPUTATION_LIMIT'; state.diag('COMPUTATION_LIMIT',f.frame_id); continue
        relations={s['candidate_id']:Relation(s['candidate_id'],s['label'],len(s['roles']),tuple(s['roles'].values()),s['label']+'; frame temporal mode: '+s['state_class']+'; token-to-role mapping: '+json.dumps(s['roles'],ensure_ascii=False,sort_keys=True)) for s in specs}
        schema=DecisionSchema(release.sha256,relations)
        prompt=build_selection_prompt(slot_id=d.slot_id,frame_id=f.frame_id,context_span=text[f.source_range[0]:f.source_range[1]],mentions={tid:evidence[tid].span for tid in f.argument_token_refs},schema=schema,candidates=ids,contextual_statements=state.context_facts)
        try:
            state.budget.spend_llm(); raw=selector.select(prompt); reply=validate_selection_response(raw,schema,allowed=frozenset(ids))
        except Exception as exc:
            d.outcome='UNRESOLVED'; state.diag(_failure_code(exc,'PROTOCOL_ERROR'),str(exc)); continue
        d.last_prompt=prompt; d.raw_response=raw; d.selector_outcome=reply.outcome; d.selected=reply.selected; d.lifecycle='PROVISIONAL'
        if reply.outcome=='ONE_SELECTED':
            d.grounds.append(Ground('M','bounded semantic selection',reply.selected[0])); d.outcome='RESOLVED'
        elif reply.outcome=='MULTIPLE_ADMISSIBLE':
            d.outcome='UNRESOLVED'; state.diag('NO_GROUNDED_CANDIDATE',f.frame_id)
        elif reply.outcome=='INSUFFICIENT_CONTEXT': d.outcome='INSUFFICIENT_CONTEXT'
        else:
            d.outcome='UNRESOLVED'; state.diag('NO_GROUNDED_CANDIDATE','found candidates rejected; source is not exhausted')
    return state
