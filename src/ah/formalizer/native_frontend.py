"""Resource-driven frame generation and sealed, bounded semantic selection.

Syntax proposes; released R-S/R-V resources and a validated local TP proposal
supply candidates. No word order heuristic asserts roles, no demo sense set is
used, and missing resources never become CHECKED_EMPTY.
"""
from __future__ import annotations
from dataclasses import asdict
from copy import deepcopy
from datetime import datetime, timedelta
import itertools
import json
import re
from .canonical_ledger import digest
from .pipeline import t0,t1
from .state import FrameCandidate,Decision,Ground,LinkedAlternative,ResourceProvenance,MorphVariant
from .seal import structural_seal
from .selection_protocol import Relation,DecisionSchema,build_selection_prompt,validate_selection_response,ProtocolError
from .t3_sources import build_source_traces
from .tp_proposer import StructureProposalRequest,build_structure_prompt,parse_and_validate
from .syntax_rules import run_srl, propose_graphs, SearchLimit

OPERATORS={'NOT','AND','OR','XOR','IMPLIES','FORALL','EXISTS','POSSIBLE','NECESSARY','COUNTERFACTUAL','BEFORE','AFTER','DURING','ASSOCIATION'}
OPERATORS.update({'AT_LEAST_N','EXACTLY_N','AT_MOST_N'})


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


def _released_slot_evidence(state, release, source, policy):
    """Project only released, region-matching syntax constraints into TP.

    The local evidence IDs preserve alternatives without exporting R-S semantic
    IDs, TemplateMap targets, memory references or a preselected predicate.
    Exhaustion blocks the proposal; a partial list never masquerades as complete.
    """
    source_set=set(source)
    tokens=sorted((e for e in state.evidence if e.token_id in source_set),key=lambda e:e.start)
    kinds=('R-S','R-V','AttitudeMap','TemporalRules')
    pin={'release_sha256':release.sha256,'release_version':release.manifest['version'],
         'resource_versions':{k:release.version(k) for k in kinds if k in release.resources}}
    limits={'alternatives':policy.get('max_nodes',64),'role_slots':policy.get('max_edges',128),
            'search_steps':policy.get('max_rule_steps',20000),
            'serialized_bytes':policy.get('max_source_tokens',256)*policy.get('max_edges',128)}
    result={'schema_version':'tp-released-slot-evidence-1','status':'COMPLETE',
            'resource_snapshot':pin,'region_token_refs':list(source),'limits':limits,
            'valency_alternatives':[],'attitude_alternatives':[],'temporal_triggers':[]}
    steps=0; slots=0

    class EvidenceLimit(Exception):
        pass

    def step():
        nonlocal steps
        steps+=1
        if steps>limits['search_steps']: raise EvidenceLimit('search_steps')

    def add(category, record, cost=1):
        nonlocal slots
        slots+=cost
        if slots>limits['role_slots']: raise EvidenceLimit('role_slots')
        result[category].append(record)
        if sum(len(result[k]) for k in ('valency_alternatives','attitude_alternatives','temporal_triggers'))>limits['alternatives']:
            raise EvidenceLimit('alternatives')

    def ref(kind,index,entry):
        return {'resource_kind':kind,'entry_index':index,'resource_version':release.version(kind),
                **{k:entry[k] for k in ('rule_id','evidence_rule_id','construction_id') if entry.get(k)}}

    def variant_matches(token, item):
        return [{'lemma':v.lemma,'POS':v.pos} for v in token.variants
                if (not item.get('lemma') or item['lemma']==v.lemma)
                and (not item.get('POS') or item['POS']==v.pos)]

    valencies={}
    for i,entry in enumerate(release.entries('R-V')):
        valencies.setdefault(entry['sense_id'],[]).append((i,entry))
    singles={}; phrases=[]
    for i,entry in enumerate(release.entries('R-S')):
        if entry.get('anchor_pattern'): phrases.append((i,entry))
        else: singles.setdefault((entry['lemma'],entry['POS']),[]).append((i,entry))
    seen=set()

    def project_valencies(sense_index,sense,anchors,pattern):
        for valency_index,valency in valencies.get(sense['sense_id'],()):
            step()
            record={'evidence_id':'slot:'+digest([release.sha256,sense_index,valency_index,[a.token_id for a in anchors]]),
                'anchor_refs':[a.token_id for a in anchors],
                'lexical_variants':[{'anchor_ref':a.token_id,'variants':variant_matches(a,item)}
                    for a,item in zip(anchors,pattern if isinstance(pattern,list) else [pattern])],
                'roles':[{k:deepcopy(r[k]) for k in ('role_id','argument_types','allowed_cases','allowed_preps','cardinality','optionality','evidence_rule_id') if k in r}
                         for r in valency.get('roles',())],
                'resource_refs':[ref('R-S',sense_index,sense),ref('R-V',valency_index,valency)]}
            add('valency_alternatives',record,len(record['roles']))

    # Indexing a frozen release is not local search. Only matching entries and
    # anchor combinations consume the per-request search budget.
    attitudes={}
    for i,entry in enumerate(release.entries('AttitudeMap')):
        attitudes.setdefault(entry['lemma'],[]).append((i,entry))
    anchor_indices={}
    for j,token in enumerate(tokens):
        for variant in token.variants:
            for key in ((variant.lemma,variant.pos),(variant.lemma,None),(None,variant.pos),(None,None)):
                anchor_indices.setdefault(key,set()).add(j)
    try:
        for token in tokens:
            for variant in token.variants:
                step()
                for i,entry in singles.get((variant.lemma,variant.pos),()):
                    step()
                    key=(i,(token.token_id,))
                    if key not in seen:
                        seen.add(key);project_valencies(i,entry,(token,),entry)
        # A declared phrase licenses ordered anchors, including nonadjacent
        # anchors. Enumerate every match within the bounded region; never choose
        # a shortest/first phrase or infer one from a matching head alone.
        for i,entry in phrases:
            choices=[sorted(anchor_indices.get((item.get('lemma'),item.get('POS')),()))
                     for item in entry['anchor_pattern']]
            if any(not choice for choice in choices): continue
            step()
            for indices in itertools.product(*choices):
                step()
                if any(a>=b for a,b in zip(indices,indices[1:])): continue
                anchors=tuple(tokens[j] for j in indices)
                project_valencies(i,entry,anchors,entry['anchor_pattern'])
        for token in tokens:
            for lemma in dict.fromkeys(v.lemma for v in token.variants):
                for i,attitude in attitudes.get(lemma,()):
                    step()
                    variants=variant_matches(token,{'lemma':lemma})
                    add('attitude_alternatives',{'evidence_id':'attitude:'+digest([release.sha256,i,token.token_id]),
                        'anchor_refs':[token.token_id],'lexical_variants':variants,
                        **{k:attitude[k] for k in ('argument_role','holder_role','attitude') if k in attitude},
                        'resource_refs':[ref('AttitudeMap',i,attitude)]})
        for i,rule in enumerate(release.resources.get('TemporalRules',{}).get('entries',())):
            for match in re.finditer(rule['pattern'],state.text,re.I):
                anchors=[t.token_id for t in tokens if t.start<match.end() and t.end>match.start()]
                # A trigger straddling the region boundary is not evidence for
                # this request. No clock/default/ownership is projected.
                full=[t.token_id for t in state.evidence if t.start<match.end() and t.end>match.start()]
                if not anchors or anchors!=full: continue
                step()
                add('temporal_triggers',{'evidence_id':'time:'+digest([release.sha256,i,anchors]),
                    'anchor_refs':anchors,**{k:rule[k] for k in ('kind','interval_semantics') if k in rule},
                    'resource_refs':[ref('TemporalRules',i,rule)]})
        if len(json.dumps(result,ensure_ascii=False,separators=(',',':')).encode('utf-8'))>limits['serialized_bytes']:
            raise EvidenceLimit('serialized_bytes')
    except EvidenceLimit as exc:
        # Discard the partial projection, but expose why it is incomplete. The
        # caller does not send this request or use an arbitrary retained prefix.
        result.update(status='LIMIT_EXCEEDED',limit=str(exc),valency_alternatives=[],
                      attitude_alternatives=[],temporal_triggers=[])
    result['search_steps']=steps
    return result


def _tp_speech_act_metadata(state, release, source):
    """Export declared/reviewed requests, without guessing speech act or WH."""
    from .query_requests import validate_request
    roles={r['role_id'] for r in release.entries('RoleRegistry')}
    metadata={'declared_request_kind':state.observation.get('request_kind'),
              'query_form':'UNDETERMINED','query_modes':[],'reviewed_query_intents':[]}
    request=state.observation.get('goal_request')
    if request is not None:
        try: request=validate_request(request,roles)
        except ValueError: metadata['goal_request_status']='INVALID'
        else:
            metadata['goal_request_status']='VALID'
            metadata['query_modes'].append(request.get('mode','FORMULA'))
            metadata['declared_query_request']={k:deepcopy(request[k]) for k in ('mode','requested_roles','count_role','count_unit') if k in request}
    for intent in state.query_intents:
        if intent['token_ref'] not in source: continue
        request=validate_request(intent['request'],roles)
        metadata['query_modes'].append(request.get('mode','FORMULA'))
        metadata['reviewed_query_intents'].append({'anchor_ref':intent['token_ref'],
            'request':{k:deepcopy(request[k]) for k in ('mode','requested_roles','count_role','count_unit') if k in request},
            'resource_provenance':deepcopy(intent['provenance'])})
    metadata['query_modes']=sorted(set(metadata['query_modes']))
    if metadata['query_modes']==['FORMULA']: metadata['query_form']='BOOLEAN'
    elif len(metadata['query_modes'])==1: metadata['query_form']=metadata['query_modes'][0]
    elif metadata['query_modes']: metadata['query_form']='ALTERNATIVES'
    return metadata


def _grammar_frames(state,release):
    p=release.entries('ProposalPolicy')[0]
    source=tuple(e.token_id for e in state.evidence)
    request=StructureProposalRequest('syntax:'+state.source_uid,'',source,allowed_node_kinds=frozenset({'PREDICATE','ENTITY','BOUND_VAR','TIME','WH','COUNT_REQUEST','NUMERAL',*OPERATORS}),
        allowed_edge_kinds=frozenset({'ARGUMENT','OPERAND','ATTITUDE','BIND','TIME_SCOPE','QUERY_SLOT'}),allowed_role_ids=frozenset(x['role_id'] for x in release.entries('RoleRegistry')),
        max_nodes=p['max_nodes'],max_edges=p['max_edges'],max_depth=p['max_depth'],required_operators=_required_operators(state,release))
    try:
        hypotheses,provenance,morph_bindings=propose_graphs(state,release,request)
        accepted=_frames_for_hypotheses(state,hypotheses,release,provenance,morph_bindings)
    except (SearchLimit,ProtocolError) as exc:
        state.grammar_search_incomplete=True
        state.diag('COMPUTATION_LIMIT' if isinstance(exc,SearchLimit) else 'STRUCTURE_NOT_COVERED',str(exc)); return []
    from .clarifications import choose_structures
    for h, _frames in accepted:
        state.linked_alternatives.append(LinkedAlternative(h.local_id,'STRUCTURAL_HYPOTHESIS',digest(asdict(h)),h.local_id,provenance=provenance[h.local_id]))
    accepted = choose_structures(state, accepted, stage='GRAMMAR', provenance=provenance)
    # Multiple overlapping structures are alternatives, never multiple facts.
    by_anchor={}
    for h,frames in accepted:
        for frame in frames:
            by_anchor.setdefault(frame.predicate_token_ref,set()).add(h.local_id)
    frames=[]
    for h,local in accepted:
        ambiguous=any(len(by_anchor[f.predicate_token_ref])>1 for f in local)
        for f in local:
            f.semantic['structural_unresolved'] |= ambiguous
        frames.extend(local)
    if len(accepted)==1 and not accepted[0][1]:
        hid=accepted[0][0].local_id
        state.logical_roots=[t for r in state.syntax_trace if r.get('literal_hypothesis')==hid for t in r['operator_forest']]
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
        def unit(node):
            anchors=sorted(node.anchor_spans,key=lambda a:bytoken[a].start)
            head=node.head_anchor or anchors[0]
            return {'head_ref':head,'anchor_refs':anchors,'surface':' '.join(bytoken[a].span for a in anchors),
                    'mention_ref':head if len(anchors)==1 else 'mention:'+digest(anchors)}
        localframes={}
        proposition_nodes={}
        variable_ids={i:i+1 for i,n in enumerate(h.nodes) if n.kind=='BOUND_VAR'}
        time_regions={}
        numerals={}
        for i,n in enumerate(h.nodes):
            if n.kind!='NUMERAL': continue
            raw=' '.join(bytoken[a].span for a in sorted(n.anchor_spans,key=lambda a:bytoken[a].start))
            values={int(raw)} if re.fullmatch(r'[0-9]{1,13}',raw) else set()
            if len(n.anchor_spans)==1:
                lemmas={v.lemma for v in bytoken[n.anchor_spans[0]].variants}
                values.update(r['value'] for r in release.resources.get('NumeralRules',{}).get('entries',()) if r['lemma'] in lemmas)
            if len(values)!=1 or not 0<=next(iter(values))<=10**12:
                state.diag('NUMERIC_BOUND_UNRESOLVED','raw numeral has no unique released value'); unsupported=True
            else: numerals[i]=next(iter(values))
        if any(n.kind=='NUMERAL' and i not in numerals for i,n in enumerate(h.nodes)): continue
        for i,n in enumerate(h.nodes):
            if n.kind!='TIME': continue
            anchors=[bytoken[a] for a in n.anchor_spans]
            value,errors=_temporal(state.text[min(a.start for a in anchors):max(a.end for a in anchors)],state.observation,release)
            if errors or value is None:
                state.diag('INTERVAL_BOUNDARY_UNKNOWN',','.join(errors))
                unsupported=True
            else: time_regions[i]=value
        if any(n.kind=='TIME' and i not in time_regions for i,n in enumerate(h.nodes)): continue
        owners={e.from_idx:e.to_idx for e in h.edges if e.kind=='TIME_SCOPE'}
        for i,n in enumerate(h.nodes):
            if n.kind!='PREDICATE': continue
            predicate_unit=unit(n)
            anchor=bytoken[predicate_unit['head_ref']]
            args=[]; roles={}; propositions={}; bound_args={}; incomplete=False
            lexical_units={anchor.token_id:predicate_unit}
            for edge in h.edges:
                if edge.from_idx!=i or edge.kind not in {'ARGUMENT','ATTITUDE'}: continue
                target=h.nodes[edge.to_idx]
                if target.kind=='PREDICATE' or target.kind in OPERATORS:
                    proposition_nodes[(i,edge.role_id)]=edge.to_idx
                    bound=morph_bindings.get(h.local_id,{}).get(anchor.token_id)
                    lemmas={bound['lemma']} if bound is not None else {v.lemma for v in anchor.variants}
                    # A phrase is not its head word. A head-only attitude entry
                    # cannot license a multi-token lexical unit.
                    attitudes=[a for a in release.entries('AttitudeMap') if a['lemma'] in lemmas and a.get('argument_role')==edge.role_id and len(predicate_unit['anchor_refs'])==1]
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
                if target.kind!='ENTITY':
                    state.diag('PROPOSAL_INVALID','entity argument not closed'); incomplete=True; continue
                target_unit=unit(target); tid=target_unit['head_ref']; args.append(tid)
                if tid in lexical_units and lexical_units[tid]!=target_unit:
                    state.diag('STRUCTURAL_OPERAND_UNRESOLVED','overlapping lexical units with one head'); incomplete=True
                lexical_units[tid]=target_unit
                if edge.role_id: roles[tid]=edge.role_id
                for binding in h.edges:
                    if binding.kind=='BIND' and binding.to_idx==edge.to_idx and binding.from_idx in variable_ids:
                        bound_args[tid]=variable_ids[binding.from_idx]
            fid='TP:'+h.local_id+':'+str(i)
            # Participant anchors remain original R1 spans for structural seal;
            # lexical-unit labels are separate data, never fabricated tokens.
            f=FrameCandidate(fid,'FLAT',anchor.span,tuple([anchor.span,*[bytoken[a].span for a in args]]),tuple(bytoken[a].span for a in args),construction='GRAMMAR' if h.local_id in provenance else 'TP',predicate_token_ref=anchor.token_id,argument_token_refs=tuple(args),source_range=(min(bytoken[a].start for a in h.alignment),max(bytoken[a].end for a in h.alignment)),semantic={'proposed_roles':roles,'hypothesis':h.local_id,'proposition_args':propositions,'bound_arguments':bound_args,'structural_unresolved':incomplete,'morph_bindings':morph_bindings.get(h.local_id,{}),'lexical_units':lexical_units},provenance=provenance.get(h.local_id,ResourceProvenance(('TP_VALIDATED',),{'release':release.sha256})))
            localframes[i]=f
            slots=[edge for edge in h.edges if edge.from_idx==i and edge.kind=='QUERY_SLOT']
            if slots:
                counts=[edge for edge in slots if h.nodes[edge.to_idx].kind=='COUNT_REQUEST']
                if counts and (len(counts)!=1 or len(slots)!=1):
                    f.semantic['structural_unresolved']=True
                    state.diag('QUERY_TARGET_UNBOUND','mixed count/WH slots require an explicit scope')
                f.semantic['query_request']={'mode':'COUNT','count_role':counts[0].role_id} if counts else {'mode':'WH','requested_roles':[edge.role_id for edge in slots]}
            bound_variant=morph_bindings.get(h.local_id,{}).get(anchor.token_id)
            intents=[q for q in state.query_intents if q['token_ref']==anchor.token_id
                     and (q['variant'] is None or bound_variant is None or q['variant']==bound_variant)]
            if intents:
                requests={digest(q['request']):q['request'] for q in intents}
                if len(requests)!=1:
                    f.semantic['structural_unresolved']=True
                    state.diag('QUERY_TARGET_UNBOUND','conflicting reviewed query intents')
                else:
                    explicit=next(iter(requests.values()))
                    previous=f.semantic.get('query_request')
                    if previous and previous.get('requested_roles',[])!=explicit.get('requested_roles',[]) and explicit.get('mode') not in {'WHY','WHEN','COMPARE'}:
                        f.semantic['structural_unresolved']=True
                        state.diag('QUERY_TARGET_UNBOUND','intent/structural gap mismatch')
                    f.semantic['query_request']=explicit
                    f.semantic['query_intent_refs']=[q['intent_id'] for q in intents]
            if i in owners:
                f.semantic['explicit_region']=time_regions[owners[i]]
                f.semantic['time_scope_owner']=i
        # Logical roots preserve the entire operator tree and operand directions.
        roots=set(range(len(h.nodes)))-{e.to_idx for e in h.edges if e.kind in {'OPERAND','ATTITUDE','ARGUMENT','BIND'}}
        def tree(i):
            n=h.nodes[i]
            if n.kind=='BOUND_VAR': return {'bound_var':variable_ids[i],'sort':'ENTITY'}
            if n.kind=='NUMERAL': return {'count_literal':numerals[i]}
            if n.kind=='TIME':
                region=time_regions[i]
                bounds=[region['point']] if region['kind']=='POINT' else [region['lo'],region['hi']]
                return {'time_literal':bounds}
            if n.kind=='PREDICATE': return {'frame_ref':localframes[i].frame_id} if i in localframes else None
            if n.kind not in OPERATORS: return None
            children=[tree(e.to_idx) for e in h.edges if e.from_idx==i and e.kind=='OPERAND']
            if not children or any(c is None for c in children): return None
            result={'operator':n.kind,'operands':children,'anchor_refs':list(n.anchor_spans)}
            if i in owners: result.update(region=time_regions[owners[i]],time_scope_owner=i)
            return result
        forest=[tree(i) for i in sorted(roots) if h.nodes[i].kind in OPERATORS]
        children={key:tree(idx) for key,idx in proposition_nodes.items()}
        if any(t is None for t in [*forest,*children.values()]):
            unsupported=True
            state.grammar_search_incomplete=True
            state.diag('PROPOSAL_INVALID','incomplete logical root'); continue
        for (idx,role),child in children.items():
            localframes[idx].semantic['proposition_args'][role]['tree']=child
        def inherit_scope(t,reg=None,owner=None):
            reg=t.get('region',reg); owner=t.get('time_scope_owner',owner)
            if 'frame_ref' in t and reg is not None:
                frame=next(f for f in localframes.values() if f.frame_id==t['frame_ref'])
                frame.semantic.setdefault('explicit_region',reg)
                frame.semantic.setdefault('time_scope_owner',owner)
            for child in t.get('operands',()): inherit_scope(child,reg,owner)
        for t in [*forest,*children.values()]: inherit_scope(t)
        for f in localframes.values(): f.semantic['operator_forest']=forest
        if not localframes and not forest:
            # A typed ENTITY/TIME-only reply is not a proposition. Keep the
            # validated structure for audit and block a valid sibling from
            # becoming the unique interpretation by silent disappearance.
            unsupported=True
            state.grammar_search_incomplete=True
            state.diag('STRUCTURE_NOT_COVERED','validated hypothesis has no frame or logical root: '
                       +h.local_id+' anchors='+json.dumps(list(h.alignment)))
        if not localframes:
            state.syntax_trace.append({'stage':'T2','literal_hypothesis':h.local_id,
                                       'operator_forest':[{**t,'alignment_refs':list(h.alignment)} for t in forest]})
        accepted.append((h,list(localframes.values())))
    # An unsupported reading cannot silently disappear and turn the remaining
    # prefix into a uniquely resolved structure.
    if unsupported:
        for h in hypotheses:
            state.syntax_trace.append({'stage':'T2','event':'UNINTERPRETED_STRUCTURAL_ALTERNATIVE',
                                       'hypothesis':asdict(h)})
            if not any(a.alt_id==h.local_id for a in state.linked_alternatives):
                state.linked_alternatives.append(LinkedAlternative(h.local_id,'STRUCTURAL_HYPOTHESIS',
                    digest(asdict(h)),h.local_id,provenance=provenance.get(h.local_id,
                        ResourceProvenance(('TP_VALIDATED',),{'release':release.sha256}))))
        return []
    return accepted


def _propose(state,selector,release):
    covered={f.predicate_token_ref for f in state.frames}
    covered.update(a for f in state.frames for unit in f.semantic.get('lexical_units',{}).values() for a in unit['anchor_refs'])
    covered.update(a for root in state.logical_roots for a in root.get('alignment_refs',()))
    uncovered=[e.token_id for e in state.evidence if e.token_id not in covered and any(v.pos in {'VERB','INFN','PRED','ADJS'} for v in e.variants)]
    attitude_lemmas={a['lemma'] for a in release.entries('AttitudeMap')}
    scope_required=state.grammar_search_incomplete or any(f.semantic.get('structural_unresolved') for f in state.frames)
    scope_required |= any(e.token_id not in covered and any(v.lemma in attitude_lemmas for v in e.variants) for e in state.evidence)
    trees=[*state.logical_roots,*[t for f in state.frames for t in f.semantic.get('operator_forest',())]]
    trees.extend(child['tree'] for f in state.frames for child in f.semantic.get('proposition_args',{}).values() if child.get('tree'))
    def scoped(operator,anchors,tree):
        return (tree.get('operator')==operator and bool(set(tree.get('anchor_refs',())) & set(anchors))) or any(scoped(operator,anchors,t) for t in tree.get('operands',()))
    required=_required_operators(state,release)
    scope_required |= any(not any(scoped(operator,anchors,t) for t in trees) for operator,anchors in required)
    scope_required |= any(e.span in {'«','»','"'} for e in state.evidence) and not any(f.semantic.get('proposition_args') for f in state.frames)
    frozen = state.observation.get('clarification_structures', {})
    scope_required |= bool(frozen)
    verify=bool(release.entries('ProposalPolicy')[0].get('verify_deterministic',False))
    if (state.frames or state.logical_roots) and not uncovered and not scope_required and not verify: return
    if scope_required or verify:
        # An unclosed scope may not be flattened into independently asserted clauses.
        for f in state.frames: f.semantic['structural_unresolved']=True
    policy=release.entries('ProposalPolicy')
    if not policy or not frozen and not hasattr(selector,'propose_local'):
        state.diag('STRUCTURE_NOT_COVERED','no declared TP capability/policy'); return
    if state.budget.llm_exhausted and not frozen:
        state.diag('COMPUTATION_LIMIT','TP budget exhausted'); return
    p=policy[0]
    source=tuple(e.token_id for e in state.evidence)
    if len(source)>p.get('max_source_tokens',256):
        state.diag('COMPUTATION_LIMIT','local TP source region too large; no truncation'); return
    slot_evidence=_released_slot_evidence(state,release,source,p)
    state.syntax_trace.append({'stage':'TP','event':'RELEASED_SLOT_EVIDENCE',
        'status':slot_evidence['status'],'resource_snapshot':slot_evidence['resource_snapshot'],
        'limits':slot_evidence['limits'],**({'limit':slot_evidence['limit']} if 'limit' in slot_evidence else {})})
    if slot_evidence['status']!='COMPLETE':
        state.diag('COMPUTATION_LIMIT','TP released slot evidence exceeds '+slot_evidence['limit']+'; no partial evidence sent')
        return
    req=StructureProposalRequest('TP:'+state.source_uid,digest([asdict(f) for f in state.frames]),source,deterministic_candidates=tuple(asdict(f) for f in state.frames),uncovered_spans=tuple(uncovered),allowed_node_kinds=frozenset({'PREDICATE','ENTITY','BOUND_VAR','TIME','WH','COUNT_REQUEST','NUMERAL',*OPERATORS}),allowed_edge_kinds=frozenset({'ARGUMENT','OPERAND','ATTITUDE','BIND','TIME_SCOPE','QUERY_SLOT'}),allowed_role_ids=frozenset(x['role_id'] for x in release.entries('RoleRegistry')),schema_version='v7',max_nodes=p.get('max_nodes',64),max_edges=p.get('max_edges',128),max_depth=p.get('max_depth',16),budget_ok=not state.budget.llm_exhausted,required_operators=tuple(required),released_slot_evidence=slot_evidence,speech_act_metadata=_tp_speech_act_metadata(state,release,source))
    prompt=build_structure_prompt(req,[{'id':e.token_id,'text':e.span,
        'variants':[asdict(v) for v in e.variants]} for e in state.evidence])
    frozen_hypotheses = list(frozen.values())
    try:
        if frozen_hypotheses:
            raw = json.dumps({'hypotheses': frozen_hypotheses})
        else:
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
    from .clarifications import offer, hypothesis_json, structure_label
    structure_key = 'structure:TP:' + digest(sorted({a for h, _ in accepted for a in h.alignment}))
    options = [{'candidate_id': h.local_id, 'label': structure_label(state, h),
                'hypothesis': hypothesis_json(h), 'stage': 'TP'} for h, _ in accepted]
    if len(accepted)>1:
        if state.budget.llm_exhausted:
            offer(state, structure_key, 'STRUCTURE', state.text, options)
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
                offer(state, structure_key, 'STRUCTURE', state.text, options)
                state.diag('STRUCTURE_UNRESOLVED','TP alternatives retained'); return
            chosen=reply.selected[0]
        except Exception as exc:
            offer(state, structure_key, 'STRUCTURE', state.text, options)
            state.diag(_failure_code(exc,'PROTOCOL_ERROR'),str(exc)); return
        for h,fs in accepted:
            if h.local_id!=chosen: state.reject(h.local_id,'TP_SELECTION','different validated hypothesis selected: '+chosen,tp_provenance)
        accepted=[pair for pair in accepted if pair[0].local_id==chosen]
    # A validated proposal replaces overlapping deterministic hypotheses only by
    # recorded discard; unrelated deterministic frames remain.
    fs=accepted[0][1]; anchors={f.predicate_token_ref for f in fs}
    # An independently validated replacement resolves its overlapping grammar
    # offers too; don't present alternatives that no longer survive TD.
    replaced = {f.semantic.get('hypothesis') for f in state.frames if f.predicate_token_ref in anchors}
    state.clarification_candidates = [r for r in state.clarification_candidates
        if not any(o.get('candidate_id') in replaced for o in r['options'])]
    if not fs:
        hid=accepted[0][0].local_id
        state.logical_roots=[t for r in state.syntax_trace if r.get('literal_hypothesis')==hid for t in r['operator_forest']]
    for f in list(state.frames):
        if f.predicate_token_ref in anchors:
            state.reject(f.frame_id,'TP','selected validated TP hypothesis'); state.frames.remove(f)
    state.frames.extend(fs)


def _bindings(frame,evidence,valency,extra_gaps=()):
    roles=valency.get('roles',())
    request=frame.semantic.get('query_request',{})
    gaps=set(request.get('requested_roles',())) | ({request['count_role']} if request.get('count_role') else set()) | set(extra_gaps)
    if not gaps<={r['role_id'] for r in roles}: return []
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
        if any(r.get('cardinality',{}).get('min',0)>0 and r['role_id'] not in rs and r['role_id'] not in gaps and r['role_id'] not in frame.semantic.get('proposition_args',{}) for r in roles): continue
        out.append(dict(choice))
    return out


def run_native(text,selector,release,observation,morph=None):
    release.assert_integrity()
    state=t0(text); state.source_uid=observation['observation_id']; state.interpretation_version=observation['interpretation_version']; state.observation=dict(observation)
    state.resource_snapshot={'snapshot_id':release.sha256,'release_version':release.manifest['version']}
    state.context_facts=tuple(observation.get('context_facts',()))
    for diagnostic in observation.get('rx_diagnostics',()): state.diag(diagnostic,'bounded optional experience retrieval')
    run_srl(state,release,morph)
    t1(state,morph=morph,preserve_variants=True,shared_form_expansion=False)
    # R-X is ordering experience only; it never adds/removes dictionary parses.
    rx1=[x for rec in observation.get('rx_reads',{}).get('T1',()) for x in rec['payload'].get('morphological_priors',())]
    for ev in state.evidence:
        preferred={(v['lemma'],v['POS']) for x in rx1 if x['surface']==ev.span for v in x['variants']}
        ev.variants=tuple(sorted(ev.variants,key=lambda v:(-int((v.lemma,v.pos) in preferred),-v.score)))
    frozen_generation=observation.get('clarification_generation')
    if frozen_generation:
        from .state import RejectionRecord
        if frozen_generation['resource_snapshot'] != release.sha256:
            raise ValueError('CLARIFICATION_RESOURCE_STALE')
        state.frames=[]
        for raw in frozen_generation['frames']:
            raw=deepcopy(raw)
            raw['provenance']=ResourceProvenance(**raw['provenance'])
            for key in ('participants','arguments','argument_token_refs','source_range'): raw[key]=tuple(raw[key])
            state.frames.append(FrameCandidate(**raw))
        state.logical_roots=deepcopy(frozen_generation['logical_roots'])
        state.syntax_trace=deepcopy(frozen_generation['syntax_trace'])
        for raw in frozen_generation['linked_alternatives']:
            raw=deepcopy(raw); raw['provenance']=ResourceProvenance(**raw['provenance'])
            state.linked_alternatives.append(LinkedAlternative(**raw))
        for raw in frozen_generation['rejections']:
            raw=deepcopy(raw); raw['provenance']=ResourceProvenance(**raw['provenance'])
            state.rejections.append(RejectionRecord(**raw))
        state.grammar_search_incomplete=frozen_generation['grammar_search_incomplete']
        from .clarifications import choice, offer
        state.clarification_candidates=deepcopy(frozen_generation.get('pending_structures',[]))
        for row in list(state.clarification_candidates):
            selected=choice(state,row['decision_ref'],[o['candidate_id'] for o in row['options']])
            if selected is None: continue
            option=next(o for o in row['options'] if o['candidate_id']==selected)
            p=release.entries('ProposalPolicy')[0]
            req=StructureProposalRequest('clarification:'+state.source_uid,'',tuple(e.token_id for e in state.evidence),
                allowed_node_kinds=frozenset({'PREDICATE','ENTITY','BOUND_VAR','TIME','WH','COUNT_REQUEST','NUMERAL',*OPERATORS}),
                allowed_edge_kinds=frozenset({'ARGUMENT','OPERAND','ATTITUDE','BIND','TIME_SCOPE','QUERY_SLOT'}),
                allowed_role_ids=frozenset(x['role_id'] for x in release.entries('RoleRegistry')),
                max_nodes=p['max_nodes'],max_edges=p['max_edges'],max_depth=p['max_depth'],
                required_operators=tuple((op,anchors) for op,anchors in _required_operators(state,release)
                                         if set(anchors)&set(option['hypothesis']['alignment'])))
            hypotheses=parse_and_validate(req,json.dumps({'hypotheses':[option['hypothesis']]}))
            prov=ResourceProvenance(**option.get('provenance',{'pattern_ids':['TP_VALIDATED'],'resource_versions':{'release':release.sha256}}))
            accepted=_frames_for_hypotheses(state,hypotheses,release,{selected:prov},
                                           {selected:option.get('morph_bindings',{})})
            if len(accepted)!=1: raise ValueError('CLARIFICATION_STRUCTURE_STALE')
            h, fs=accepted[0]
            alternatives={o['candidate_id'] for o in row['options']}
            anchors={f.predicate_token_ref for f in fs}
            removed={f.frame_id for f in state.frames if f.semantic.get('hypothesis') in alternatives
                     or option['stage']=='TP' and f.predicate_token_ref in anchors}
            state.frames=[f for f in state.frames if f.frame_id not in removed]+fs
            for other in alternatives-{selected}:
                state.reject(other,'CLARIFICATION','explicit speaker selection: '+selected,prov)
            if not fs:
                state.logical_roots=[t for trace in state.syntax_trace if trace.get('literal_hypothesis')==selected for t in trace['operator_forest']]
            state.clarification_candidates.remove(row)
    else:
        state.frames=_grammar_frames(state,release)
        _propose(state,selector,release)
    state.generation_snapshot={'resource_snapshot':release.sha256,
        'frames':[asdict(f) for f in state.frames], 'logical_roots':deepcopy(state.logical_roots),
        'syntax_trace':deepcopy(state.syntax_trace),
        'linked_alternatives':[asdict(a) for a in state.linked_alternatives],
        'rejections':[asdict(r) for r in state.rejections],
        'pending_structures':deepcopy([r for r in state.clarification_candidates if r['kind']=='STRUCTURE']),
        'grammar_search_incomplete':state.grammar_search_incomplete}
    if observation.get('goal_request'):
        from .query_requests import validate_request
        owners=[f for f in state.frames if f.semantic.get('query_request')]
        if len(owners)==1 or not owners and len(state.frames)==1:
            owner=owners[0] if owners else state.frames[0]
            try:
                request=validate_request(observation['goal_request'])
                old=owner.semantic.get('query_request',{})
                if old.get('requested_roles') and request.get('requested_roles')!=old['requested_roles']:
                    raise ValueError('QUERY_TARGET_UNBOUND')
                owner.semantic['query_request']=request
            except ValueError as exc:
                owner.semantic['structural_unresolved']=True; state.diag(str(exc),'host query intent')
    preferred_shapes={x['construction'] for rec in observation.get('rx_reads',{}).get('T2',()) for x in rec['payload'].get('structural_priors',())}
    state.frames.sort(key=lambda f:(f.construction not in preferred_shapes,f.source_range,f.frame_id))
    from .coreference import prepare_references,resolve_references
    reference_slots=prepare_references(state,release)
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
        lexical=frame.semantic.get('lexical_units',{}).get(frame.predicate_token_ref,{})
        if len(lexical.get('anchor_refs',()))>1:
            def phrase_match(s):
                pattern=s.get('anchor_pattern')
                anchors=lexical['anchor_refs']
                if not isinstance(pattern,list) or len(pattern)!=len(anchors): return False
                return all(any((not item.get('lemma') or item['lemma']==v.lemma) and (not item.get('POS') or item['POS']==v.pos)
                               for v in _frame_variants(frame,evidence[tid])) for tid,item in zip(anchors,pattern))
            # The complete anchor pattern licenses a lexical unit. A phrase's
            # canonical lemma need not equal its syntactic head lemma, so a
            # head-only prefilter must not discard the resource sense first.
            senses=[s for s in release.entries('R-S') if phrase_match(s)]
            allowed={s['sense_id'] for s in senses}
            declared_ids &= allowed; priors &= allowed; context_senses &= allowed
        else:
            # A phrase sense is not licensed by an isolated matching head.
            senses=[s for s in senses if not s.get('anchor_pattern')]
            allowed={s['sense_id'] for s in senses}
            declared_ids &= allowed; priors &= allowed; context_senses &= allowed
        frame.semantic['has_known_senses']=bool(senses)
        specs=[]
        for s in senses:
            valencies=[v for v in release.entries('R-V') if v['sense_id']==s['sense_id']]
            for v in valencies:
                # A declared measured-value question can existentially bind
                # an omitted value. This is licensed by its actual mapped T,
                # not by an arbitrary missing mandatory predicate argument.
                request=frame.semantic.get('query_request',{}); extra=()
                if request.get('mode') in {'SUPERLATIVE','COMPARE'}:
                    measures=[m for m in release.resources.get('MeasureSchema',{}).get('entries',()) if m['measure_id']==request.get('measure_id')]
                    if len(measures)==1:
                        measure=measures[0]
                        mappings=[m for m in release.entries('TemplateMap') if m['sense_id']==s['sense_id'] and m['template_ref']==measure['template_ref']
                                  and set(m['roles'])=={r['role_id'] for r in v.get('roles',())}]
                        supplied=set(frame.semantic.get('proposed_roles',{}).values())|set(request.get('requested_roles',()))
                        if mappings and measure['value_role'] not in supplied:
                            extra=(measure['value_role'],)
                try: bindings=_bindings(frame,evidence,v,extra)
                except ValueError:
                    frame.semantic['binding_budget_exhausted']=True; state.diag('COMPUTATION_LIMIT',frame.frame_id); continue
                for bs in bindings:
                    mode=v.get('temporal_mode_hint') or v.get('state_class') or 'UNKNOWN'
                    implicit=tuple(r for r in extra if r not in bs.values())
                    cid=s['sense_id']+':'+digest([bs,v,implicit])[:16] if implicit else s['sense_id']+':'+digest([bs,v])[:16]
                    specs.append({'candidate_id':cid,'sense_id':s['sense_id'],'label':s.get('label',s['sense_id']),'sense_kind':'KNOWN','roles':bs,'state_class':mode,'valency_ref':v.get('construction_id',digest(v)),
                                  **({'query_existential_roles':list(implicit)} if implicit else {})})
        open_spec=None
        if not senses:
            policy=release.entries('OpenTemplatePolicy')
            if policy and policy[0].get('allow',False):
                bs=frame.semantic.get('proposed_roles') or {tid:'SURFACE_ARG' for tid in frame.argument_token_refs}
                open_spec={'candidate_id':'open:'+digest([state.source_uid,frame.frame_id]),'label':lexical.get('surface',e.span),'sense_kind':'OPEN_LEXICAL','roles':bs,'state_class':'UNKNOWN'}
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
        if 'explicit_region' in frame.semantic:
            frame.semantic['region'],temporal_diag=frame.semantic['explicit_region'],[]
        else:
            frame.semantic['region'],temporal_diag=_temporal(text[frame.source_range[0]:frame.source_range[1]],observation,release)
        for code in temporal_diag: state.diag(code,frame.frame_id)
        frame.semantic['temporal_unresolved']=bool(temporal_diag)
        candidate_specs[frame.frame_id]=specs
    structural_seal(state)
    resolve_references(state,reference_slots,selector,release)
    for f in state.frames:
        specs=candidate_specs[f.frame_id]; ids=tuple(s['candidate_id'] for s in specs)
        d=Decision('predicate_value',f.frame_id,ids); d.source_traces=f.semantic['source_traces']; state.decisions[f.frame_id+'|predicate_value']=d
        from .clarifications import choice
        selected_by_speaker = choice(state, f.frame_id+'|predicate_value', ids)
        if f.semantic.get('source_blocked'):
            d.outcome='UNRESOLVED'; state.diag('SEARCH_INCOMPLETE',f.frame_id); continue
        if not specs:
            d.outcome='UNRESOLVED' if f.semantic['has_known_senses'] else 'NO_CANDIDATE'
            state.diag('CANDIDATE_SOURCE_EXHAUSTED' if not f.semantic['has_known_senses'] else 'VALENCY_UNKNOWN',f.frame_id); continue
        if selected_by_speaker is not None and not f.semantic.get('structural_unresolved'):
            d.selected=(selected_by_speaker,); d.lifecycle='PROVISIONAL'; d.outcome='RESOLVED'
            d.grounds.append(Ground('C', 'durable explicit speaker disambiguation: '+state.observation['clarification_selection_ref'], selected_by_speaker))
            continue
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
    from .clarifications import offer
    for f in state.frames:
        d = state.decisions.get(f.frame_id+'|predicate_value')
        if d is None or d.outcome == 'RESOLVED' or f.semantic.get('structural_unresolved') or f.semantic.get('source_blocked'):
            continue
        options = []
        for cid in d.candidates:
            spec = f.semantic['candidate_specs'][cid]
            bindings = ', '.join(role+'='+evidence[tid].span for tid, role in sorted(spec['roles'].items()))
            options.append({'candidate_id': cid, 'label': spec['label'] + ('; '+bindings if bindings else '')})
        offer(state, f.frame_id+'|predicate_value', 'SEMANTIC', f.anchor_span, options)
    state.complete_t4()
    return state
